"""
A/B comparison: LocalEncoder (free, sentence-transformers) vs. VoyageEncoder
(Anthropic's recommended embeddings provider) as the Pass-1 backend.

Pass 1 only -- deliberately excludes the judge, to isolate the effect of
embedding quality specifically rather than measuring the whole pipeline.
Scored against BOTH eval_set.jsonl (self-authored) and
independent_eval_set.jsonl (blind subagent), same principle as
threshold_sweep.py: a backend that only helps on the self-authored set
isn't real progress.

Reports whichever result actually comes out -- this project's whole
methodology has been measuring instead of assuming, and "the paid,
Anthropic-recommended option is obviously better" is exactly the kind of
claim that should be checked, not assumed.

IMPORTANT: attack_threshold/benign_threshold are NOT portable across
embedding models. Different models produce different baseline similarity
distributions (a known phenomenon -- embedding anisotropy) -- Voyage's raw
cosine scores run systematically higher than the local model's even for
totally unrelated text (0.48 for "what's a good recipe for banana bread"
vs. 0.09 locally). Reusing the local model's thresholds (0.5/0.25) against
Voyage's score distribution produced ~100% false-positive rates -- not a
Voyage weakness, an apples-to-oranges bug in the comparison. Each backend
below is scored at thresholds separately calibrated for its own score
distribution.
"""
import json
from collections import defaultdict
from pathlib import Path

from embedding_filter import EmbeddingFilter
from encoders import LocalEncoder, VoyageEncoder

EVAL_PATH = Path(__file__).parent / "eval_set.jsonl"
INDEPENDENT_PATH = Path(__file__).parent / "independent_eval_set.jsonl"


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def score_set(filt, rows, group_key):
    """Run every row through the filter, bucket by group_key, return per-group recall/FPR."""
    stats = defaultdict(lambda: defaultdict(int))
    for row in rows:
        result = filt.check(row["text"])
        key = row[group_key]
        stats[key]["total"] += 1
        stats[key][result.verdict] += 1
    return stats


def print_eval_set_results(name, stats, attack_subtypes):
    print(f"\n  {name}:")
    for subtype, s in stats.items():
        total = s["total"]
        is_attack = subtype in attack_subtypes
        rate = s["attack"] / total
        label = f"recall={rate:.0%}" if is_attack else f"FPR={rate:.0%}"
        print(f"    {subtype:<20} n={total:<3} attack={s['attack']:<3} uncertain={s['uncertain']:<3} benign={s['benign']:<3}  {label}")


def main():
    eval_rows = load(EVAL_PATH)
    independent_rows = load(INDEPENDENT_PATH)
    attack_subtypes = {"known_attack", "novel_attack", "obfuscated_attack", "diluted_injection"}

    backends = [
        ("LocalEncoder (free, all-MiniLM-L6-v2)", LocalEncoder(), 0.5, 0.25),
        ("VoyageEncoder (voyage-4)", VoyageEncoder(), 0.70, 0.45),
    ]
    for backend_name, encoder, attack_t, benign_t in backends:
        print(f"\n{'=' * 70}\n{backend_name}  (attack_t={attack_t}, benign_t={benign_t})\n{'=' * 70}")
        filt = EmbeddingFilter(encoder=encoder, attack_threshold=attack_t, benign_threshold=benign_t)

        eval_stats = score_set(filt, eval_rows, "subtype")
        print_eval_set_results("eval_set.jsonl (self-authored)", eval_stats, attack_subtypes)

        indep_attack = [r for r in independent_rows if r["label"] == "attack"]
        indep_benign = [r for r in independent_rows if r["label"] == "benign"]
        indep_recall = sum(1 for r in indep_attack if filt.check(r["text"]).verdict == "attack") / len(indep_attack)
        indep_fpr = sum(1 for r in indep_benign if filt.check(r["text"]).verdict == "attack") / len(indep_benign)
        print(f"\n  independent_eval_set.jsonl (blind subagent):")
        print(f"    attack recall={indep_recall:.0%}  benign FPR={indep_fpr:.0%}")


if __name__ == "__main__":
    main()
