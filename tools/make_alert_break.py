# -*- coding: utf-8 -*-
# 🎨 สร้างรูปป้ายเตือน "ใกล้หมดเวลา" (assets/alert_break.png)
# รันใหม่เมื่อไหร่ก็ได้:  py -3 tools/make_alert_break.py
# ขนาด/สไตล์อ้างอิงจาก alert_checkin.png ให้ป้ายสองแบบดูเป็นชุดเดียวกัน
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "alert_break.png")

W, H = 677, 369
BG = (14, 23, 48, 255)        # น้ำเงินเข้มเหมือนพื้นแอพ
EDGE = (248, 113, 113, 255)   # ขอบแดง — ป้ายนี้คือของด่วน
GOLD = (241, 217, 124, 255)
GOLD_DIM = (212, 175, 55, 255)
TEXT = (244, 241, 232, 255)
MUTED = (147, 160, 196, 255)
RED_SOFT = (255, 157, 157, 255)


def font(name, size):
    # Leelawadee UI = ฟอนต์ไทยมาตรฐานของ Windows (มีทุกเครื่อง) — ถ้าหาไม่เจอค่อยถอยไป Tahoma
    for candidate in (name, "tahoma.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def emoji_font(size):
    try:
        return ImageFont.truetype("seguiemj.ttf", size)  # อิโมจิสีของ Windows
    except OSError:
        return None


img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# การ์ดขอบมน + ขอบแดงหนา (เงาบางๆ ด้านล่างให้ดูลอย)
d.rounded_rectangle([6, 10, W - 4, H - 4], radius=28, fill=(4, 7, 15, 180))
d.rounded_rectangle([4, 4, W - 8, H - 12], radius=28, fill=BG, outline=EDGE, width=4)
d.rounded_rectangle([14, 14, W - 18, H - 22], radius=22, outline=GOLD_DIM, width=1)

# แถบสีแดงบางๆ ด้านบน ให้รู้ทันทีว่าเป็นป้ายเตือน
d.rounded_rectangle([26, 26, W - 30, 34], radius=4, fill=EDGE)

ef = emoji_font(112)
if ef is not None:
    d.text((58, 120), "⏰", font=ef, embedded_color=True, anchor="lm")
else:
    d.text((58, 120), "!", font=font("leelawuib.ttf", 112), fill=EDGE, anchor="lm")

# ⚠️ Pillow ที่เครื่องนี้ไม่มี Raqm จึงวางสระ+วรรณยุกต์ซ้อนสองชั้นไม่ได้ (ิ่ ี่ ั่ จะเพี้ยน)
#    ข้อความในรูปจึงเลือกใช้เฉพาะคำที่มีเครื่องหมายชั้นเดียว — ประโยคเต็มอย่าง "กลับที่นั่ง"
#    กับตัวเลขนับถอยหลัง ให้ Tk วาดเป็น label ใต้รูปแทน (Tk ใช้ตัวเรนเดอร์ของ Windows ไทยตรงทุกตัว)
x = 196
d.text((x, 96), "ใกล้หมดเวลาแล้ว!", font=font("leelawuib.ttf", 54), fill=RED_SOFT, anchor="lm")
d.text((x, 162), "รีบกลับด่วน!", font=font("leelawuib.ttf", 46), fill=GOLD, anchor="lm")
d.text((x, 214), "เหลือเวลาไม่ถึง 1 นาที", font=font("leelawui.ttf", 26), fill=TEXT, anchor="lm")

# เส้นคั่น + บรรทัดล่างบอกที่มาของป้าย (กันเข้าใจผิดว่าเป็นการเรียกเช็คชื่อ)
d.line([40, 268, W - 44, 268], fill=(90, 106, 150, 255), width=1)
d.text((W // 2, 300), "GOLDEN BELL · เตือนเวลาออกไปข้างนอก",
       font=font("leelawui.ttf", 24), fill=MUTED, anchor="mm")

img.save(OUT)
print(f"✅ สร้างแล้ว: {OUT}  ({img.width}x{img.height})")
