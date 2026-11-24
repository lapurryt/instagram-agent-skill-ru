# Calibration of hookscore_ru (2026-11-13)

## Data

- **Niche hooks:** 68 Russian hooks from 9 Russian accounts in the 2026-11-13 niche swipe. These are reels older than 3 days. The hook is the first spoken sentence, transcribed by Whisper. The swipe itself is not part of the repo.
- **The author's hooks:** 8 spoken hooks from his latest reels. City reels have no voice, so they are left out.
- **Target:** views ÷ the account's own median views (the outlier multiple).
- **Test:** AUC of the top third against the bottom third by multiple (0.5 = coin flip), and Spearman correlation over all hooks.

## Results

| | AUC top vs bottom | Spearman |
|---|---|---|
| English `hookscore.py` on translations of the author's 18 hooks | 0.51 | −0.01 |
| **`hookscore_ru` overall** | **0.63** | **+0.16** |
| ВЫГОДА (viewer's personal gain) | 0.62 | +0.18 |
| ЗРИТЕЛЬ (addresses «ты») | 0.51 | +0.03 |
| НАЧАЛО (payload up front, no warm-up) | 0.48 | −0.03 |
| КОНКРЕТИКА (numbers, names) | 0.48 | −0.05 |
| ДЛИНА | 0.46 | −0.11 |
| СТАВКА | 0.39 | −0.16 |

- **Anti-formulas** (СТОП flags) appeared in 0 of 25 top-third hooks and in 5 of 25 bottom-third hooks.
- **Author only** (n=8): Spearman of the overall score is +0.45. The sample is too small to claim anything.

## What this means

- **It is a filter, not a predictor.** It reliably catches the anti-formulas and the hooks that promise the viewer nothing. It does not pick the winner between two decent hooks.
- **Gain matters, grammar doesn't.** Only ВЫГОДА carries signal: the viewer has to understand what he gets. Length, stakes words and numbers do not separate hits from flops here; stakes even leans the wrong way. The checks are kept because they catch broken hooks (a 20-word first sentence, no payload), and ВЫГОДА has the highest weight (1.6).
- **Re-run this after the next niche swipe**, about monthly. To rebuild it: load `viral_rows.json`, take the first sentence of `first45`, and score each with `hookscore_ru.run()`.
