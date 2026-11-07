#!/usr/bin/env python3
"""
ไล่เก็บข้อมูลย้อนหลัง (รันซ้ำได้ ไม่เขียนทับแถวที่ละเอียดกว่า และไม่ลบ notes)
- ย้อนหลัง ~30 วัน: แท่ง 1 นาทีรวม pre-market (Yahoo ให้ทีละ 7 วัน) → ละเอียดเท่า live (source = backfill_1m)
  และเก็บไฟล์ดิบลง data/intraday/<วันที่>/ ด้วย
- ย้อนหลัง ~60 วัน: แท่ง 5 นาทีรวม pre-market → VWAP, pre-market gap, คลื่นขาย (source = backfill_5m)
- ย้อนหลัง 5 ปี: แท่งรายวัน → gap, เปลี่ยนแปลง, ปิด gap, เทียบกลุ่ม แต่ไม่มี VWAP/pre-market (source = backfill_1d)
ลำดับความละเอียด: live_1m > backfill_1m > backfill_5m > backfill_1d
"""
import sys
from datetime import timedelta

import pandas as pd
import capture as c

PRIORITY = {"live_1m": 0, "backfill_1m": 1, "backfill_5m": 2, "backfill_1d": 3}
DAILY_YEARS = "5y"
ONE_MIN_DAYS = 29      # Yahoo ให้แท่ง 1 นาทีย้อนหลังได้ราว 30 วัน
CHUNK_DAYS = 7         # และขอได้ครั้งละไม่เกิน 7 วัน


def one_minute(sym: str) -> pd.DataFrame:
    """ดึงแท่ง 1 นาทีย้อนหลัง ~30 วัน โดยขอทีละ 7 วันแล้วต่อกัน"""
    end = pd.Timestamp.now(tz=c.ET).normalize() + timedelta(days=1)
    start = end - timedelta(days=ONE_MIN_DAYS)
    parts = []
    while start < end:
        stop = min(start + timedelta(days=CHUNK_DAYS), end)
        if all(d.weekday() >= 5 for d in pd.date_range(start, stop - timedelta(days=1))):
            start = stop      # ช่วงที่มีแต่เสาร์-อาทิตย์ ไม่ต้องขอ
            continue
        df = c.history(sym, start=start.strftime("%Y-%m-%d"), end=stop.strftime("%Y-%m-%d"),
                       interval="1m", prepost=True)
        if not df.empty:
            parts.append(df)
        start = stop
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts)
    return out[~out.index.duplicated(keep="last")].sort_index()


def save_intraday(sym: str, df: pd.DataFrame) -> int:
    n = 0
    for day in sorted(set(df.index.date)):
        f = c.DATA / "intraday" / day.isoformat() / f"{sym}.csv"
        _, reg = c.split_session(df, day)
        if not f.exists() and c.session_complete(reg):
            f.parent.mkdir(parents=True, exist_ok=True)
            df[df.index.date == day].to_csv(f)
            n += 1
    return n


def main() -> None:
    c.DATA.mkdir(parents=True, exist_ok=True)
    syms = sorted(set(c.WATCHLIST) | set(c.WATCHLIST.values()))
    dailies = {s: c.history(s, period=DAILY_YEARS, interval="1d") for s in syms + list(c.MARKET.values())}

    # แท่ง 1 นาที: เก็บไฟล์ดิบของหุ้น + peer
    ones = {}
    for s in syms:
        ones[s] = one_minute(s)
        print(f"1m {s}: {len(set(ones[s].index.date)) if not ones[s].empty else 0} วัน, "
              f"ไฟล์ใหม่ {save_intraday(s, ones[s]) if not ones[s].empty else 0}", file=sys.stderr)

    rows = []
    for s, peer in c.WATCHLIST.items():
        print(f"backfill {s}", file=sys.stderr)
        earn = c.earnings_dates(s)
        if earn:
            c.save_earnings(s, earn)
        one = ones.get(s, pd.DataFrame())
        one_days = set(one.index.date) if not one.empty else set()
        five = c.history(s, period="60d", interval="5m", prepost=True)
        five_days = set(five.index.date) if not five.empty else set()
        for day in sorted(set(dailies[s].index.date)):
            r = None
            for src, intra, days in (("backfill_1m", one, one_days), ("backfill_5m", five, five_days)):
                if day in days:
                    r = c.summarize(s, peer, intra, dailies[s], dailies[peer], dailies["SPY"], earn, day)
                    if r:
                        r["source"] = src
                        break
            if r is None:
                r = c.summarize_daily(s, peer, dailies[s], dailies[peer], dailies["SPY"], day)
            if r:
                rows.append(r)

    old = c.load_summary()
    new = pd.DataFrame(rows)
    allr = pd.concat([old.assign(_o=1), new.assign(_o=0)], ignore_index=True)
    allr["notes"] = allr["notes"].fillna("")
    allr["_p"] = allr["source"].fillna("live_1m").map(PRIORITY).fillna(9)
    # ละเอียดกว่าชนะ / ถ้าเท่ากัน แถวที่คำนวณใหม่ชนะ (notes อยู่ใน notes.csv จะใส่กลับด้านล่าง)
    allr = (allr.sort_values(["_p", "_o"], kind="stable").drop_duplicates(["date", "ticker"], keep="first")
                .drop(columns=["_p", "_o"]).sort_values(["date", "ticker"]))
    allr = c.apply_notes(c.tag_events(c.fill_followups(allr.reset_index(drop=True), dailies)))
    allr.to_csv(c.SUMMARY, index=False)

    # บริบทตลาดย้อนหลัง
    ctx = []
    for day in sorted(set(dailies["SPY"].index.date)):
        r = {"date": day.isoformat()}
        for name, s in c.MARKET.items():
            d = dailies[s]
            row = d[d.index.date == day]
            r[f"{name}_close"] = round(float(row["Close"].iloc[-1]), 4) if not row.empty else None
            r[f"{name}_chg_pct"] = c.day_change(d, day)
        ctx.append(r)
    old_ctx = pd.read_csv(c.CONTEXT) if c.CONTEXT.exists() else pd.DataFrame()
    pd.concat([old_ctx, pd.DataFrame(ctx)]).drop_duplicates("date", keep="last").sort_values("date").to_csv(c.CONTEXT, index=False)
    print(f"done: {len(allr)} rows", file=sys.stderr)
    print(allr["source"].value_counts().to_string(), file=sys.stderr)


if __name__ == "__main__":
    main()
