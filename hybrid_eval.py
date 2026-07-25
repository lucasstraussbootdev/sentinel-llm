"""
Eval harness for the full hybrid pipeline (Pass 1 + Pass 2).

eval.py only ever scored EmbeddingFilter in isolation -- useful for tuning
Pass 1, but it can't answer the actual question this project is about: what
does the *hybrid* detector's real precision/recall look like once the judge
resolves Pass 1's "uncertain" cases? That requires live API calls, which is
why this has been a separate, unrun script until credits were available.

Reports the same per-subtype recall/FPR as eval.py, but on Sentinel's final
verdict rather than EmbeddingFilter's. Also reports judge-specific stats:
of the cases Pass 1 escalated, how many did the judge get right.
"""
import json
from collections import defaultdict
from pathlib import Path

from eval import ATTACK_SUBTYPES, SUBTYPES, load_eval_set
from sentinel import Sentinel

EVAL_PATH = Path(__file__).parent / "eval_set.jsonl"


def main():
    sentinel = Sentinel()
    rows = load_eval_set(EVAL_PATH)

    stats = defaultdict(lambda: defaultdict(int))
    misses = []
    judge_calls = []  # (text, label, subtype, judge_verdict, judge_confidence, correct)

    for row in rows:
        result = sentinel.check(row["text"])
        subtype = row["subtype"]
        stats[subtype]["total"] += 1
        stats[subtype][result.verdict] += 1

        is_attack_subtype = row["label"] == "attack"
        wrong = (
            (is_attack_subtype and result.verdict == "benign")
            or (not is_attack_subtype and result.verdict == "attack")
        )
        if wrong:
            misses.append((row["text"], row["label"], result.verdict, result.stage))

        if result.stage == "judge":
            correct = (result.verdict == "attack") == is_attack_subtype
            judge_calls.append((row["text"], row["label"], subtype, result.verdict, result.detail.confidence, correct))

    print(f"{'subtype':<20} {'n':>4} {'attack':>8} {'benign':>8}   rate")
    print("-" * 60)
    for subtype in SUBTYPES:
        s = stats[subtype]
        total = s["total"]
        if total == 0:
            continue
        is_attack_subtype = subtype in ATTACK_SUBTYPES
        rate_label = f"recall={s['attack']/total:.0%}" if is_attack_subtype else f"FPR={s['attack']/total:.0%}"
        print(f"{subtype:<20} {total:>4} {s['attack']:>8} {s['benign']:>8}   {rate_label}")

    print()
    if misses:
        print(f"Hard misses (hybrid pipeline wrong, end to end): {len(misses)}")
        for text, label, verdict, stage in misses:
            print(f"  [{label} -> {verdict}, decided by {stage}] {text[:70]}")
    else:
        print("No hard misses -- the hybrid pipeline got every row right.")

    print()
    n_correct = sum(1 for c in judge_calls if c[5])
    print(f"Judge resolved {len(judge_calls)} escalated cases, {n_correct} correctly ({n_correct/len(judge_calls):.0%} if any)" if judge_calls else "Judge was never escalated to.")
    for text, label, subtype, verdict, confidence, correct in judge_calls:
        mark = "OK " if correct else "ERR"
        print(f"  [{mark}] truth={label:<7} judge={verdict:<7} conf={confidence:<6} ({subtype}) {text[:60]}")


if __name__ == "__main__":
    main()
