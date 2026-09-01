# -*- coding: utf-8 -*-
# 🚀 ปล่อยเวอร์ชันใหม่ครบวงจร: build .exe ทั้งสอง → อัพขึ้น GitHub Release → อัพเดทชุด .zip
#
# วิธีใช้:  py -3 release.py "ข้อความบอกว่ามีอะไรใหม่ (ผู้ใช้เห็นตอนกดอัพเดท)"
# เลขเวอร์ชันอ่านจาก APP_VERSION ใน updater.py — แก้ที่นั่นที่เดียวก่อนปล่อย
#
# หมายเหตุ: build ลงโฟลเดอร์ build-out ก่อน (ไม่ใช่ dist โดยตรง) เพราะถ้าผู้ใช้เปิด
# โปรแกรมค้างอยู่ ไฟล์ใน dist จะถูกล็อกจน build ล้ม — แยก build ออกมาแล้วค่อยคัดลอก
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build-out")
DIST = os.path.join(HERE, "dist")

ver = re.search(r'APP_VERSION = "([^"]+)"',
                open(os.path.join(HERE, "updater.py"), encoding="utf-8").read()).group(1)
tag = f"v{ver}"
notes = sys.argv[1] if len(sys.argv) > 1 else f"เวอร์ชัน {ver}"

print(f"🔨 build {tag} ...")
for spec in ("เช็คชื่อ-ครู.spec", "เช็คชื่อ-นักเรียน.spec"):
    subprocess.run([sys.executable, "-m", "PyInstaller", spec, "--noconfirm",
                    "--distpath", OUT, "--log-level", "WARN"], cwd=HERE, check=True)

# GitHub เปลี่ยนชื่อ asset ที่มีอักษรไทย — อัพโหลดเป็นชื่อ ASCII ที่ updater.py ใช้หา
pairs = [("กระดิ่งทองมรณะ-แอดมิน.exe", "golden-bell-admin.exe"),
         ("กระดิ่งทองมรณะ-พนักงาน.exe", "golden-bell-employee.exe")]
uploads = []
for thai, ascii_name in pairs:
    dst = os.path.join(OUT, ascii_name)
    shutil.copyfile(os.path.join(OUT, thai), dst)
    uploads.append(dst)

print(f"📤 สร้าง GitHub Release {tag} ...")
subprocess.run(["gh", "release", "create", tag, *uploads,
                "--title", tag, "--notes", notes], cwd=HERE, check=True)
print(f"✅ ปล่อย {tag} แล้ว — ผู้ใช้กดปุ่ม '🔄 อัพเดทโปรแกรม' ในแอพได้เลย")

# อัพเดทชุด .zip สำหรับแจกเครื่องใหม่ — ข้ามได้ถ้าโปรแกรมเปิดค้างอยู่ (ไฟล์ถูกล็อก)
os.makedirs(DIST, exist_ok=True)
locked = []
for thai, _ in pairs:
    try:
        shutil.copyfile(os.path.join(OUT, thai), os.path.join(DIST, thai))
    except OSError:
        locked.append(thai)
if locked:
    print(f"⚠️  ข้ามการอัพเดทชุด .zip — ปิดโปรแกรมที่เปิดค้างอยู่ ({', '.join(locked)}) "
          f"แล้วรัน: py -3 make_packages.py")
else:
    subprocess.run([sys.executable, os.path.join(HERE, "make_packages.py")], check=True)
