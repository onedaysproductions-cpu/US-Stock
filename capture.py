#!/usr/bin/env python3
"""
Daily market capture สำหรับ watchlist
- เก็บแท่ง 1 นาที (รวม pre/post market) ของหุ้น + ETF เทียบกลุ่ม ลง data/intraday/
- สรุปรายวันต่อหุ้น: gap, pre-market, VWAP, คลื่นขาย, relative volume, label Go/Fade
- บริบทตลาด: SPY, QQQ, VIX, ยีลด์ 10 ปี, น้ำมัน
- ข่าวล่าสุดต่อหุ้น ลง data/news/
- เติมผล 1/3/5 วันถัดไปย้อนหลังให้อัตโนมัติ (ใช้ดูว่าเป็นเทรดสั้นหรือยาว)

ข้อมูลจาก Yahoo Finance ผ่าน yfinance (ฟรี ไม่ต้องใช้ API key แต่เป็นแหล่งไม่เป็นทางการ)
แท่ง 1 นาทีย้อนหลังได้ราว 7 วัน จึงต้องรันทุกวันทำการ
"""
from __future__ import annotations

import json
import sys
import time as _time
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------- ตั้งค่า ----------------
WATCHLIST = {          # หุ้น : ETF/peer ที่ใช้เทียบกลุ่ม
    "MXL": "SOXX",     # semiconductor
    "STRL": "PWR",     # infrastructure / data center construction
    "BTSG": "XLV",     # healthcare
    "MO": "XLP",       # consumer staples
    "UUUU": "URA",     # uranium
}
MARKET = {"SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "US10Y": "^TNX", "OIL": "CL=F"}

GAP_THRESHOLD = 2.0    # % ที่นับว่า "gap"
WAVE_PCT = 0.75        # % ที่ราคาย่อจากยอดย่อย แล้วนับเป็น 1 คลื่นขาย
ET = "America/New_York"
DATA = Path(__file__).resolve().parent / "data"
SUMMARY = DATA / "daily_summary.csv"
CONTEXT = DATA / "market_context.csv"
EARNINGS = DATA / "earnings.csv"
EVENTS = Path(__file__).resolve().parent / "events.csv"   # ปฏิทินเศรษฐกิจ (แก้/เพิ่มเองได้)


# ---------------- ดึงข้อมูล ----------------
CLOSE_CUTOFF = time(16, 30)   # หลังเวลานี้ (ET) ถือว่าแท่งรายวันของวันนี้ปิดแล้ว


def drop_incomplete(df: pd.DataFrame) -> pd.DataFrame:
    """ตัดแท่งรายวันของวันนี้ทิ้งถ้าตลาดยังไม่ปิด (กันราคาระหว่างวันหลุดไปเป็นราคาปิด)"""
    now = pd.Timestamp.now(tz=ET)
    if df.empty or now.time() >= CLOSE_CUTOFF:
        return df
    return df[df.index.date < now.date()]


def history(sym: str, **kw) -> pd.DataFrame:
    for attempt in range(3):
        try:
            df = yf.Ticker(sym).history(auto_adjust=False, **kw)
            if not df.empty:
                df.index = df.index.tz_convert(ET)
                return drop_incomplete(df) if kw.get("interval") == "1d" else df
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym} attempt {attempt + 1}: {e}", file=sys.stderr)
        _time.sleep(2 * (attempt + 1))
    return pd.DataFrame()


def intraday(sym: str) -> pd.DataFrame:
    return history(sym, period="5d", interval="1m", prepost=True)


def daily(sym: str) -> pd.DataFrame:
    return history(sym, period="6mo", interval="1d")


# ---------------- คำนวณ ----------------
def split_session(df: pd.DataFrame, day):
    d = df[df.index.date == day]
    t = d.index.time
    pre = d[(t >= time(4, 0)) & (t < time(9, 30))]
    reg = d[(t >= time(9, 30)) & (t < time(16, 0))]
    return pre, reg


def session_complete(reg: pd.DataFrame) -> bool:
    return not reg.empty and reg.index[-1].time() >= time(15, 50)


def vwap(reg: pd.DataFrame) -> float:
    tp = (reg["High"] + reg["Low"] + reg["Close"]) / 3
    vol = reg["Volume"].sum()
    return float((tp * reg["Volume"]).sum() / vol) if vol > 0 else float(reg["Close"].mean())


def count_waves(closes, pct: float = WAVE_PCT) -> int:
    """นับจำนวนครั้งที่ราคาย่อจากยอดย่อย >= pct% (แบบ zigzag)"""
    closes = list(closes)
    if not closes:
        return 0
    waves, peak, trough, dropping = 0, closes[0], closes[0], False
    for p in closes:
        if not dropping:
            if p > peak:
                peak = p
            elif (peak - p) / peak * 100 >= pct:
                waves, dropping, trough = waves + 1, True, p
        else:
            if p < trough:
                trough = p
            elif (p - trough) / trough * 100 >= pct:
                dropping, peak = False, p
    return waves


def classify(gap: float, o: float, c: float, vw: float, filled: bool) -> str:
    if abs(gap) < GAP_THRESHOLD:
        return "NO_GAP"
    if gap > 0:
        if c > o and c > vw:
            return "GAP_UP_GO"
        if c < vw and (filled or c < o):
            return "GAP_UP_FADE"
        return "GAP_UP_MIXED"
    if c < o and c < vw:
        return "GAP_DOWN_GO"
    if c > vw and (filled or c > o):
        return "GAP_DOWN_REVERSAL"
    return "GAP_DOWN_MIXED"


def prev_close(d: pd.DataFrame, day) -> float | None:
    before = d[d.index.date < day]
    return float(before["Close"].iloc[-1]) if not before.empty else None


def day_change(d: pd.DataFrame, day) -> float | None:
    pc = prev_close(d, day)
    row = d[d.index.date == day]
    if pc is None or row.empty:
        return None
    return round((float(row["Close"].iloc[-1]) / pc - 1) * 100, 2)


def earnings_dates(sym: str) -> list:
    try:
        ed = yf.Ticker(sym).get_earnings_dates(limit=12)
        if ed is None or ed.empty:
            return []
        return sorted({ts.tz_convert(ET).date() for ts in ed.index})
    except Exception:  # noqa: BLE001
        return []


def decompose(chg, peer_chg, spy_chg) -> dict:
    """แยกการขยับของหุ้นเป็น 3 ส่วน: ตลาด (SPY) + กลุ่ม (peer เหนือ SPY) + ตัวเอง (หุ้นเหนือ peer)"""
    if peer_chg is None or spy_chg is None:
        return {"part_market": None, "part_sector": None, "part_own": None, "driver": None}
    parts = {"MARKET": spy_chg, "SECTOR": peer_chg - spy_chg, "OWN": chg - peer_chg}
    driver = max(parts, key=lambda k: abs(parts[k]))
    return {"part_market": round(parts["MARKET"], 2), "part_sector": round(parts["SECTOR"], 2),
            "part_own": round(parts["OWN"], 2), "driver": driver}


def classify_daily(gap: float, o: float, c: float, filled: bool) -> str:
    """ใช้กับข้อมูลย้อนหลังรายวัน (ไม่มี VWAP) — หยาบกว่า live"""
    if abs(gap) < GAP_THRESHOLD:
        return "NO_GAP"
    if gap > 0:
        return "GAP_UP_GO" if c > o else ("GAP_UP_FADE" if filled or c < o else "GAP_UP_MIXED")
    return "GAP_DOWN_GO" if c < o else ("GAP_DOWN_REVERSAL" if filled or c > o else "GAP_DOWN_MIXED")


def summarize_daily(sym, peer, d, peer_d, spy_d, day) -> dict | None:
    pc = prev_close(d, day)
    row = d[d.index.date == day]
    if pc is None or row.empty:
        return None
    o, h, l, c, v = (float(row[k].iloc[-1]) for k in ("Open", "High", "Low", "Close", "Volume"))
    gap = (o / pc - 1) * 100
    filled = l <= pc if gap > 0 else h >= pc
    hist = d[d.index.date < day].tail(20)
    avg_vol = float(hist["Volume"].mean()) if not hist.empty else np.nan
    chg = (c / pc - 1) * 100
    peer_chg, spy_chg = day_change(peer_d, day), day_change(spy_d, day)
    return {"source": "backfill_1d", **decompose(chg, peer_chg, spy_chg),
            "date": day.isoformat(), "ticker": sym, "peer": peer, "prev_close": round(pc, 4),
            "open": round(o, 4), "high": round(h, 4), "low": round(l, 4), "close": round(c, 4),
            "volume": int(v), "rel_volume": round(v / avg_vol, 2) if avg_vol and avg_vol > 0 else None,
            "gap_pct": round(gap, 2), "change_pct": round(chg, 2),
            "close_vs_open_pct": round((c / o - 1) * 100, 2), "gap_filled": bool(filled),
            "fade_from_high_pct": round((c / h - 1) * 100, 2),
            "peer_change_pct": peer_chg, "spy_change_pct": spy_chg,
            "vs_peer_pct": round(chg - peer_chg, 2) if peer_chg is not None else None,
            "vs_spy_pct": round(chg - spy_chg, 2) if spy_chg is not None else None,
            "label": classify_daily(gap, o, c, filled), "events": "", "notes": ""}


def load_events() -> pd.DataFrame:
    frames = []
    if EVENTS.exists():
        frames.append(pd.read_csv(EVENTS, dtype=str).fillna(""))
    if EARNINGS.exists():
        e = pd.read_csv(EARNINGS, dtype=str).fillna("")
        frames.append(pd.DataFrame({"date": e["date"], "type": "EARNINGS",
                                    "title": e["ticker"] + " earnings", "ticker": e["ticker"]}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "type", "title", "ticker"])


def tag_events(df: pd.DataFrame) -> pd.DataFrame:
    """ใส่ป้ายเหตุการณ์ (CPI, FOMC, EARNINGS ...) ให้ทุกแถว คำนวณใหม่ทุกรอบ"""
    ev = load_events()
    if ev.empty or df.empty:
        return df
    ev["d"] = pd.to_datetime(ev["date"]).dt.date
    tags = []
    for _, r in df.iterrows():
        day = pd.Timestamp(r["date"]).date()
        t = set()
        for _, e in ev.iterrows():
            if e["type"] == "EARNINGS":
                if e["ticker"] == r["ticker"] and abs((e["d"] - day).days) <= 1:
                    t.add("EARNINGS")
            elif e["d"] == day and e["ticker"] in ("", r["ticker"]):
                t.add(e["type"])
        tags.append(";".join(sorted(t)))
    df["events"] = tags
    df["earnings_window"] = df["events"].str.contains("EARNINGS")
    return df


TEXT_COLS = {"notes": "str", "events": "str", "source": "str", "label": "str", "driver": "str"}


def load_summary() -> pd.DataFrame:
    """อ่าน daily_summary โดยบังคับคอลัมน์ข้อความเป็น str (pandas 3 ไม่ยอมใส่ข้อความลงคอลัมน์ float)"""
    if not SUMMARY.exists():
        return pd.DataFrame()
    df = pd.read_csv(SUMMARY, dtype=TEXT_COLS)
    df["notes"] = df["notes"].fillna("") if "notes" in df else ""
    return apply_notes(df)


NOTES = Path(__file__).resolve().parent / "notes.csv"   # date,ticker,notes — Claude/คุณแก้ไฟล์นี้ บอทไม่แตะ


def apply_notes(df: pd.DataFrame) -> pd.DataFrame:
    """เอา notes จาก notes.csv มาใส่คอลัมน์ notes (แยกไฟล์เพื่อไม่ให้ชนกับบอทที่เขียน daily_summary)"""
    if df.empty or not NOTES.exists():
        return df
    n = pd.read_csv(NOTES, dtype=str).fillna("")
    m = {(r["date"], r["ticker"]): r["notes"] for _, r in n.iterrows() if r["notes"]}
    df["notes"] = [m.get(k, old) for k, old in zip(zip(df["date"], df["ticker"]), df["notes"].fillna(""))]
    return df


def save_earnings(sym: str, dates: list) -> None:
    old = pd.read_csv(EARNINGS, dtype=str) if EARNINGS.exists() else pd.DataFrame(columns=["date", "ticker"])
    new = pd.DataFrame({"date": [d.isoformat() for d in dates], "ticker": sym})
    pd.concat([old, new]).drop_duplicates().sort_values(["date", "ticker"]).to_csv(EARNINGS, index=False)


def summarize(sym: str, peer: str, intra: pd.DataFrame, d: pd.DataFrame,
              peer_d: pd.DataFrame, spy_d: pd.DataFrame, earn: list, day) -> dict | None:
    pre, reg = split_session(intra, day)
    if not session_complete(reg):
        return None
    pc = prev_close(d, day)
    if pc is None:
        return None

    o, c = float(reg["Open"].iloc[0]), float(reg["Close"].iloc[-1])
    hi, lo, vol = float(reg["High"].max()), float(reg["Low"].min()), int(reg["Volume"].sum())
    # ใช้ OHLCV ทางการจากแท่งรายวัน (รวม opening/closing auction) ถ้ามี — แท่งนาทีสุดท้ายอาจต่างจากราคาปิดจริง
    drow = d[d.index.date == day]
    if not drow.empty:
        o, c = float(drow["Open"].iloc[-1]), float(drow["Close"].iloc[-1])
        hi, lo, vol = float(drow["High"].iloc[-1]), float(drow["Low"].iloc[-1]), int(drow["Volume"].iloc[-1])
    vw = vwap(reg)
    gap = (o / pc - 1) * 100
    filled = lo <= pc if gap > 0 else hi >= pc
    first30 = reg[reg.index.time < time(10, 0)]
    closes5 = reg["Close"].resample("5min").last().dropna()

    hist = d[d.index.date < day].tail(20)
    avg_vol = float(hist["Volume"].mean()) if not hist.empty else np.nan

    chg = (c / pc - 1) * 100
    peer_chg, spy_chg = day_change(peer_d, day), day_change(spy_d, day)
    next_e = next((e for e in earn if e >= day), None)

    return {"source": "live_1m", **decompose(chg, peer_chg, spy_chg),
        "date": day.isoformat(), "ticker": sym, "peer": peer,
        "prev_close": round(pc, 4),
        "pre_last": round(float(pre["Close"].iloc[-1]), 4) if not pre.empty else None,
        "pre_high": round(float(pre["High"].max()), 4) if not pre.empty else None,
        "pre_volume": int(pre["Volume"].sum()) if not pre.empty else 0,
        "pre_gap_pct": round((float(pre["Close"].iloc[-1]) / pc - 1) * 100, 2) if not pre.empty else None,
        "open": round(o, 4), "high": round(hi, 4), "low": round(lo, 4), "close": round(c, 4),
        "volume": vol,
        "rel_volume": round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 else None,
        "gap_pct": round(gap, 2),
        "change_pct": round(chg, 2),
        "close_vs_open_pct": round((c / o - 1) * 100, 2),
        "vwap": round(vw, 4),
        "close_vs_vwap_pct": round((c / vw - 1) * 100, 2),
        "gap_filled": bool(filled),
        "first30_high": round(float(first30["High"].max()), 4) if not first30.empty else None,
        "first30_low": round(float(first30["Low"].min()), 4) if not first30.empty else None,
        "fade_from_high_pct": round((c / hi - 1) * 100, 2),
        "sell_waves": count_waves(closes5),
        "peer_change_pct": peer_chg,
        "spy_change_pct": spy_chg,
        "vs_peer_pct": round(chg - peer_chg, 2) if peer_chg is not None else None,
        "vs_spy_pct": round(chg - spy_chg, 2) if spy_chg is not None else None,
        "next_earnings": next_e.isoformat() if next_e else None,
        "earnings_window": any(abs((e - day).days) <= 1 for e in earn),
        "label": classify(gap, o, c, vw, filled),
        "events": "",
        "ret_1d": None, "ret_3d": None, "ret_5d": None,
        "notes": "",   # ให้ Claude/คุณเติมเหตุผลหรือ catalyst
    }


def fill_followups(df: pd.DataFrame, dailies: dict) -> pd.DataFrame:
    for i, row in df.iterrows():
        d = dailies.get(row["ticker"])
        if d is None or d.empty:
            continue
        dates = list(d.index.date)
        day = pd.Timestamp(row["date"]).date()
        if day not in dates:
            continue
        k = dates.index(day)
        base = float(d["Close"].iloc[k])
        for n in (1, 3, 5):
            col = f"ret_{n}d"
            if pd.isna(row.get(col)) and k + n < len(dates):
                df.at[i, col] = round((float(d["Close"].iloc[k + n]) / base - 1) * 100, 2)
    return df


def news_items(sym: str) -> list:
    out = []
    try:
        for it in (yf.Ticker(sym).news or [])[:10]:
            c = it.get("content", it)
            out.append({
                "title": c.get("title"),
                "publisher": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
                "published": c.get("pubDate") or c.get("providerPublishTime"),
                "url": (c.get("canonicalUrl") or {}).get("url") or c.get("link"),
            })
    except Exception as e:  # noqa: BLE001
        print(f"  ! news {sym}: {e}", file=sys.stderr)
    return out


# ---------------- main ----------------
def main() -> None:
    (DATA / "intraday").mkdir(parents=True, exist_ok=True)
    (DATA / "news").mkdir(parents=True, exist_ok=True)

    syms = sorted(set(WATCHLIST) | set(WATCHLIST.values()))
    intras, dailies = {}, {}
    for s in syms + list(MARKET.values()):
        print(f"fetch {s}")
        dailies[s] = daily(s)
        if s in syms:
            intras[s] = intraday(s)

    # 1) เก็บแท่ง 1 นาทีดิบ (ทุกวันที่ยังไม่เคยเก็บ)
    for s, df in intras.items():
        for day in sorted(set(df.index.date)):
            f = DATA / "intraday" / day.isoformat() / f"{s}.csv"
            _, reg = split_session(df, day)
            if not f.exists() and session_complete(reg):
                f.parent.mkdir(parents=True, exist_ok=True)
                df[df.index.date == day].to_csv(f)

    # 2) สรุปรายวัน
    # แถวที่เป็น live_1m แล้วไม่ทำซ้ำ / แถว backfill (5m, 1d) จะถูกแทนด้วย live_1m ที่ละเอียดกว่า
    old = load_summary()
    done = set(zip(old.loc[old["source"] == "live_1m", "date"],
                   old.loc[old["source"] == "live_1m", "ticker"])) if not old.empty else set()
    rows = []
    for s, peer in WATCHLIST.items():
        intra = intras.get(s, pd.DataFrame())
        if intra.empty:
            continue
        earn = earnings_dates(s)
        if earn:
            save_earnings(s, earn)
        for day in sorted(set(intra.index.date)):
            if (day.isoformat(), s) in done:
                continue
            r = summarize(s, peer, intra, dailies[s], dailies[peer], dailies["SPY"], earn, day)
            if r:
                rows.append(r)
    if rows and not old.empty:
        new = pd.DataFrame(rows)
        keys = set(zip(new["date"], new["ticker"]))
        replaced = old[[k in keys for k in zip(old["date"], old["ticker"])]]
        keep_notes = {(r["date"], r["ticker"]): r["notes"] for _, r in replaced.iterrows() if r["notes"]}
        new["notes"] = [keep_notes.get(k, "") for k in zip(new["date"], new["ticker"])]
        old = old.drop(replaced.index)
        rows = new.to_dict("records")
        print(f"upgrade to live_1m: {len(replaced)} rows")
    summary = pd.concat([old, pd.DataFrame(rows)], ignore_index=True) if rows else old
    if not summary.empty:
        summary = tag_events(fill_followups(summary, dailies)).sort_values(["date", "ticker"])
        summary.to_csv(SUMMARY, index=False)
    print(f"summary: +{len(rows)} rows")

    # 3) บริบทตลาด
    # คำนวณ 5 วันล่าสุดใหม่ทุกรอบแล้วแทนของเดิม (กันกรณีรอบก่อนรันตอนตลาดยังไม่ปิด)
    ctx_old = pd.read_csv(CONTEXT) if CONTEXT.exists() else pd.DataFrame()
    spy = dailies["SPY"]
    ctx_rows = []
    for day in sorted(set(spy.index.date))[-5:]:
        r = {"date": day.isoformat()}
        for name, s in MARKET.items():
            d = dailies[s]
            row = d[d.index.date == day]
            r[f"{name}_close"] = round(float(row["Close"].iloc[-1]), 4) if not row.empty else None
            r[f"{name}_chg_pct"] = day_change(d, day)
        ctx_rows.append(r)
    if ctx_rows:
        ctx_new = pd.DataFrame(ctx_rows)
        if not ctx_old.empty:
            ctx_old = ctx_old[~ctx_old["date"].isin(ctx_new["date"])]
        pd.concat([ctx_old, ctx_new], ignore_index=True).sort_values("date").to_csv(CONTEXT, index=False)

    # 4) ข่าว
    today = pd.Timestamp.now(tz=ET).date().isoformat()
    news = {s: news_items(s) for s in WATCHLIST}
    (DATA / "news" / f"{today}.json").write_text(json.dumps(news, ensure_ascii=False, indent=2, default=str))
    print("done")


if __name__ == "__main__":
    main()
