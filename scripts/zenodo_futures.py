"""
Download Nifty futures 1-min data (2017-2020) from Zenodo record 10899828
and save it as clean CSVs in data/futures/.

Source: "Nifty spot and futures data.zip" (~9 MB)
https://zenodo.org/records/10899828

Output:
  data/futures/NIFTY_FUT_1min_<YEAR>.csv   one file per year
  data/futures/NIFTY_FUT_1min_all.csv      everything combined
  data/futures/zip_manifest.txt            list of files found in the zip
Columns: datetime,open,high,low,close,volume
"""
import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

URL = ("https://zenodo.org/records/10899828/files/"
       "Nifty%20spot%20and%20futures%20data.zip?download=1")
OUT = Path("data/futures")
OUT.mkdir(parents=True, exist_ok=True)


def download() -> zipfile.ZipFile:
    print("Downloading", URL)
    r = requests.get(URL, timeout=300)
    r.raise_for_status()
    print(f"Got {len(r.content)/1e6:.1f} MB")
    return zipfile.ZipFile(io.BytesIO(r.content))


def is_futures(name: str) -> bool:
    n = name.lower().rsplit("/", 1)[-1]
    return ("fut" in n) or bool(re.search(r"(^|[^a-z])f1([^0-9]|$)", n))


def read_any(zf: zipfile.ZipFile, name: str) -> list[pd.DataFrame]:
    data = zf.read(name)
    low = name.lower()
    if low.endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None)
        return list(sheets.values())
    if low.endswith((".csv", ".txt")):
        return [pd.read_csv(io.BytesIO(data), header=None, sep=None,
                            engine="python")]
    return []


def normalise(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Find the header row and map columns to datetime/o/h/l/c/v."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return None

    # Detect a header row in the first few rows
    header_idx = None
    for i in range(min(5, len(raw))):
        row = " ".join(str(x).lower() for x in raw.iloc[i].tolist())
        if "open" in row and "close" in row:
            header_idx = i
            break

    if header_idx is not None:
        df = raw.iloc[header_idx + 1:].copy()
        df.columns = [str(c).strip().lower() for c in raw.iloc[header_idx]]
    else:
        # No header: assume [ticker,] date, time, O, H, L, C, V
        df = raw.copy()
        n = df.shape[1]
        if n >= 8:
            df = df.iloc[:, :8]
            df.columns = ["ticker", "date", "time", "open", "high", "low",
                          "close", "volume"]
        elif n == 7:
            df.columns = ["date", "time", "open", "high", "low", "close",
                          "volume"]
        else:
            return None

    def pick(*keys):
        for c in df.columns:
            if any(k in c for k in keys):
                return c
        return None

    c_date = pick("date", "dt")
    c_time = pick("time")
    c_o, c_h, c_l, c_c = pick("open"), pick("high"), pick("low"), pick("close")
    c_v = pick("vol")
    if not all([c_date, c_o, c_h, c_l, c_c]):
        return None

    if c_time and c_time != c_date:
        stamp = df[c_date].astype(str).str.split(" ").str[0] + " " + \
            df[c_time].astype(str)
    else:
        stamp = df[c_date].astype(str)

    # ISO dates (2017-01-02) are year-first; others (02-01-2017) day-first
    iso = stamp.str.match(r"^\d{4}[-/]")
    dt = pd.Series(pd.NaT, index=stamp.index, dtype="datetime64[ns]")
    dt[iso] = pd.to_datetime(stamp[iso], errors="coerce", yearfirst=True)
    dt[~iso] = pd.to_datetime(stamp[~iso], errors="coerce", dayfirst=True,
                              format="mixed")

    out = pd.DataFrame({
        "datetime": dt,
        "open": pd.to_numeric(df[c_o], errors="coerce"),
        "high": pd.to_numeric(df[c_h], errors="coerce"),
        "low": pd.to_numeric(df[c_l], errors="coerce"),
        "close": pd.to_numeric(df[c_c], errors="coerce"),
        "volume": pd.to_numeric(df[c_v], errors="coerce") if c_v else 0,
    })
    return out.dropna(subset=["datetime", "open", "close"])


def flatten(zf: zipfile.ZipFile) -> zipfile.ZipFile:
    """Unpack zips nested inside the zip (e.g. 2017.zip) into one in-memory zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        def add(z, prefix=""):
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                data = z.read(n)
                if n.lower().endswith(".zip"):
                    add(zipfile.ZipFile(io.BytesIO(data)), prefix + n[:-4] + "/")
                else:
                    out.writestr(prefix + n, data)
        add(zf)
    return zipfile.ZipFile(buf)


def main():
    zf = flatten(download())
    names = [n for n in zf.namelist() if not n.endswith("/")]
    (OUT / "zip_manifest.txt").write_text("\n".join(names))
    print(f"{len(names)} files in zip")

    fut_files = [n for n in names if is_futures(n)]
    print("Futures files:", fut_files or "none matched by name")

    # Fallback: if no file name says futures, scan contents for "F1"
    if not fut_files:
        for n in names:
            try:
                head = zf.read(n)[:2000].decode("utf-8", "ignore").lower()
            except Exception:
                continue
            if "nifty_f1" in head or "niftyf1" in head:
                fut_files.append(n)
    if not fut_files:
        sys.exit("No futures files found. Check data/futures/zip_manifest.txt")

    frames = []
    for n in fut_files:
        for raw in read_any(zf, n):
            df = normalise(raw)
            if df is not None and len(df):
                print(f"  {n}: {len(df)} rows")
                frames.append(df)
    if not frames:
        sys.exit("Futures files found but none could be parsed.")

    allf = (pd.concat(frames).drop_duplicates("datetime")
            .sort_values("datetime").reset_index(drop=True))
    allf["volume"] = allf["volume"].fillna(0).astype("int64")

    allf.to_csv(OUT / "NIFTY_FUT_1min_all.csv", index=False)
    for yr, g in allf.groupby(allf["datetime"].dt.year):
        g.to_csv(OUT / f"NIFTY_FUT_1min_{yr}.csv", index=False)
        print(f"Saved {yr}: {len(g)} rows")
    print(f"Total {len(allf)} rows, "
          f"{allf['datetime'].min()} -> {allf['datetime'].max()}")


if __name__ == "__main__":
    main()
