"""
Stitches the per-contract files into one continuous near-month series:
for each trading day, use the nearest-month contract that traded that day.
Output: data/NIFTY_FUT_continuous_1min.csv  (this is the file to upload for backtests)
"""
import re
from pathlib import Path
import pandas as pd

MON = {m: i for i, m in enumerate(["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}
files = sorted(Path("data/futures").glob("*.csv"))
frames = []
for f in files:
    m = re.match(r"NIFTY(\d{2})([A-Z]{3})FUT", f.stem)
    if not m:
        print("skip (name not understood):", f.name); continue
    df = pd.read_csv(f, parse_dates=["Timestamp"])
    df["contract"] = f.stem
    df["order"] = int(m.group(1)) * 100 + MON[m.group(2)]
    frames.append(df)
if not frames:
    raise SystemExit("no futures files yet")
a = pd.concat(frames)
a["day"] = a.Timestamp.dt.normalize()
near = a.groupby("day")["order"].min().rename("near")
a = a.join(near, on="day")
c = a[a.order == a.near].drop(columns=["order", "near", "day"]).sort_values("Timestamp")
c.to_csv("data/NIFTY_FUT_continuous_1min.csv", index=False)
print("continuous rows:", len(c), "from", c.Timestamp.min(), "to", c.Timestamp.max())
