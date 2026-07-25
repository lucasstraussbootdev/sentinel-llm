"""
Sweep attack_threshold/benign_threshold and chunking window size, instead of
the single hand-picked operating point (0.5/0.25, window=2) used everywhere
else in this project.

Scores against BOTH eval sets on purpose: eval_set.jsonl (self-authored,
optimistic) and independent_eval_set.jsonl (blind subagent, the harder and
more honest test -- see INDEPENDENT_EVAL.md). A threshold change that helps
the self-authored set but not the independent one isn't really progress,
it's overfitting to the same blind spots that produced the reference bank.

Pass 1 only -- no API calls, so this is cheap enough to run a real grid
instead of eyeballing one point.
"""
import json
from pathlib import Path

from embedding_filter import EmbeddingFilter

EVAL_PATH = Path(__file__).parent / "eval_set.jsonl"
INDEPENDENT_PATH = Path(__file__).parent / "independent_eval_set.jsonl"


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def score_all(filt, rows):
    """Run each row's text through the filter once, return (label, score) pairs."""
    return [(row["label"], filt.check(row["text"]).score) for row in rows]


def metrics_at_threshold(scored, attack_threshold, benign_threshold):
    attack_rows = [s for label, s in scored if label == "attack"]
    benign_rows = [s for label, s in scored if label == "benign"]

    recall = sum(1 for s in attack_rows if s >= attack_threshold) / len(attack_rows) if attack_rows else float("nan")
    fpr = sum(1 for s in benign_rows if s >= attack_threshold) / len(benign_rows) if benign_rows else float("nan")
    # "resolved wrong" ignores threshold entirely, or rather: anything not
    # caught as attack here either escalates (uncertain) or is a hard miss
    # (scored <= benign_threshold while actually an attack)
    hard_miss = sum(1 for s in attack_rows if s <= benign_threshold)
    return recall, fpr, hard_miss


def sweep_thresholds():
    filt = EmbeddingFilter()  # default window=2, chunking on -- only the thresholds vary below
    eval_scored = score_all(filt, load(EVAL_PATH))
    indep_scored = score_all(filt, load(INDEPENDENT_PATH))

    attack_thresholds = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    benign_thresholds = [0.10, 0.15, 0.20, 0.25, 0.30]

    print(f"{'attack_t':>9} {'benign_t':>9}   {'self recall':>12} {'self FPR':>9}   {'indep recall':>13} {'indep FPR':>10}")
    print("-" * 80)
    for at in attack_thresholds:
        for bt in benign_thresholds:
            if at <= bt:
                continue
            self_recall, self_fpr, _ = metrics_at_threshold(eval_scored, at, bt)
            indep_recall, indep_fpr, _ = metrics_at_threshold(indep_scored, at, bt)
            print(f"{at:>9.2f} {bt:>9.2f}   {self_recall:>11.0%} {self_fpr:>8.0%}   {indep_recall:>12.0%} {indep_fpr:>9.0%}")


def sweep_window():
    print("\n\nchunk_window sweep (thresholds fixed at defaults: attack=0.5, benign=0.25)")
    print(f"{'window':>6}   {'diluted_injection recall':>25} {'self FPR (benign_suspicious)':>29} {'indep recall':>13} {'indep FPR':>10}")
    print("-" * 90)

    eval_rows = load(EVAL_PATH)
    indep_rows = load(INDEPENDENT_PATH)
    diluted_rows = [r for r in eval_rows if r["subtype"] == "diluted_injection"]
    suspicious_rows = [r for r in eval_rows if r["subtype"] == "benign_suspicious"]

    for window in [1, 2, 3, 4]:
        filt = EmbeddingFilter(chunk_window=window)

        diluted_recall = sum(1 for r in diluted_rows if filt.check(r["text"]).verdict == "attack") / len(diluted_rows)
        suspicious_fpr = sum(1 for r in suspicious_rows if filt.check(r["text"]).verdict == "attack") / len(suspicious_rows)

        indep_scored = score_all(filt, indep_rows)
        indep_recall, indep_fpr, _ = metrics_at_threshold(indep_scored, 0.5, 0.25)

        print(f"{window:>6}   {diluted_recall:>24.0%} {suspicious_fpr:>28.0%} {indep_recall:>13.0%} {indep_fpr:>10.0%}")


if __name__ == "__main__":
    sweep_thresholds()
    sweep_window()
