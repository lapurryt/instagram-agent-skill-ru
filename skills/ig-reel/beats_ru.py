#!/usr/bin/env python3
"""
beats_ru.py - сценарий рилса в таблицу битов по секундам, до записи. Порт
beats.py из Jakeschincariol/instagram-agent-skill (MIT) под русский.

Что изменено против оригинала: кириллица в словах; темп автора 195 слов в
минуту после монтажа (РЕПО, Человек, ФАУНДЕР), у Джейка по умолчанию 165;
петля сравнивает основы слов (у нас падежи: «лимит» и «лимита» одно эхо);
вывод по-русски (с 23.11.2026, до этого печатал по-английски).

Считает, сколько каждая строка говорится, складывает их в тайм-коды и отмечает
четыре вещи, которые убивают рилс на монтаже: хук дольше трёх секунд, бит,
на котором зритель успевает уйти, несколько строк подряд без конкретики и
общую длину, которая не совпадает с задуманной.

Время это оценка по числу слов при заданном темпе. Её хватает, чтобы
спланировать монтаж, но не заменяет записи. Свой темп задай флагом --wpm,
когда засечёшь, как читаешь сценарий вслух: у большинства 150-200.

Запуск
  python -I -X utf8 beats_ru.py script.txt
  python -I -X utf8 beats_ru.py script.txt --target 30
  python -I -X utf8 beats_ru.py script.txt --wpm 185 --target 45
  python -I -X utf8 beats_ru.py - < script.txt
  python -I -X utf8 beats_ru.py script.txt --json
"""

import argparse
import json
import re
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$%₽'’-]+")
SENT_RE = re.compile(r"[^.!?]+[.!?]*")
CONCRETE_RE = re.compile(
    r"\$\s?\d|\d[\d\s,.]*|\b[A-Za-z][A-Za-z0-9.+-]{1,}\b|(?<!^)\b[А-ЯЁ][а-яё]{2,}"
    r"|(?i:\b(?:два|две|три|пять|десять|сто|тысяч\w*|миллион\w*|рубл\w*|доллар\w*)\b)", re.MULTILINE)
STOPWORDS = {
    "и", "а", "но", "или", "в", "во", "на", "с", "со", "к", "по", "о", "об", "от", "до", "за", "из", "у",
    "что", "это", "этот", "эта", "как", "так", "не", "ни", "да", "же", "ли", "бы", "то", "если", "чтобы",
    "ты", "тебе", "тебя", "твой", "я", "мне", "меня", "мой", "мы", "он", "она", "они", "его", "её", "их",
    "просто", "уже", "ещё", "еще", "вот", "там", "тут", "все", "всё", "один", "одна", "напиши", "подпишись",
}

HOOK_WINDOW = 3.0        # seconds. Past this, the thumb has already decided.
MAX_BEAT = 4.0           # seconds on one idea with no change on screen.
ABSTRACT_RUN = 3         # beats in a row with nothing checkable in them.


def words(text):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def pretty(token):
    """Put the thousands separator back for display."""
    return re.sub(r"(\d)(?=(\d{3})+$)", r"\1,", token)


def tc(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def split_beats(raw, wps):
    """One line is one beat, unless a line is too long to be one."""
    beats = []
    for line in [l.strip() for l in raw.splitlines()]:
        if not line:
            continue
        if len(words(line)) / wps <= MAX_BEAT * 1.5:
            beats.append(line)
            continue
        # Long paragraph: break it at sentence ends so the timings mean
        # something, and let the report say it was split.
        parts = [p.strip() for p in SENT_RE.findall(line) if p.strip()]
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip()
            if buf and len(words(candidate)) / wps > MAX_BEAT:
                beats.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            beats.append(buf)
    return beats


def analyse(raw, wpm=195, target=None):
    wps = wpm / 60.0
    beats = split_beats(raw, wps)
    if not beats:
        return None

    rows, clock = [], 0.0
    for i, text in enumerate(beats):
        n = len(words(text))
        dur = n / wps
        rows.append({
            "n": i + 1,
            "start": round(clock, 2),
            "dur": round(dur, 2),
            "words": n,
            "text": text,
            "concrete": len(CONCRETE_RE.findall(text)),
            "label": "",
            "flags": [],
        })
        clock += dur
    total = clock

    # Отметить места, вокруг которых строится рилс.
    for r in rows:
        if r["n"] == 1 or r["start"] + r["dur"] <= HOOK_WINDOW:
            r["label"] = "ХУК"
    rows[-1]["label"] = "ПРИЗЫВ" if rows[-1]["label"] != "ХУК" else "ХУК/ПРИЗ"
    half = total / 2
    for r in rows:
        if not r["label"] and r["start"] <= half < r["start"] + r["dur"]:
            r["label"] = "СЕРЕДИНА"

    notes = []
    if rows[0]["dur"] > HOOK_WINDOW:
        rows[0]["flags"].append(f"хук идёт {rows[0]['dur']:.1f} с, дольше {HOOK_WINDOW:.0f} с")
        notes.append(f"Бит 1 говорится {rows[0]['dur']:.1f} с. Сократи до "
                     f"{int(HOOK_WINDOW * wps)} слов или меньше, иначе хук прозвучит, "
                     "когда решение уже принято.")
    if rows[0]["concrete"] == 0:
        notes.append("В бите 1 нет ни цифры, ни имени. Хуки, в которых нечего проверить, "
                     "и пролистывают.")

    for r in rows:
        if r["dur"] > MAX_BEAT:
            r["flags"].append(f"{r['dur']:.1f} с на одном бите")
    long_beats = [r["n"] for r in rows if r["dur"] > MAX_BEAT]
    if long_beats:
        notes.append(f"Бит(ы) {', '.join(map(str, long_beats))} дольше {MAX_BEAT:.0f} с. "
                     "Раздели строку или поменяй картинку внутри неё. "
                     "На статичном кадре и уходят.")

    run, start = 0, None
    for r in rows:
        if r["concrete"] == 0:
            run += 1
            start = start if start is not None else r["n"]
            if run == ABSTRACT_RUN:
                notes.append(f"В битах {start}-{r['n']} нет ничего конкретного. "
                             "Поставь в один из них цифру, имя или цену.")
        else:
            run, start = 0, None

    # Does the last line hand you back to the first one?
    def stem(w):  # Russian inflection: «лимит» and «лимита» are the same echo
        return w.lower()[:5]
    first = {stem(w) for w in words(rows[0]["text"]) if w.lower() not in STOPWORDS and len(w) > 2}
    last = {stem(w) for w in words(rows[-1]["text"]) if w.lower() not in STOPWORDS and len(w) > 2}
    common = first & last
    # Показываем слово, как оно стоит в хуке, а не обрубок основы («догов»).
    loop, seen = [], set()
    for w in words(rows[0]["text"]):
        if stem(w) in common and stem(w) not in seen:
            seen.add(stem(w))
            loop.append(pretty(w))
    if loop:
        notes.append(f"Петля: последний бит повторяет «{', '.join(loop[:3])}» из хука. "
                     "Второй просмотр это бесплатный охват.")
    else:
        notes.append("Петли нет. Последний бит не повторяет ни одного слова хука, и ролик "
                     "кончается плоско. Повторить одно слово из бита 1 самый дешёвый "
                     "повторный просмотр, какой бывает.")

    if target:
        delta = total - target
        if abs(delta) <= target * 0.1:
            notes.append(f"Длина в цель ({total:.1f} с против {target} с).")
        elif delta > 0:
            notes.append(f"{delta:.1f} с сверх цели. Убери около {int(delta * wps)} слов.")
        else:
            notes.append(f"{-delta:.1f} с меньше цели. Добавь {int(-delta * wps)} слов "
                         "или сними короче. Короче обычно правильно.")

    return {
        "wpm": wpm, "target": target,
        "total_seconds": round(total, 2),
        "total_words": sum(r["words"] for r in rows),
        "beats": rows,
        "notes": notes,
    }


def render(a, out=sys.stdout):
    head = (f"БИТЫ  ·  слов {a['total_words']}  ·  ~{a['total_seconds']:.1f} с "
            f"при {a['wpm']:g} сл/мин" + (f"  ·  цель {a['target']:g} с" if a["target"] else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for r in a["beats"]:
        label = f"{r['label']:<9}" if r["label"] else " " * 9
        print(f"  {tc(r['start'])}  {r['dur']:4.1f} с  {label}{r['text']}", file=out)
        for f in r["flags"]:
            print(f"  {'':>6}  {'':>6}  {'':<9}^ {f}", file=out)
    print("-" * max(len(head), 72), file=out)
    for n in a["notes"]:
        print(f"  - {n}", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Сценарий рилса в таблицу битов по секундам.")
    ap.add_argument("input", nargs="?", default="-", help="файл сценария или - для stdin")
    sys.stdout.reconfigure(encoding="utf-8")
    ap.add_argument("--wpm", type=float, default=195, help="темп речи, слов в минуту (по умолчанию 195, как у автора)")
    ap.add_argument("--target", type=float, help="задуманная длина в секундах")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, wpm=args.wpm, target=args.target)
    if not a:
        print("empty script", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0)


if __name__ == "__main__":
    main()
