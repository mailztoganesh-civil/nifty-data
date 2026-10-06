from openchart import NSEData
from datetime import datetime, timedelta
nse = NSEData()
r = nse.session.get("https://www.nseindia.com", timeout=10)
print("Cookie page status:", r.status_code, "cookies:", list(nse.session.cookies.keys()))
fo = nse.search("NIFTY", segment="FO")
print("FO results:", len(fo)); print(fo.head(40).to_string())
ix = nse.search("NIFTY 50", segment="IDX"); print(ix.to_string())
row = ix.iloc[0]
end = datetime.now(); 
for iv, days in (("1d", 30), ("1m", 2), ("5m", 5)):
    p = {"token": str(row.scripcode), "fromDate": int((end-timedelta(days=days)).timestamp()),
         "toDate": int(end.timestamp()), "symbol": row.symbol, "symbolType": row.type,
         "chartType": "D" if iv == "1d" else "I", "timeInterval": {"1d":1,"1m":1,"5m":5}[iv]}
    x = nse.session.post(nse.historical_url, json=p, timeout=15)
    print(iv, "HTTP", x.status_code, x.text[:300])
