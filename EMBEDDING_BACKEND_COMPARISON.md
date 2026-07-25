# Embedding backend comparison: local model vs. Voyage AI

Anthropic doesn't offer its own embedding model — their docs explicitly
recommend Voyage AI, with `voyage-4` as the current balanced/recommended
model. This compares that against the project's original backend
(`all-MiniLM-L6-v2`, running locally via `sentence_transformers`, free).

## A bug caught before the comparison meant anything

The first run used the local model's thresholds (`attack_threshold=0.5`,
`benign_threshold=0.25`) against Voyage's scores and got ~100% false
positives — every benign message flagged as an attack. That was not a
Voyage weakness, it was an invalid comparison: **embedding models have
different baseline similarity distributions** (a known effect called
anisotropy). Voyage's raw cosine score for "What's a good recipe for
banana bread?" against the attack reference bank is 0.483; the local
model's score for the same message is 0.094. Same message, same reference
bank, systematically different scale. Reusing one model's thresholds on
another's score distribution is an apples-to-oranges error, caught here by
noticing a 100% FPR is implausible on its face rather than reporting it as
a finding about Voyage.

Fix: calibrated Voyage's own thresholds from its own score distribution
(`attack_t=0.75`, `benign_t=0.55` — chosen so zero known attacks fall
below `benign_t`, checked against `eval_set.jsonl`), the same way the
local model's 0.5/0.25 was originally chosen. See
`embedding_backend_comparison.py`.

## Results (Pass 1 only, both eval sets, each backend at its own calibrated thresholds)

| | Local (free) | Voyage (`voyage-4`) |
|---|---|---|
| `known_attack` recall | 90% | 90% |
| `novel_attack` recall | 30% | 40% |
| `obfuscated_attack` recall | **100%** | 83% |
| `diluted_injection` recall | 67% | 67% |
| `benign_suspicious` FPR | 17% | **8%** |
| `benign_boring` FPR | 0% | 0% |
| **Independent eval set — attack recall** | 8% | **17%** |
| **Independent eval set — benign FPR** | 12% | **0%** |
| Overall escalation rate to Pass 2 (judge) | 35% (19/54) | 46% (25/54) |

## Honest read

Voyage is better where it matters most — the independent (harder, more
honest) eval set shows both higher recall and zero false positives — but
it's not a clean win. `obfuscated_attack` recall actually regressed (100%
→ 83%); the decode/normalize variants that make leetspeak/ROT13/homoglyph
attacks recognizable to the local model don't transfer as cleanly to
Voyage's embedding space, and this wasn't investigated further.

The bigger practical point: **Voyage escalates more to the judge (46% vs
35%).** Its own thresholds were calibrated to avoid hard misses, which
pushed more of the middle ground into "uncertain" rather than confidently
resolving it either way. That means the real cost of switching isn't just
Voyage's own (small, likely-free-tier) API cost — it's also more Claude
judge calls, which do cost money per call. Better precision at the
boundary, paid for partly in more paid judge calls, not just Voyage's own
bill.

## What this is NOT a test of

This is Pass 1 in isolation, not the full hybrid pipeline — a fair
follow-up would be `hybrid_eval.py` with each backend, measuring end-to-end
accuracy and total cost (Voyage tokens + judge calls) together, not
Pass 1's accuracy alone. Not done here.

## Recommendation

The local model stays the default in this repo — it's what's tested most
extensively throughout this project, it's genuinely free at any volume,
and the Voyage improvement, while real, isn't dramatic enough to call the
free option broken. `encoders.py` makes Voyage a one-line swap
(`EmbeddingFilter(encoder=VoyageEncoder())`) for anyone who wants the
modest recall/FPR improvement and is fine with the added judge-escalation
cost.
