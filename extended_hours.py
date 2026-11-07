#!/usr/bin/env python3
"""
กราฟช่วงก่อนตลาดเปิด (04:00–09:30 ET) และหลังตลาดปิด (16:00–20:00 ET) จาก data/intraday/
Yahoo ไม่ให้ volume ช่วงนอกเวลา (เป็น 0) จึงแสดง 2 อย่างแทน:
- ราคา: % จากราคาอ้างอิง (ก่อนเปิด = ราคาปิดวันก่อน, หลังปิด = ราคาปิดทางการของวันนั้น)
- ความคึกคัก: % ของนาทีที่มีการซื้อขาย (Yahoo สร้างแท่ง 1 นาทีเฉพาะนาทีที่มีการซื้อขาย)
เทียบวันพิเศษ (กลุ่มเดียวกับ volume_profile.GROUPS) กับวันปกติในกราฟเดียว
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta

import pandas as pd

from glossary import howto
from volume_profile import BKK, ET, GROUPS, INTRA, MAX_DAYS, ROOT

STEP = 5
PRE = (time(4, 0), time(9, 30))
POST = (time(16, 0), time(20, 0))


def _grid(a: time, b: time) -> list[time]:
    out, m = [], a.hour * 60 + a.minute
    while m < b.hour * 60 + b.minute:
        out.append(time(m // 60, m % 60))
        m += STEP
    return out


SLOTS = {"pre": _grid(*PRE), "post": _grid(*POST)}


def _session(df: pd.DataFrame, rng: tuple, ref: float, slots: list[time]) -> dict:
    t = df.index.time
    x = df[(t >= rng[0]) & (t < rng[1])]
    if x.empty or not ref:
        return {"p": [None] * len(slots), "a": [0] * len(slots)}
    slot = pd.Series(x.index.floor(f"{STEP}min").time, index=x.index)
    last = x["Close"].groupby(slot.values).last()
    cnt = x["Close"].groupby(slot.values).size()
    p, cur = [], None
    for s in slots:
        if s in last.index:
            cur = round((float(last[s]) / ref - 1) * 100, 2)
        p.append(cur)                      # ใช้ราคาล่าสุดต่อไปจนกว่าจะมีการซื้อขายใหม่
    a = [round(int(cnt.get(s, 0)) / STEP * 100) for s in slots]
    return {"p": p, "a": a}


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
            row = s.loc[(d, tk)]
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
            per[d] = {"pre": _session(df, PRE, float(row["prev_close"]), SLOTS["pre"]),
                      "post": _session(df, POST, float(row["close"]), SLOTS["post"]),
                      "ref": {"pre": float(row["prev_close"]), "post": float(row["close"])}}
        if per:
            out[tk] = per
    return out


def _thai(slots: list[time]) -> list[str]:
    today = datetime.now(ET).date()
    return [datetime.combine(today, x, tzinfo=ET).astimezone(BKK).strftime("%H:%M") for x in slots]


JS = r"""
(function(){
const X = JSON.parse(document.getElementById('vx-data').textContent);
const cmp=document.getElementById('vx-cmp'), met=document.getElementById('vx-met'), tip=document.getElementById('vp-tip');
const W=720, L=44, R=70, GAP=26, T=14, HP=120, HA=56, MID=18, B=22, H=T+HP+MID+HA+B;
const np=X.th.pre.length, nq=X.th.post.length, plotW=W-L-R-GAP, wp=plotW*np/(np+nq), wq=plotW-wp;
const xs={pre:i=>L+i*wp/(np-1), post:i=>L+wp+GAP+i*wq/(nq-1)};
function avg(rows){rows=rows.filter(Boolean); if(!rows.length) return null;
  return rows[0].map((_,i)=>{const v=rows.map(r=>r[i]).filter(v=>v!=null); return v.length? v.reduce((a,b)=>a+b,0)/v.length : null;});}
function nice(v){if(v<=0) return 1; const e=Math.pow(10,Math.floor(Math.log10(v))), f=v/e; return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e;}
function draw(){
  const key=cmp.value, m=met.value, abs=m==='abs';
  const res={}; let pmax=0.5, pmin=0;
  for(const tk in X.t){
    const g=X.g[tk]||{}, have=Object.keys(X.t[tk]);
    const norm=have.filter(d=>(g[d]||['NORMAL']).includes('NORMAL'));
    const ev = key.startsWith('G:') ? have.filter(d=>(g[d]||[]).includes(key.slice(2))) : (have.includes(key)?[key]:[]);
    const sel=(ds,ses,k)=>avg(ds.map(d=>X.t[tk][d][ses][k].map(v=>v==null?null:(abs&&k==='p'?Math.abs(v):v))));
    const r={na:norm.length, nb:ev.length};
    for(const ses of ['pre','post']){ r[ses]={a:{p:sel(norm,ses,'p'),a:sel(norm,ses,'a')}, b:{p:sel(ev,ses,'p'),a:sel(ev,ses,'a')}};
      [r[ses].a.p,r[ses].b.p].forEach(s=>s&&s.forEach(v=>{if(v!=null){pmax=Math.max(pmax,v);pmin=Math.min(pmin,v);}}));}
    res[tk]=r;
  }
  pmax=nice(pmax); pmin=pmin<0?-nice(-pmin):0;
  const yp=v=>T+HP*(pmax-v)/(pmax-pmin), ya=v=>T+HP+MID+HA*(100-v)/100;
  for(const tk in res){
    const r=res[tk], box=document.getElementById('vx-'+tk);
    document.getElementById('vx-n-'+tk).textContent=`· วันปกติ n=${r.na} · วันที่เลือก n=${r.nb}`+(r.nb&&r.nb<3?' (ตัวอย่างน้อย)':'');
    let g='';
    // กรอบ 2 ช่วง + ป้าย
    [['pre','ก่อนตลาดเปิด'],['post','หลังตลาดปิด']].forEach(([ses,txt])=>{const x0=xs[ses](0), x1=xs[ses](ses==='pre'?np-1:nq-1);
      g+=`<text x="${x0}" y="${T-3}" font-size="10.5" fill="var(--axis)">${txt}</text>`;
      g+=`<text x="${x0}" y="${T+HP+MID-5}" font-size="10" fill="var(--axis)">ความคึกคัก (% ของนาทีที่มีการซื้อขาย)</text>`;
      [pmin,(pmin<0?0:pmax/2),pmax].forEach(v=>{g+=`<line x1="${x0}" x2="${x1}" y1="${yp(v)}" y2="${yp(v)}" stroke="var(--grid)"/>`;});
      [0,50,100].forEach(v=>{g+=`<line x1="${x0}" x2="${x1}" y1="${ya(v)}" y2="${ya(v)}" stroke="var(--grid)"/>`;});
      if(pmin<0) g+=`<line x1="${x0}" x2="${x1}" y1="${yp(0)}" y2="${yp(0)}" stroke="var(--axis)"/>`;
      const th=X.th[ses], step=ses==='pre'?12:12;
      th.forEach((lb,i)=>{ if(i%step===0) g+=`<text x="${xs[ses](i)}" y="${H-6}" font-size="10" fill="var(--axis)" text-anchor="middle">${lb}</text>`;});
    });
    [pmin,(pmin<0?0:pmax/2),pmax].forEach(v=>{g+=`<text x="${L-4}" y="${yp(v)+4}" text-anchor="end" font-size="10" fill="var(--axis)">${(v>0&&!abs?'+':'')+(+v.toFixed(2))}%</text>`;});
    [0,100].forEach(v=>{g+=`<text x="${L-4}" y="${ya(v)+4}" text-anchor="end" font-size="10" fill="var(--axis)">${v}%</text>`;});
    const path=(ses,s,y)=>{let d='',pen=false; s.forEach((v,i)=>{if(v==null){pen=false;return;} d+=(pen?'L':'M')+xs[ses](i).toFixed(1)+' '+y(v).toFixed(1); pen=true;}); return d;};
    for(const ses of ['pre','post']) for(const [k,col] of [['a','var(--normal)'],['b','var(--event)']]){
      const s=r[ses][k]; if(!s.p) continue;
      g+=`<path d="${path(ses,s.p,yp)}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>`;
      g+=`<path d="${path(ses,s.a,ya)}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>`;
    }
    // ป้ายท้ายเส้นราคา (หลังปิด)
    const lastv=s=>{if(!s) return null; for(let i=s.length-1;i>=0;i--) if(s[i]!=null) return s[i]; return null;};
    let la=lastv(r.post.a.p), lb=lastv(r.post.b.p); let ya1=la!=null?yp(la):null, yb1=lb!=null?yp(lb):null;
    if(ya1!=null&&yb1!=null&&Math.abs(ya1-yb1)<14){const c=(ya1+yb1)/2, up=ya1<=yb1; ya1=c+(up?-7:7); yb1=c+(up?7:-7);}
    if(ya1!=null) g+=`<text x="${W-R+6}" y="${ya1+4}" font-size="11" fill="var(--ink)"><tspan fill="var(--normal)">●</tspan> ปกติ</text>`;
    if(yb1!=null) g+=`<text x="${W-R+6}" y="${yb1+4}" font-size="11" fill="var(--ink)"><tspan fill="var(--event)">●</tspan> พิเศษ</text>`;
    g+=`<line class="xh" y1="${T}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="3 3" visibility="hidden"/>`;
    g+=`<rect class="ov" x="${L}" y="${T}" width="${plotW+GAP}" height="${H-T-B}" fill="transparent"/>`;
    box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${tk} ราคาและความคึกคักนอกเวลาตลาด">${g}</svg>`;
    const svg=box.querySelector('svg'), xh=svg.querySelector('.xh'), ov=svg.querySelector('.ov');
    ov.addEventListener('mousemove',e=>{const bb=svg.getBoundingClientRect(), sx=(e.clientX-bb.left)*W/bb.width;
      let ses,i; if(sx<L+wp+GAP/2){ses='pre'; i=Math.round((sx-L)/(wp/(np-1)));} else {ses='post'; i=Math.round((sx-L-wp-GAP)/(wq/(nq-1)));}
      const n=ses==='pre'?np:nq; i=Math.max(0,Math.min(n-1,i)); const xx=xs[ses](i);
      xh.setAttribute('x1',xx); xh.setAttribute('x2',xx); xh.setAttribute('visibility','visible');
      const f=v=>v==null?'–':((v>0&&!abs?'+':'')+v.toFixed(2)+'%'), fa=v=>v==null?'–':Math.round(v)+'%';
      const A=r[ses].a, Bv=r[ses].b, ref=ses==='pre'?'เทียบราคาปิดวันก่อน':'เทียบราคาปิดวันนี้';
      const one=!key.startsWith('G:') && X.t[tk][key], base=one?X.t[tk][key].ref[ses]:null;
      const usd=v=>(base&&v!=null&&!abs)?' ($'+(base*(1+v/100)).toFixed(base>=10?2:3)+')':'';
      tip.innerHTML=`<b>${tk}</b> ${X.th[ses][i]} น. (ไทย) · ${X.et[ses][i]} ET · ${ref}<br>`+
        `<span class="ln" style="background:var(--normal)"></span>วันปกติ: ราคา ${f(A.p&&A.p[i])} · คึกคัก ${fa(A.a&&A.a[i])}<br>`+
        `<span class="ln" style="background:var(--event)"></span>${cmp.options[cmp.selectedIndex].text}: ราคา ${f(Bv.p&&Bv.p[i])}${usd(Bv.p&&Bv.p[i])} · คึกคัก ${fa(Bv.a&&Bv.a[i])}`;
      tip.style.display='block'; tip.style.left=Math.min(e.clientX+12,innerWidth-360)+'px'; tip.style.top=(e.clientY+12)+'px';});
    ov.addEventListener('mouseleave',()=>{tip.style.display='none'; xh.setAttribute('visibility','hidden');});
  }
}
cmp.addEventListener('change',draw); met.addEventListener('change',draw); draw();
})();
"""


def section_html(tickers: list[str], groups: dict) -> str:
    data = build(tickers)
    if not data:
        return ""
    all_days = sorted({d for t in data.values() for d in t}, reverse=True)
    cnt = {k: sum(1 for d in all_days if any(k in groups.get(tk, {}).get(d, []) for tk in data)) for k in GROUPS}
    special = {d for d in all_days if any(groups.get(tk, {}).get(d, ["NORMAL"]) != ["NORMAL"] for tk in data)}
    opts = "".join(f"<option value='G:{k}'>{v} — {cnt[k]} วัน</option>" for k, v in GROUPS.items() if cnt[k])
    opts += "<optgroup label='เลือกเป็นรายวัน'>" + "".join(
        f"<option value='{d}'>{d}{' ★' if d in special else ''}</option>" for d in all_days) + "</optgroup>"
    payload = {"t": data, "g": groups, "th": {k: _thai(v) for k, v in SLOTS.items()},
               "et": {k: [x.strftime("%H:%M") for x in v] for k, v in SLOTS.items()}}
    charts = "".join(f"<div class='ch'><h3>{tk} <span class='mute' id='vx-n-{tk}'></span></h3><div id='vx-{tk}'></div></div>"
                     for tk in data)
    return (
        "<h2>ก่อนตลาดเปิด / หลังตลาดปิด: ราคาและความคึกคัก</h2><div class='card vc'>"
        + howto("ราคาและความคึกคักนอกเวลาตลาด เทียบวันพิเศษกับวันปกติ", [
            "ซ้าย = ก่อนตลาดเปิด (15:00–21:30 น. ไทย) · ขวา = หลังตลาดปิด (04:00–08:00 น. ไทย)",
            "ครึ่งบน = ราคาขึ้น/ลงกี่ % (ก่อนเปิดเทียบราคาปิดวันก่อน, หลังปิดเทียบราคาปิดวันนั้น) → ดูว่า gap เริ่มก่อตัวตอนกี่โมง",
            "ครึ่งล่าง = ความคึกคัก: % ของนาทีที่มีการซื้อขายเกิดขึ้น (100% = ซื้อขายทุกนาที) → ยิ่งสูง = มีคนสนใจซื้อขายมาก",
            "เลือกวันเดียวแล้วเอาเมาส์ชี้ จะเห็นราคาเป็นดอลลาร์ด้วย"])
        + "<div class='ctl'><label>เทียบ: <select id='vx-cmp'>" + opts + "</select></label>"
        "<label>ราคาแสดงเป็น: <select id='vx-met'><option value='signed'>% ขึ้น/ลง</option>"
        "<option value='abs'>ขนาดการขยับ (ไม่สนทิศ)</option></select></label>"
        "<span><i class='ln' style='background:var(--normal)'></i>วันปกติ (เฉลี่ย)</span>"
        "<span><i class='ln' style='background:var(--event)'></i>วันพิเศษที่เลือก</span></div>"
        + charts +
        "<div class='mute'>บน = ราคา (ก่อนเปิดเทียบราคาปิดวันก่อน · หลังปิดเทียบราคาปิดทางการวันนั้น) · "
        "ล่าง = ความคึกคัก: % ของนาทีในช่วง 5 นาทีที่มีการซื้อขายเกิดขึ้น (Yahoo ไม่ให้ volume นอกเวลา จึงใช้ตัวนี้แทน) · "
        "เวลาไทยตามฤดูกาลปัจจุบัน · ถ้าเลือกเป็นกลุ่ม เส้น % ขึ้น/ลง เป็นค่าเฉลี่ยซึ่งวันขึ้นกับวันลงอาจหักล้างกัน "
        "ให้ดู \"ขนาดการขยับ\" ประกอบ</div></div>"
        f"<script type='application/json' id='vx-data'>{json.dumps(payload, separators=(',', ':'))}</script>"
        f"<script>{JS}</script>")
