"""
Eval harness for the embedding filter.

Runs eval_set.jsonl (held out -- never used as reference data) through
EmbeddingFilter and reports, per subtype:
  - attack subtypes (known_attack, novel_attack): recall = caught as "attack" directly
  - benign subtypes (benign_suspicious, benign_boring): false positive rate =
    wrongly flagged as "attack"
  - uncertain rate: fraction routed to the (not-yet-built) Pass-2 judge

"uncertain" is not scored as wrong -- it's a deliberate escalation, not a
mistake. The point of this harness is to see how much load a judge would
carry, and whether that load falls where it should (mostly on novel_attack
and benign_suspicious, the hard cases) rather than on the easy ones.
"""
import json
from collections import defaultdict
from pathlib import Path

from embedding_filter import EmbeddingFilter

EVAL_PATH = Path(__file__).parent / "eval_set.jsonl"


def load_eval_set(path: Path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    filt = EmbeddingFilter()
    rows = load_eval_set(EVAL_PATH)

    # subtype -> {"attack": n, "benign": n, "uncertain": n, "total": n}
    stats = defaultdict(lambda: defaultdict(int))
    misses = []

    for row in rows:
        result = filt.check(row["text"])
        subtype = row["subtype"]
        stats[subtype]["total"] += 1
        stats[subtype][result.verdict] += 1

        is_attack_subtype = row["label"] == "attack"
        wrong = (
            (is_attack_subtype and result.verdict == "benign")
            or (not is_attack_subtype and result.verdict == "attack")
        )
        if wrong:
            misses.append((row["text"], row["label"], result.verdict, result.score))

    print(f"{'subtype':<20} {'n':>4} {'attack':>8} {'uncertain':>10} {'benign':>8}   rate")
    print("-" * 70)
    for subtype in ["known_attack", "novel_attack", "benign_suspicious", "benign_boring"]:
        s = stats[subtype]
        total = s["total"]
        if total == 0:
            continue
        is_attack_subtype = subtype in ("known_attack", "novel_attack")
        if is_attack_subtype:
            rate_label = f"recall={s['attack']/total:.0%}"
        else:
            rate_label = f"FPR={s['attack']/total:.0%}"
        print(f"{subtype:<20} {total:>4} {s['attack']:>8} {s['uncertain']:>10} {s['benign']:>8}   {rate_label}")

    print()
    if misses:
        print(f"Hard misses (wrong verdict, not just 'uncertain'): {len(misses)}")
        for text, label, verdict, score in misses:
            print(f"  [{label} -> {verdict}, score={score:.3f}] {text}")
    else:
        print("No hard misses (everything wrong at worst landed in 'uncertain').")


if __name__ == "__main__":
    main()
