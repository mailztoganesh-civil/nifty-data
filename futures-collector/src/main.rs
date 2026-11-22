//! NIFTY futures collector (free, no account) using the nse-rs library.
//!
//! Each run:
//!  1. 1-min candles (last 29 days) for every listed NIFTY futures contract
//!     -> data/futures_live/NIFTY_FUT_<expiry>_1min.csv   (merged, deduped)
//!  2. Near-month continuous 1-min series built from all contract files
//!     -> data/futures_live/NIFTY_FUT_near_1min.csv
//!  3. Daily continuous futures from 2010 (OI roll, raw + ratio-adjusted)
//!     -> data/futures_live/NIFTY_FUT_daily_continuous.csv
//!
//! Run from the repo root:  cargo run --release --manifest-path futures-collector/Cargo.toml

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use chrono::{DateTime, Duration, FixedOffset, NaiveDate, NaiveDateTime, Utc};
use nse_rs::{Adjustment, ContinuousOptions, NseClient, RollRule};

const OUT: &str = "data/futures_live";
const HEADER: &str = "datetime,open,high,low,close,volume";

type Bars = BTreeMap<NaiveDateTime, String>; // IST time -> "o,h,l,c,v"

fn ist() -> FixedOffset {
    FixedOffset::east_opt(5 * 3600 + 1800).unwrap()
}

fn parse_expiry(s: &str) -> Option<NaiveDate> {
    let s = s.trim();
    ["%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"]
        .iter()
        .find_map(|f| NaiveDate::parse_from_str(s, f).ok())
}

fn read_bars(path: &Path) -> Bars {
    let mut m = Bars::new();
    if let Ok(txt) = fs::read_to_string(path) {
        for line in txt.lines().skip(1) {
            if let Some((t, rest)) = line.split_once(',') {
                if let Ok(dt) = NaiveDateTime::parse_from_str(t, "%Y-%m-%d %H:%M:%S") {
                    m.insert(dt, rest.to_string());
                }
            }
        }
    }
    m
}

fn write_bars(path: &Path, bars: &Bars, extra_col: Option<&BTreeMap<NaiveDateTime, String>>) -> Result<()> {
    let mut s = String::from(HEADER);
    if extra_col.is_some() {
        s.push_str(",contract");
    }
    s.push('\n');
    for (t, v) in bars {
        s.push_str(&format!("{},{}", t.format("%Y-%m-%d %H:%M:%S"), v));
        if let Some(e) = extra_col {
            s.push(',');
            s.push_str(e.get(t).map(String::as_str).unwrap_or(""));
        }
        s.push('\n');
    }
    fs::write(path, s).with_context(|| format!("write {}", path.display()))
}

fn contract_file(expiry: NaiveDate) -> PathBuf {
    Path::new(OUT).join(format!("NIFTY_FUT_{}_1min.csv", expiry.format("%Y-%m-%d")))
}

async fn collect_intraday(client: &NseClient) -> Result<()> {
    let contracts = client.get_futures("NIFTY").await.context("get_futures NIFTY")?;
    let mut expiries: Vec<NaiveDate> = contracts
        .iter()
        .filter(|c| c.underlying.eq_ignore_ascii_case("NIFTY"))
        .filter_map(|c| parse_expiry(&c.expiry_date))
        .collect();
    expiries.sort();
    expiries.dedup();
    println!("Listed NIFTY futures: {:?}", expiries);
    anyhow::ensure!(!expiries.is_empty(), "no NIFTY futures contracts returned");

    let end: DateTime<Utc> = Utc::now();
    let start = end - Duration::days(29);

    for exp in expiries {
        let sym = format!("NIFTY{}FUT", exp.format("%y%b").to_string().to_uppercase());
        match client.get_historical_candles(&sym, start, end, "1").await {
            Ok(candles) => {
                let path = contract_file(exp);
                let mut bars = read_bars(&path);
                let before = bars.len();
                for c in candles {
                    // nse-rs candle times are already IST wall-clock in epoch ms
                    let Some(t) = DateTime::from_timestamp_millis(c.time) else { continue };
                    let t = t.naive_utc();
                    bars.insert(t, format!("{},{},{},{},{}", c.open, c.high, c.low, c.close, c.volume));
                }
                write_bars(&path, &bars, None)?;
                println!("  {sym}: {} bars (+{} new)", bars.len(), bars.len() - before);
            }
            Err(e) => eprintln!("  {sym}: FAILED {e:#}"),
        }
    }
    Ok(())
}

/// Near-month series: for each bar, use the contract with the nearest expiry
/// on or after that bar's date (rolls on expiry day).
fn build_near_month() -> Result<()> {
    let mut files: Vec<(NaiveDate, Bars)> = Vec::new();
    for entry in fs::read_dir(OUT)? {
        let p = entry?.path();
        let name = p.file_name().unwrap().to_string_lossy().to_string();
        if let Some(d) = name.strip_prefix("NIFTY_FUT_").and_then(|r| r.strip_suffix("_1min.csv")) {
            if let Ok(exp) = NaiveDate::parse_from_str(d, "%Y-%m-%d") {
                files.push((exp, read_bars(&p)));
            }
        }
    }
    files.sort_by_key(|(e, _)| *e);

    let mut out = Bars::new();
    let mut which = BTreeMap::new();
    for (exp, bars) in &files {
        for (t, v) in bars {
            if t.date() > *exp || out.contains_key(t) {
                continue; // earlier expiry already filled this bar
            }
            out.insert(*t, v.clone());
            which.insert(*t, exp.format("%Y-%m-%d").to_string());
        }
    }
    write_bars(&Path::new(OUT).join("NIFTY_FUT_near_1min.csv"), &out, Some(&which))?;
    println!("Near-month 1-min series: {} bars", out.len());
    Ok(())
}

async fn collect_daily(client: &NseClient) -> Result<()> {
    let from = NaiveDate::from_ymd_opt(2010, 1, 1).unwrap();
    let to = Utc::now().with_timezone(&ist()).date_naive();
    let s = client
        .get_continuous_futures("NIFTY", from, to, ContinuousOptions {
            roll: RollRule::OpenInterest,
            adjustment: Adjustment::Ratio,
        })
        .await
        .context("continuous futures")?;

    let mut txt = String::from("date,open,high,low,close,settle,raw_close,volume,oi,contract_expiry\n");
    for b in &s.bars {
        txt.push_str(&format!(
            "{},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{},{},{}\n",
            b.date, b.open, b.high, b.low, b.close, b.settle, b.raw_close, b.volume, b.oi, b.contract
        ));
    }
    fs::write(Path::new(OUT).join("NIFTY_FUT_daily_continuous.csv"), txt)?;
    println!("Daily continuous: {} bars, {} rolls", s.bars.len(), s.rolls.len());
    Ok(())
}

async fn debug(client: &NseClient) {
    let end = Utc::now();
    let syms = ["NIFTY 50", "SBIN", "NIFTY26DECFUT", "NIFTY26NOVFUT", "NIFTY"];
    let tries: [(&str, i64); 6] = [("1", 3), ("1", 7), ("1", 15), ("1", 29), ("5", 7), ("D", 30)];
    for sym in syms {
        for (iv, days) in tries {
            match client.get_historical_candles(sym, end - Duration::days(days), end, iv).await {
                Ok(c) => println!("DEBUG {sym:>14} iv={iv} days={days}: {} candles {}", c.len(),
                    c.first().map(|x| format!("first={} close={}", x.time, x.close)).unwrap_or_default()),
                Err(e) => println!("DEBUG {sym:>14} iv={iv} days={days}: ERR {e:#}"),
            }
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    fs::create_dir_all(OUT)?;
    let client = NseClient::new();
    client.init_session().await.context("NSE session (NSE may be blocking this IP)")?;
    if std::env::args().any(|a| a == "--debug") {
        debug(&client).await;
        return Ok(());
    }

    let mut ok = false;
    match collect_intraday(&client).await {
        Ok(()) => ok = true,
        Err(e) => eprintln!("Intraday failed: {e:#}"),
    }
    build_near_month()?;

    let daily_flag = std::env::args().any(|a| a == "--daily");
    if daily_flag {
        match collect_daily(&client).await {
            Ok(()) => ok = true,
            Err(e) => eprintln!("Daily failed: {e:#}"),
        }
    }
    anyhow::ensure!(ok, "nothing collected");
    Ok(())
}
