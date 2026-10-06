import time
from pathlib import Path
import pandas as pd
import yfinance as yf

out = Path("data/NIFTY50_yahoo_1min.csv")
out.parent.mkdir(exist_ok=True)
df = pd.DataFrame()
for attempt in range(3):
    try:
        df = yf.download("^NSEI", period="7d", interval="1m", progress=False, auto_adjust=False)
        if not df.empty: break
    except Exception as e:
        print("attempt", attempt + 1, "failed:", e)
    time.sleep(20)
if df.empty:
    raise SystemExit("ERROR: Yahoo returned no data")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
df.index.name = "Timestamp"
df = df[["Open", "High", "Low", "Close", "Volume"]]
if out.exists():
    old = pd.read_csv(out, index_col="Timestamp", parse_dates=True)
    df = pd.concat([old, df])
df = df[~df.index.duplicated(keep="last")].sort_index()
df.to_csv(out)
print("stored", len(df), "rows:", df.index.min(), "to", df.index.max())
