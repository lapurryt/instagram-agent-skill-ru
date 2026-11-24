#!/usr/bin/env python3
"""
hookscore_ru.py - оценка первой фразы рилса на русском, под наш аккаунт.

Особенности:
- русские слова, числительные, деньги, имена (Claude, ChatGPT...), обращение на «ты»;
- длина считается в темпе автора: около 195 слов в минуту после монтажа, 3 секунды это ~10 слов;
- шестая проверка ВЫГОДА: понимает ли зритель, что получит лично он. На нашей нише это
  единственное, что заметно отделяет хиты от провалов (см. calibration.md);
- антиформулы из hooks_ru.json (новость, приглашение на эфир, свои просмотры, разгон);
- определяет формулу по hooks_ru.json.

Чем это НЕ является: прогнозом просмотров. Оригинальный счётчик на хуках автора дал
корреляцию -0,01. Используй его как фильтр явно слабых хуков, а выбор между двумя
нормальными хуками решает тема и монтаж.

Запуск
  python -I -X utf8 hookscore_ru.py hooks.txt         # по одному хуку в строке, рейтинг
  python -I -X utf8 hookscore_ru.py --hook "фраза"
  python -I -X utf8 hookscore_ru.py hooks.txt --json
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
HOOKS = json.loads((HERE / "hooks_ru.json").read_text(encoding="utf-8"))
WPM = 195

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$%₽'’-]+")
NUM_RE = re.compile(r"\d[\d\s,.]*")
LATIN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.+-]{1,}\b")
CAP_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b[А-ЯЁ][а-яё]{2,}")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")

NUM_WORDS = re.compile(
    r"(?i)\b(ноль|нол[яюе]|два|две|двух|три|тр[её]х|четыре|пять|пяти|шесть|семь|восемь|девять|десять|"
    r"двадцать|тридцать|сорок|пятьдесят|сто|ст[аоу]|двести|пятьсот|тысяч\w*|миллион\w*|миллиард\w*|"
    r"половин\w*|вдвое|втрое|раз в \w+)\b")
MONEY = re.compile(r"(?i)(\$|₽|руб\w*|доллар\w*|бакс\w*|евро|зарплат\w*|бесплатн\w*|платн\w*|плат(ишь|ить|ит)|"
                   r"тариф\w*|подписк\w*|сэконом\w*|экономи\w*|деньг\w*|денег|дорог\w*|дешёв\w*|дешев\w*)")

STAKES = re.compile(
    r"(?i)\b(не|ни|нет|никто|никогда|нельзя|хватит|перестань|ошибк\w*|потерял\w*|теряешь|теряет|слил\w*|сжига\w*|"
    r"сгора\w*|кончает\w*|закончил\w*|заблокир\w*|бан\w*|удал\w*|украл\w*|опасн\w*|риск\w*|секрет\w*|скрыт\w*|"
    r"правд\w*|хуже|худш\w*|провал\w*|впустую|зря|лишн\w*|переплачива\w*|бесплатн\w*|вместо|без|только|уже|"
    r"всё ещё|до сих пор|первым делом|срочно|прогор\w*|обман\w*|лимит\w*)\b")

WEAK_OPENERS = re.compile(
    r"(?i)^\s*(привет|всем привет|итак|короче|ну|так вот|слушайте|смотрите|ребята|друзья|давайте|сегодня|"
    r"в этом (видео|ролике)|сейчас (я )?(расскажу|покажу)|я хочу|хочу рассказать|знаете|вы знали|это видео|"
    r"многие|есть такая)\b")
NEWS_OPENER = re.compile(r"(?i)^\s*(теперь можно|теперь (ты )?можешь|вышел|вышла|вышло|только что|"
                         r"представил[аи]?|выпустил[аи]?|запустил[аи]?|появил(ся|ась|ось))")

ADDRESS = re.compile(r"(?i)\b(ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоих|твоего|твоей|вы|вас|вам|ваш\w*)\b")
IMPERATIVE = re.compile(
    r"(?i)^\s*(перестань|хватит|сделай|проверь|удали|скачай|поставь|включи|отключи|запомни|сохрани|укради|забирай|"
    r"попроси|открой|выдели|отдай|не (делай|пиши|плати|покупай|используй)|смотри|найди|узнай|загрузи)")
FIRST_PERSON = re.compile(r"(?i)\b(я|мне|меня|мой|моя|моё|мои|мы|нам|наш\w*)\b")

# What the viewer gets personally. In our niche swipe the topic, not the grammar, separates
# hits from flops: money, limits, personal data, work, time, an assistant that works for you.
GAIN = re.compile(
    r"(?i)(деньг|денег|руб|доллар|\$|₽|бесплатн|сэконом|экономи|тариф|подписк|лимит|токен|"
    r"работ[ау]|зарплат|резюме|ваканси|данн(ые|ых)|телефон|адрес|фото|паспорт|"
    r"за тебя|вместо тебя|твой личн|ассистент|помощник|за выходные|за вечер|"
    r"время|минут|час(ов|а)?\b|быстрее|проще|без кода|бизнес|клиент|продаж|заработ)")


def clamp(n):
    return max(0.0, min(100.0, n))


def words(text):
    return WORD_RE.findall(re.sub(r"(?<=\d)[\s,](?=\d{3})", "", text))


def first_sentence(text):
    m = re.match(r"\s*(.+?[.!?…])(\s|$)", text)
    return m.group(1) if m else text


def check_length(text):
    hook = first_sentence(text)
    n = len(words(hook))
    secs = n / (WPM / 60)
    if 4 <= n <= 10:
        score = 100.0
    elif n < 4:
        score = clamp(100 - (4 - n) * 20)
    else:
        score = clamp(100 - (n - 10) * 10)
    if len(hook) > 70:
        score -= 10
    return clamp(score), f"{n} слов в первой фразе, ~{secs:.1f} с (нужно 4-10 слов, до 3 с)"


def check_specificity(text):
    nums = [x.strip() for x in NUM_RE.findall(text) if x.strip()]
    spoken = NUM_WORDS.findall(text)
    names = set(LATIN_RE.findall(text)) | set(CAP_RE.findall(text))
    money = MONEY.findall(text)
    hits = len(nums) + len(spoken) + len(names) + (1 if money else 0)
    score = 15.0 if hits == 0 else clamp(45 + hits * 25)
    found = ", ".join((nums + [s if isinstance(s, str) else s[0] for s in spoken] + sorted(names))[:4])
    return score, f"{hits} конкретных деталей" + (f": {found}" if found else ": ни цифры, ни имени")


def check_stakes(text):
    hits = sorted({m.group(0).lower() for m in STAKES.finditer(text)})
    score = {0: 20.0, 1: 70.0}.get(len(hits), 100.0)
    return score, (f"{len(hits)} маркеров ставки: {', '.join(hits[:4])}" if hits else "ничего не на кону")


def check_frontload(text):
    w = words(text)
    if not w:
        return 0.0, "пусто"
    penalty, why = 0, ""
    if WEAK_OPENERS.match(text):
        penalty, why = 30, "; пустой разгон в начале"
    if NEWS_OPENER.match(text):
        penalty, why = 25, "; начало как у новости («теперь можно», «вышел»)"
    payload = None
    for i, tok in enumerate(w):
        if (STAKES.fullmatch(tok) or NUM_RE.fullmatch(tok) or NUM_WORDS.fullmatch(tok) or MONEY.fullmatch(tok)
                or LATIN_RE.fullmatch(tok) or (i and CAP_RE.fullmatch(tok))):
            payload = i
            break
    if payload is None:
        base, where = 30.0, "главного слова нет"
    elif payload <= 3:
        base, where = 100.0, f"главное слово на позиции {payload + 1}"
    elif payload <= 6:
        base, where = 70.0, f"главное слово на позиции {payload + 1}, можно раньше"
    else:
        base, where = 40.0, f"главное слово на позиции {payload + 1}, поздно"
    return clamp(base - penalty), where + why


def check_address(text):
    if ADDRESS.search(text):
        return 100.0, "говорит со зрителем"
    if IMPERATIVE.match(text):
        return 90.0, "начинается с команды зрителю"
    if FIRST_PERSON.search(text):
        return 70.0, "от первого лица, зритель не назван"
    return 35.0, "в третьем лице, зрителя в кадре нет"


def check_gain(text):
    hits = sorted({m.group(0).lower() for m in GAIN.finditer(text)})
    you = bool(ADDRESS.search(text) or IMPERATIVE.match(text))
    if hits and you:
        return 100.0, f"зритель получает: {', '.join(hits[:3])}"
    if hits:
        return 70.0, f"выгода есть ({', '.join(hits[:3])}), но не названо, что это ему"
    if you:
        return 45.0, "обращение есть, а выгоды нет"
    return 20.0, "про ИИ, а не про зрителя: что он получит?"


CHECKS = ["ДЛИНА", "КОНКРЕТИКА", "СТАВКА", "НАЧАЛО", "ЗРИТЕЛЬ", "ВЫГОДА"]
FUNCS = [check_length, check_specificity, check_stakes, check_frontload, check_address, check_gain]
WEIGHTS = {"ДЛИНА": 1.0, "КОНКРЕТИКА": 1.0, "СТАВКА": 0.8, "НАЧАЛО": 1.0, "ЗРИТЕЛЬ": 0.8, "ВЫГОДА": 1.6}

DEALBREAKERS = [(HASHTAG_RE, "Хештег в хуке. Хештегам место в подписи"),
                (EMOJI_RE, "Эмодзи в голосовом хуке. Эмодзи только на плашке")]
for a in HOOKS["anti"]:
    DEALBREAKERS.append((re.compile(a["match"]), f"{a['name']}: {a['why']}. {a['fix']}"))


def classify(text):
    by_id = {h["id"]: h for h in HOOKS["hooks"]}
    for i in HOOKS["classify_order"]:
        h = by_id[i]
        if re.search(h["match"], text):
            return f"#{h['id']} {h['name']}"
    return "-"


def run(text):
    results = {name: f(text) for name, f in zip(CHECKS, FUNCS)}
    flags = [msg for pat, msg in DEALBREAKERS if pat.search(text)]
    scores = [results[c][0] for c in CHECKS]
    weighted = sum(results[c][0] * WEIGHTS[c] for c in CHECKS) / sum(WEIGHTS.values())
    overall = clamp(weighted * 0.6 + min(scores) * 0.4 - len(flags) * 15)
    verdict = ("СИЛЬНЫЙ" if overall >= 70 and min(scores) >= 55 and not flags
               else "НОРМ" if overall >= 50 else "СЛАБЫЙ")
    return results, overall, verdict, flags


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def main():
    ap = argparse.ArgumentParser(description="Оценка хука рилса на русском")
    ap.add_argument("input", nargs="?", default="-")
    ap.add_argument("--hook")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    rows = []
    for line in lines:
        results, overall, verdict, flags = run(line)
        rows.append({"hook": line, "score": round(overall, 1), "verdict": verdict, "formula": classify(line),
                     "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
                     "weakest": min(CHECKS, key=lambda c: results[c][0]), "flags": flags})
    if args.json:
        print(json.dumps(rows if len(rows) > 1 else rows[0], ensure_ascii=False, indent=1))
        return
    if len(rows) == 1:
        r = rows[0]
        print(f"\nОЦЕНКА ХУКА\n{'=' * 64}\n  «{r['hook']}»\n  формула: {r['formula']}\n")
        for c in CHECKS:
            print(f"  {c:<11} {bar(r['checks'][c]['score'])} {r['checks'][c]['score']:5.1f}")
            print(f"  {'':<11} {r['checks'][c]['detail']}")
        print(f"{'-' * 64}\n  {'ИТОГ':<11} {bar(r['score'])} {r['score']:5.1f}   {r['verdict']}")
        for f in r["flags"]:
            print(f"\n  СТОП  {f}")
        print()
        return
    print(f"\nРЕЙТИНГ ХУКОВ\n{'=' * 78}")
    for i, r in enumerate(sorted(rows, key=lambda r: -r["score"]), 1):
        hook = r["hook"] if len(r["hook"]) <= 64 else r["hook"][:61] + "..."
        print(f"{'->' if i == 1 else '  '} {r['score']:5.1f} {r['verdict']:<8} {hook}")
        print(f"        формула {r['formula']}; слабее всего: {r['weakest']} ({r['checks'][r['weakest']]['score']:.0f})")
        for f in r["flags"]:
            print(f"        стоп: {f}")
    print("\nЭто фильтр слабых хуков, не прогноз просмотров. Между двумя нормальными выбирай по теме и картинке\n")


if __name__ == "__main__":
    main()
