#!/usr/bin/env python3
"""
detect_ru.py - пять проверок: насколько черновик похож на машинный текст.
Порт detect.py из Jakeschincariol/instagram-agent-skill (MIT) под русский.

Что это: пять местных эвристик по тем сигналам, на которые смотрят публичные
детекторы ИИ: разброс длины предложений, конкретика, штампы, типографский
отпечаток и голос. Всё считается на твоём компьютере по одному тексту. Ничего
никуда не отправляется.

Чем это НЕ является: GPTZero, Originality, Copyleaks, Winston или Turnitin.
Их API не вызываются, их вердикт не обещается. Скрипт ловит то, на что смотрят
они все, поэтому исправления обычно двигают и их цифры, но честно можно сказать
только то, что написано в этой строке.

Что изменено против оригинала:
- русские слова, числительные словами («десять», «тысяча») и латинские названия
  (Claude, Wi-Fi) считаются конкретикой;
- в ГОЛОСЕ вместо английских сокращений (it's, don't) считаются разговорные
  частицы (ну, вот, же, реально, прям, короче...), а к местоимениям добавлены
  глаголы на «ты» (открываешь, пишешь): по-русски «ты» часто сидит в глаголе;
- словарь штампов slop_ru.json; приметы с "report_only" (например «вы» вместо
  «ты») в счёт не идут, их показывает только humanize_ru.py.

Каждая проверка даёт оценку ЧЕЛОВЕЧНОСТИ от 0 до 100. Выше лучше.

Запуск
  python -I -X utf8 detect_ru.py draft.txt
  python -I -X utf8 detect_ru.py - < draft.txt
  python -I -X utf8 detect_ru.py draft.txt --json
  python -I -X utf8 detect_ru.py before.txt after.txt      # сравнить два черновика
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop_ru.json")

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'-]*")
ADJ_ENDINGS = r"(ый|ая|ое|ые|ого|ому|ым|ом|ую|ой|ых|ыми|ою)"
COLLOQUIAL = re.compile(
    r"(?i)(?<![\w-])(?:ну|вот|же|ж|типа|реально|прям|прямо|короче|вообще|кстати|ведь|как раз|просто|"
    r"ок|окей|блин|норм|жесть|смотри|слушай|щас|чё|ага|видишь|прикинь|кайф)(?![\w-])|\w+-то\b")
PRONOUNS = re.compile(
    r"(?i)(?<![\w-])(?:я|меня|мне|мной|мой|моя|моё|мое|мои|моего|моей|моих|мою|моим|"
    r"мы|нас|нам|нами|наш|наша|наше|наши|нашего|нашей|наших|нашу|"
    r"ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоего|твоей|твоих|твою|твоим|"
    r"вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|ваших|вашу)(?![\w-])")
YOU_VERBS = re.compile(r"(?i)(?<![\w-])[а-яё]{2,}(?:ешь|ёшь|ишь)(?:ся)?(?![\w-])")
NUMBERS = re.compile(r"\b\d[\d\s,.]*%?|\$\d|\d\s?₽")
NUM_WORDS = re.compile(
    r"(?i)(?<![\w-])(?:два|две|двух|три|трёх|трех|четыре|пять|пяти|шесть|семь|восемь|девять|десять|"
    r"двадцать|тридцать|сорок|пятьдесят|сто|двести|триста|пятьсот|тысяч\w*|миллион\w*|миллиард\w*|"
    r"вдвое|втрое|половин\w*)(?![\w-])")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b", re.MULTILINE)
LATIN = re.compile(r"\b[A-Za-z][A-Za-z0-9.+-]{1,}\b")


def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Перевести value в 0-100: `human` -> 100, `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text):
    return WORD_RE.findall(text)


def lex_pattern(entry):
    body = re.sub(r"[её]", "[её]", re.escape(entry["find"])).replace(r"\ ", r"\s+")
    if entry.get("stem"):
        return re.compile(r"(?<![\w-])" + body + ADJ_ENDINGS + r"(?![\w-])", re.IGNORECASE)
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.IGNORECASE)


def check_burstiness(text):
    """Люди сильно меняют длину предложений. Модели пишут ровно."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "слишком коротко, не оценить"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=0.70, machine=0.22)
    return score, f"разброс {cv:.2f} на {len(lens)} предложениях (нужно 0,55+)"


def check_specificity(text):
    """Цифры, имена, названия. Штампы абстрактны."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "слишком коротко, не оценить"
    per100 = 100 / len(w)
    hits = (len(NUMBERS.findall(text)) + len(NUM_WORDS.findall(text))
            + len(set(PROPER.findall(text)) | set(LATIN.findall(text))))
    density = hits * per100
    score = scale(density, human=6.0, machine=0.5)
    return score, f"конкретики {hits}, {density:.1f} на 100 слов (нужно 4+)"


def check_slop(text, lex):
    """Плотность штампов по словарю."""
    w = words(text)
    if not w:
        return 50.0, "пусто"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        n = len(lex_pattern(entry).findall(text))
        if n:
            hits += n
            found.append(entry["find"] + ("-" if entry.get("stem") else ""))
    density = hits * 100 / len(w)
    score = scale(density, human=0.0, machine=4.0)
    detail = f"штампов {hits}, {density:.1f} на 100 слов"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text):
    """Символы, которых не даёт клавиатура телефона."""
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf")
    em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”„")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    total = invisible * 4 + em * 2 + curly + ellip + nbsp
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=0.0, machine=12.0)
    detail = (f"невидимых {invisible}, длинных тире {em}, “лапок” {curly}, "
              f"многоточий одним знаком {ellip}, жёстких пробелов {nbsp}")
    return score, detail


def check_voice(text, lex):
    """Разговорность, лицо и формы, к которым тянутся модели."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "слишком коротко, не оценить"
    per100 = 100 / len(w)
    colloquial = len(COLLOQUIAL.findall(text)) * per100
    person = (len(PRONOUNS.findall(text)) + len(YOU_VERBS.findall(text))) * per100
    tells = 0
    names = []
    for s in lex["structures"]:
        if s.get("report_only"):
            continue
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3 and statistics.pstdev(bullets) < 1.6)
    score = (scale(colloquial, human=3.0, machine=0.0) * 0.35
             + scale(person, human=8.0, machine=1.0) * 0.35
             + clamp(100 - tells * 22) * 0.30)
    if uniform:
        score -= 12
        names.append("uniform-bullets")
    detail = (f"разговорных частиц {colloquial:.1f}, «я/ты/мы» {person:.1f} на 100 слов, "
              f"примет в строении {tells}")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["РАЗБРОС", "КОНКРЕТИКА", "ШТАМПЫ", "ОТПЕЧАТОК", "ГОЛОС"]


def run(text, lex):
    results = {}
    results["РАЗБРОС"] = check_burstiness(text)
    results["КОНКРЕТИКА"] = check_specificity(text)
    results["ШТАМПЫ"] = check_slop(text, lex)
    results["ОТПЕЧАТОК"] = check_fingerprint(text)
    results["ГОЛОС"] = check_voice(text, lex)
    scores = [results[c][0] for c in CHECKS]
    # Самая слабая проверка тянет вердикт вниз: детектору хватает одного сигнала.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4
    verdict = "ОК" if overall >= 70 and min(scores) >= 55 else (
        "ПРОВЕРЬ" if overall >= 50 else "МАШИНА")
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout):
    title = "ПАНЕЛЬ ПРОВЕРКИ НА ИИ" + (f"  -  {label}" if label else "")
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'ЧЕЛОВЕЧНОСТЬ':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != "ОК":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Слабее всего: {weakest}. Начни с неё.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Насколько черновик похож на машинный текст.")
    ap.add_argument("input", nargs="?", default="-", help="файл или - для stdin")
    ap.add_argument("compare", nargs="?", help="второй файл, чтобы показать до и после")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lexicon", default=LEX)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2, ensure_ascii=False))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == "ОК" else 1)


if __name__ == "__main__":
    main()
