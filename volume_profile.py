#!/usr/bin/env python3
"""
กราฟ "ช่วงเวลาไหนซื้อ/ขายเยอะ" ใน 1 วัน จากแท่ง 1 นาทีใน data/intraday/
- แบ่งวันเป็นช่วงละ 5 นาที (08:00–16:30 เวลา New York) แสดงเป็นเวลาไทย
- ปริมาณ "ฝั่งซื้อ" (ประมาณ) = volume ของแท่งที่ปิดสูงกว่าเปิด / "ฝั่งขาย" = แท่งที่ปิดต่ำกว่าเปิด
  แท่งที่ปิดเท่าเปิดแบ่งครึ่ง (Yahoo ไม่บอกฝั่งของแต่ละรายการจริง จึงเป็นค่าประมาณ)
- หน่วย = % ของ volume ทั้งวัน (ช่วง 08:00–16:30) เพื่อเทียบข้ามวัน/ข้ามหุ้นได้
ใช้: from volume_profile import section_html
"""
from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
INTRA = ROOT / "data" / "intraday"
ET = ZoneInfo("America/New_York")
BKK = ZoneInfo("Asia/Bangkok")
START, END, STEP = time(8, 0), time(16, 30), 5     # ช่วงเวลา ET และขนาดช่อง (นาที)
MAX_DAYS = 20                                      # ใช้ย้อนหลังกี่วันทำการ


def _slots() -> list[time]:
    out, m = [], START.hour * 60 + START.minute
    while m < END.hour * 60 + END.minute:
        out.append(time(m // 60, m % 60))
        m += STEP
    return out


def _day_profile(f: Path) -> dict | None:
    df = pd.read_csv(f, index_col=0)
    if df.empty or "Volume" not in df:
        return None
    idx = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df.index = idx
    t = idx.time
    df = df[(t >= START) & (t < END)]
    if df.empty or df["Volume"].sum() <= 0:
        return None
    up = (df["Close"] > df["Open"]).astype(float) + (df["Close"] == df["Open"]).astype(float) * 0.5
    slot = df.index.floor(f"{STEP}min").time
    g = pd.DataFrame({"slot": slot, "buy": df["Volume"] * up, "sell": df["Volume"] * (1 - up)}).groupby("slot").sum()
    tot = float(df["Volume"].sum())
    slots = _slots()
    buy = [round(float(g["buy"].get(s, 0)) / tot * 100, 3) for s in slots]
    sell = [round(float(g["sell"].get(s, 0)) / tot * 100, 3) for s in slots]
    return {"buy": buy, "sell": sell, "vol": int(tot)}


def build_data(tickers: list[str]) -> dict:
    days = sorted(p.name for p in INTRA.iterdir() if p.is_dir())[-MAX_DAYS:] if INTRA.exists() else []
    out = {}
    for tk in tickers:
        per = {}
        for d in days:
            f = INTRA / d / f"{tk}.csv"
            if f.exists():
                prof = _day_profile(f)
                if prof:
                    per[d] = prof
        if not per:
            continue
        n = len(per)
        avg = {k: [round(sum(p[k][i] for p in per.values()) / n, 3) for i in range(len(_slots()))]
               for k in ("buy", "sell")}
        out[tk] = {"avg": avg, "days": per, "n": n}
    return out


def _thai_labels() -> list[str]:
    """แปลงเวลา ET เป็นเวลาไทย ตามช่วงเวลาปัจจุบัน (สหรัฐฯ ฤดูร้อน +11 ชม. / ฤดูหนาว +12 ชม.)"""
    today = datetime.now(ET).date()
    return [datetime.combine(today, s, tzinfo=ET).astimezone(BKK).strftime("%H:%M") for s in _slots()]


def _peaks(d: dict) -> str:
    """สรุปเป็นตัวหนังสือ: 3 ช่วงที่ volume สูงสุด + ช่วงที่ซื้อ/ขายเด่นสุด (จากค่าเฉลี่ย)"""
    lab = _thai_labels()
    buy, sell = d["avg"]["buy"], d["avg"]["sell"]
    tot = [b + s for b, s in zip(buy, sell)]
    top = sorted(range(len(tot)), key=lambda i: -tot[i])[:3]
    reg = [i for i, s in enumerate(_slots()) if time(9, 30) <= s < time(16, 0)]
    net = {i: buy[i] - sell[i] for i in reg}
    nb, ns = max(net, key=net.get), min(net, key=net.get)
    tops = ", ".join(f"{lab[i]} ({tot[i]:.1f}%)" for i in sorted(top))
    return (f"ช่วงที่ซื้อขายเยอะสุด (เวลาไทย): {tops} · ช่วงตลาดเปิดที่ซื้อสุทธิเด่นสุด {lab[nb]} (+{net[nb]:.2f}%) · "
            f"ขายสุทธิเด่นสุด {lab[ns]} ({net[ns]:.2f}%)")


CSS = """
.vp{--buy:#2a78d6;--sell:#eb6834;--grid:#e4e2dd;--axis:#6e6e73}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .vp{--buy:#3987e5;--sell:#d95926;--grid:#2e2e33;--axis:#9a9aa0}}
:root[data-theme="dark"] .vp{--buy:#3987e5;--sell:#d95926;--grid:#2e2e33;--axis:#9a9aa0}
.vp .ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 10px}
.vp select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.vp .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.vp .ch{margin:0 0 14px}.vp .ch h3{font-size:15px;margin:0 0 2px}.vp svg{width:100%;height:auto;display:block}
.vp .tip{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:6px 9px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:9;white-space:nowrap}
.vp details{margin-top:6px}.vp details table{font-size:12.5px}
"""

JS = r"""
(function(){
const D = JSON.parse(document.getElementById('vp-data').textContent);
const sel = document.getElementById('vp-day'), tip = document.getElementById('vp-tip');
const W=720,H=190,L=34,R=8,T=10,B=24, mid=T+(H-T-B)/2;
const N=D.labels.length, bw=(W-L-R)/N;
function series(tk,key){const t=D.t[tk]; if(!t) return null; return key==='avg'?t.avg:(t.days[key]||null);}
function maxv(key){let m=0;for(const tk in D.t){const s=series(tk,key);if(!s)continue;
  s.buy.forEach((v,i)=>{m=Math.max(m,v,s.sell[i])});}
  const st=[0.5,1,2,2.5,5,10,15,20,25,50]; for(const x of st){ if(m<=x*2) return x*2; } return Math.ceil(m/10)*10;}
function draw(){
  const key=sel.value, m=maxv(key), sc=(H-T-B)/2/m;
  for(const tk in D.t){
    const box=document.getElementById('vp-'+tk), s=series(tk,key);
    if(!s){box.innerHTML='<div class="mute">ไม่มีข้อมูลวันนี้</div>';continue;}
    let g='';
    [m,m/2].forEach(v=>{const y1=mid-v*sc,y2=mid+v*sc;
      g+=`<line x1="${L}" x2="${W-R}" y1="${y1}" y2="${y1}" stroke="var(--grid)"/><line x1="${L}" x2="${W-R}" y1="${y2}" y2="${y2}" stroke="var(--grid)"/>`+
         `<text x="${L-4}" y="${y1+4}" text-anchor="end" font-size="10" fill="var(--axis)">${v}%</text>`+
         `<text x="${L-4}" y="${y2+4}" text-anchor="end" font-size="10" fill="var(--axis)">${v}%</text>`;});
    // ช่วงตลาดเปิด 09:30–16:00 ET
    const o=D.open_i, c=D.close_i;
    g+=`<rect x="${L+o*bw}" y="${T}" width="${(c-o)*bw}" height="${H-T-B}" fill="var(--grid)" opacity=".35"/>`;
    s.buy.forEach((v,i)=>{const x=L+i*bw+1, w=Math.max(1,bw-2);
      if(v>0) g+=`<rect x="${x}" y="${mid-1-v*sc}" width="${w}" height="${v*sc}" rx="1.5" fill="var(--buy)"/>`;
      const u=s.sell[i]; if(u>0) g+=`<rect x="${x}" y="${mid+1}" width="${w}" height="${u*sc}" rx="1.5" fill="var(--sell)"/>`;});
    g+=`<line x1="${L}" x2="${W-R}" y1="${mid}" y2="${mid}" stroke="var(--axis)" stroke-width="1"/>`;
    D.labels.forEach((lb,i)=>{ if(i%6===0) g+=`<text x="${L+i*bw}" y="${H-6}" font-size="10" fill="var(--axis)">${lb}</text>`;});
    g+=`<text x="${L+o*bw+3}" y="${T+11}" font-size="10" fill="var(--axis)">ตลาดเปิด</text>`;
    D.labels.forEach((lb,i)=>{g+=`<rect class="hit" data-i="${i}" x="${L+i*bw}" y="${T}" width="${bw}" height="${H-T-B}" fill="transparent"/>`;});
    box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${tk} ปริมาณซื้อขายตามช่วงเวลา">${g}</svg>`;
    box.querySelectorAll('.hit').forEach(r=>{
      r.addEventListener('mousemove',e=>{const i=+r.dataset.i, b=s.buy[i], u=s.sell[i];
        tip.innerHTML=`<b>${tk}</b> ${D.labels[i]} น. (ไทย) · ${D.et[i]} ET<br>`+
          `<span class="sw" style="background:var(--buy)"></span>ซื้อ ${b.toFixed(2)}%<br>`+
          `<span class="sw" style="background:var(--sell)"></span>ขาย ${u.toFixed(2)}%<br>`+
          `รวม ${(b+u).toFixed(2)}% · สุทธิ ${(b-u>=0?'+':'')}${(b-u).toFixed(2)}%`;
        tip.style.display='block'; tip.style.left=Math.min(e.clientX+12,innerWidth-200)+'px'; tip.style.top=(e.clientY+12)+'px';
        r.setAttribute('fill','rgba(127,127,127,.15)');});
      r.addEventListener('mouseleave',()=>{tip.style.display='none'; r.setAttribute('fill','transparent');});
    });
  }
}
sel.addEventListener('change',draw); draw();
})();
"""


SWING_SPY = 1.5     # |SPY| >= นี้ = วันตลาดผันผวนแรง
BIG_MOVE = 5.0      # |หุ้น| >= นี้ = วันหุ้นขยับแรง
GROUPS = {"SWING": f"ตลาดผันผวนแรง (SPY ±{SWING_SPY}%+)", "MACRO": "วัน CPI / FOMC",
          "EARN": "ช่วงประกาศงบ (±1 วัน)", "BIG": f"หุ้นขยับแรง (±{BIG_MOVE:.0f}%+)"}


def day_groups(tickers: list[str]) -> dict:
    """จัดกลุ่มแต่ละวันของแต่ละหุ้น: วันพิเศษ (SWING/MACRO/EARN/BIG) หรือ NORMAL"""
    import capture
    s = capture.load_summary()
    if s.empty:
        return {}
    s["events"] = s["events"].fillna("")
    ctx_f = ROOT / "data" / "market_context.csv"
    spy = pd.read_csv(ctx_f).set_index("date")["SPY_chg_pct"].to_dict() if ctx_f.exists() else {}
    out = {}
    for r in s[s["ticker"].isin(tickers)].itertuples(index=False):
        g = []
        if abs(spy.get(r.date) or 0) >= SWING_SPY:
            g.append("SWING")
        if "CPI" in r.events or "FOMC" in r.events:
            g.append("MACRO")
        if "EARNINGS" in r.events:
            g.append("EARN")
        if pd.notna(r.change_pct) and abs(r.change_pct) >= BIG_MOVE:
            g.append("BIG")
        out.setdefault(r.ticker, {})[r.date] = g or ["NORMAL"]
    return out


CMP_CSS = """
.vp,.vc{--normal:#2a78d6;--event:#d55181}.vc{--grid:#e4e2dd;--axis:#6e6e73}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) :is(.vp,.vc){--normal:#3987e5;--event:#e87ba4}:root:not([data-theme="light"]) .vc{--grid:#2e2e33;--axis:#9a9aa0}}
:root[data-theme="dark"] :is(.vp,.vc){--normal:#3987e5;--event:#e87ba4}:root[data-theme="dark"] .vc{--grid:#2e2e33;--axis:#9a9aa0}
.vc .ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 10px}
.vc select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.ln{display:inline-block;width:16px;height:3px;border-radius:2px;margin-right:5px;vertical-align:3px}
.vc .ch{margin:0 0 14px}.vc .ch h3{font-size:15px;margin:0 0 2px}.vc svg{width:100%;height:auto;display:block}
"""

CMP_JS = r"""
(function(){
const D = JSON.parse(document.getElementById('vp-data').textContent);
const cmp=document.getElementById('vc-cmp'), met=document.getElementById('vc-met'), tip=document.getElementById('vp-tip');
const W=720,H=200,L=40,R=70,T=12,B=24, N=D.labels.length, dx=(W-L-R)/(N-1);
function vals(tk,d,m,base){const p=D.t[tk].days[d]; if(!p) return null;
  return p.buy.map((b,i)=>{const u=p.sell[i];
    if(m==='net') return b-u; if(m==='rel') return (b+u)*p.vol/base; return b+u;});}
function avg(tk,dates,m,base){const rows=dates.map(d=>vals(tk,d,m,base)).filter(Boolean); if(!rows.length) return null;
  return rows[0].map((_,i)=>rows.reduce((a,r)=>a+r[i],0)/rows.length);}
function smooth(a){return a.map((_,i)=>{const w=a.slice(Math.max(0,i-1),i+2);return w.reduce((x,y)=>x+y,0)/w.length;});}
function draw(){
  const key=cmp.value, m=met.value;
  const res={}; let lo=0, hi=0;
  for(const tk in D.t){
    const g=D.g[tk]||{}, have=Object.keys(D.t[tk].days);
    const norm=have.filter(d=>(g[d]||['NORMAL']).includes('NORMAL'));
    const ev = key.startsWith('G:') ? have.filter(d=>(g[d]||[]).includes(key.slice(2))) : (have.includes(key)?[key]:[]);
    const base = norm.length ? norm.reduce((a,d)=>a+D.t[tk].days[d].vol,0)/norm.length : 1;
    const a=avg(tk,norm,m,base), b=avg(tk,ev,m,base);
    res[tk]={a:a&&smooth(a), b:b&&smooth(b), na:norm.length, nb:ev.length};
    [a,b].forEach(s=>s&&smooth(s).forEach(v=>{hi=Math.max(hi,v);lo=Math.min(lo,v);}));
  }
  const nice=v=>{if(v<=0) return 0; const e=Math.pow(10,Math.floor(Math.log10(v))), f=v/e;
    return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e;};
  hi=nice(hi||1); lo=lo<0?-nice(-lo):0;
  const y=v=>T+(H-T-B)*(hi-v)/(hi-lo), x=i=>L+i*dx;
  const unit = m==='rel' ? '%' : '%';
  for(const tk in res){
    const box=document.getElementById('vc-'+tk), r=res[tk];
    const head=document.getElementById('vc-n-'+tk);
    head.textContent=`· วันปกติ n=${r.na} · วันที่เลือก n=${r.nb}`+(r.nb && r.nb<3?' (ตัวอย่างน้อย)':'');
    if(!r.a && !r.b){box.innerHTML='<div class="mute">ไม่มีข้อมูล</div>';continue;}
    let g=`<rect x="${x(D.open_i)}" y="${T}" width="${x(D.close_i)-x(D.open_i)}" height="${H-T-B}" fill="var(--grid)" opacity=".35"/>`;
    const ticks=(lo<0?[lo,0,hi]:[0,hi/2,hi]).map(v=>+v.toFixed(2));
    ticks.forEach(v=>{g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>`+
      `<text x="${L-4}" y="${y(v)+4}" text-anchor="end" font-size="10" fill="var(--axis)">${v}${unit}</text>`;});
    if(lo<0) g+=`<line x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)"/>`;
    D.labels.forEach((lb,i)=>{ if(i%12===0) g+=`<text x="${x(i)}" y="${H-6}" font-size="10" fill="var(--axis)" text-anchor="middle">${lb}</text>`;});
    const path=s=>s.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
    const lab=(s,txt,col)=>`<text x="${W-R+6}" y="${y(s[s.length-1])+4}" font-size="11" fill="var(--ink)"><tspan fill="${col}">●</tspan> ${txt}</text>`;
    if(r.a) g+=`<path d="${path(r.a)}" fill="none" stroke="var(--normal)" stroke-width="2" stroke-linejoin="round"/>`;
    if(r.b) g+=`<path d="${path(r.b)}" fill="none" stroke="var(--event)" stroke-width="2" stroke-linejoin="round"/>`;
    // ป้ายท้ายเส้น: ถ้าใกล้กันเกินไปให้ดันออกจากกัน
    let ya=r.a?y(r.a[N-1]):null, yb=r.b?y(r.b[N-1]):null;
    if(ya!=null&&yb!=null&&Math.abs(ya-yb)<14){const m2=(ya+yb)/2, up=ya<=yb; ya=m2+(up?-7:7); yb=m2+(up?7:-7);
      if(Math.max(ya,yb)>H-B){const d=Math.max(ya,yb)-(H-B); ya-=d; yb-=d;}}
    const lab2=(yy,txt,col)=>`<text x="${W-R+6}" y="${yy+4}" font-size="11" fill="var(--ink)"><tspan fill="${col}">●</tspan> ${txt}</text>`;
    if(r.a) g+=lab2(ya,'ปกติ','var(--normal)');
    if(r.b) g+=lab2(yb,'พิเศษ','var(--event)');
    g+=`<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="3 3" visibility="hidden"/>`;
    g+=`<rect class="ov" x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent"/>`;
    box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${tk} เทียบวันพิเศษกับวันปกติ">${g}</svg>`;
    const svg=box.querySelector('svg'), xh=svg.querySelector('.xh'), ov=svg.querySelector('.ov');
    ov.addEventListener('mousemove',e=>{const pt=svg.getBoundingClientRect(), sx=(e.clientX-pt.left)*W/pt.width;
      const i=Math.max(0,Math.min(N-1,Math.round((sx-L)/dx))); xh.setAttribute('x1',x(i)); xh.setAttribute('x2',x(i)); xh.setAttribute('visibility','visible');
      const f=v=>v==null?'–':(m==='net'&&v>=0?'+':'')+v.toFixed(2)+unit;
      tip.innerHTML=`<b>${tk}</b> ${D.labels[i]} น. (ไทย) · ${D.et[i]} ET<br>`+
        `<span class="ln" style="background:var(--normal)"></span>วันปกติ ${f(r.a&&r.a[i])}<br>`+
        `<span class="ln" style="background:var(--event)"></span>${cmp.options[cmp.selectedIndex].text} ${f(r.b&&r.b[i])}`;
      tip.style.display='block'; tip.style.left=Math.min(e.clientX+12,innerWidth-260)+'px'; tip.style.top=(e.clientY+12)+'px';});
    ov.addEventListener('mouseleave',()=>{tip.style.display='none'; xh.setAttribute('visibility','hidden');});
  }
}
cmp.addEventListener('change',draw); met.addEventListener('change',draw); draw();
})();
"""


def compare_html(data: dict, groups: dict) -> str:
    if not data:
        return ""
    all_days = sorted({d for t in data.values() for d in t["days"]}, reverse=True)
    cnt = {k: sum(1 for d in all_days if any(k in groups.get(tk, {}).get(d, []) for tk in data)) for k in GROUPS}
    special = [d for d in all_days if any(groups.get(tk, {}).get(d, ["NORMAL"]) != ["NORMAL"] for tk in data)]
    opts = "".join(f"<option value='G:{k}'>{v} — {cnt[k]} วัน</option>" for k, v in GROUPS.items() if cnt[k])
    opts += "<optgroup label='เลือกเป็นรายวัน'>" + "".join(
        f"<option value='{d}'>{d}{' ★' if d in special else ''}</option>" for d in all_days) + "</optgroup>"
    charts = "".join(f"<div class='ch'><h3>{tk} <span class='mute' id='vc-n-{tk}'></span></h3><div id='vc-{tk}'></div></div>"
                     for tk in data)
    return (
        f"<style>{CMP_CSS}</style>"
        "<h2>วันพิเศษ vs วันปกติ: ซื้อขายต่างกันช่วงไหน</h2><div class='card vc'>"
        "<div class='ctl'><label>เทียบ: <select id='vc-cmp'>" + opts + "</select></label>"
        "<label>วัดเป็น: <select id='vc-met'><option value='share'>% ของ volume ทั้งวัน</option>"
        "<option value='rel'>volume เทียบวันปกติ (% ของ volume ทั้งวันปกติ)</option>"
        "<option value='net'>ซื้อสุทธิ (ซื้อ − ขาย, % ของวัน)</option></select></label>"
        "<span><i class='ln' style='background:var(--normal)'></i>วันปกติ (เฉลี่ย)</span>"
        "<span><i class='ln' style='background:var(--event)'></i>วันพิเศษที่เลือก</span></div>"
        + charts +
        "<div class='mute'>วันปกติ = ไม่มี CPI/FOMC/งบ, SPY ขยับไม่ถึง ±1.5% และหุ้นขยับไม่ถึง ±5% · ★ = วันพิเศษ · "
        "เส้นเฉลี่ยเคลื่อนที่ 15 นาทีให้อ่านง่าย · "
        "<b>volume เทียบวันปกติ</b> ช่วยดูว่าวันพิเศษคึกคักกว่าปกติกี่เท่า (เส้นปกติรวมทั้งวัน = 100%) · "
        "ข้อมูลแท่ง 1 นาทีมี 20 วันล่าสุด จะเทียบรายเดือนได้เมื่อเก็บครบหลายเดือน</div></div>"
        f"<script>{CMP_JS}</script>")


def section_html(tickers: list[str]) -> str:
    data = build_data(tickers)
    if not data:
        return ""
    slots, labels = _slots(), _thai_labels()
    all_days = sorted({d for t in data.values() for d in t["days"]}, reverse=True)
    n = max(t["n"] for t in data.values())
    groups = day_groups(list(data))
    payload = {"t": data, "g": groups, "labels": labels, "et": [s.strftime("%H:%M") for s in slots],
               "open_i": slots.index(time(9, 30)), "close_i": slots.index(time(16, 0))}
    opts = f"<option value='avg'>เฉลี่ย {n} วันล่าสุด</option>" + "".join(
        f"<option value='{d}'>{d}</option>" for d in all_days)
    offset = "+12" if labels[slots.index(time(9, 30))] == "21:30" else "+11"
    charts = "".join(
        f"<div class='ch'><h3>{tk} <span class='mute'>· n={data[tk]['n']} วัน</span></h3>"
        f"<div id='vp-{tk}'></div><div class='mute'>เฉลี่ย {data[tk]['n']} วัน — {_peaks(data[tk])}</div></div>"
        for tk in data)
    # ตารางสำรอง (เข้าถึงได้โดยไม่ต้องดูสี): ค่าเฉลี่ยรายชั่วโมง
    hours = sorted({s.hour for s in slots})
    rows = "".join(
        f"<tr><td class='l'>{tk}</td>" + "".join(
            f"<td>{sum(d['avg']['buy'][i] for i, s in enumerate(slots) if s.hour == h):.1f} / "
            f"{sum(d['avg']['sell'][i] for i, s in enumerate(slots) if s.hour == h):.1f}</td>" for h in hours) + "</tr>"
        for tk, d in data.items())
    head = "".join(f"<th>{labels[[s.hour for s in slots].index(h)][:2]}:xx</th>" for h in hours)
    return (
        f"<style>{CSS}</style>"
        "<h2>ช่วงเวลาไหนซื้อ/ขายเยอะใน 1 วัน</h2><div class='card vp'>"
        "<div class='ctl'><label>ดู: <select id='vp-day'>" + opts + "</select></label>"
        "<span><i class='sw' style='background:var(--buy)'></i>ฝั่งซื้อ (เหนือเส้น)</span>"
        "<span><i class='sw' style='background:var(--sell)'></i>ฝั่งขาย (ใต้เส้น)</span></div>"
        + charts +
        f"<div class='mute'>แกนนอน = เวลาไทย (ET {offset} ชม. ตามฤดูกาลปัจจุบัน) ช่องละ {STEP} นาที · แกนตั้ง = % ของ volume ทั้งวัน "
        "(08:00–16:30 ET) ทุกหุ้นใช้สเกลเดียวกัน · พื้นเทา = ช่วงตลาดเปิด · "
        "ฝั่งซื้อ/ขายเป็น<b>ค่าประมาณ</b>: volume ของแท่ง 1 นาทีที่ปิดสูงกว่าเปิด = ซื้อ, ต่ำกว่า = ขาย</div>"
        f"<details><summary class='mute'>ตารางรายชั่วโมง (ซื้อ / ขาย %, เฉลี่ย)</summary><div class='tbl'><table>"
        f"<tr><th class='l'>หุ้น</th>{head}</tr>{rows}</table></div></details>"
        "<div class='tip' id='vp-tip'></div></div>"
        f"<script type='application/json' id='vp-data'>{json.dumps(payload, separators=(',', ':'))}</script>"
        f"<script>{JS}</script>" + compare_html(data, groups))
