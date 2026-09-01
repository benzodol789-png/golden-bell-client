# -*- coding: utf-8 -*-
# สร้างชุดแจกจ่าย (รุ่นคลาวด์ v3 — เซิร์ฟเวอร์รันบน Railway ตลอด 24 ชม.)
# ☁️ ไม่ต้องมี server exe / ngrok.exe อีกแล้ว — client ต่อตรงที่โดเมนถาวรของ Railway
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
SERVER_URL = "https://goldenbell.jed89.com"

# ไฟล์ตั้งค่า — โปรแกรมอ่านไฟล์นี้แล้วต่อลิงก์นี้ก่อนเสมอ (ต่อติดทันที ไม่ต้องเดา)
server_txt = os.path.join(DIST, "เซิร์ฟเวอร์.txt")
with open(server_txt, "w", encoding="utf-8") as f:
    f.write("# ที่อยู่เซิร์ฟเวอร์คลาวด์ (Railway) — โปรแกรมจะต่อที่นี่ก่อนเสมอ\n")
    f.write("# ปกติไม่ต้องแก้ไข ถ้าย้ายเซิร์ฟเวอร์ค่อยเปลี่ยนบรรทัดล่าง\n")
    f.write(f"{SERVER_URL}\n")

# ========== 1. Admin .zip ==========
admin_exe = os.path.join(DIST, "กระดิ่งทองมรณะ-แอดมิน.exe")

readme_admin = os.path.join(DIST, "README-แอดมิน.txt")
with open(readme_admin, "w", encoding="utf-8") as f:
    f.write(
        "กระดิ่งทอง มรณะ — โปรแกรมแอดมิน (รุ่นคลาวด์ Railway)\n"
        "=====================================================\n\n"
        "เซิร์ฟเวอร์รันบนคลาวด์ตลอด 24 ชม. — ไม่ต้องเปิดเครื่องเซิร์ฟเวอร์เอง\n\n"
        "วิธีใช้:\n"
        "1. แตกไฟล์ .zip นี้ออกมาให้ครบทุกไฟล์ (อยู่โฟลเดอร์เดียวกัน)\n"
        "2. ดับเบิลคลิก 'กระดิ่งทองมรณะ-แอดมิน.exe'\n"
        "3. โปรแกรมเชื่อมต่อเซิร์ฟเวอร์คลาวด์อัตโนมัติ\n"
        "4. ใส่ชื่อแอดมิน สร้างห้อง แล้วเรียกเช็คชื่อพนักงานได้เลย\n\n"
        f"เซิร์ฟเวอร์: {SERVER_URL}\n\n"
        "ถ้าขึ้นเตือนความปลอดภัยของ Windows (SmartScreen):\n"
        "  กด 'ข้อมูลเพิ่มเติม (More info)' แล้วกด 'เรียกใช้อยู่ดี (Run anyway)'\n\n"
        "หมายเหตุ: ต้องเก็บไฟล์ 'เซิร์ฟเวอร์.txt' ไว้ในโฟลเดอร์เดียวกับ .exe เสมอ\n"
    )

zip_admin = os.path.join(DIST, "กระดิ่งทองมรณะ-แอดมิน.zip")
with zipfile.ZipFile(zip_admin, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(admin_exe, "กระดิ่งทองมรณะ-แอดมิน.exe")
    z.write(server_txt, "เซิร์ฟเวอร์.txt")
    z.write(readme_admin, "README-แอดมิน.txt")

print(f"✅ Admin .zip: {zip_admin} ({os.path.getsize(zip_admin)//1024//1024} MB)")

# ========== 2. Employee .zip ==========
employee_exe = os.path.join(DIST, "กระดิ่งทองมรณะ-พนักงาน.exe")

readme_emp = os.path.join(DIST, "วิธีใช้-พนักงาน.txt")
with open(readme_emp, "w", encoding="utf-8") as f:
    f.write(
        "กระดิ่งทอง มรณะ — โปรแกรมพนักงาน (รุ่นคลาวด์ Railway)\n"
        "======================================================\n\n"
        "วิธีใช้:\n"
        "1. แตกไฟล์ .zip นี้ออกมาให้ครบทุกไฟล์ (อยู่โฟลเดอร์เดียวกัน)\n"
        "2. ดับเบิลคลิก 'กระดิ่งทองมรณะ-พนักงาน.exe'\n"
        "3. โปรแกรมเชื่อมต่อเซิร์ฟเวอร์คลาวด์อัตโนมัติ\n"
        "4. ป้อนชื่อของคุณ แล้วเลือกห้อง\n"
        "5. รอแอดมินเรียกเช็คชื่อ\n\n"
        "ถ้าขึ้นเตือนความปลอดภัยของ Windows (SmartScreen):\n"
        "  กด 'ข้อมูลเพิ่มเติม (More info)' แล้วกด 'เรียกใช้อยู่ดี (Run anyway)'\n\n"
        "หมายเหตุ:\n"
        "  - ต้องมี Internet เพื่อเชื่อมต่อเซิร์ฟเวอร์\n"
        "  - ต้องเก็บไฟล์ 'เซิร์ฟเวอร์.txt' ไว้ในโฟลเดอร์เดียวกับ .exe เสมอ\n"
    )

zip_emp = os.path.join(DIST, "กระดิ่งทองมรณะ-พนักงาน.zip")
with zipfile.ZipFile(zip_emp, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(employee_exe, "กระดิ่งทองมรณะ-พนักงาน.exe")
    z.write(server_txt, "เซิร์ฟเวอร์.txt")
    z.write(readme_emp, "วิธีใช้-พนักงาน.txt")

print(f"✅ Employee .zip: {zip_emp} ({os.path.getsize(zip_emp)//1024//1024} MB)")

for zp in (zip_admin, zip_emp):
    with zipfile.ZipFile(zp) as z:
        print(os.path.basename(zp) + ":")
        for n in z.namelist():
            print("  -", n)

print("\n📦 ส่งต่อได้แล้ว! (เซิร์ฟเวอร์อยู่บน Railway — ไม่ต้องแจก server exe / ngrok.exe)")
