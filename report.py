#!/usr/bin/env python3
"""
สร้างรายงาน report.html และปฏิทิน calendar.ics จากข้อมูลใน data/
  python report.py            → report.html + calendar.ics
  python report.py --demo     → ใส่แถบ "ข้อมูลสมมติ" (ใช้ตอนทดสอบ)
"""
from __future__ import annotations

import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ET = ZoneInfo("America/New_York")
BKK = ZoneInfo("Asia/Bangkok")
MIN_N = 10   # ตัวอย่างขั้นต่ำก่อนจะเรียกว่า "เริ่มเห็นแนวโน้ม"

# ---------- สมมติฐาน (ดูคำอธิบายใน hypotheses.md) ----------
# filter = เงื่อนไขเลือกแถว (pandas query), success = เงื่อนไขที่ถือว่า "สมมติฐานถูก"
HYPOTHESES = [
    {"id": "H1", "name": "Gap ขึ้น 3–5% แล้วโดนขายเป็นรอบ = เทรดสั้น",
     "filter": "gap_pct >= 3 and gap_pct <= 5 and sell_waves >= 3",
     "success": lambda d: d["ret_5d"] < 0, "outcome": "ret_5d",
     "meaning": "ราคาใน 5 วันถัดไปต่ำกว่าวันนั้น"},
    {"id": "H2", "name": "Gap ขึ้นแล้วปิดเหนือ VWAP = มีแรงซื้อต่อเนื่อง",
     "filter": "gap_pct >= 2 and close_vs_vwap_pct > 0",
     "success": lambda d: d["ret_5d"] > 0, "outcome": "ret_5d",
     "meaning": "ราคาใน 5 วันถัดไปสูงกว่าวันนั้น"},
    {"id": "H3", "name": "วัน CPI/FOMC หุ้นขยับตามตลาดมากกว่าตามตัวเอง",
     "filter": "events.str.contains('CPI|FOMC', na=False)",
     "success": lambda d: d["driver"] == "MARKET", "outcome": None,
     "meaning": "ส่วนที่มาจากตลาด (SPY) ใหญ่ที่สุด"},
]

LABEL_TH = {
    "GAP_UP_GO": "Gap ขึ้น → ไปต่อ", "GAP_UP_FADE": "Gap ขึ้น → โดนขาย", "GAP_UP_MIXED": "Gap ขึ้น → ไม่ชัด",
    "GAP_DOWN_GO": "Gap ลง → ลงต่อ", "GAP_DOWN_REVERSAL": "Gap ลง → ดีดกลับ", "GAP_DOWN_MIXED": "Gap ลง → ไม่ชัด",
    "NO_GAP": "ไม่มี gap",
}
DRIVER_TH = {"OWN": "ตัวเอง", "SECTOR": "กลุ่ม", "MARKET": "ตลาด"}


def esc(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x))


def pct(x, d=1) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"{x:+.{d}f}%"


def cls(x) -> str:
    return "" if x is None or pd.isna(x) else ("up" if x > 0 else "down" if x < 0 else "")


# ---------- ส่วนคำนวณ ----------
def driver_share(df: pd.DataFrame) -> pd.DataFrame:
    big = df[df["change_pct"].abs() >= 1].dropna(subset=["driver"])
    if big.empty:
        return pd.DataFrame()
    t = big.groupby("ticker")["driver"].value_counts(normalize=True).unstack(fill_value=0) * 100
    t["n"] = big.groupby("ticker").size()
    return t


def label_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df["label"] != "NO_GAP"].groupby("label")
    if not len(g):
        return pd.DataFrame()
    out = g.agg(n=("ticker", "size"), r1=("ret_1d", "mean"), r3=("ret_3d", "mean"), r5=("ret_5d", "mean"))
    out["win5"] = g.apply(lambda x: (x["ret_5d"].dropna() > 0).mean() * 100 if x["ret_5d"].notna().any() else np.nan)
    return out.sort_values("n", ascending=False)


def hypothesis_results(df: pd.DataFrame) -> list:
    res = []
    for h in HYPOTHESES:
        try:
            sub = df.query(h["filter"], engine="python")
        except Exception:  # noqa: BLE001  (คอลัมน์ยังไม่มี เช่นข้อมูลรายวันไม่มี VWAP)
            sub = df.iloc[0:0]
        if h["outcome"]:
            sub = sub.dropna(subset=[h["outcome"]])
        n = len(sub)
        hit = float(h["success"](sub).mean() * 100) if n else np.nan
        avg = float(sub[h["outcome"]].mean()) if n and h["outcome"] else np.nan
        if n == 0:
            status = "ยังไม่เกิดเหตุการณ์ตามเงื่อนไข"
        elif n < MIN_N:
            status = f"ตัวอย่างยังน้อย (n={n}) ยังสรุปไม่ได้"
        elif hit >= 65:
            status = "เริ่มเห็นแนวโน้มว่าจริง"
        elif hit <= 35:
            status = "เริ่มเห็นแนวโน้มว่าไม่จริง"
        else:
            status = "ยังก้ำกึ่ง ไม่ต่างจากการสุ่ม"
        res.append({**h, "n": n, "hit": hit, "avg": avg, "status": status,
                    "tickers": ", ".join(sorted(sub["ticker"].unique())) if n else ""})
    return res


def conclusions(df: pd.DataFrame, ds: pd.DataFrame) -> list[str]:
    out = []
    for t, r in ds.iterrows():
        top = max(DRIVER_TH, key=lambda k: r.get(k, 0))
        out.append(f"<b>{esc(t)}</b>: ในวันที่ขยับเกิน 1% (n={int(r['n'])}) "
                   f"{r.get(top, 0):.0f}% มาจากปัจจัย<b>{DRIVER_TH[top]}</b> "
                   f"(ตัวเอง {r.get('OWN', 0):.0f}% · กลุ่ม {r.get('SECTOR', 0):.0f}% · ตลาด {r.get('MARKET', 0):.0f}%)")
    ev = df["events"].fillna("").str.contains("CPI|FOMC")
    if ev.any() and (~ev).any():
        a, b = df.loc[ev, "change_pct"].abs().mean(), df.loc[~ev, "change_pct"].abs().mean()
        out.append(f"วัน CPI/FOMC หุ้นในลิสต์ขยับเฉลี่ย <b>{a:.1f}%</b> เทียบวันปกติ {b:.1f}% "
                   f"(n={int(ev.sum())} แถว)")
    er = df["events"].fillna("").str.contains("EARNINGS")
    if er.any():
        out.append(f"ช่วงประกาศงบ (±1 วัน) ขยับเฉลี่ย <b>{df.loc[er, 'change_pct'].abs().mean():.1f}%</b> "
                   f"เทียบวันอื่น {df.loc[~er, 'change_pct'].abs().mean():.1f}% (n={int(er.sum())} แถว)")
    return out


# ---------- ปฏิทิน ----------
def load_calendar() -> pd.DataFrame:
    frames = []
    if (ROOT / "events.csv").exists():
        frames.append(pd.read_csv(ROOT / "events.csv", dtype=str).fillna(""))
    if (DATA / "earnings.csv").exists():
        e = pd.read_csv(DATA / "earnings.csv", dtype=str).fillna("")
        frames.append(pd.DataFrame({"date": e["date"], "type": "EARNINGS", "ticker": e["ticker"],
                                    "title": e["ticker"] + " ประกาศงบ (วันจาก Yahoo อาจเป็นวันประมาณการ)",
                                    "time_et": ""}))
    if not frames:
        return pd.DataFrame(columns=["date", "type", "title", "ticker", "time_et"])
    cal = pd.concat(frames, ignore_index=True)
    cal["d"] = pd.to_datetime(cal["date"]).dt.date
    return cal.sort_values("d")


def to_bkk(row) -> str:
    if not row["time_et"]:
        return "ทั้งวัน"
    h, m = map(int, row["time_et"].split(":"))
    t = datetime(row["d"].year, row["d"].month, row["d"].day, h, m, tzinfo=ET).astimezone(BKK)
    return t.strftime("%d %b %H:%M") + " (ไทย)"


def write_ics(cal: pd.DataFrame, path: Path) -> None:
    today = datetime.now(ET).date()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//market-capture//TH", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Market Capture – Watchlist", "X-WR-TIMEZONE:Asia/Bangkok"]
    for _, r in cal[cal["d"] >= today - timedelta(days=7)].iterrows():
        uid = f"{r['type']}-{r['ticker'] or 'ALL'}-{r['date']}@market-capture"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"SUMMARY:{r['title']}"]
        if r["time_et"]:
            h, m = map(int, r["time_et"].split(":"))
            st = datetime(r["d"].year, r["d"].month, r["d"].day, h, m, tzinfo=ET).astimezone(timezone.utc)
            lines += [f"DTSTART:{st:%Y%m%dT%H%M%SZ}", f"DTEND:{st + timedelta(minutes=30):%Y%m%dT%H%M%SZ}",
                      "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Reminder", "TRIGGER:-PT30M", "END:VALARM"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{r['d']:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{r['d'] + timedelta(days=1):%Y%m%d}"]
        lines += ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


# ---------- HTML ----------
CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--mute:#6e6e73;--line:#e4e2dd;--up:#1a8f5a;--down:#d0453a;
--mkt:#8a8f98;--sec:#4f7cff;--own:#f29b30;--warn:#fff4d6;--warnink:#7a5600;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--card:#1e1e21;--ink:#f2f2f2;
--mute:#9a9aa0;--line:#2e2e33;--up:#3ccf8e;--down:#ff6b5e;--warn:#3a3000;--warnink:#ffd76a;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 "Noto Sans Thai","Prompt",system-ui,sans-serif}
.wrap{max-width:1100px;margin:auto;padding:24px 16px 60px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}.mute{color:var(--mute);font-size:13px}
.demo{background:var(--warn);color:var(--warnink);padding:10px 14px;border-radius:10px;margin:12px 0;font-weight:600}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.big{font-size:22px;font-weight:700}.up{color:var(--up)}.down{color:var(--down)}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--line);margin:2px 4px 0 0}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--line);margin:8px 0 4px}
.legend span{font-size:12px;margin-right:10px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child,td.l,th.l{text-align:left}th{color:var(--mute);font-weight:600}tr:last-child td{border-bottom:0}
ul.c{margin:0;padding-left:18px}ul.c li{margin:6px 0}
"""


def bar(r) -> str:
    vals = {"MARKET": r.get("part_market"), "SECTOR": r.get("part_sector"), "OWN": r.get("part_own")}
    if any(v is None or pd.isna(v) for v in vals.values()):
        return ""
    tot = sum(abs(v) for v in vals.values()) or 1
    col = {"MARKET": "var(--mkt)", "SECTOR": "var(--sec)", "OWN": "var(--own)"}
    segs = "".join(f'<div style="width:{abs(v) / tot * 100:.1f}%;background:{col[k]}"></div>' for k, v in vals.items())
    txt = " · ".join(f"{DRIVER_TH[k]} {pct(v)}" for k, v in vals.items())
    return f'<div class="bar">{segs}</div><div class="mute">{txt}</div>'


def build(demo: bool) -> str:
    import capture  # ใช้ load_summary เพื่อรวม notes.csv
    s = capture.load_summary()
    ctx = pd.read_csv(DATA / "market_context.csv") if (DATA / "market_context.csv").exists() else pd.DataFrame()
    s["events"] = s.get("events", pd.Series("", index=s.index)).fillna("")
    last = s["date"].max()
    today_rows = s[s["date"] == last]
    cal = load_calendar()
    ds = driver_share(s)
    p = []
    p.append(f"<h1>Market Capture · {esc(last)}</h1>")
    p.append(f'<div class="mute">ข้อมูล {esc(s["date"].min())} ถึง {esc(last)} · {len(s)} แถว · '
             + " · ".join(f"{k} {v}" for k, v in s["source"].value_counts().items()) + "</div>")
    if demo:
        p.append('<div class="demo">ตัวอย่างหน้าตา: ตัวเลขทั้งหมดเป็นข้อมูลสมมติ ไม่ใช่ราคาจริง</div>')
    from glossary import glossary_html
    from volume_profile import shared_head
    p.append(shared_head() + glossary_html())

    # ตลาด
    if not ctx.empty and last in set(ctx["date"]):
        c = ctx[ctx["date"] == last].iloc[0]
        ev_today = today_rows["events"].str.split(";").explode().replace("", np.nan).dropna().unique()
        p.append("<h2>ภาพรวมตลาดวันล่าสุด</h2><div class='grid'>")
        for k, name in [("SPY", "S&P 500 (SPY)"), ("QQQ", "Nasdaq (QQQ)"), ("VIX", "VIX"),
                        ("US10Y", "ยีลด์ 10 ปี"), ("OIL", "น้ำมัน")]:
            v = c.get(f"{k}_chg_pct")
            p.append(f"<div class='card'><div class='mute'>{name}</div><div class='big {cls(v)}'>{pct(v, 2)}</div>"
                     f"<div class='mute'>{esc(c.get(f'{k}_close'))}</div></div>")
        p.append("</div>")
        if len(ev_today):
            p.append("<p>" + "".join(f"<span class='tag'>{esc(e)}</span>" for e in ev_today) + "</p>")

    # รายตัว
    p.append("<h2>รายตัววันล่าสุด</h2><div class='legend'><span><i class='dot' style='background:var(--mkt)'></i>ตลาด</span>"
             "<span><i class='dot' style='background:var(--sec)'></i>กลุ่ม</span>"
             "<span><i class='dot' style='background:var(--own)'></i>ตัวเอง</span></div><div class='grid'>")
    for _, r in today_rows.iterrows():
        tags = "".join(f"<span class='tag'>{esc(e)}</span>" for e in str(r["events"]).split(";") if e)
        extra = (f"<div class='mute'>pre-market {pct(r.get('pre_gap_pct'))} · VWAP {pct(r.get('close_vs_vwap_pct'))}"
                 f" · คลื่นขาย {esc(r.get('sell_waves'))}</div>") if pd.notna(r.get("vwap")) else ""
        note = f"<div class='mute'>📝 {esc(r['notes'])}</div>" if pd.notna(r.get("notes")) and r.get("notes") else ""
        p.append(f"<div class='card'><b>{esc(r['ticker'])}</b> <span class='mute'>vs {esc(r['peer'])}</span>"
                 f"<div class='big {cls(r['change_pct'])}'>${r['close']:,.2f} "
                 f"<span style='font-size:15px'>{pct(r['change_pct'], 2)}</span></div>"
                 f"<div>gap {pct(r['gap_pct'])} · {esc(LABEL_TH.get(r['label'], r['label']))}</div>{extra}"
                 f"{bar(r)}<div>ตัวขับหลัก: <b>{esc(DRIVER_TH.get(r.get('driver'), '–'))}</b></div>{tags}{note}</div>")
    p.append("</div>")

    # ข้อสรุปปัจจัย
    p.append("<h2>ข้อสรุปปัจจัยภายนอก / ภายใน (ทั้งช่วงข้อมูล)</h2><div class='card'><ul class='c'>")
    p += [f"<li>{x}</li>" for x in conclusions(s, ds)] or ["<li>ข้อมูลยังไม่พอ</li>"]
    p.append("</ul><div class='mute'>ตลาด = SPY · กลุ่ม = ETF/peer เหนือกว่า SPY · ตัวเอง = หุ้นเหนือกว่า peer "
             "(สะท้อนข่าว/งบของบริษัท)</div></div>")

    # กราฟช่วงเวลาซื้อ/ขายใน 1 วัน (จากแท่ง 1 นาที)
    import intraday_price
    p.append(intraday_price.section_html(sorted(s["ticker"].unique())))
    from volume_profile import section_html
    p.append(section_html(sorted(s["ticker"].unique())))

    # สมมติฐาน
    p.append("<h2>สมมติฐาน</h2><div class='tbl'><table><tr><th class='l'>สมมติฐาน</th><th>n</th>"
             "<th>ถูก</th><th>ผลเฉลี่ย 5 วัน</th><th class='l'>สถานะ</th></tr>")
    for h in hypothesis_results(s):
        hit = f"{h['hit']:.0f}%" if not np.isnan(h["hit"]) else "–"
        p.append(f"<tr><td class='l'><b>{h['id']}</b> {esc(h['name'])}<div class='mute'>ถูก = {esc(h['meaning'])}"
                 f"{' · ' + esc(h['tickers']) if h['tickers'] else ''}</div></td><td>{h['n']}</td><td>{hit}</td>"
                 f"<td class='{cls(h['avg'])}'>{pct(h['avg'])}</td><td class='l'>{esc(h['status'])}</td></tr>")
    p.append("</table></div>")

    # label stats
    ls = label_stats(s)
    if not ls.empty:
        p.append("<h2>ผลหลัง gap แยกตามรูปแบบ</h2><div class='tbl'><table><tr><th class='l'>รูปแบบ</th><th>n</th>"
                 "<th>+1 วัน</th><th>+3 วัน</th><th>+5 วัน</th><th>% บวกใน 5 วัน</th></tr>")
        for lab, r in ls.iterrows():
            warn = " <span class='mute'>(น้อย)</span>" if r["n"] < MIN_N else ""
            win = "–" if pd.isna(r["win5"]) else f"{r['win5']:.0f}%"
            p.append(f"<tr><td class='l'>{esc(LABEL_TH.get(lab, lab))}{warn}</td><td>{int(r['n'])}</td>"
                     + "".join(f"<td class='{cls(r[k])}'>{pct(r[k])}</td>" for k in ("r1", "r3", "r5"))
                     + f"<td>{win}</td></tr>")
        p.append("</table></div>")

    # ปฏิทิน
    today = datetime.now(ET).date()
    up = cal[(cal["d"] >= today) & (cal["d"] <= today + timedelta(days=60))]
    p.append("<h2>ปฏิทิน 60 วันข้างหน้า</h2><div class='tbl'><table><tr><th class='l'>วันที่</th><th class='l'>เวลาไทย</th>"
             "<th class='l'>เหตุการณ์</th></tr>")
    p += [f"<tr><td class='l'>{r['d']:%a %d %b %Y}</td><td class='l'>{esc(to_bkk(r))}</td><td class='l'>{esc(r['title'])}</td></tr>"
          for _, r in up.iterrows()] or ["<tr><td class='l' colspan=3>ไม่มี</td></tr>"]
    p.append("</table></div>")

    # 10 วันล่าสุด
    rec = s[s["date"].isin(sorted(s["date"].unique())[-10:])].sort_values(["date", "ticker"], ascending=[False, True])
    p.append("<h2>10 วันทำการล่าสุด</h2><div class='tbl'><table><tr><th class='l'>วันที่</th><th class='l'>หุ้น</th>"
             "<th>เปลี่ยน</th><th>gap</th><th class='l'>รูปแบบ</th><th class='l'>ตัวขับ</th><th class='l'>เหตุการณ์</th>"
             "<th>+5 วัน</th></tr>")
    for _, r in rec.iterrows():
        p.append(f"<tr><td class='l'>{esc(r['date'])}</td><td class='l'>{esc(r['ticker'])}</td>"
                 f"<td class='{cls(r['change_pct'])}'>{pct(r['change_pct'])}</td><td>{pct(r['gap_pct'])}</td>"
                 f"<td class='l'>{esc(LABEL_TH.get(r['label'], r['label']))}</td>"
                 f"<td class='l'>{esc(DRIVER_TH.get(r.get('driver'), '–'))}</td><td class='l'>{esc(r['events'])}</td>"
                 f"<td class='{cls(r.get('ret_5d'))}'>{pct(r.get('ret_5d'))}</td></tr>")
    p.append("</table></div><p class='mute'>สร้างอัตโนมัติจาก report.py · ไม่ใช่คำแนะนำการลงทุน</p>")

    return (f"<!doctype html><html lang='th'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>Market Capture {esc(last)}</title>"
            f"<style>{CSS}</style></head><body><div class='wrap'>{''.join(p)}</div></body></html>")


def main() -> None:
    demo = "--demo" in sys.argv
    (ROOT / "report.html").write_text(build(demo), encoding="utf-8")
    write_ics(load_calendar(), ROOT / "calendar.ics")
    print("report.html + calendar.ics written")


if __name__ == "__main__":
    main()
