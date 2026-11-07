#!/usr/bin/env python3
"""
ส่วนวิเคราะห์ที่ report.py ใช้: สมมติฐาน (มี base rate + edge), สถิติหลัง gap แยก intraday/daily,
ความผูกพันกับตลาด/กลุ่ม (R²), ตารางหลังงบ และบันทึกการเทรด (trades.csv)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
TRADES = ROOT / "trades.csv"
MIN_N = 10          # ตัวอย่างขั้นต่ำ
EDGE_MIN = 10.0     # |hit − base| ต่ำกว่านี้ (จุด %) = ไม่ต่างจากปกติ
GROUPS = {"intraday": ("live_1m", "backfill_1m", "backfill_5m"), "daily": ("backfill_1d",)}
GROUP_TH = {"intraday": "intraday (1 นาที/5 นาที)", "daily": "daily (รายวัน)"}


# ---------------- สมมติฐาน ----------------
def _pm_big(d: pd.DataFrame, U: pd.DataFrame) -> pd.Series:
    """|part_market| มากกว่าค่ากลางของทุกวันในชุดเดียวกัน"""
    return d["part_market"].abs() > U["part_market"].abs().median()


HYPOTHESES = [
    {"id": "H1", "name": "Gap ขึ้น 3–5% แล้วโดนขายเป็นรอบ = เทรดสั้น (ตามที่สังเกตเห็น)",
     "filter": "gap_pct >= 3 and gap_pct <= 5 and sell_waves >= 3",
     "success": lambda d, U: d["ret_5d"] < 0, "outcome": "ret_5d", "groups": ["intraday"],
     "meaning": "ราคาปิดอีก 5 วันต่ำกว่าวันนั้น (ret_5d < 0)"},
    {"id": "H1b", "name": "Gap ขึ้น ≥ 0.75 ATR แล้วโดนขายเป็นรอบ = เทรดสั้น (เทียบความผันผวนของหุ้นตัวนั้น)",
     "filter": "gap_atr >= 0.75 and sell_waves >= 3",
     "success": lambda d, U: d["ret_5d"] < 0, "outcome": "ret_5d", "groups": ["intraday"],
     "meaning": "ราคาปิดอีก 5 วันต่ำกว่าวันนั้น (ret_5d < 0)"},
    {"id": "H2", "name": "Gap ขึ้น (≥ 0.75 ATR) แล้วปิดเหนือ VWAP = มีแรงซื้อต่อเนื่อง",
     "filter": "gap_atr >= 0.75 and close_vs_vwap_pct > 0",
     "success": lambda d, U: d["ret_5d"] > 0, "outcome": "ret_5d", "groups": ["intraday"],
     "meaning": "ราคาปิดอีก 5 วันสูงกว่าวันนั้น (ret_5d > 0)"},
    {"id": "H3", "name": "วัน CPI/FOMC ตลาดขยับแรงกว่าวันปกติ (|part_market| สูงกว่า)",
     "filter": "events.str.contains('CPI|FOMC', na=False)",
     "success": _pm_big, "outcome": None, "groups": ["intraday", "daily"], "dedupe": "date",
     "meaning": "|SPY| วันนั้นสูงกว่าค่ากลางของทุกวัน (นับ 1 ครั้งต่อวัน)"},
]


def _status(n: int, edge: float) -> str:
    if n == 0:
        return "ยังไม่เกิดเหตุการณ์ตามเงื่อนไข"
    if n < MIN_N:
        return f"ตัวอย่างยังน้อย (n={n}) ยังสรุปไม่ได้"
    if abs(edge) < EDGE_MIN:
        return "ไม่ต่างจากปกติ"
    if edge > 0:
        return f"ดีกว่าปกติ {edge:+.0f} จุด — เริ่มเห็นแนวโน้มว่าจริง"
    return f"แย่กว่าปกติ {edge:+.0f} จุด — ข้อมูลไม่สนับสนุน"


def hypothesis_results(df: pd.DataFrame) -> list[dict]:
    res = []
    for h in HYPOTHESES:
        for g in h["groups"]:
            U = df[df["source"].isin(GROUPS[g])]
            if h.get("dedupe"):
                U = U.drop_duplicates(h["dedupe"])
            if h["outcome"]:
                U = U.dropna(subset=[h["outcome"]])
            try:
                sub = U.query(h["filter"], engine="python")
            except Exception:  # noqa: BLE001
                sub = U.iloc[0:0]
            n = len(sub)
            hit = float(h["success"](sub, U).mean() * 100) if n else np.nan
            base = float(h["success"](U, U).mean() * 100) if len(U) else np.nan
            edge = hit - base if n else np.nan
            r = {**h, "group": g, "n": n, "days": sub["date"].nunique() if n else 0, "hit": hit,
                 "base": base, "edge": edge, "N": len(U), "status": _status(n, edge),
                 "avg": float(sub[h["outcome"]].mean()) if n and h["outcome"] else np.nan,
                 "avg_all": float(U[h["outcome"]].mean()) if h["outcome"] and len(U) else np.nan,
                 "tickers": ", ".join(sorted(sub["ticker"].unique())) if n and not h.get("dedupe") else "",
                 "recent": ([[d, ""] for d in sub.sort_values("date")["date"].tail(3)] if h.get("dedupe") else
                            sub.sort_values("date").tail(3)[["date", "ticker"]].values.tolist()) if n else []}
            if h["id"] == "H3":
                ev = U["events"].fillna("").str.contains("CPI|FOMC")
                r["extra"] = (f"|SPY| เฉลี่ย วัน CPI/FOMC {U.loc[ev, 'part_market'].abs().mean():.2f}% "
                              f"(n={int(ev.sum())} วัน) เทียบวันอื่น {U.loc[~ev, 'part_market'].abs().mean():.2f}% "
                              f"(n={int((~ev).sum())} วัน)")
            res.append(r)
    return res


# ---------------- ผลหลัง gap แยก source ----------------
def label_stats(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for g, srcs in GROUPS.items():
        U = df[df["source"].isin(srcs)]
        base = (U["ret_5d"].dropna() > 0).mean() * 100 if U["ret_5d"].notna().any() else np.nan
        G = U[U["label"] != "NO_GAP"].groupby("label")
        if not len(G):
            continue
        t = G.agg(n=("ticker", "size"), days=("date", "nunique"), r1=("ret_1d", "mean"),
                  r3=("ret_3d", "mean"), r5=("ret_5d", "mean"))
        t["win5"] = G["ret_5d"].apply(lambda x: (x.dropna() > 0).mean() * 100 if x.notna().any() else np.nan)
        t["base"] = base
        t["edge"] = t["win5"] - base
        out[g] = t.sort_values("n", ascending=False)
    return out


# ---------------- ผูกกับตลาด/กลุ่ม ----------------
def linkage(df: pd.DataFrame) -> list[dict]:
    out = []
    for tk, g in df.sort_values("date").groupby("ticker"):
        g = g.dropna(subset=["r2_peer_60", "r2_spy_60"])
        if g.empty:
            continue
        now, prev = g.iloc[-1], (g.iloc[-61] if len(g) > 60 else None)
        out.append({"ticker": tk, "peer": now["peer"], "date": now["date"],
                    "r2_peer": now["r2_peer_60"], "r2_spy": now["r2_spy_60"],
                    "beta_peer": now["beta_peer_60"], "beta_spy": now["beta_spy_60"],
                    "r2_peer_prev": prev["r2_peer_60"] if prev is not None else np.nan,
                    "r2_spy_prev": prev["r2_spy_60"] if prev is not None else np.nan,
                    "r2_peer_5y": g["r2_peer_60"].mean(), "r2_spy_5y": g["r2_spy_60"].mean()})
    return out


def linkage_text(r: dict) -> str:
    own = 100 - max(r["r2_peer"], r["r2_spy"]) * 100

    def trend(now, prev):
        if pd.isna(prev):
            return ""
        d = (now - prev) * 100
        return " (ทรงตัว)" if abs(d) < 5 else (f" (เพิ่มขึ้น {d:+.0f} จุดจาก 60 วันก่อน)" if d > 0 else f" (ลดลง {d:+.0f} จุดจาก 60 วันก่อน)")
    return (f"<b>{r['ticker']}</b>: 60 วันล่าสุด <b>{r['r2_peer'] * 100:.0f}%</b> ของการขยับอธิบายได้ด้วยกลุ่ม "
            f"{r['peer']}{trend(r['r2_peer'], r['r2_peer_prev'])}, <b>{r['r2_spy'] * 100:.0f}%</b> ด้วย SPY"
            f"{trend(r['r2_spy'], r['r2_spy_prev'])}, ที่เหลือราว <b>{own:.0f}%</b> เป็นปัจจัยเฉพาะตัว · "
            f"beta เทียบ SPY {r['beta_spy']:.2f} / เทียบ {r['peer']} {r['beta_peer']:.2f} "
            f"<span class='mute'>(เฉลี่ย 5 ปี: กลุ่ม {r['r2_peer_5y'] * 100:.0f}% · SPY {r['r2_spy_5y'] * 100:.0f}%)</span>")


# ---------------- หลังงบ ----------------
def post_earnings(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    e = df[df["earnings_reaction"].astype(str) == "True"].copy()
    if e.empty:
        return e, pd.DataFrame()
    sgn = np.sign(e["change_pct"]) * np.sign(e["ret_5d"])
    e["after"] = np.where(e["ret_5d"].isna(), "รอข้อมูล", np.where(sgn > 0, "ไปต่อ", np.where(sgn < 0, "กลับตัว", "ทรงตัว")))
    rows = []
    for tk, g in e.groupby("ticker"):
        done = g[g["ret_5d"].notna()]
        allt = df[(df["ticker"] == tk) & df["ret_5d"].notna() & (df["earnings_reaction"].astype(str) != "True")]
        base = (np.sign(allt["change_pct"]) * np.sign(allt["ret_5d"]) > 0).mean() * 100 if len(allt) else np.nan
        cont = (done["after"] == "ไปต่อ").mean() * 100 if len(done) else np.nan
        rows.append({"ticker": tk, "n": len(g), "n5": len(done),
                     "abs_day1": g["change_pct"].abs().mean(), "abs_normal": allt["change_pct"].abs().mean(),
                     "up_share": (g["change_pct"] > 0).mean() * 100,
                     "cont": cont, "base": base, "edge": cont - base if len(done) else np.nan,
                     "timing": ", ".join(f"{k} {v}" for k, v in g["earnings_timing"].value_counts().items())})
    return e.sort_values("date", ascending=False), pd.DataFrame(rows)


# ---------------- บันทึกการเทรด ----------------
TRADE_COLS = ["date", "ticker", "action", "price", "shares", "reason", "emotion", "plan_followed", "note"]


def load_trades() -> pd.DataFrame:
    if not TRADES.exists():
        return pd.DataFrame(columns=TRADE_COLS)
    t = pd.read_csv(TRADES, comment="#", dtype=str).fillna("")
    if t.empty:
        return t
    t["price"] = pd.to_numeric(t["price"], errors="coerce")
    t["shares"] = pd.to_numeric(t["shares"], errors="coerce")
    t["action"] = t["action"].str.upper().str.strip()
    t["ticker"] = t["ticker"].str.upper().str.strip()
    return t


def trades_vs_market(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    t = load_trades()
    if t.empty:
        return t, []
    s = df.sort_values(["ticker", "date"]).copy()
    s["close_5d"] = s.groupby("ticker")["close"].shift(-5)
    m = t.merge(s[["date", "ticker", "label", "driver", "events", "change_pct", "gap_pct", "close", "close_5d"]],
                on=["date", "ticker"], how="left")
    m["ret_5d_after"] = (m["close_5d"] / m["price"] - 1) * 100
    notes = []
    for act, g in m.groupby("action"):
        n = len(g)
        lab = g["label"].fillna("ไม่มีข้อมูล").value_counts().head(2)
        drv = g["driver"].fillna("ไม่มีข้อมูล").value_counts().head(1)
        ev = (g["events"].fillna("") != "").mean() * 100
        avg = g["ret_5d_after"].mean()
        plan = (g["plan_followed"].str.upper() == "Y").mean() * 100
        emo = g["emotion"].replace("", np.nan).dropna().value_counts().head(2)
        txt = (f"<b>{act}</b> {n} ครั้ง: รูปแบบที่เจอบ่อย " + ", ".join(f"{k} ({v})" for k, v in lab.items())
               + f" · ตัวขับ {', '.join(f'{k} ({v})' for k, v in drv.items())} · มีเหตุการณ์พิเศษ {ev:.0f}%"
               + (f" · 5 วันหลังเทรดราคาเปลี่ยนเฉลี่ย {avg:+.1f}%" if pd.notna(avg) else "")
               + f" · ทำตามแผน {plan:.0f}%"
               + (f" · อารมณ์ที่พบบ่อย: {', '.join(emo.index)}" if len(emo) else ""))
        if n < MIN_N:
            txt += f" <span class='mute'>(n={n} ยังน้อย ยังสรุปไม่ได้)</span>"
        notes.append(txt)
    return m, notes
