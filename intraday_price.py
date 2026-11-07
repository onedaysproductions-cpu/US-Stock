#!/usr/bin/env python3
"""
กราฟราคาระหว่างวัน (USD) ของแต่ละหุ้น เลือกวันได้ จาก data/intraday/ (แท่ง 1 นาที รวมก่อนเปิด/หลังปิด)
- ช่องละ 5 นาที ใช้ราคาปิดของแท่งสุดท้ายในช่อง (ถ้าช่องนั้นไม่มีการซื้อขาย ใช้ราคาล่าสุดก่อนหน้า)
- เส้นประ = ราคาปิดวันก่อน / หัวกราฟ = เปิด สูง ต่ำ ปิด VWAP ทางการจาก daily_summary
"""
from __future__ import annotations

import json
from datetime import datetime, time

import pandas as pd

from glossary import howto
from volume_profile import BKK, ET, INTRA, MAX_DAYS

STEP = 5
START, END = time(4, 0), time(20, 0)


def _slots() -> list[time]:
    out, m = [], START.hour * 60
    while m < END.hour * 60:
        out.append(time(m // 60, m % 60))
        m += STEP
    return out


SLOTS = _slots()


def build(tickers: list[str]) -> dict:
    import capture
    s = capture.load_summary().set_index(["date", "ticker"])
    days = sorted(p.name for p in INTRA.iterdir() if p.is_dir())[-MAX_DAYS:] if INTRA.exists() else []
    out = {}
    for tk in tickers:
        per = {}
        for d in days:
            f = INTRA / d / f"{tk}.csv"
            if not f.exists() or (d, tk) not in s.index:
                continue
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
            last = df["Close"].groupby(df.index.floor(f"{STEP}min").time).last()
            p, cur = [], None
            for x in SLOTS:
                if x in last.index:
                    cur = round(float(last[x]), 4)
                p.append(cur)
            r = s.loc[(d, tk)]
            g = lambda k: None if pd.isna(r.get(k)) else round(float(r[k]), 4)   # noqa: E731
            per[d] = {"p": p, "pc": g("prev_close"), "o": g("open"), "h": g("high"), "l": g("low"),
                      "c": g("close"), "vw": g("vwap"), "chg": g("change_pct")}
        if per:
            out[tk] = per
    return out


JS = r"""
(function(){
const P = JSON.parse(document.getElementById('ip-data').textContent);
const sel=document.getElementById('ip-day'), tip=document.getElementById('vp-tip');
const W=720,H=200,L=52,R=12,T=12,B=24, N=P.th.length, dx=(W-L-R)/(N-1);
const fm=v=>v==null?'–':'$'+(v>=100?v.toFixed(2):v>=10?v.toFixed(2):v.toFixed(3));
function nice(lo,hi){const span=hi-lo||hi*0.02||1, e=Math.pow(10,Math.floor(Math.log10(span/4))), f=span/4/e;
  const st=(f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e; return {lo:Math.floor(lo/st)*st, hi:Math.ceil(hi/st)*st, st};}
function draw(){
  const d=sel.value;
  for(const tk in P.t){
    const box=document.getElementById('ip-'+tk), hd=document.getElementById('ip-h-'+tk), r=P.t[tk][d];
    if(!r){box.innerHTML='<div class="mute">ไม่มีข้อมูลวันนี้</div>'; hd.textContent=''; continue;}
    const cc=r.chg==null?'':(r.chg>=0?'up':'down');
    hd.innerHTML=`ปิด <b>${fm(r.c)}</b> <span class="${cc}">${r.chg==null?'':(r.chg>=0?'+':'')+r.chg.toFixed(2)+'%'}</span> · `+
      `เปิด ${fm(r.o)} · สูง ${fm(r.h)} · ต่ำ ${fm(r.l)}`+(r.vw?` · VWAP ${fm(r.vw)}`:'')+` · ปิดวันก่อน ${fm(r.pc)}`;
    const vals=r.p.filter(v=>v!=null).concat([r.pc,r.h,r.l].filter(v=>v!=null));
    const sc=nice(Math.min(...vals),Math.max(...vals)), y=v=>T+(H-T-B)*(sc.hi-v)/(sc.hi-sc.lo), x=i=>L+i*dx;
    let g=`<rect x="${x(P.open_i)}" y="${T}" width="${x(P.close_i)-x(P.open_i)}" height="${H-T-B}" fill="var(--grid)" opacity=".35"/>`;
    for(let v=sc.lo; v<=sc.hi+1e-9; v+=sc.st){g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>`+
      `<text x="${L-4}" y="${y(v)+4}" text-anchor="end" font-size="10" fill="var(--axis)">${fm(+v.toFixed(4))}</text>`;}
    if(r.pc!=null) g+=`<line x1="${L}" x2="${W-R}" y1="${y(r.pc)}" y2="${y(r.pc)}" stroke="var(--axis)" stroke-dasharray="4 4"/>`+
      `<text x="${W-R-2}" y="${y(r.pc)-4}" text-anchor="end" font-size="10" fill="var(--axis)">ปิดวันก่อน</text>`;
    if(r.vw!=null) g+=`<line x1="${x(P.open_i)}" x2="${x(P.close_i)}" y1="${y(r.vw)}" y2="${y(r.vw)}" stroke="var(--event)" stroke-width="1.5" stroke-dasharray="2 3"/>`+
      `<text x="${x(P.open_i)+3}" y="${y(r.vw)-4}" font-size="10" fill="var(--axis)">VWAP</text>`;
    let dd='',pen=false; r.p.forEach((v,i)=>{if(v==null){pen=false;return;} dd+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1); pen=true;});
    g+=`<path d="${dd}" fill="none" stroke="var(--normal)" stroke-width="2" stroke-linejoin="round"/>`;
    P.th.forEach((lb,i)=>{ if(i%24===0) g+=`<text x="${x(i)}" y="${H-6}" font-size="10" fill="var(--axis)" text-anchor="middle">${lb}</text>`;});
    g+=`<text x="${x(P.open_i)+3}" y="${T+11}" font-size="10" fill="var(--axis)">ตลาดเปิด</text>`;
    g+=`<line class="xh" y1="${T}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="3 3" visibility="hidden"/><circle class="dt" r="4" fill="var(--normal)" stroke="var(--card)" stroke-width="2" visibility="hidden"/>`;
    g+=`<rect class="ov" x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent"/>`;
    box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${tk} ราคาระหว่างวัน ${d}">${g}</svg>`;
    const svg=box.querySelector('svg'), xh=svg.querySelector('.xh'), dt=svg.querySelector('.dt'), ov=svg.querySelector('.ov');
    ov.addEventListener('mousemove',e=>{const bb=svg.getBoundingClientRect(), sx=(e.clientX-bb.left)*W/bb.width;
      const i=Math.max(0,Math.min(N-1,Math.round((sx-L)/dx))), v=r.p[i];
      xh.setAttribute('x1',x(i)); xh.setAttribute('x2',x(i)); xh.setAttribute('visibility','visible');
      if(v!=null){dt.setAttribute('cx',x(i)); dt.setAttribute('cy',y(v)); dt.setAttribute('visibility','visible');} else dt.setAttribute('visibility','hidden');
      const ses=i<P.open_i?'ก่อนตลาดเปิด':(i<P.close_i?'ตลาดเปิด':'หลังตลาดปิด');
      const ch=(v!=null&&r.pc)?((v/r.pc-1)*100):null;
      tip.innerHTML=`<b>${tk}</b> ${d} · ${P.th[i]} น. (ไทย) · ${P.et[i]} ET · ${ses}<br>`+
        `ราคา <b>${fm(v)}</b>`+(ch==null?'':` (${ch>=0?'+':''}${ch.toFixed(2)}% จากปิดวันก่อน)`);
      tip.style.display='block'; tip.style.left=Math.min(e.clientX+12,innerWidth-340)+'px'; tip.style.top=(e.clientY+12)+'px';});
    ov.addEventListener('mouseleave',()=>{tip.style.display='none'; xh.setAttribute('visibility','hidden'); dt.setAttribute('visibility','hidden');});
  }
}
sel.addEventListener('change',draw); draw();
})();
"""


def section_html(tickers: list[str]) -> str:
    data = build(tickers)
    if not data:
        return ""
    days = sorted({d for t in data.values() for d in t}, reverse=True)
    today = datetime.now(ET).date()
    th = [datetime.combine(today, x, tzinfo=ET).astimezone(BKK).strftime("%H:%M") for x in SLOTS]
    payload = {"t": data, "th": th, "et": [x.strftime("%H:%M") for x in SLOTS],
               "open_i": SLOTS.index(time(9, 30)), "close_i": SLOTS.index(time(16, 0))}
    opts = "".join(f"<option value='{d}'>{d}</option>" for d in days)
    charts = "".join(f"<div class='ch'><h3>{tk} <span class='mute' id='ip-h-{tk}'></span></h3><div id='ip-{tk}'></div></div>"
                     for tk in data)
    return (
        "<h2>ราคาระหว่างวัน (USD)</h2><div class='card vc'>"
        + howto("ราคาจริงของหุ้นแต่ละตัวตลอดวันที่เลือก ตั้งแต่ก่อนตลาดเปิดถึงหลังตลาดปิด", [
            "เส้นน้ำเงิน = ราคา (ช่องละ 5 นาที) · พื้นเทา = ช่วงตลาดเปิด 21:30–04:00 น. ไทย",
            "เส้นประเทา = ราคาปิดวันก่อน → เส้นราคาอยู่เหนือ = ขึ้นจากเมื่อวาน, อยู่ใต้ = ลง",
            "เส้นประชมพู = VWAP (ต้นทุนเฉลี่ยของวัน) → ราคาอยู่เหนือ VWAP = คนซื้อวันนั้นส่วนใหญ่มีกำไร",
            "เอาเมาส์ชี้เพื่อดูราคา ณ เวลานั้นและ % จากราคาปิดวันก่อน",
            "ข้อมูลอัปเดตวันละครั้งหลังตลาดปิด (ไม่ใช่ราคาเรียลไทม์) ถ้าต้องการราคาสดให้ดูที่ Yahoo Finance หรือแอปโบรกเกอร์"])
        + "<div class='ctl'><label>วันที่: <select id='ip-day'>" + opts + "</select></label></div>"
        + charts + "</div>"
        f"<script type='application/json' id='ip-data'>{json.dumps(payload, separators=(',', ':'))}</script>"
        f"<script>{JS}</script>")
