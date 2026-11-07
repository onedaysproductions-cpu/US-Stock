# Market Capture — คำสั่งสำหรับ Claude (Claude Code / Cowork)

โฟลเดอร์นี้เก็บข้อมูลตลาดรายวันของ watchlist: MXL, STRL, BTSG, MO, UUUU
ข้อมูลทั้งหมดมาจาก `capture.py` ห้ามแก้ตัวเลขราคาใน data/ ด้วยมือ ห้ามเติมข้อมูลด้วยการเดา

## ไฟล์
- `data/daily_summary.csv` — 1 แถวต่อหุ้นต่อวัน (gap, ATR, pre-market, VWAP, sell_waves, label, driver, beta/R², งบ, ret_1d/3d/5d)
- `data/market_context.csv` — SPY, QQQ, VIX, ยีลด์ 10 ปี (^TNX เป็น %), น้ำมัน รายวัน
- `data/intraday/<วันที่>/<หุ้น>.csv` — แท่ง 1 นาทีดิบ รวม pre/post market (เวลา New York)
- `data/news/<วันที่>.json` — หัวข้อข่าวล่าสุดต่อหุ้น
- `data/earnings.csv` — วัน+เวลาประกาศงบจาก Yahoo: `date,ticker,time_et,timing` (BMO/AMC/DURING/UNKNOWN)
- `events.csv` — ปฏิทินเศรษฐกิจ FOMC (Fed) / CPI (BLS) 2021–2027 แก้/เพิ่มได้ คอลัมน์ `date,type,title,ticker,time_et`
- `notes.csv` — catalyst ของแต่ละวัน (Claude/ผู้ใช้เขียน บอทไม่แตะ)
- `trades.csv` — บันทึกการเทรดของผู้ใช้ `date,ticker,action,price,shares,reason,emotion,plan_followed,note`
- `hypotheses.md` — สมมติฐาน / เงื่อนไขอยู่ใน `HYPOTHESES` ของ `analysis.py`
- โค้ด: `capture.py` (ดึงรายวัน) · `backfill.py` (ย้อนหลัง) · `enrich.py` (คำนวณคอลัมน์อนุพันธ์ทั้งหมดใหม่ทุกรอบ)
  · `analysis.py` (สมมติฐาน/base rate/หลังงบ/เทรด) · `report.py` (+ glossary.py, volume_profile.py, extended_hours.py, intraday_price.py)
- `report.html` — รายงานอัตโนมัติ / `calendar.ics` — ปฏิทินสำหรับนำเข้า Google Calendar

## คอลัมน์สำคัญ
- `source` = live_1m / backfill_1m (~30 วัน) / backfill_5m (~60 วัน) = **intraday** · backfill_1d (5 ปี) = **daily**
  intraday กับ daily ห้ามรวมกันในสถิติ (daily ไม่มี VWAP, pre-market, sell_waves, ช่วงเวลาในวัน)
- `atr_pct` = ATR 14 วันก่อนหน้า (% ของราคา) · `gap_atr` = gap_pct / atr_pct
- `label` ใช้ |gap_atr| >= 0.75 (`GAP_ATR_THRESHOLD` ใน enrich.py) เป็นเกณฑ์ "มี gap" · `gap_pct` ยังเก็บไว้แสดงผล
- `part_market` = SPY, `part_sector` = peer เหนือ SPY, `part_own` = หุ้นเหนือ peer
- `driver` = MARKET / SECTOR / OWN หรือ **QUIET** ถ้า |change_pct| < 1 หรือ < 0.5 × atr_pct
- `beta_spy_60`, `r2_spy_60`, `beta_peer_60`, `r2_peer_60` = ย้อนหลัง 60 วันทำการ (R² ใช้เป็นตัวหลักในการบอกว่าผูกกับตลาด/กลุ่มแค่ไหน)
- `events` = CPI, FOMC, EARNINGS (±1 วัน) · `earnings_reaction` = True เฉพาะ session แรกที่ตลาดตอบสนองงบ
  (BMO = วันเดียวกัน, AMC = วันทำการถัดไป) · `earnings_timing`, `earnings_date`
- intraday เท่านั้น: `ret_first30` (09:30–10:00), `ret_mid` (10:00–15:00), `ret_last60` (15:00–ปิด) เป็น %,
  `vol_share_first30`, `vol_share_last60` (% ของ volume ช่วงตลาดเปิด)
- `pre_vol_ratio` = pre_volume / เฉลี่ย 10 วันก่อน — **Yahoo ให้ pre-market volume = 0 จึงว่างเกือบทั้งหมด**
  ใช้ `pre_active_min` (จำนวนนาทีก่อนเปิดที่มีการซื้อขาย, เฉพาะแท่ง 1 นาที) และ `pre_min_ratio` แทน

## งานรายวัน (เมื่อถูกสั่ง "อัปเดตวันนี้")
1. git pull แล้วเปิดแถวของวันล่าสุดใน daily_summary.csv
2. ตัวที่ |gap_atr| >= 0.75 หรือ |change_pct| >= 3 หรือ earnings_reaction = True หรือ events มี EARNINGS:
   อ่านข่าวใน data/news และค้นเว็บเพิ่มได้ แล้วเติม notes สั้นๆ **ลงไฟล์ `notes.csv`** (คอลัมน์ date,ticker,notes)
   ห้ามเขียน notes ลง data/daily_summary.csv ตรงๆ (บอท GitHub Actions เขียนไฟล์นั้น จะชนกัน) — capture/report จะรวมให้เอง
   ตัวอย่าง notes: `earnings beat / guidance cut`, `analyst upgrade`, `sector sympathy (SOXX +3%)`, `macro: FOMC`, `no clear catalyst`
   ถ้าไม่แน่ใจให้เขียน `unconfirmed:` นำหน้า ห้ามเดา
3. ดูว่าหุ้นขยับเพราะอะไร จาก part_* / driver (QUIET = ขยับน้อยกว่าปกติ ไม่ต้องหาสาเหตุ) และ R² 60 วัน
4. สรุปเป็นภาษาไทยสั้นๆ: ตลาดวันนั้นเป็นแบบไหน (VIX ระดับ+เปลี่ยน, ยีลด์เป็น bp) และแต่ละตัวมีอะไรผิดปกติ

## บันทึกเทรด (เมื่อถูกสั่ง "บันทึกเทรด: ...")
- ผู้ใช้พิมพ์เป็นภาษาธรรมดา เช่น "บันทึกเทรด: ซื้อ MXL 100 หุ้นที่ 45.20 เพราะ gap ลงแล้วดีดเหนือ VWAP กลัวตกรถ ทำตามแผน"
- แปลงเป็น 1 แถวใน `trades.csv`: date (วันเทรดตามเวลา New York; ถ้าไม่บอกให้ถาม), ticker, action BUY/SELL,
  price, shares, reason, emotion, plan_followed Y/N, note
- ถ้าข้อมูลไหนไม่ได้บอก (ราคา จำนวน ทำตามแผนไหม) ให้ถามก่อน ห้ามเดา · ห้ามเปลี่ยนแถวเดิมถ้าไม่ได้ถูกสั่ง
- รัน `python report.py` แล้วบอกว่าวันนั้นตลาด/หุ้นอยู่ในสถานการณ์แบบไหน (label, driver, events) — ไม่วิจารณ์ว่าเทรดถูกหรือผิด

## ระบบอัตโนมัติ
- GitHub Actions `daily-capture` รัน capture.py + report.py ทุกวันทำการ 05:30 เวลาไทย แล้ว commit data/
- งานสรุปของ Claude (ตั้งเวลาใน Claude desktop): git pull → อ่านข้อมูล → เติม notes.csv → `python report.py`
  → commit เฉพาะ notes.csv / trades.csv / hypotheses.md / โค้ด (ไม่ commit data/ เอง ให้บอททำ)
- ใช้ `.venv\Scripts\python.exe` บนเครื่องนี้ / ถ้าไม่มี remote ให้รัน `run_local.ps1` เก็บข้อมูลเอง
- ราคาปิดใช้ OHLCV ทางการจากแท่งรายวัน / VWAP, pre-market, sell_waves มาจากแท่งนาที
- แท่งรายวันของวันที่ตลาดยังไม่ปิด (ก่อน 16:30 ET) จะถูกตัดทิ้งอัตโนมัติ
- `enrich.py` คำนวณคอลัมน์อนุพันธ์ใหม่ทั้งหมดทุกรอบ (ย้อนหลังได้) — เพิ่มคอลัมน์ใหม่ให้เพิ่มที่นี่

## เช็กสมมติฐาน (เมื่อถูกสั่ง "เช็กสมมติฐาน")
1. อ่าน hypotheses.md และรัน `python report.py`
2. รายงานแต่ละข้อ แยก intraday / daily: n, จำนวนวันไม่ซ้ำ, % ถูก, **อัตราปกติ (base rate)**, **ต่างจากปกติ (edge = hit − base)**,
   ผลเฉลี่ย, หุ้นที่เกี่ยวข้อง และตัวอย่างวันที่เกิดล่าสุด 3 วัน
3. เกณฑ์สถานะ: n < 10 = ยังสรุปไม่ได้ · n ≥ 10 และ |edge| < 10 จุด = ไม่ต่างจากปกติ · edge ≥ +10 = เริ่มเห็นแนวโน้มว่าจริง
   · edge ≤ −10 = ข้อมูลไม่สนับสนุน — ห้ามสรุปเกินข้อมูล และบอกเสมอถ้าหลายแถวมาจากวันเดียวกัน
4. ถ้าผู้ใช้เพิ่มข้อใหม่ใน hypotheses.md ให้แปลงเป็น filter/success/groups ใน `HYPOTHESES` ของ analysis.py
   สมมติฐานที่ใช้ VWAP/sell_waves/ช่วงเวลาในวัน ให้ groups = ["intraday"] เท่านั้น
   ถ้าต้องใช้คอลัมน์ที่ยังไม่มี ให้เพิ่มใน enrich.py และคำนวณย้อนหลังจาก data/intraday ถ้าเป็นไปได้

## ปัจจัยภายนอก / ภายใน (ใส่ทุกครั้งที่สรุป)
- ภายนอก: ตลาด (SPY/VIX/ยีลด์/น้ำมัน), กลุ่ม (peer ETF), เหตุการณ์ใน events
- ภายใน: งบ, ข่าวบริษัท, analyst, insider — ดูจาก part_own และข่าว
- ใช้ R² 60 วันบอกว่าหุ้นผูกกับกลุ่ม/ตลาดแค่ไหน และ part_* บอกว่าวันนั้นขยับเพราะอะไร พร้อมตัวเลข ไม่ใช่ความรู้สึก

## งานรายสัปดาห์ (เมื่อถูกสั่ง "สรุปสัปดาห์")
- แยกตาม label และแยก intraday / daily แล้วดู ret_1d / ret_3d / ret_5d เฉลี่ย, n, จำนวนวัน และ base rate
- เทียบกลุ่ม: ปิดเหนือ vs ใต้ VWAP, gap_filled จริง/ไม่จริง, ret_first30 / ret_last60, ประเภท catalyst ใน notes
- หลังงบ: ไปต่อ/กลับตัว เทียบ base rate ของหุ้นตัวนั้น
- บอกจำนวนตัวอย่าง (n) ทุกครั้ง ถ้า n < 10 ให้ระบุว่า "ตัวอย่างยังน้อย ยังสรุปไม่ได้"
- ไม่ให้คำแนะนำซื้อขาย ให้เป็นข้อสังเกตทางสถิติเท่านั้น

## ความหมายของ label (มี gap = |gap_atr| >= 0.75)
- GAP_UP_GO: gap ขึ้น ปิดเหนือราคาเปิดและเหนือ VWAP (แรงซื้อต่อเนื่อง)
- GAP_UP_FADE: gap ขึ้น แต่ปิดใต้ VWAP และปิด gap หรือปิดต่ำกว่าราคาเปิด (โดนขาย)
- GAP_DOWN_GO: gap ลง และลงต่อ ปิดใต้ราคาเปิดและ VWAP
- GAP_DOWN_REVERSAL: gap ลง แต่ดีดกลับ ปิดเหนือ VWAP
- *_MIXED: ไม่ชัด / NO_GAP: |gap_atr| น้อยกว่า 0.75 (ถ้าไม่มี ATR ใช้ gap_pct < 2%)
- daily (ไม่มี VWAP) ใช้แค่ราคาเปิด/ปิด/ปิด gap — หยาบกว่า
