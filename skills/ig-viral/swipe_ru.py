#!/usr/bin/env python3
"""
swipe_ru.py - отсортировать собранные рилсы по тому, во сколько раз каждый
обогнал свой аккаунт, назвать формулу хука и записать свайп-файл.

Весь смысл скрипта в одной поправке: голые просмотры не доказательство.
Аккаунт на 2 000 000 подписчиков с 400 000 просмотров просто провёл тихий
день. Аккаунт на 4 000 подписчиков с 400 000 просмотров что-то нашёл. Здесь
рейтинг по множителю над собственной медианой аккаунта, и это единственная
версия «залетело», из которой можно что-то скопировать.

На входе таблица через табуляцию, которую заполняешь, пока смотришь: один
рилс на строку, первой строкой названия столбцов:

    account   followers   median   views    hook
    @someone  48000       11000    412000   никто не говорит, что первые 30 рилсов провалятся

`median` это обычные свежие просмотры этого аккаунта, и это лучшая база.
Если есть только `followers`, оставь median пустым, скрипт об этом скажет.
`hook` это первая фраза рилса, голосом или на экране, его словами.

Что изменено против оригинала:
- формулы и оценка из нашего ig-reel: hooks_ru.json и hookscore_ru.py
  (русские regex, 29 формул, 6 проверок);
- столбцы можно назвать по-русски (аккаунт, подписчики, медиана, просмотры, хук);
- можно подать .json: список записей с теми же полями. Так читаются
  выгрузки, сведённые в такой список;
- вывод по-русски.

Запуск
  python -I -X utf8 swipe_ru.py captured.tsv
  python -I -X utf8 swipe_ru.py captured.tsv --out ~/.claude/instagram/swipe.md
  python -I -X utf8 swipe_ru.py rows.json --json
"""

import argparse
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "ig-reel", "hooks_ru.json")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$%₽'’-]+")
ALIASES = {"аккаунт": "account", "подписчики": "followers", "медиана": "median",
           "просмотры": "views", "хук": "hook"}

try:                                              # не обязательно: заодно оценить хуки
    sys.path.insert(0, os.path.join(HERE, "..", "ig-reel"))
    from hookscore_ru import run as score_hook    # noqa: E402
except Exception:                                 # ig-viral скопировали отдельно
    score_hook = None


def load_formulas(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    by_id = {h["id"]: h for h in d["hooks"]}
    order = d.get("classify_order") or sorted(by_id)
    return [(by_id[i]["id"], by_id[i]["name"],
             re.compile(by_id[i]["match"], re.IGNORECASE)) for i in order if i in by_id]


def classify(hook, formulas):
    if not formulas:
        return None, "без формулы"
    for fid, name, pattern in formulas:
        if pattern.search(hook):
            return fid, name
    return None, "без формулы"


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def read_rows(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    if path.lower().endswith(".json") or raw.lstrip().startswith("["):
        items = json.loads(raw)
    else:
        lines = [l for l in raw.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        if not lines:
            return []
        head = [ALIASES.get(c.strip().lower(), c.strip().lower()) for c in lines[0].split("\t")]
        if "views" in head and "hook" in head:
            cols, body = head, lines[1:]
        else:
            cols, body = ["account", "followers", "views", "hook"], lines
        items = []
        for line in body:
            cells = line.split("\t")
            if len(cells) < len(cols):
                cells += [""] * (len(cols) - len(cells))
            items.append(dict(zip(cols, [c.strip() for c in cells])))
    rows = []
    for it in items:
        r = {ALIASES.get(k, k): v for k, v in it.items()}
        r["views"] = _num(r.get("views")) or 0
        for k in ("followers", "median"):
            r[k] = _num(r.get(k))
        r["account"] = str(r.get("account") or "")
        r["hook"] = str(r.get("hook") or "").strip()
        if r["views"] and r["hook"]:
            rows.append(r)
    return rows


def analyse(rows, formulas):
    used_median = any(r.get("median") for r in rows)
    for r in rows:
        base = r.get("median") or r.get("followers") or 0
        r["baseline"] = base
        r["outlier"] = round(r["views"] / base, 2) if base else None
        r["formula_id"], r["formula"] = classify(r["hook"], formulas)
        r["words"] = len(WORD_RE.findall(r["hook"]))
        if score_hook:
            _, overall, verdict, _ = score_hook(r["hook"])
            r["hook_score"], r["hook_verdict"] = round(overall, 1), verdict
        else:
            r["hook_score"], r["hook_verdict"] = None, None
    ranked = sorted(rows, key=lambda r: -(r["outlier"] or 0))
    third = max(1, len(ranked) // 3)
    top, bottom = ranked[:third], ranked[-third:]

    def med(items, key):
        vals = [i[key] for i in items if i.get(key) is not None]
        return round(statistics.median(vals), 1) if vals else None

    counts = {}
    for r in top:
        counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    return {
        "baseline": "медиана аккаунта" if used_median else "число подписчиков",
        "n": len(ranked),
        "accounts": len({r.get("account", "") for r in ranked}),
        "reels": ranked,
        "top_formulas": sorted(counts.items(), key=lambda kv: -kv[1]),
        "top_hook_score": med(top, "hook_score"),
        "bottom_hook_score": med(bottom, "hook_score"),
        "top_words": med(top, "words"),
        "bottom_words": med(bottom, "words"),
        "unclassified": sum(1 for r in ranked if r["formula"] == "без формулы"),
    }


def render(a, out=sys.stdout, limit=None):
    head = (f"СВАЙП-ФАЙЛ  ·  рилсов {a['n']}  ·  аккаунтов {a['accounts']}  ·  "
            f"база: {a['baseline']}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 78), file=out)
    for r in a["reels"][:limit] if limit else a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "   ?"
        score = f"{r['hook_score']:.0f}" if r["hook_score"] is not None else " -"
        fid = f"#{r['formula_id']:<2}" if r["formula_id"] else "-  "
        print(f"  {mult:>7}  хук {score:>3}  {fid} {r['formula'][:22]:<22} "
              f"{r.get('account', '')[:16]:<16} {r['views']:>11,}".replace(",", " "), file=out)
        print(f"           «{r['hook'][:96]}»", file=out)
    if limit and a["n"] > limit:
        print(f"  ... и ещё {a['n'] - limit} (все в --out или --json)", file=out)
    print("-" * max(len(head), 78), file=out)
    print("ЧТО РАБОТАЕТ В ЭТОЙ ПАЧКЕ", file=out)
    if a["top_formulas"]:
        print("  верхняя треть по множителю:  "
              + ", ".join(f"{n} x{c}" for n, c in a["top_formulas"][:4]), file=out)
    if a["top_hook_score"] is not None:
        print(f"  медиана оценки хука:         верх {a['top_hook_score']:.0f}  "
              f"против низа {a['bottom_hook_score']:.0f}", file=out)
    print(f"  медиана длины хука:          верх {a['top_words']} слов  "
          f"против низа {a['bottom_words']} слов", file=out)
    print(f"  без формулы:                 {a['unclassified']} из {a['n']}. Прочитай их руками, "
          "там прячется формула, которой у тебя ещё нет.", file=out)
    print("\n  Пачка, собранная руками, это улика, а не доказательство. Двенадцать рилсов "
          "не показывают ничего;\n  сорок на шести аккаунтах показывают кое-что. Собери "
          "больше, прежде чем верить.\n", file=out)


def to_markdown(a):
    lines = ["# Свайп-файл", "",
             f"Рилсов {a['n']} на {a['accounts']} аккаунтах. "
             f"Рейтинг по множителю над базой: {a['baseline']}.", ""]
    for r in a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "?"
        lines += [f"## {mult}  {r['formula']}  ({r.get('account', '')})",
                  f"- просмотры: {r['views']:,}  база: {r['baseline']:,}".replace(",", " "),
                  f"- оценка хука: {r['hook_score']}  слов: {r['words']}",
                  f"- хук: «{r['hook']}»", ""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Рейтинг собранных рилсов по множителю.")
    ap.add_argument("input", nargs="?", default="-", help="TSV или JSON, или - для stdin")
    ap.add_argument("--hooks", default=HOOKS, help="путь к ig-reel/hooks_ru.json")
    ap.add_argument("--out", help="ещё и записать свайп-файл в markdown сюда")
    ap.add_argument("--top", type=int, help="в выводе показать только первые N рилсов")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    rows = read_rows(args.input)
    if not rows:
        print("нет годных строк. Нужна таблица через табуляцию хотя бы с views и hook.",
              file=sys.stderr)
        sys.exit(2)
    formulas = load_formulas(args.hooks)
    a = analyse(rows, formulas)
    if not formulas:
        print("заметка: hooks_ru.json не найден, формулы не названы. Укажи --hooks.", file=sys.stderr)
    if score_hook is None:
        print("заметка: hookscore_ru.py не импортируется, оценки хуков пропущены.", file=sys.stderr)

    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a, limit=args.top)
    if args.out:
        path = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "w", encoding="utf-8").write(to_markdown(a))
        print(f"записано: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
