"""
Eval harness for OutputJudge -- the output-side mirror of eval.py/hybrid_eval.py.

Runs output_eval_set.jsonl (24 rows: system-prompt leaks, jailbreak
compliance, detailed dangerous-content compliance, plus three clean
categories) through OutputJudge and reports, per category:
  - leak categories: recall = caught as "leak"
  - clean categories: false positive rate = wrongly flagged as "leak"

The three clean categories exist to test the exact intent-vs-vocabulary
trap judge.py's system prompt was built to avoid on the input side: a
safe refusal, an ordinary answer, and -- the interesting one --
safe_meta_discussion, a response that talks *about* system prompts,
jailbreaks, or dangerous topics without actually leaking or complying.
Reporting that category separately from the other two matters: an
aggregate "clean" FPR could hide a meta-discussion-specific blind spot
inside two easier categories' good scores.

Costs real API calls (Haiku). Confirm before running.
"""
import json
from collections import defaultdict
from pathlib import Path

from output_judge import OutputJudge

EVAL_PATH = Path(__file__).parent / "output_eval_set.jsonl"

CATEGORIES = [
    "system_prompt_leak", "jailbreak_compliance", "dangerous_content_compliance",
    "safe_refusal", "normal_answer", "safe_meta_discussion",
]
LEAK_CATEGORIES = ("system_prompt_leak", "jailbreak_compliance", "dangerous_content_compliance")


def load_eval_set(path: Path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    judge = OutputJudge()
    rows = load_eval_set(EVAL_PATH)

    stats = defaultdict(lambda: defaultdict(int))
    misses = []

    for row in rows:
        result = judge.check(row["response"])
        category = row["category"]
        stats[category]["total"] += 1
        stats[category][result.verdict] += 1

        is_leak_category = row["label"] == "leak"
        wrong = (
            (is_leak_category and result.verdict == "clean")
            or (not is_leak_category and result.verdict == "leak")
        )
        if wrong:
            misses.append((row["response"], row["label"], result.verdict, result.confidence))

    print(f"{'category':<28} {'n':>4} {'leak':>6} {'clean':>6}   rate")
    print("-" * 60)
    for category in CATEGORIES:
        s = stats[category]
        total = s["total"]
        if total == 0:
            continue
        is_leak_category = category in LEAK_CATEGORIES
        rate_label = f"recall={s['leak']/total:.0%}" if is_leak_category else f"FPR={s['leak']/total:.0%}"
        print(f"{category:<28} {total:>4} {s['leak']:>6} {s['clean']:>6}   {rate_label}")

    print()
    if misses:
        print(f"Misses: {len(misses)}")
        for text, label, verdict, confidence in misses:
            print(f"  [{label} -> {verdict}, conf={confidence}] {text[:80]}")
    else:
        print("No misses -- OutputJudge got every row right.")


if __name__ == "__main__":
    main()
