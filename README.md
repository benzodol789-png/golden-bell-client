# 🔔 กระดิ่งทอง มรณะ — โปรแกรมฝั่งผู้ใช้ (Client)

โปรแกรม Windows สำหรับระบบเช็คชื่อ "กระดิ่งทอง มรณะ" — เชื่อมต่อเซิร์ฟเวอร์คลาวด์บน Railway
(ฝั่งเซิร์ฟเวอร์อยู่ที่ repo [golden-bell-server](https://github.com/benzodol789-png/golden-bell-server))

- `admin.py` — โปรแกรมแอดมิน: สร้างห้อง เรียกเช็คชื่อ ดูประวัติ (บอกชื่อผู้เรียก)
- `student.py` — โปรแกรมพนักงาน: เข้าห้อง รอเรียก กดยืนยันเช็คชื่อ
- `updater.py` — ระบบอัพเดทโปรแกรมในตัว (ปุ่ม "🔄 อัพเดทโปรแกรม" เช็คจาก GitHub Releases)
- `assets/` — เสียงแจ้งเตือน + โลโก้ (ถูก bundle เข้า .exe)
- `tests/` — ทดสอบ E2E โปรโตคอลกับเซิร์ฟเวอร์จริง

เซิร์ฟเวอร์: `https://goldenbell.jed89.com` (Railway, auto-deploy จาก repo ฝั่ง server)

## Build

```
py -3 -m PyInstaller เช็คชื่อ-ครู.spec --noconfirm       # → dist/กระดิ่งทองมรณะ-แอดมิน.exe
py -3 -m PyInstaller เช็คชื่อ-นักเรียน.spec --noconfirm   # → dist/กระดิ่งทองมรณะ-พนักงาน.exe
py -3 make_packages.py                                    # → .zip แจกจ่ายทั้งสองชุด
```

## ปล่อยเวอร์ชันใหม่ (ระบบอัพเดทในโปรแกรมดึงจากตรงนี้)

1. แก้โค้ด แล้วอัพเลขเวอร์ชัน `APP_VERSION` ใน `updater.py` (ที่เดียวพอ)
2. รันสคริปต์ปล่อยเวอร์ชัน — build + zip + สร้าง GitHub Release ให้ครบในคำสั่งเดียว:

```
py -3 release.py "สรุปว่ามีอะไรใหม่ (ผู้ใช้เห็นข้อความนี้ตอนกดอัพเดท)"
```

3. ผู้ใช้กดปุ่ม "🔄 อัพเดทโปรแกรม" ในแอพ → โปรแกรมดาวน์โหลด สลับไฟล์ และรีสตาร์ทเอง

> release.py จะอัพโหลด asset เป็นชื่อ ASCII (`golden-bell-admin.exe` / `golden-bell-employee.exe`)
> เพราะ GitHub เปลี่ยนชื่อไฟล์ภาษาไทย — โปรแกรมใช้ชื่อ ASCII นี้หาไฟล์อัพเดท
> ส่วนชื่อไฟล์บนเครื่องผู้ใช้ยังเป็นภาษาไทยเหมือนเดิม

## ทดสอบ

```
set ODOL_URL=https://goldenbell.jed89.com
py -3 tests/e2e_cleanup.py && py -3 tests/e2e_v3.py && py -3 tests/e2e_cleanup.py
```
