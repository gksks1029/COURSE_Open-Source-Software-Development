"""Display representative rows from an actual autoscaling run for a screenshot."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results/autoscaling")
    parser.add_argument("--run", type=Path, help="Explicit run directory; defaults to the latest completed run")
    args = parser.parse_args()
    candidates = list(args.results_dir.glob("*/summary.json")) if args.run is None else [args.run / "summary.json"]
    if not candidates:
        parser.error("No completed autoscaling run found")
    summary_path = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    summary = json.loads(summary_path.read_text())
    with (summary_path.parent / "replicas.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    phases = {phase: [row for row in rows if row["phase"] == phase]
              for phase in ("baseline", "load", "cooldown")}
    if any(not group for group in phases.values()):
        parser.error("CSV must contain baseline, load, and cooldown samples")
    chosen = [phases["baseline"][0], phases["load"][0],
              max(phases["load"], key=lambda row: int(row["ready"])),
              phases["cooldown"][0], phases["cooldown"][-1]]
    start = datetime.fromisoformat(rows[0]["timestamp"])
    print("KServe Autoscaling - actual recorded samples")
    print("Source:", summary_path.parent)
    print("Revision:", summary["revision"])
    print(f"{'Elapsed(s)':>10}  {'Phase':<10} {'Desired':>7} {'Ready':>7} {'KPA desired':>11} {'KPA actual':>10}")
    for row in chosen:
        elapsed = (datetime.fromisoformat(row["timestamp"]) - start).total_seconds()
        print(f"{elapsed:10.1f}  {row['phase']:<10} {row['desired']:>7} {row['ready']:>7} {row['kpa_desired']:>11} {row['kpa_actual']:>10}")
    print("Peak ready during load:", summary["peak_ready_during_load"])
    print("Final ready replicas:", summary["final"]["ready"])
    print("Requests:", summary["requests"], " Failed:", summary["failed"])
    print("Result:", "PASS" if summary["passed"] else "FAIL")


if __name__ == "__main__":
    main()
