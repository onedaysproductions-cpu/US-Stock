# Market Capture (MXL, STRL, BTSG, MO, UUUU)

เก็บข้อมูลตลาดรายวันอัตโนมัติด้วย GitHub Actions (ฟรี รันได้แม้ปิดคอม)

## ติดตั้ง (ครั้งเดียว)
1. สร้าง repo ใหม่บน GitHub (Private ได้)
2. อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์นี้ รวมโฟลเดอร์ `.github`
3. ไปที่แท็บ **Actions** → เลือก `daily-capture` → กด **Run workflow** เพื่อทดสอบ
4. เลือก workflow `backfill` → Run workflow **ครั้งเดียว** เพื่อไล่เก็บย้อนหลัง (1 นาที ~30 วัน + 5 นาที ~60 วัน + รายวัน 5 ปี)
5. หลังจากนั้น `daily-capture` จะรันเองทุกวัน 05:30 เวลาไทย และอัปเดต `report.html` กับ `calendar.ics`

## ดูรายงาน
ดาวน์โหลด `report.html` จาก repo แล้วเปิดในเบราว์เซอร์ (หรือเปิด GitHub Pages ถ้า repo เป็น public)

## ผูกกับ Google Calendar
- Google Calendar → การตั้งค่า → นำเข้าและส่งออก → นำเข้า → เลือก `calendar.ics`
- นำเข้าใหม่เมื่อมีวันประกาศงบเพิ่ม (event ซ้ำจะถูกแทนที่ด้วย UID เดิม)
- ถ้า repo เป็น public: ใช้ "เพิ่มปฏิทินจาก URL" ใส่ลิงก์ raw ของ `calendar.ics` จะอัปเดตเอง
- ปฏิทินเศรษฐกิจอยู่ใน `events.csv` (FOMC, CPI) เพิ่มเหตุการณ์อื่นได้ เช่น NFP, PCE

## รันบนเครื่องตัวเอง (ทางเลือก)
```
pip install -r requirements.txt
python capture.py
```

## แก้รายชื่อหุ้น
แก้ `WATCHLIST` ใน `capture.py` (หุ้น : ETF ที่ใช้เทียบกลุ่ม)

## ข้อควรรู้
- แท่ง 1 นาทีจาก Yahoo ย้อนหลังได้ราว 7 วัน ถ้า workflow ล้มเกิน 5 วันทำการ ข้อมูลรายนาทีช่วงนั้นจะหาย
- yfinance เป็นแหล่งไม่เป็นทางการ บางวันอาจดึงไม่ได้ ให้กด Run workflow ซ้ำ
- GitHub อาจรัน schedule ช้ากว่ากำหนดไม่กี่นาทีถึงชั่วโมง ไม่กระทบข้อมูล
