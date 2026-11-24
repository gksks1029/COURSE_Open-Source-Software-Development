"""Render the submitted real replica CSV without contacting Kubernetes."""
import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
directory = root / "results/submitted/autoscaling"
source = directory / "replicas.csv"
with source.open() as stream:
    rows = list(csv.DictReader(stream))
if not rows:
    raise SystemExit("Replica CSV is empty")

timezone = ZoneInfo("Asia/Taipei")
times = [datetime.fromisoformat(row["timestamp"]).astimezone(timezone) for row in rows]
ready = [int(row["ready"]) for row in rows]
desired = [int(row["desired"]) for row in rows]
load_start = next(time for row, time in zip(rows, times) if row["phase"] == "load")
load_end = next(time for row, time in zip(rows, times) if row["phase"] == "cooldown")

figure, axis = plt.subplots(figsize=(10, 4.8))
figure.subplots_adjust(left=.08, right=.98, top=.88, bottom=.23)
axis.axvspan(load_start, load_end, color="#ffda79", alpha=.35, label="Load phase (sampled boundaries)")
axis.step(times, desired, where="post", color="#d35400", linestyle="--", label="Desired replicas")
axis.step(times, ready, where="post", color="#1565c0", linewidth=2.2, label="Ready replicas")
axis.set(title="KServe Iris autoscaling: 1 → 3 → 1", ylabel="Replicas",
         xlabel="Time, Asia/Taipei (UTC+08:00)", ylim=(0, 3.6))
axis.set_yticks([0, 1, 2, 3])
axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone))
axis.grid(axis="y", alpha=.25)
axis.legend(loc="lower right", fontsize=9)
figure.text(.01, .025, "Source: submitted autoscaling/replicas.csv. Derived chart; not a live terminal screenshot.", fontsize=8, color="#555555")
target = directory / "replicas.png"
figure.savefig(target, dpi=160, bbox_inches="tight")
plt.close(figure)
print(target)
