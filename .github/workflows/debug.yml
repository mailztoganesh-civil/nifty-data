from openchart import NSEData
from datetime import datetime, timedelta
nse = NSEData()
for url in ("https://charting.nseindia.com", "https://charting.nseindia.com/?symbol=NIFTY"):
    r = nse.session.get(url, timeout=10)
    print("GET", url, r.status_code, "cookies:", list(nse.session.cookies.keys()))
for q in ("NIFTY26OCT", "NIFTY FUT", "NIFTY26"):
    fo = nse.search(q, segment="FO")
    print("search", q, len(fo)); print(fo.head(8).to_string())
end = datetime.now()
p = {"token": "26000", "fromDate": int((end-timedelta(days=30)).timestamp()), "toDate": int(end.timestamp()),
     "symbol": "NIFTY 50", "symbolType": "Index", "chartType": "D", "timeInterval": 1}
x = nse.session.post(nse.historical_url, json=p, timeout=15)
print("1d HTTP", x.status_code, x.text[:300])
