# Market Capture — คำสั่งสำหรับ Claude (Claude Code / Cowork)

โฟลเดอร์นี้เก็บข้อมูลตลาดรายวันของ watchlist: MXL, STRL, BTSG, MO, UUUU
ข้อมูลทั้งหมดมาจาก `capture.py` ห้ามแก้ตัวเลขราคาใน data/ ด้วยมือ

## ไฟล์
- `data/daily_summary.csv` — 1 แถวต่อหุ้นต่อวัน (gap, pre-market, VWAP, sell_waves, label, ret_1d/3d/5d, notes)
- `data/market_context.csv` — SPY, QQQ, VIX, ยีลด์ 10 ปี, น้ำมัน รายวัน
- `data/intraday/<วันที่>/<หุ้น>.csv` — แท่ง 1 นาทีดิบ รวม pre/post market (เวลา New York)
- `data/news/<วันที่>.json` — หัวข้อข่าวล่าสุดต่อหุ้น
- `data/earnings.csv` — วันประกาศงบจาก Yahoo (อาจเป็นวันประมาณการ)
- `events.csv` — ปฏิทินเศรษฐกิจ (FOMC, CPI) แก้/เพิ่มได้ คอลัมน์ `date,type,title,ticker,time_et`
- `hypotheses.md` — สมมติฐานที่ผู้ใช้สังเกตเห็น / `report.py` มีเงื่อนไขของแต่ละข้อใน `HYPOTHESES`
- `report.html` — รายงานอัตโนมัติ / `calendar.ics` — ปฏิทินสำหรับนำเข้า Google Calendar

## คอลัมน์สำคัญเรื่องปัจจัย
- `part_market` = การขยับของ SPY, `part_sector` = peer เหนือ SPY, `part_own` = หุ้นเหนือ peer
- `driver` = ส่วนที่ใหญ่ที่สุด (MARKET / SECTOR / OWN)
- `events` = ป้ายเหตุการณ์วันนั้น (CPI, FOMC, EARNINGS ±1 วัน)
- `source` = live_1m (ละเอียดสุด) / backfill_5m / backfill_1d (ไม่มี VWAP, pre-market, sell_waves)

## งานรายวัน (เมื่อถูกสั่ง "อัปเดตวันนี้")
1. เปิดแถวของวันล่าสุดใน daily_summary.csv
2. ตัวที่ |gap_pct| >= 2 หรือ |change_pct| >= 3 หรือ earnings_window = True:
   อ่านข่าวใน data/news และค้นเว็บเพิ่มได้ แล้วเติม notes สั้นๆ **ลงไฟล์ `notes.csv`** (คอลัมน์ date,ticker,notes)
   ห้ามเขียน notes ลง data/daily_summary.csv ตรงๆ (บอท GitHub Actions เขียนไฟล์นั้น จะชนกัน) — capture/report จะรวมให้เอง
   ตัวอย่าง notes:
   `earnings beat / guidance cut`, `analyst upgrade`, `sector sympathy (SOXX +3%)`, `macro: FOMC`, `no clear catalyst`
   ถ้าไม่แน่ใจให้เขียน `unconfirmed:` นำหน้า ห้ามเดา
3. ดูว่าหุ้นขยับเพราะตัวเองหรือตามกลุ่ม จาก `vs_peer_pct` และ `vs_spy_pct`
4. สรุปเป็นภาษาไทยสั้นๆ: ตลาดวันนั้นเป็นแบบไหน และแต่ละตัวมีอะไรผิดปกติ

## ระบบอัตโนมัติ
- GitHub Actions `daily-capture` รัน capture.py + report.py ทุกวันทำการ 05:30 เวลาไทย แล้ว commit data/
- งานสรุปของ Claude (ตั้งเวลาใน Claude desktop): git pull → อ่านข้อมูล → เติม notes.csv → `python report.py`
  → commit เฉพาะ notes.csv / hypotheses.md / report.py (ไม่ commit data/ เอง ให้บอททำ)
- ใช้ `.venv\Scripts\python.exe` บนเครื่องนี้ / ถ้าไม่มี remote ให้รัน `run_local.ps1` เก็บข้อมูลเอง
- ราคาปิดใช้ OHLCV ทางการจากแท่งรายวัน / VWAP, pre-market, sell_waves มาจากแท่งนาที
- แท่งรายวันของวันที่ตลาดยังไม่ปิด (ก่อน 16:30 ET) จะถูกตัดทิ้งอัตโนมัติ

## เช็กสมมติฐาน (เมื่อถูกสั่ง "เช็กสมมติฐาน")
1. อ่าน hypotheses.md และรัน `python report.py`
2. รายงานแต่ละข้อ: n, % ถูก, ผลเฉลี่ย, หุ้นที่เกี่ยวข้อง และตัวอย่างวันที่เกิดล่าสุด 3 วัน
3. ถ้า n < 10 ให้บอกว่ายังสรุปไม่ได้ ห้ามสรุปเกินข้อมูล
4. ถ้าผู้ใช้เพิ่มข้อใหม่ใน hypotheses.md ให้แปลงเป็น filter/success ใน `HYPOTHESES` ของ report.py
   ถ้าต้องใช้คอลัมน์ที่ยังไม่มี ให้เพิ่มใน capture.py และคำนวณย้อนหลังจาก data/intraday ได้ถ้าเป็นไปได้

## ปัจจัยภายนอก / ภายใน (ใส่ทุกครั้งที่สรุป)
- ภายนอก: ตลาด (SPY/VIX/ยีลด์/น้ำมัน), กลุ่ม (peer ETF), เหตุการณ์ใน events
- ภายใน: งบ, ข่าวบริษัท, analyst, insider — ดูจาก part_own และข่าว
- บอกว่าวันนั้นหุ้นแต่ละตัวขยับเพราะอะไรเป็นหลัก พร้อมตัวเลขจาก part_* ไม่ใช่ความรู้สึก

## งานรายสัปดาห์ (เมื่อถูกสั่ง "สรุปสัปดาห์")
- แยกตาม label (GAP_UP_GO / GAP_UP_FADE / ...) แล้วดู ret_1d / ret_3d / ret_5d เฉลี่ยและจำนวนตัวอย่าง
- เทียบกลุ่ม: ปิดเหนือ vs ใต้ VWAP, gap_filled จริง/ไม่จริง, ประเภท catalyst ใน notes
- บอกจำนวนตัวอย่าง (n) ทุกครั้ง ถ้า n < 10 ให้ระบุว่า "ตัวอย่างยังน้อย ยังสรุปไม่ได้"
- ไม่ให้คำแนะนำซื้อขาย ให้เป็นข้อสังเกตทางสถิติเท่านั้น

## ความหมายของ label
- GAP_UP_GO: gap ขึ้น ปิดเหนือราคาเปิดและเหนือ VWAP (แรงซื้อต่อเนื่อง)
- GAP_UP_FADE: gap ขึ้น แต่ปิดใต้ VWAP และปิด gap หรือปิดต่ำกว่าราคาเปิด (โดนขาย)
- GAP_DOWN_GO: gap ลง และลงต่อ ปิดใต้ราคาเปิดและ VWAP
- GAP_DOWN_REVERSAL: gap ลง แต่ดีดกลับ ปิดเหนือ VWAP
- *_MIXED: ไม่ชัด / NO_GAP: gap น้อยกว่า 2%
