#!/usr/bin/env python3
"""
ไล่เก็บข้อมูลย้อนหลัง (รันครั้งเดียว หรือรันซ้ำได้ ไม่เขียนทับของเดิม)
- ย้อนหลัง ~60 วัน: แท่ง 5 นาทีรวม pre-market → ได้ VWAP, pre-market gap, คลื่นขาย ครบ (source = backfill_5m)
- ย้อนหลัง 2 ปี: แท่งรายวัน → ได้ gap, เปลี่ยนแปลง, ปิด gap, เทียบกลุ่ม แต่ไม่มี VWAP/pre-market (source = backfill_1d)
ถ้ามีข้อมูล live_1m ของวันนั้นอยู่แล้ว จะไม่แทนที่
"""
import sys
import pandas as pd
import capture as c

PRIORITY = {"live_1m": 0, "backfill_5m": 1, "backfill_1d": 2}
DAILY_YEARS = "2y"


def main() -> None:
    c.DATA.mkdir(parents=True, exist_ok=True)
    syms = sorted(set(c.WATCHLIST) | set(c.WATCHLIST.values()))
    dailies = {s: c.history(s, period=DAILY_YEARS, interval="1d") for s in syms + list(c.MARKET.values())}
    rows = []
    for s, peer in c.WATCHLIST.items():
        print(f"backfill {s}", file=sys.stderr)
        earn = c.earnings_dates(s)
        if earn:
            c.save_earnings(s, earn)
        five = c.history(s, period="60d", interval="5m", prepost=True)
        five_days = set(five.index.date) if not five.empty else set()
        for day in sorted(set(dailies[s].index.date)):
            r = None
            if day in five_days:
                r = c.summarize(s, peer, five, dailies[s], dailies[peer], dailies["SPY"], earn, day)
                if r:
                    r["source"] = "backfill_5m"
            if r is None:
                r = c.summarize_daily(s, peer, dailies[s], dailies[peer], dailies["SPY"], day)
            if r:
                rows.append(r)

    old = c.load_summary()
    allr = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    allr["notes"] = allr["notes"].fillna("")
    allr["_p"] = allr["source"].fillna("live_1m").map(PRIORITY).fillna(9)
    # stable sort: ถ้า priority เท่ากัน แถวเดิม (ที่อาจมี notes) ชนะ
    allr = (allr.sort_values("_p", kind="stable").drop_duplicates(["date", "ticker"], keep="first")
                .drop(columns="_p").sort_values(["date", "ticker"]))
    allr = c.tag_events(c.fill_followups(allr.reset_index(drop=True), dailies))
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
