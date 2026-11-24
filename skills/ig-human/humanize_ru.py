#!/usr/bin/env python3
"""
humanize_ru.py - убрать из черновика следы машины. Порт humanize.py из
Jakeschincariol/instagram-agent-skill (MIT) под русский текст.

Три прохода, в этом порядке:

  1. НЕВИДИМЫЕ    удалить или заменить пробелом символы, которых нет на
                  клавиатуре: нулевой ширины, word joiner, мягкий перенос,
                  BOM, теговые символы Unicode, неразрывные и узкие пробелы.
                  Они переживают копирование и это самая механическая примета
                  сгенерированного текста.
  2. ТИПОГРАФИКА  длинное тире: «X — это Y» -> «X это Y», в начале строки
                  -> дефис, иначе запятая. Короткое тире -> дефис, “лапки” ->
                  «ёлочки», многоточие одним знаком -> три точки, жирная точка
                  -> дефис.
  3. СЛОВАРЬ      заменить штампы из slop_ru.json простыми словами, сохранить
                  заглавные буквы, ссылки не трогать.

Что изменено против оригинала:
- словарь русский и составлен заново (slop_ru.json);
- у прилагательных с "stem": true меняется основа, окончание остаётся
  (уникальн-ую -> особ-ую), поэтому падеж не ломается;
- «е» и «ё» в словаре считаются одной буквой;
- кавычки становятся «ёлочками», а не прямыми: так печатает русская
  клавиатура телефона;
- «— это» отдельно, потому что запятая на его месте читается криво.

Приметы в строении фраз («не просто X, а Y», тройки, стена хештегов) только
ПОКАЗЫВАЮТСЯ, автоматически не переписываются: менять форму фразы надо с
головой, это работа модели, а не регулярного выражения.

Запуск
  python -I -X utf8 humanize_ru.py draft.txt
  python -I -X utf8 humanize_ru.py draft.txt --report
  python -I -X utf8 humanize_ru.py - --report < draft.txt
  python -I -X utf8 humanize_ru.py draft.txt --json
  python -I -X utf8 humanize_ru.py draft.txt -o clean.txt
"""

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop_ru.json")

URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
# Окончания твёрдых прилагательных на -ый: у основы и у замены они одинаковые.
ADJ_ENDINGS = r"(ый|ая|ое|ые|ого|ому|ым|ом|ую|ой|ых|ыми|ою)"


def load_lexicon(path=LEX):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _cp(spec):
    """'U+200B' -> 0x200b;  'U+E0000-U+E007F' -> (start, end)."""
    if "-" in spec:
        a, b = spec.split("-")
        return (int(a[2:], 16), int(b[2:], 16))
    return int(spec[2:], 16)


def _yo(escaped):
    """«е» и «ё» в словаре одна буква: «разберёмся» ловит и «разберемся»."""
    return re.sub(r"[её]", "[её]", escaped)


def lex_pattern(entry):
    body = _yo(re.escape(entry["find"])).replace(r"\ ", r"\s+")
    if entry.get("stem"):
        return re.compile(r"(?<![\w-])(" + body + ")" + ADJ_ENDINGS + r"(?![\w-])", re.IGNORECASE)
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.IGNORECASE)


def protect_urls(text):
    """Спрятать ссылки под заглушки, чтобы ни один проход не правил внутри."""
    found = []

    def stash(m):
        found.append(m.group(0))
        return f"\x00URL{len(found) - 1}\x00"

    return URL_RE.sub(stash, text), found


def restore_urls(text, found):
    for i, url in enumerate(found):
        text = text.replace(f"\x00URL{i}\x00", url)
    return text


def pass_invisible(text, lex):
    """Удалить невидимые символы или заменить пробелом. Возвращает (text, hits)."""
    hits = []
    for entry in lex["invisible"]:
        cp = _cp(entry["cp"])
        if isinstance(cp, tuple):
            pattern = "[" + re.escape(chr(cp[0])) + "-" + re.escape(chr(cp[1])) + "]"
        else:
            pattern = re.escape(chr(cp))
        n = len(re.findall(pattern, text))
        if n:
            hits.append({"name": entry["cp"] + " " + entry["name"], "count": n,
                         "action": "удалить" if entry["action"] == "delete" else "пробел"})
            text = re.sub(pattern, "" if entry["action"] == "delete" else " ", text)
    # Любой оставшийся символ категории Cf невидим по определению.
    stray = [c for c in text if unicodedata.category(c) == "Cf"]
    if stray:
        hits.append({"name": "прочие невидимые символы форматирования", "count": len(stray),
                     "action": "удалить"})
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return text, hits


def _smart_quotes(text):
    """Любые “лапки” и „лапки“ -> «ёлочки»: открывающая после пробела или начала."""
    out = []
    for i, ch in enumerate(text):
        if ch in "“”„":
            prev = text[i - 1] if i else " "
            out.append("«" if (prev.isspace() or prev in "([{«-—") else "»")
        else:
            out.append(ch)
    return "".join(out)


def pass_typographic(text, lex):
    hits = []
    quotes_done = False
    for entry in lex["typographic"]:
        ch = entry["from"]
        n = text.count(ch)
        if not n:
            continue
        hits.append({"name": f"{ch} {entry['name']}", "count": n,
                     "to": entry["to"].strip() or "(пробел)"})
        if ch == "—":
            text = re.sub(r"\s*—\s*(?=это\b)", " ", text)          # X — это Y  -> X это Y
            text = re.sub(r"(?m)^([ \t]*)—\s*", r"\1- ", text)    # — пункт      -> - пункт
            text = re.sub(r"\s*—\s*", ", ", text)                 # остальное    -> запятая
        elif ch == "–":
            text = re.sub(r"\s*–\s*(?=\d)", "-", text)            # 5–10  -> 5-10
            text = re.sub(r"\s+–\s+", ", ", text)                 # вместо длинного
            text = text.replace("–", "-")
        elif ch in "“”„":
            if not quotes_done:
                text = _smart_quotes(text)
                quotes_done = True
        else:
            text = text.replace(ch, entry["to"])
    # Запятая перед уже стоящим знаком читается криво.
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*\n", "\n", text)
    text = re.sub(r"(?m)^,\s*", "", text)
    return text, hits


def _match_case(src, repl):
    if not repl:
        return repl
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


def pass_lexical(text, lex):
    """Заменить штампы. Длинные первыми, чтобы фраза выигрывала у слова."""
    hits = []
    entries = sorted(lex["phrases"] + lex["words"],
                     key=lambda e: len(e["find"]), reverse=True)
    for entry in entries:
        pattern = lex_pattern(entry)
        found = pattern.findall(text)
        if not found:
            continue
        shown = entry["find"] + ("-" if entry.get("stem") else "")
        hits.append({"find": shown, "replace": (entry["replace"] + ("-" if entry.get("stem") else ""))
                     if entry["replace"] else "(удалено)",
                     "count": len(found), "family": entry["family"]})
        if entry.get("stem"):
            text = pattern.sub(lambda m: _match_case(m.group(1), entry["replace"]) + m.group(2), text)
        else:
            text = pattern.sub(lambda m: _match_case(m.group(0), entry["replace"]), text)
    # Уборка после удалений. Удалённый оборот оставляет висящие знаки
    # («система. .» или строку, которая начинается с запятой), и это читается
    # хуже, чем сам штамп.
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Настоящее многоточие прячем до уборки: у Джейка уборка начала строки
    # съедала «...» в хуке #21 «С середины фразы».
    text = text.replace("...", "\x00ELL\x00")
    # У Джейка тут только [,.;:]. По-русски удалённый зачин часто стоит с «!»
    # («Стоп, не листай!»), поэтому висящие ! и ? тоже убираем.
    text = re.sub(r"(?m)^[ \t]*(?:[,.;:!?]+[ \t]*)+", "", text)
    text = re.sub(r"(?m)^[ \t](?=\S)", "", text)       # один пробел от удаления.
                                                      # Глубокий отступ оставляем.
    # У Джейка \s+, и знак прилипал к прошлой строке через перенос. Только пробелы.
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?m)^[ \t]*(?:[,.;:!?]+[ \t]*)+", "", text)
    text = re.sub(r",[ \t]*([,.;:!?])", r"\1", text)   # тире стало запятой,
                                                      # а оборот за ним удалён
    text = re.sub(r"\.[ \t]*\.+", ".", text)
    text = re.sub(r"([!?])[ \t]*\.", r"\1", text)
    text = text.replace("\x00ELL\x00", "...")
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # «Тем не менее, ...» стало «Но, ...»: после «но» запятая не нужна.
    text = re.sub(r"(?m)(^|[.!?]\s+)(Но|но|А ещё|а ещё|Так что|так что),\s+", r"\1\2 ", text)
    # Тире стало запятой, а за ним связка: получается склейка («важно, а ещё, это
    # доказательство»). Делаем из неё новое предложение.
    text = re.sub(r",\s*(а ещё|так что|значит|в итоге|по сути)\s*,\s*",
                  lambda m: ". " + m.group(1)[0].upper() + m.group(1)[1:] + " ", text)
    return text, hits


def scan_structures(text, lex):
    flags = []
    for s in lex["structures"]:
        try:
            pattern = re.compile(s["regex"], re.MULTILINE)
        except re.error:
            continue
        found = pattern.findall(text)
        if found:
            flags.append({"name": s["name"], "count": len(found), "fix": s["fix"]})
    # Одинаковая длина предложений тоже примета строения.
    lens = [len(s.split()) for s in SENT_RE.findall(text) if len(s.split()) > 2]
    if len(lens) >= 4:
        mean = sum(lens) / len(lens)
        var = sum((n - mean) ** 2 for n in lens) / len(lens)
        cv = (var ** 0.5) / mean if mean else 0
        if cv < 0.35:
            flags.append({
                "name": f"Одинаковая длина предложений (разброс {cv:.2f})",
                "count": len(lens),
                "fix": "Разрежь одно предложение пополам. Другое пусть будет длинным. Машина пишет ровно",
            })
    return flags


def restore_capitals(original, text):
    """Удалённый зачин оставляет следующее слово с маленькой буквы.

    Чиним только у тех, кто вообще пишет предложения с заглавной: нарочно
    строчный голос это стиль, а не след машины, и перекрикивать его значило бы
    сделать ровно то, против чего этот скрипт.
    """
    letter = r"[A-Za-zА-Яа-яЁё]"
    starts = re.findall(r"(?:^|[.!?]\s+|\n)\s*(" + letter + ")", original)
    if not starts or sum(1 for c in starts if c.isupper()) * 2 < len(starts):
        return text
    return re.sub(r"(?:^|(?<=[.!?] )|(?<=[.!?]\n)|(?<=\n))\s*([a-zа-яё])",
                  lambda m: m.group(0)[:-1] + m.group(1).upper(), text)


def humanize(text, lex):
    raw_for_case = text
    text, urls = protect_urls(text)
    text, inv = pass_invisible(text, lex)
    text, typo = pass_typographic(text, lex)
    text, lexi = pass_lexical(text, lex)
    text = restore_capitals(raw_for_case, text)
    text = restore_urls(text, urls)
    return text.strip() + "\n", {
        "invisible": inv,
        "typographic": typo,
        "lexical": lexi,
        "structures": scan_structures(text, lex),
    }


def render_report(report, out=sys.stderr):
    def head(title):
        print(f"\n{title}\n" + "-" * len(title), file=out)

    total = sum(h["count"] for h in report["invisible"]) \
        + sum(h["count"] for h in report["typographic"]) \
        + sum(h["count"] for h in report["lexical"])

    head("ОТЧЁТ ОЧЕЛОВЕЧИВАТЕЛЯ")
    print(f"убрано следов машины: {total}; приметы в строении фраз, которые надо "
          f"переписать руками: {len(report['structures'])}", file=out)

    if report["invisible"]:
        head("1. НЕВИДИМЫЕ СИМВОЛЫ")
        for h in report["invisible"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['action']}", file=out)
    if report["typographic"]:
        head("2. ТИПОГРАФИКА")
        for h in report["typographic"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['to']}", file=out)
    if report["lexical"]:
        head("3. СЛОВАРЬ ШТАМПОВ")
        for h in report["lexical"]:
            print(f"  {h['count']:>3}x  {h['find']}  -> {h['replace']}   [{h['family']}]", file=out)
    if report["structures"]:
        head("4. ПРИМЕТЫ В СТРОЕНИИ  (сами не чинятся, перепиши эти места)")
        for h in report["structures"]:
            print(f"  {h['count']:>3}x  {h['name']}\n        {h['fix']}", file=out)
    if not any(report.values()):
        head("ЧИСТО")
        print("  Убирать нечего.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Убрать из черновика следы машины.")
    ap.add_argument("input", nargs="?", default="-", help="файл или - для stdin")
    ap.add_argument("-o", "--out", help="записать чистый текст сюда, а не в stdout")
    ap.add_argument("--report", action="store_true", help="показать, что изменилось (в stderr)")
    ap.add_argument("--json", action="store_true", help="вывести {text, report} как JSON")
    ap.add_argument("--lexicon", default=LEX, help="путь к slop_ru.json")
    args = ap.parse_args()
    # newline="\n": на Windows иначе каждая строка получает CRLF и файл меняется весь.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8")

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    lex = load_lexicon(args.lexicon)
    clean, report = humanize(raw, lex)

    if args.json:
        print(json.dumps({"text": clean, "report": report}, indent=2, ensure_ascii=False))
        return
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(clean)
        print(f"записано: {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(clean)
    if args.report:
        render_report(report)


if __name__ == "__main__":
    main()
