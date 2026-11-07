#!/usr/bin/env python3
"""
คำนวณคอลัมน์อนุพันธ์ทั้งหมดใหม่ทุกรอบ จาก daily_summary + data/intraday + data/earnings.csv
(ไม่แตะราคา OHLC — คำนวณจากตัวเลขที่มีอยู่เท่านั้น จึงย้อนหลังได้ทุกแถวที่ข้อมูลพอ)

- atr_pct      : ATR 14 วันก่อนหน้า เป็น % ของราคา (True Range / ราคาปิดวันก่อน เฉลี่ย 14 วัน ไม่รวมวันนั้น)
- gap_atr      : gap_pct / atr_pct  (gap ใหญ่แค่ไหนเมื่อเทียบความผันผวนปกติของหุ้นตัวนั้น)
- label        : ใช้ |gap_atr| >= GAP_ATR_THRESHOLD เป็นเกณฑ์หลักว่า "มี gap" (ถ้าไม่มี ATR ใช้ gap_pct >= 2%)
- driver       : MARKET / SECTOR / OWN หรือ QUIET ถ้า |change| < 1% หรือ < 0.5 × atr_pct
- beta/r2 60 วัน: change_pct เทียบ spy_change_pct และ peer_change_pct
- earnings_timing / earnings_reaction : BMO (ก่อนเปิด) / AMC (หลังปิด) / DURING และ session แรกที่ตลาดตอบสนองงบ
- ret_first30 / ret_mid / ret_last60 / vol_share_first30 / vol_share_last60 : จากแท่งนาที (intraday เท่านั้น)
- pre_vol_ratio : pre_volume / เฉลี่ย 10 วันก่อน (Yahoo ให้ pre-market volume = 0 → มักว่าง)
- pre_active_min / pre_min_ratio : จำนวนนาทีก่อนตลาดเปิดที่มีการซื้อขาย (แทน volume) / เฉลี่ย 10 วันก่อน
"""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

import capture as c

GAP_ATR_THRESHOLD = 0.75
ATR_DAYS = 14
QUIET_ABS, QUIET_ATR = 1.0, 0.5
ROLL = 60
INTRADAY_SOURCES = ("live_1m", "backfill_1m", "backfill_5m")
ONE_MIN_SOURCES = ("live_1m", "backfill_1m")


# ---------------- ATR / gap_atr / label ----------------
def add_atr(df: pd.DataFrame) -> pd.DataFrame:
    pc = df["prev_close"]
    tr = (np.maximum(df["high"], pc) - np.minimum(df["low"], pc)) / pc * 100
    df["_tr"] = tr
    df["atr_pct"] = (df.groupby("ticker")["_tr"]
                       .transform(lambda s: s.rolling(ATR_DAYS, min_periods=10).mean().shift(1))).round(2)
    df["gap_atr"] = (df["gap_pct"] / df["atr_pct"]).round(2)
    return df.drop(columns="_tr")


def label_row(gap, gap_atr, o, cl, vw, filled) -> str:
    if pd.notna(gap_atr):
        is_gap = abs(gap_atr) >= GAP_ATR_THRESHOLD
    else:
        is_gap = pd.notna(gap) and abs(gap) >= c.GAP_THRESHOLD
    if not is_gap or pd.isna(gap):
        return "NO_GAP"
    filled = bool(filled) if pd.notna(filled) else False
    if pd.isna(vw):                                    # รายวัน ไม่มี VWAP
        if gap > 0:
            return "GAP_UP_GO" if cl > o else ("GAP_UP_FADE" if filled or cl < o else "GAP_UP_MIXED")
        return "GAP_DOWN_GO" if cl < o else ("GAP_DOWN_REVERSAL" if filled or cl > o else "GAP_DOWN_MIXED")
    if gap > 0:
        if cl > o and cl > vw:
            return "GAP_UP_GO"
        if cl < vw and (filled or cl < o):
            return "GAP_UP_FADE"
        return "GAP_UP_MIXED"
    if cl < o and cl < vw:
        return "GAP_DOWN_GO"
    if cl > vw and (filled or cl > o):
        return "GAP_DOWN_REVERSAL"
    return "GAP_DOWN_MIXED"


# ---------------- ตัวขับ ----------------
def add_driver(df: pd.DataFrame) -> pd.DataFrame:
    parts = df[["part_market", "part_sector", "part_own"]].abs()
    drv = parts.idxmax(axis=1, skipna=True).map({"part_market": "MARKET", "part_sector": "SECTOR", "part_own": "OWN"})
    drv[parts.isna().any(axis=1)] = np.nan
    chg = df["change_pct"].abs()
    quiet = (chg < QUIET_ABS) | (df["atr_pct"].notna() & (chg < QUIET_ATR * df["atr_pct"]))
    drv[quiet & drv.notna()] = "QUIET"
    df["driver"] = drv
    return df


def add_beta_r2(df: pd.DataFrame) -> pd.DataFrame:
    for ref, tag in (("spy_change_pct", "spy"), ("peer_change_pct", "peer")):
        b, r = [], []
        for _, g in df.groupby("ticker", sort=False):
            y, x = g["change_pct"], g[ref]
            cov = y.rolling(ROLL, min_periods=40).cov(x)
            var = x.rolling(ROLL, min_periods=40).var()
            corr = y.rolling(ROLL, min_periods=40).corr(x)
            b.append((cov / var).round(2))
            r.append((corr ** 2).round(3))
        df[f"beta_{tag}_60"] = pd.concat(b)
        df[f"r2_{tag}_60"] = pd.concat(r)
    return df


# ---------------- งบ ----------------
def timing_of(t: str) -> str:
    if not t:
        return "UNKNOWN"
    hh, mm = map(int, t.split(":"))
    tt = time(hh, mm)
    if tt < time(9, 30):
        return "BMO"
    if tt >= time(16, 0):
        return "AMC"
    return "DURING"


def add_earnings(df: pd.DataFrame) -> pd.DataFrame:
    df["earnings_reaction"] = False
    df["earnings_timing"] = ""
    df["earnings_date"] = ""
    if not c.EARNINGS.exists():
        return df
    e = pd.read_csv(c.EARNINGS, dtype=str).fillna("")
    if "timing" not in e:
        e["timing"] = [timing_of(t) for t in e.get("time_et", pd.Series([""] * len(e)))]
    for r in e.itertuples(index=False):
        if r.timing not in ("BMO", "AMC", "DURING"):
            continue
        rows = df.index[(df["ticker"] == r.ticker) & (df["date"] >= r.date)]
        if not len(rows):
            continue
        dates = df.loc[rows, "date"].sort_values()
        if r.timing == "AMC":
            nxt = dates[dates > r.date]
            if not len(nxt):
                continue
            i = nxt.index[0]
        else:
            i = dates.index[0]                         # วันประกาศเอง (หรือวันทำการถัดไปถ้าตรงวันหยุด)
        df.at[i, "earnings_reaction"] = True
        df.at[i, "earnings_timing"] = r.timing
        df.at[i, "earnings_date"] = r.date
    return df


# ---------------- ช่วงเวลาในวัน (intraday) ----------------
def segments(reg: pd.DataFrame, o: float, cl: float) -> dict:
    """ret_first30 / ret_mid / ret_last60 (%) และสัดส่วน volume ช่วงแรก/ช่วงท้าย จากแท่งช่วงตลาดเปิด"""
    out = dict.fromkeys(["ret_first30", "ret_mid", "ret_last60", "vol_share_first30", "vol_share_last60"])
    if reg.empty or not o or not cl:
        return out
    t = reg.index.time
    a, b = reg[t < time(10, 0)], reg[t < time(15, 0)]
    if a.empty or b.empty:
        return out
    p10, p15 = float(a["Close"].iloc[-1]), float(b["Close"].iloc[-1])
    vol = float(reg["Volume"].sum())
    out.update({"ret_first30": round((p10 / o - 1) * 100, 2), "ret_mid": round((p15 / p10 - 1) * 100, 2),
                "ret_last60": round((cl / p15 - 1) * 100, 2)})
    if vol > 0:
        out["vol_share_first30"] = round(float(a["Volume"].sum()) / vol * 100, 1)
        out["vol_share_last60"] = round(float(reg[t >= time(15, 0)]["Volume"].sum()) / vol * 100, 1)
    return out


def _read_intraday(day: str, tk: str) -> pd.DataFrame | None:
    f = c.DATA / "intraday" / day / f"{tk}.csv"
    if not f.exists():
        return None
    x = pd.read_csv(f, index_col=0)
    x.index = pd.to_datetime(x.index, utc=True).tz_convert(c.ET)
    return x


def add_intraday(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["ret_first30", "ret_mid", "ret_last60", "vol_share_first30", "vol_share_last60"]
    for col in cols + ["pre_active_min"]:
        if col not in df:
            df[col] = np.nan
    intra = df["source"].isin(INTRADAY_SOURCES)
    df.loc[~intra, cols] = np.nan                     # รายวันไม่มีข้อมูลระหว่างวัน
    for i in df.index[intra]:
        need_seg = df.loc[i, cols].isna().all()
        need_pre = df.loc[i, "source"] in ONE_MIN_SOURCES and pd.isna(df.loc[i, "pre_active_min"])
        if not (need_seg or need_pre):
            continue
        x = _read_intraday(df.at[i, "date"], df.at[i, "ticker"])
        if x is None:
            continue
        day = pd.Timestamp(df.at[i, "date"]).date()
        pre, reg = c.split_session(x, day)
        if need_seg:
            for k, v in segments(reg, df.at[i, "open"], df.at[i, "close"]).items():
                df.at[i, k] = v
        if need_pre:
            df.at[i, "pre_active_min"] = len(pre)
    # อัตราส่วนเทียบค่าเฉลี่ย 10 วันก่อนหน้า (ของหุ้นตัวเดียวกัน)
    def ratio(col):
        prev = df.groupby("ticker")[col].transform(lambda s: s.shift(1).rolling(10, min_periods=5).mean())
        return (df[col] / prev.where(prev > 0)).round(2)
    df["pre_vol_ratio"] = ratio("pre_volume") if "pre_volume" in df else np.nan
    df["pre_min_ratio"] = ratio("pre_active_min")
    return df


# ---------------- รวม ----------------
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df = add_atr(df)
    df["label"] = [label_row(*a) for a in zip(df["gap_pct"], df["gap_atr"], df["open"], df["close"],
                                              df.get("vwap", pd.Series(np.nan, index=df.index)), df["gap_filled"])]
    df = add_driver(df)
    df = add_beta_r2(df)
    df = add_earnings(df)
    df = add_intraday(df)
    if "sell_waves" in df:
        df["sell_waves"] = pd.to_numeric(df["sell_waves"], errors="coerce").round().astype("Int64")
    return df.sort_values(["date", "ticker"]).reset_index(drop=True)


if __name__ == "__main__":
    s = c.load_summary()
    s = enrich(s)
    s.to_csv(c.SUMMARY, index=False)
    print(f"enriched {len(s)} rows")
