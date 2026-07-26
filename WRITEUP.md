# Sentinel: a hybrid prompt-injection detector, and what red-teaming it taught me

This pulls together everything in `FAILURE_ANALYSIS.md`, `INDEPENDENT_EVAL.md`,
`EMBEDDING_BACKEND_COMPARISON.md`, and `CONSTITUTIONAL_CLASSIFIERS_COMPARISON.md`
into one narrative. Those documents have the full detail and the raw numbers;
this is the story, in the order it actually happened, including the parts
that didn't work.

## Threat model

Sentinel screens a single text message — before it reaches an LLM
application's real model — for two kinds of attack:

- **Attacks on the underlying application**: prompt injection, jailbreak
  role-play, prompt/system-prompt extraction, obfuscated payloads,
  indirect injection via wrapped content. Each attack is tagged along two
  axes: *technique* (how it's delivered) and *goal* (what it's after —
  restricted info, unrestricted behavior, or the system's own
  configuration).
- **Attacks on the detector itself**: three of the five red-team scenarios
  in this project turned out to target Sentinel's own components (the
  embedding filter, the input judge, and — added later — the output
  judge) rather than the underlying application — an attack surface I
  didn't originally design for and only found by trying to break my own
  system.

Explicitly out of scope, stated up front rather than discovered late:
anything that isn't a plain text string handed to `Sentinel.check()`
(images, files, tool output). What the model says back is no longer
entirely out of scope — `output_judge.py` is now a tested, wired-in
component (`Sentinel.check_output()`, `output_eval_set.jsonl`,
`FAILURE_ANALYSIS.md` scenario 5) — but it only catches the specific
leak-shaped failures it was built to name (system-prompt leaks, visible
jailbreak compliance, detailed dangerous-content compliance). A model
quietly connecting dots it shouldn't in an otherwise unremarkable response
is still outside what any of this catches.

## Design

Two-stage pipeline, cheap-and-fast first, expensive-and-smart only when
needed:

```
message → normalize (decode obfuscation) → chunk (fight dilution)
        → embedding similarity vs. reference bank (Pass 1, free)
        → confident? return verdict
        → uncertain? → Claude judge, reasons about intent (Pass 2, paid)
```

- **Pass 1** (`embedding_filter.py`): cosine similarity against a
  15-example hand-written reference bank. Every candidate — the raw
  message, decoded variants, sentence-level chunks — gets scored, and the
  most attack-like result wins. Backend is pluggable (`encoders.py`): a
  free local model by default, or Voyage AI (see below). Session-aware:
  optional `history` gets scored through the same pipeline, so a
  confidently-benign current message only escalates to the judge if
  something earlier in the conversation actually scored attack-like —
  not just because history exists at all.
- **`normalize.py`**: decodes base64, ROT13, leetspeak, and Cyrillic
  homoglyphs before scoring, so an obfuscated attack can't hide by having
  its garbled form embed as benign.
- **`chunking.py`**: splits the message into sentence windows and scores
  each independently, so a short injected instruction can't be diluted by
  sitting next to eight paragraphs of benign text.
- **Pass 2** (`judge.py`): Claude (Haiku 4.5) reasons about intent vs.
  vocabulary for anything Pass 1 isn't confident about. This is where a
  security-researcher's question about prompt injection gets correctly
  separated from an actual prompt injection attempt.
- **`sentinel.py`**: `Sentinel` wires the two passes together, plus
  `check_output()` for the output side (see below). `ConversationSentinel`
  adds a rolling window of prior turns, passed to both Pass 1 and the
  judge as context, for attacks that only make sense across multiple
  messages.
- **`output_judge.py`**: same model, same structured-output pattern as
  Pass 2, opposite direction — classifies the model's own *response*,
  after the fact, for signs a leak or jailbreak compliance already
  happened. Exposed as `Sentinel.check_output()`. No Pass-1-equivalent
  cheap filter here: there's no reference bank of known leak *shapes* to
  embed a response against, so every call goes straight to the judge.

## Eval methodology — the part that actually matters most

The single biggest lesson of this project has nothing to do with model
architecture: **an eval set written by the same person who built the
detector measures how well the detector recognizes its own author's
assumptions, not how well it catches attacks.**

Early numbers looked clean: 100% recall across every attack category on
`eval_set.jsonl` (54 hand-written rows: known attacks, "novel" attacks,
obfuscated attacks, diluted injections, plus suspicious and boring benign
controls). Those numbers were real, and also close to worthless as a
claim about real-world performance, because I wrote the reference bank
*and* the eval set from the same mental model of what an attack looks
like.

The fix: had a fresh subagent — zero visibility into this project, no
access to the reference bank — write its own 20-row adversarial set from
scratch (`independent_eval_set.jsonl`). Result: **recall dropped from
100% to 50%.** Six real attack techniques (a "grandmother" emotional
jailbreak, markdown-image data exfiltration, an acrostic hiding a command
inside a poem, a restricted-content request disguised as a pytest
fixture, a translation-relay obfuscation, "opposite day" reverse
psychology) sailed through as confident `benign`, because none of them
resembled anything in a 15-example reference bank written by one person
imagining what attacks look like.

That 50% is the real number this project should be judged on, not the
100%. It's also the number that motivated the two concrete fixes below.

## Results

### Fixes with real, measured before/after numbers

| Fix | What it targets | Before → After |
|---|---|---|
| `normalize.py` (decode obfuscation) | base64/ROT13/leetspeak/homoglyph attacks | 0% → **100%** recall on `obfuscated_attack` |
| `chunking.py` (sentence windows) | short injections diluted in long messages | 0% → **100%** recall on `diluted_injection` (full pipeline) |
| Chunk window swept 2→1 | dilution fix, retuned | independent-set recall (full pipeline) **50% → 67%**, no FPR cost |
| History-aware short-circuit fix | Pass 1 skipping the judge even with conversation context | confirmed catch of an attack that scored confidently `benign` alone, correctly escalated once prior turns exist |
| Voyage AI embedding backend, properly calibrated | Pass 1 accuracy ceiling | independent-set recall **8% → 42%** (5x), independent FPR **12% → 0%** |
| Reference bank expanded 15→40, independently written | Pass 1 coverage | independent-set recall (local backend) **67% → 92%** (11/12), benign accuracy unchanged |
| Judge hardened against embedded instructions | prompt injection targeting the judge itself | scenario 4 at scale: **5/10 → 3/10** attacks succeed |

### Full hybrid pipeline (self-authored eval set, local backend)

100% recall across all four attack subtypes; the judge resolved 20/20
escalated ambiguous cases correctly. Two false positives remain — both
score confidently `attack` at Pass 1 and never reach the judge at all,
which is itself the finding: **the judge's accuracy doesn't help if Pass
1 is confident enough to skip it.**

### The Voyage AI investigation — a methodology story more than a model story

Anthropic doesn't have a first-party embedding model; Voyage AI is who
they recommend. Swapping it in surfaced three separate, real mistakes,
each caught by measuring rather than assuming:

1. Reusing the local model's similarity thresholds against Voyage's
   scores gave **~100% false positives** — different embedding models
   score on entirely different scales (a known effect, anisotropy), and
   nothing about that showed up until it was actually run.
2. "Correcting" the code to match Voyage's own documented best practice
   (asymmetric query/document encoding) made separation quality
   measurably *worse* (79% → 60% on a direct discriminability metric).
   The documented practice is built for short-question-vs-long-passage
   retrieval; this task is short-example-vs-short-example similarity — a
   different shape of comparison, and only testing it revealed that.
3. The first "final" threshold pair was four hand-picked candidates, not
   a real sweep. A proper grid search, explicitly optimizing to eliminate
   silent misses, found a clearly better pair.

After all three fixes, Voyage is close to a clean win — every
attack-recall metric improved or tied, independent-set recall 5x'd, FPR
on it dropped to zero — at the real cost of escalating more messages to
the paid judge (47% vs. 38%). I then chased the two remaining false
positives individually rather than stopping at the aggregate number: one
turned out to be a genuine, fixable bug in `chunking.py` (fixed for
free); the other is structurally a case only the judge's reasoning can
resolve, no matter how the embedding side is tuned. Full detail:
`EMBEDDING_BACKEND_COMPARISON.md`.

## Failure modes — red-teaming the pipeline against itself

Four scenarios, each targeting a specific architectural assumption
(`FAILURE_ANALYSIS.md` has the full writeup):

1. **Indirect injection via a wrapped document** — a short injected
   instruction inside a long "document to summarize" scored confidently
   `benign` and never reached the judge at all. Fixed by chunking.
2. **Split payload across two messages** — neither message alone looks
   like an attack; the pair does. Fixed via `ConversationSentinel`,
   validated live: the judge correctly used turn-1 context to read
   turn-2's ask as extraction.
3. **Multi-turn trust-building escalation** — same mechanism, same fix,
   same live validation.
4. **Prompt injection against the judge itself** — the most important
   negative result in this project, and the one with the clearest
   before/after. A single resisted attempt initially looked like a good
   sign; testing 10 distinct framings at scale found **5 of 10 succeeded**
   (3 never reached the judge at all via Pass 1's own confident-benign
   zone, 2 fooled the judge directly by spoofing its expected output
   format or a fake authority tag). The fix — an explicit instruction
   naming fabricated-approval claims, output-format spoofing, and fake
   system-note tags as attack signals — was added and the identical 10
   framings re-run: **5/10 → 3/10**, with both judge-fooling cases now
   resisted and nothing else changed. The remaining 3/10 are the separate
   Pass-1 short-circuit problem, untouched by this fix since those never
   reach the judge. Honest caveat: this is evidence against the specific
   attack shapes tested, not proof of immunity to prompt injection in
   general — a genuinely novel eleventh framing is untested.

## Comparison to Anthropic's Constitutional Classifiers

Written after this project's design and failure analysis were mostly
locked in, specifically to compare independently-made choices against the
published approach rather than reverse-engineer this project to match it.
Converges on: synthetic/generated training data over scraped examples,
treating false-positive rate as a first-class metric rather than a
footnote. Diverges on: a single general-purpose judge vs. dual
purpose-trained input *and* output classifiers (this is the direct
architectural reason scenario 4 exists — a system-prompted judge inherits
some of the manipulability of the model class it's built from, in a way a
classifier trained specifically to resist that wouldn't), a broad
"detect attacks in general" scope vs. a narrower "universal jailbreaks"
target, and validation scale (one person, one afternoon, vs. 183
red-teamers and 3,000+ hours). Full comparison in
`CONSTITUTIONAL_CLASSIFIERS_COMPARISON.md`.

## What I'd do with more time or compute

This list was originally five items. Four are done:

- **Harden the judge, re-run scenario 4** — see the failure modes section
  above for the real 5/10 → 3/10 result.
- **A genuinely larger and more diverse reference bank**, built the same
  way the independent eval set was — a fresh subagent with zero visibility
  into this project, writing 25 new attack examples independently.
  Reference bank grew 15→40; independent-set recall **67% → 92%**. The one
  remaining miss (an acrostic hiding a command inside a poem) stumped the
  judge too, not just Pass 1 — a genuinely hard structural case, not a
  reference-bank coverage gap. Full detail in `INDEPENDENT_EVAL.md`.
- **Session-aware Pass 1.** `embedding_filter.py`'s `check()` now takes
  `history` and scores prior turns through the same normalize/chunk
  pipeline as the current message. This replaced a blunter rule (any
  history at all forced a judge call, even for an obviously benign
  multi-turn conversation) with a real one: a confidently-benign current
  message only escalates if something *in that history* actually scored
  attack-like. Verified live: a genuinely benign three-turn conversation
  now resolves at Pass 1 on turns after the first (previously impossible
  under the old rule), while `FAILURE_ANALYSIS.md` scenarios 2/3 still
  correctly escalate and get caught by the judge, unchanged.
- **Real output-side coverage.** `output_judge.py` now has a 24-row eval
  set (`output_eval_set.jsonl`), is wired into `Sentinel.check_output()`,
  and has been red-teamed (`FAILURE_ANALYSIS.md` scenario 5). Eval result:
  100% recall across all three leak categories, 0% false positives across
  all three clean categories — but read that with the same caveat
  `INDEPENDENT_EVAL.md` already taught this project once: it's a
  self-authored, 24-row eval set, the same size and provenance
  `eval_set.jsonl` had before a blind version cut its recall in half.
  There is no blind independent output-side eval set yet — that's the
  most valuable next step for this specific piece, not a victory lap. The
  red-team pass is a more honest signal than the eval set: of three
  attempts to hide a real leak behind safe-sounding framing, the
  unhardened judge was fooled by all three; after adding an explicit
  "framing doesn't neutralize content" defense, one is now caught, one
  remains (a genuinely hard case — a real refusal stance sitting right
  next to the actual leaked text — not a one-line prompt-engineering miss)
  and zero new false positives were introduced fixing it.

One item remains:

1. **Production concerns not addressed anywhere in this project**: rate
   limiting, cost monitoring at scale, drift detection as attackers adapt
   over time, actual enforcement (this project produces verdicts, not
   blocks).

None of this is a request for more scope for its own sake — each item
above is the next question this project's own evidence points at, not a
generic "future work" list.
