#!/usr/bin/env python3
"""
caption_ru.py - проверить подпись Instagram и показать ровно то, что видно в
ленте до «… ещё», для русских подписей.

Instagram показывает в ленте около 125 знаков подписи, остальное прячет за
нажатием. Почти каждая неудачная подпись проваливается именно там: хук в
третьем предложении, первая строка это приветствие, или всё начинается с
хештега. Скрипт печатает видимое окно в рамке, чтобы ты прочитал его, как
листающий незнакомец, а потом проверяет восемь вещей, которые стоит проверять.

Отсечка в 125 знаков приблизительная. Настоящее число зависит от телефона,
размера шрифта и того, где у тебя переносы строк, поэтому и нужен запас, а не
подпись, подогнанная ровно под 125. Проверить отсечку жёстче можно флагом
--truncate.

Что изменено против оригинала:
- русские призывы («напиши», «подпишись», «сохрани», «ссылка в шапке»),
  русские пустые хештеги (#рек, #втоп), ссылки на .ru и t.me;
- «Подпишись и напиши СЛОВО» в одной фразе считается ОДНИМ призывом: у нас
  это одна воронка (ChatPlace проверяет подписку и шлёт гайд);
- две наши проверки, помечены «(наше)»: точка в конце строки и длинное тире.
  Правило автора: в публичном тексте их нет.

Запуск
  python -I -X utf8 caption_ru.py caption.txt
  python -I -X utf8 caption_ru.py caption.txt --keywords "claude code,ии агент"
  python -I -X utf8 caption_ru.py - < caption.txt
  python -I -X utf8 caption_ru.py caption.txt --json
"""

import argparse
import json
import re
import sys
import textwrap

LIMIT = 2200             # Жёсткий лимит подписи в Instagram.
TRUNCATE = 125           # Примерно здесь лента режет до «… ещё».
HASHTAG_LIMIT = 5        # Лимит Instagram на пост и рилс с 18.12.2025, раньше 30.
                         # Объявил аккаунт @Creators: "using fewer (up to 5) more
                         # targeted hashtags, rather than many generic ones, can
                         # improve both your content's performance and people's
                         # experience". Проверено 23.11.2026 (Business Today
                         # 19.12.2025, Social Media Today).

HASHTAG_RE = re.compile(r"(?:^|\s)(#\w+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[\w.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\bt\.me/\S+|"
                     r"\b[\w-]+\.(?:com|co|io|net|org|ai|app|ru|рф|me|su)/\S*",
                     re.IGNORECASE)
# \u0423 \u0414\u0436\u0435\u0439\u043A\u0430 \u0432 \u043A\u043B\u0430\u0441\u0441\u0435 \u0435\u0441\u0442\u044C \u0438 U+FE0F (\u0437\u043D\u0430\u043A \u00AB\u043F\u043E\u043A\u0430\u0436\u0438 \u043A\u0430\u043A \u044D\u043C\u043E\u0434\u0437\u0438\u00BB), \u043F\u043E\u044D\u0442\u043E\u043C\u0443 \u26A1\uFE0F \u0441\u0447\u0438\u0442\u0430\u043B\u0441\u044F
# \u0437\u0430 \u0434\u0432\u0430 \u044D\u043C\u043E\u0434\u0437\u0438. \u0421\u0447\u0438\u0442\u0430\u0435\u043C \u0442\u043E\u043B\u044C\u043A\u043E \u0441\u0430\u043C \u0437\u043D\u0430\u0447\u043E\u043A.
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF]")
CONCRETE_RE = re.compile(
    r"\$\s?\d|\d\s?₽|\b\d[\d\s,.]*\b|(?<!^)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b|\b[A-Za-z][A-Za-z0-9.+-]{1,}\b|"
    r"(?i:\b(?:два|две|три|пять|десять|двадцать|сто|тысяч\w*|миллион\w*|вдвое|втрое)\b)",
    re.MULTILINE)

# Кодовое слово: написано капсом (СКОРОСТЬ, ЛИМИТ), часто в «ёлочках».
KEYWORD = r"[«\"]?\b(?=[A-ZА-ЯЁ0-9]*[A-ZА-ЯЁ])[A-ZА-ЯЁ0-9]{2,}\b[»\"]?"
ASKS = [
    (re.compile(r"(?i:\b(?:напиши|напишите|пиши|пишите|оставь|оставьте|коммент\w*)\b)[^.!?\n]{0,40}?"
                + KEYWORD), "кодовое слово в комментарии"),
    (re.compile(r"(?i)\b(?:напиши|пиши|напишите)\s+(?:мне\s+)?в\s+(?:директ|личку|лс|личные)|"
                r"\bв\s+директ\s+слово"), "в директ"),
    (re.compile(r"(?i)\bсохран(?:и|ите|яй)\b"), "сохрани"),
    (re.compile(r"(?i)\b(?:отправь|отправьте|перешли|поделись|поделитесь)\b"), "отправь другу"),
    (re.compile(r"(?i)\bподпис(?:ывайся|ывайтесь|шись|шитесь|ываемся)\b|\bподпишись\b"), "подпишись"),
    (re.compile(r"(?i)\bссылк\w*\s+(?:в\s+)?(?:шапке|профиле|био|bio|описании профиля)\b"), "ссылка в шапке"),
    (re.compile(r"(?i)\b(?:листай|листайте|свайпни|свайпай|жми|нажми)\b"), "листай или жми"),
    (re.compile(r"(?i)\b(?:расскажи|расскажите|как думаешь|как думаете|а у тебя|а у вас|какой из|"
                r"какой вариант|что выберешь)\b"), "ответь на вопрос"),
]

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily",
               "#рек", "#реки", "#рекомендации", "#вреки", "#врек", "#хочуврек", "#хочуврекомендации",
               "#втоп", "#популярное", "#тренды", "#тренд", "#лайк", "#лайки", "#подпишись",
               "#взаимнаяподписка", "#рилс", "#рилсы", "#инстаграм", "#вирусное"}


def visible_window(text, cut):
    """То, что видно в ленте. Instagram режет посреди слова, и мы тоже."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  ЧТО ВИДНО В ЛЕНТЕ", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "… ещё" if truncated else "(подпись видна целиком)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def count_asks(text):
    asks = [name for pattern, name in ASKS if pattern.search(text)]
    # Наше: «Подпишись и напиши СЛОВО» в одной фразе это одна воронка, один призыв.
    if "подпишись" in asks and "кодовое слово в комментарии" in asks:
        for sent in re.split(r"[.!?\n]", text):
            if ASKS[4][0].search(sent) and ASKS[0][0].search(sent):
                asks = [a for a in asks if a not in ("подпишись", "кодовое слово в комментарии")]
                asks.insert(0, "подпишись + кодовое слово")
                break
    return asks


def analyse(text, cut=TRUNCATE, keywords=None):
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = HASHTAG_RE.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    asks = count_asks(stripped)
    filler = [t for t in tags if t.lower() in FILLER_TAGS]
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    add("ДЛИНА", "ОШИБКА" if chars > LIMIT else "ОК",
        f"{chars} / {LIMIT} знаков" + (f", на {chars - LIMIT} больше лимита"
                                       if chars > LIMIT else ""))

    if not first_line:
        add("ПЕРВАЯ СТРОКА", "ОШИБКА", "подпись начинается с пустой строки")
    elif first_line.startswith("#") or first_line.startswith("@"):
        add("ПЕРВАЯ СТРОКА", "ОШИБКА",
            "начинается с хештега или отметки, а это единственное место, которое стоит фразы")
    elif len(first_line) > cut:
        add("ПЕРВАЯ СТРОКА", "ВНИМ",
            f"{len(first_line)} зн., поэтому режется на {cut} посреди мысли. "
            "Нормально, если обрыв это интрига, плохо, если это придаточное")
    else:
        add("ПЕРВАЯ СТРОКА", "ОК", f"{len(first_line)} зн., видна целиком")

    add("КОНКРЕТНЫЙ ХУК", "ОК" if CONCRETE_RE.search(window) else "ВНИМ",
        f"цифр или имён в видимом окне: {len(CONCRETE_RE.findall(window))}"
        + ("" if CONCRETE_RE.search(window) else ", до нажатия проверить нечего"))

    if len(tags) > HASHTAG_LIMIT:
        add("ХЕШТЕГИ", "ОШИБКА", f"{len(tags)} тегов, больше лимита Instagram в {HASHTAG_LIMIT}. "
                                 "Теги после пятого не считаются, а блок выглядит старым")
    elif len(tags) == HASHTAG_LIMIT and filler:
        add("ХЕШТЕГИ", "ВНИМ", f"{len(tags)} тегов, это лимит, и "
                               f"{len(filler)} из них пустые. Потрать пять на темы")
    elif filler:
        add("ХЕШТЕГИ", "ВНИМ", f"{len(tags)} тегов, {len(filler)} из них пустые "
                               f"({', '.join(filler[:3])}). Они ничего не описывают")
    else:
        add("ХЕШТЕГИ", "ОК", f"тегов: {len(tags)}" + (f": {' '.join(tags)}" if tags else ""))

    if not tags:
        add("МЕСТО ТЕГОВ", "ОК", "тегов нет, ставить нечего")
    elif any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        add("МЕСТО ТЕГОВ", "ВНИМ", "хештег в видимом окне, место в ленте ушло на ярлык")
    else:
        add("МЕСТО ТЕГОВ", "ОК", "теги ниже отсечки")

    add("ССЫЛКИ", "ВНИМ" if links else "ОК",
        f"ссылок в подписи: {len(links)}, а подпись не кликается. "
        f"Перенеси в шапку или в директ" if links else "мёртвых ссылок в тексте нет")

    if len(asks) == 1:
        add("ОДИН ПРИЗЫВ", "ОК", f"один призыв: {asks[0]}")
    elif not asks:
        add("ОДИН ПРИЗЫВ", "ВНИМ", "призыва нет. Реши, для чего этот пост")
    else:
        add("ОДИН ПРИЗЫВ", "ВНИМ", f"призывов {len(asks)} ({', '.join(asks)}). "
                                   "Два призыва то же самое, что ни одного")

    density = len(emoji) * 100 / max(chars, 1)
    add("ЭМОДЗИ", "ВНИМ" if density > 4 else "ОК",
        f"эмодзи: {len(emoji)}, {density:.1f} на 100 зн."
        + (", читается как украшение" if density > 4 else ""))

    if keywords:
        low = stripped.lower()
        found = [k for k in keywords if k.lower() in low]
        missing = [k for k in keywords if k.lower() not in low]
        in_window = [k for k in found if k.lower() in window.lower()]
        status = "ОК" if not missing else ("ВНИМ" if found else "ОШИБКА")
        add("ПОИСКОВЫЕ СЛОВА", status,
            f"есть {len(found)}/{len(keywords)}"
            + (f", в видимом окне {len(in_window)}" if found else "")
            + (f". Нет: {', '.join(missing)}" if missing else ""))

    # Наше: правило автора для публичного текста.
    dotted = [l.strip() for l in lines if re.search(r"(?<!\.)\.\s*$", l.strip())]
    add("ТОЧКИ В КОНЦЕ (наше)", "ВНИМ" if dotted else "ОК",
        f"строк с точкой в конце: {len(dotted)}. В публичном тексте у автора без точки"
        if dotted else "строк с точкой в конце нет")
    dashes = stripped.count("—")
    add("ДЛИННОЕ ТИРЕ (наше)", "ВНИМ" if dashes else "ОК",
        f"длинных тире: {dashes}. Прогони через /ig-human" if dashes else "длинных тире нет")

    fails = sum(1 for c in checks if c["status"] == "ОШИБКА")
    warns = sum(1 for c in checks if c["status"] == "ВНИМ")
    verdict = "ИСПРАВЬ" if fails else ("ПРОВЕРЬ" if warns else "ГОТОВО")

    return {
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks,
        "checks": checks, "verdict": verdict,
    }


def render(a, out=sys.stdout):
    head = (f"ПРОВЕРКА ПОДПИСИ  ·  {a['characters']} / {a['limit']} знаков  ·  "
            f"хештегов {len(a['hashtags'])}  ·  призывов {len(a['asks'])}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {c['status']:<6} {c['check']:<21} {c['detail']}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  ВЕРДИКТ  {a['verdict']}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Проверить подпись Instagram.")
    ap.add_argument("input", nargs="?", default="-", help="файл с подписью или - для stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"сколько знаков видно до «… ещё» (по умолчанию {TRUNCATE})")
    ap.add_argument("--keywords", default="", help="через запятую: по каким словам тебя должны находить")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","))
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0 if a["verdict"] == "ГОТОВО" else 1)


if __name__ == "__main__":
    main()
