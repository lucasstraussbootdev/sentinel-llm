# Comparing Sentinel to Constitutional Classifiers

Written after Sentinel's design and failure analysis were mostly locked in,
deliberately — the point is to compare independently-arrived-at choices
against Anthropic's published approach, not to reverse-engineer Sentinel to
match it. Source: Anthropic's "Constitutional Classifiers" research post.
Numbers below are as reported there; I have not independently verified them.

## What Constitutional Classifiers do, briefly

Start from a **constitution** — a written list of what content classes are
allowed/disallowed. Use Claude to generate synthetic prompts and completions
across those classes, augmented with translations and known jailbreak
styles, plus benign queries to control false positives. Train **two**
classifiers on that data: one screens incoming prompts, one screens model
outputs, both enforcing the same constitution. Targets **universal
jailbreaks** specifically — one attack method that works across many
harmful queries — not attacks in general. Reported results: 183 red-teamers,
3,000+ hours, zero universal jailbreaks found against the prototype;
automated jailbreak success dropped 86% → 4.4%; harmless-query refusal rate
rose only 0.38%; ~24% compute overhead.

## Where Sentinel converges

- **Synthetic/generated training data over hand-labeled scraping.**
  Sentinel's `reference_bank.jsonl` and `eval_set.jsonl` are both
  hand-written rather than scraped from real incidents — closer in spirit
  to CC's synthetic generation than to a found dataset, for the same
  reason: you want coverage of attack *categories*, not just examples that
  happen to exist.
- **Separating false-positive cost from recall as a first-class metric.**
  CC reports over-refusal (0.38%) as a headline number, not a footnote.
  `eval.py` does the same — FPR per subtype is reported alongside recall,
  not blended into one accuracy figure, specifically so a filter that's
  great at recall but hostile to security researchers and novelists
  doesn't look good on paper.
- **A cheap-fast-stage-first structure.** CC screens both directions with
  a purpose-built classifier before/around the main model call; Sentinel
  screens with a cheap embedding pass before a Claude call. Different
  granularity, same instinct: don't pay full LLM cost on every message if
  you don't have to.

## Where Sentinel diverges, and why

- **One judge, not two classifiers.** CC has a dedicated *output*
  classifier as well as an input one. Sentinel has no output-side coverage
  at all — flagged explicitly in `FAILURE_ANALYSIS.md`'s scope-limits
  section. This isn't a design disagreement, it's scale: CC trains
  purpose-built classifiers on generated data at a scope this project
  doesn't have the infrastructure for. Given the resources, I'd want
  output coverage before anything else on this list — a judge that only
  ever looks at the user's message can't catch a model that leaks
  something through its own inference, no matter how good the input side
  gets.
- **General attack detection, not universal-jailbreak-specific.** CC
  explicitly scopes to universal jailbreaks — a narrower, harder-to-defend
  target chosen because it's the highest-leverage attack class in
  production. Sentinel's taxonomy (`prompt_injection`, `role_play`,
  `prompt_extraction`, `indirect_injection`, ...) doesn't distinguish
  "reusable across many harmful queries" from "one-off" at all. Given
  Sentinel's failure analysis, this seems like the right lesson to borrow:
  a narrower, explicit threat model would have made scenario 1 and
  scenario 4 easier to reason about, instead of discovering after the
  fact that "attack targets the classifier, not just the model" wasn't in
  the taxonomy anywhere.
- **A general-purpose model as the judge, not a purpose-trained
  classifier.** `judge.py` asks Claude, via a system prompt, to classify —
  it isn't a model trained on constitution-derived synthetic data the way
  CC's classifiers are. This is the direct cause of scenario 4
  (prompt-injection-against-the-judge): a general instruction-following
  model reading untrusted text inside its own prompt has to resist
  manipulation via its general instruction-following behavior, which is
  a weaker guarantee than a classifier trained specifically not to have
  that behavior. CC's approach is architecturally immune to this exact
  failure mode in a way a system-prompted judge is not.
- **Scale of adversarial validation.** CC: 183 people, 3,000+ hours.
  Sentinel: one developer, four scenarios, an afternoon. This isn't a
  design choice to defend, it's the honest gap between a research project
  and a portfolio project — worth stating plainly rather than implying
  Sentinel's failure analysis is comparably rigorous.

## What I'd take from this if I kept building

Output-side coverage first (closes the biggest scope gap), then narrowing
the threat model to something specific enough to red-team exhaustively
rather than "attacks in general" (closes the taxonomy gap CC's narrower
scoping avoids), then — only after both of those — moving off a
system-prompted judge toward something trained specifically to resist
prompt injection in its own input, which is the one gap here that a bigger
compute budget alone doesn't fix.
