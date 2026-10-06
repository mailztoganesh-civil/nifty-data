"""
Daily collector: NIFTY futures (all live contracts) + NIFTY 50 index, 1-minute.
Runs on GitHub Actions after market close and appends to data/ (deduplicated).
"""
import re, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from openchart import NSEData

DATA = Path("data")
LOOKBACK_DAYS = 7          # re-fetch the last week each run, so a missed day is filled later
nse = NSEData()

def merge_save(df, path):
    df = df.copy()
    df.index.name = "Timestamp"
    if path.exists():
        old = pd.read_csv(path, index_col="Timestamp", parse_dates=True)
        df = pd.concat([old, df])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(path)
    return len(df)

def fetch(token, symbol, stype):
    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS)
    for attempt in range(3):
        try:
            df = nse.historical_direct(token=token, symbol=symbol, symbol_type=stype,
                                       start=start, end=end, interval="1m")
            if not df.empty:
                return df
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}")
        time.sleep(5)
    return pd.DataFrame()

def main():
    ok = 0
    # ---- futures ----
    res = nse.search("NIFTY", segment="FO")
    if res.empty:
        print("ERROR: NSE search returned nothing (NSE may be blocking this server).")
        sys.exit(1)
    fut = res[res["type"].str.contains("fut", case=False, na=False)
              & res["symbol"].str.match(r"^NIFTY\d", na=False)]
    print("Live NIFTY futures:", list(fut["symbol"]))
    (DATA / "futures").mkdir(parents=True, exist_ok=True)
    for _, r in fut.iterrows():
        df = fetch(r.scripcode, r.symbol, r.type)
        if df.empty:
            print(f"{r.symbol}: no data"); continue
        n = merge_save(df, DATA / "futures" / f"{r.symbol}.csv")
        print(f"{r.symbol}: +{len(df)} fetched, {n} rows stored"); ok += 1
        time.sleep(2)
    # ---- index (reference) ----
    idx = nse.search("NIFTY 50", segment="IDX")
    idx = idx[idx["symbol"].str.upper() == "NIFTY 50"] if not idx.empty else idx
    if not idx.empty:
        r = idx.iloc[0]
        df = fetch(r.scripcode, r.symbol, r.type)
        if not df.empty:
            n = merge_save(df, DATA / "NIFTY50_index_1min.csv"); ok += 1
            print(f"NIFTY 50 index: {n} rows stored")
    if ok == 0:
        print("ERROR: nothing downloaded"); sys.exit(1)

if __name__ == "__main__":
    main()
