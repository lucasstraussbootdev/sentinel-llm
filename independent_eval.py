"""
Eval against independent_eval_set.jsonl -- an adversarial test set written by
a fresh subagent with no visibility into reference_bank.jsonl or
eval_set.jsonl, specifically so it isn't just an echo of the same author's
phrasing patterns and blind spots.

Runs the full hybrid pipeline (Pass 1 + Pass 2), since the point is testing
the whole system against unfamiliar attack styles, not just calibration.
"""
import json
from pathlib import Path

from sentinel import Sentinel

EVAL_PATH = Path(__file__).parent / "independent_eval_set.jsonl"


def main():
    sentinel = Sentinel()
    rows = [json.loads(l) for l in open(EVAL_PATH) if l.strip()]

    attack_rows = [r for r in rows if r["label"] == "attack"]
    benign_rows = [r for r in rows if r["label"] == "benign"]

    attack_correct = 0
    misses = []
    for row in attack_rows:
        result = sentinel.check(row["text"])
        correct = result.verdict == "attack"
        attack_correct += correct
        mark = "OK " if correct else "MISS"
        print(f"[{mark}] verdict={result.verdict:<9} (via {result.stage:<9}) {row['text'][:65]}")
        if not correct:
            misses.append((row["text"], row["note"]))

    print()
    benign_correct = 0
    for row in benign_rows:
        result = sentinel.check(row["text"])
        correct = result.verdict == "benign"
        benign_correct += correct
        mark = "OK " if correct else "MISS"
        print(f"[{mark}] verdict={result.verdict:<9} (via {result.stage:<9}) {row['text'][:65]}")
        if not correct:
            misses.append((row["text"], row["note"]))

    print()
    print(f"Independent attack recall: {attack_correct}/{len(attack_rows)} ({attack_correct/len(attack_rows):.0%})")
    print(f"Independent benign accuracy (1 - FPR): {benign_correct}/{len(benign_rows)} ({benign_correct/len(benign_rows):.0%})")

    if misses:
        print(f"\nMisses ({len(misses)}):")
        for text, note in misses:
            print(f"  - {text}")
            print(f"    ({note})")


if __name__ == "__main__":
    main()
