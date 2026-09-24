# -*- coding: utf-8 -*-
# 🔔 กระดิ่งทอง มรณะ — โปรแกรมพนักงาน
import ctypes
import math
import os
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import socketio

import prefs    # 💾 เก็บค่าตั้งค่าของผู้ใช้ (ระดับเสียง)
import theme    # 🎨 ระบบธีม มืด/สว่าง
import updater  # 🔄 ระบบอัพเดทโปรแกรมจาก GitHub Releases

updater.cleanup_old()  # ลบไฟล์ .old ที่ค้างจากการอัพเดทรอบก่อน

APP_NAME = "กระดิ่งทอง มรณะ"


def resource_path(filename):
    # ตอนรันเป็น .exe ไฟล์ asset อยู่ที่ root ของ bundle (_MEIPASS) / ตอน dev อยู่ในโฟลเดอร์ assets
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    return os.path.join(base, filename)


def app_dir():
    # โฟลเดอร์ของ .exe (ตอน build) หรือของสคริปต์ — ไม่พึ่ง working directory
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ========== หาเซิร์ฟเวอร์ในเครือข่าย ==========
def server_candidates():
    candidates = []
    addr_file = os.path.join(app_dir(), "server_address.txt")
    if os.path.exists(addr_file):
        try:
            with open(addr_file, "r", encoding="utf-8") as f:
                addr = f.read().strip()
                if ":" in addr:
                    candidates.append(addr.split(":")[0])
        except:
            pass
    candidates.append("127.0.0.1")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
        s.close()
        candidates.insert(0, my_ip)
        parts = my_ip.split(".")
        if len(parts) == 4:
            prefix = ".".join(parts[:3])
            candidates.extend([f"{prefix}.1", f"{prefix}.100", f"{prefix}.254"])
    except:
        pass
    return list(dict.fromkeys(candidates))


PORT = 5000
SERVER_DOMAIN = "goldenbell.jed89.com"  # ☁️ โดเมนถาวร (custom domain บน Railway)
ACCESS_CODE = "ODOL-2569"  # รหัสเข้าระบบ — ต้องตรงกับเซิร์ฟเวอร์


def pinned_address():
    # ✅ ถ้ามีไฟล์ "เซิร์ฟเวอร์.txt" วางข้าง .exe → ใช้ที่อยู่นั้นก่อน (ต่อติดทันที)
    #    ✅ บั๊ก #5 แก้: ใช้ encoding="utf-8-sig" เพื่อขจัด BOM ที่ Notepad บันทึกไว้
    for fn in ("เซิร์ฟเวอร์.txt", "server.txt", "server_url.txt"):
        path = os.path.join(app_dir(), fn)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            return line
            except Exception:
                pass
    return ""


PINNED = pinned_address()


def normalize_target(text):
    # ช่องที่อยู่รับได้ทั้ง IP ("192.168.1.109"), IP:พอร์ต, ชื่อเครื่อง, หรือลิงก์/โดเมน
    text = text.strip().rstrip("/")
    if not text:
        return ""
    if "://" in text:
        return text
    if ":" in text:
        return f"http://{text}"  # ระบุพอร์ตเอง = เซิร์ฟเวอร์ในวงแลน (http)
    if "." in text and any(ch.isalpha() for ch in text):
        return f"https://{text}"  # โดเมนอินเทอร์เน็ต
    return f"http://{text}:{PORT}"  # IP หรือชื่อเครื่องในวงแลน


DISCOVERY_PORT = 5001


def discover_servers(wait=1.0):
    # ✅ broadcast หาเซิร์ฟเวอร์ในวง LAN — IP ที่ตอบกลับคือเส้นทางที่คุยกันได้จริง
    # (แก้ปัญหาเครื่องเซิร์ฟเวอร์มีหลายการ์ดแลน/VPN แล้วประกาศ IP ผิดตัว)
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.35)
        for _ in range(2):
            try:
                s.sendto(b"ODOL_DISCOVER", ("255.255.255.255", DISCOVERY_PORT))
                s.sendto(b"ODOL_DISCOVER", ("127.0.0.1", DISCOVERY_PORT))
            except OSError:
                pass
            end = time.time() + wait / 2
            while time.time() < end:
                try:
                    data, addr = s.recvfrom(64)
                    if data == b"ODOL_HERE" and addr[0] not in found:
                        found.append(addr[0])
                except OSError:
                    break
        s.close()
    except Exception:
        pass
    return found


# ========== จำชื่อพนักงานไว้ในเครื่อง — เปิดครั้งต่อไปไม่ต้องพิมพ์ใหม่ ==========
def name_store_path():
    base = os.environ.get("APPDATA") or app_dir()
    folder = os.path.join(base, "GoldenBellCheckin")
    try:
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "user.txt")
    except OSError:
        return None


def load_saved_name():
    try:
        path = name_store_path()
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def save_name(name):
    try:
        path = name_store_path()
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(name)
    except Exception:
        pass


# ========== เสียงแจ้งเตือน (MCI ของ Windows) ==========
_sound_ready = False
_alert_sounds = []  # ✅ ฟีเจอร์ใหม่: เสียงแจ้งหลายตัว
_checkin_sound = None  # 🔔 เสียงเตือน "ถึงรอบเช็คชื่อในกลุ่ม" (คนละตัวกับเสียงเรียกของแอดมิน)
_break_voice = None  # ⏰ เสียงพูด "ใกล้หมดเวลาแล้ว อย่าลืมกดกลับที่นั่งด้วยนะ" — ใช้เมื่อไม่รู้จักกิจกรรม
# ⏰ เสียงพูดแยกตามกิจกรรม — บอกไปเลยว่ากำลังจะหมดเวลาของอะไร ("ปวดน้อย ใกล้หมดเวลาแล้ว...")
_break_voice_files = {"ปวดน้อย": "alert_break_light.mp3",
                      "ปวดหนัก": "alert_break_heavy.mp3",
                      "กินข้าว": "alert_break_food.mp3"}
_break_voices = {}  # ชื่อกิจกรรม -> alias ของ MCI


def init_sound():
    global _sound_ready, _alert_sounds
    try:
        # ✅ ฟีเจอร์ใหม่: load เสียงแจ้งหลายตัว แล้วสุ่มเลือกตอน play
        for sound_name in ("alert_thai.mp3", "alert_thai2.mp3", "alert_thai3.mp3"):
            path = resource_path(sound_name)
            if os.path.exists(path):
                alias = f"odol_alert_{len(_alert_sounds)}"
                try:
                    ret = ctypes.windll.winmm.mciSendStringW(
                        f'open "{path}" type mpegvideo alias {alias}', None, 0, None
                    )
                    if ret == 0:
                        _alert_sounds.append(alias)
                except:
                    pass
        _sound_ready = len(_alert_sounds) > 0
        # 🔔 เสียงเตือน "ถึงรอบเช็คชื่อในกลุ่ม" — คนละไฟล์กับเสียงเรียกของแอดมิน
        global _checkin_sound, _break_voice
        path = resource_path("alert_checkin.mp3")
        if os.path.exists(path):
            if ctypes.windll.winmm.mciSendStringW(
                    f'open "{path}" type mpegvideo alias odol_checkin', None, 0, None) == 0:
                _checkin_sound = "odol_checkin"
        # ⏰ เสียงพูดสำหรับป้ายใกล้หมดเวลา — เล่นต่อจากเสียงเช็คชื่อ (เสียงเดียวกัน) ให้รู้ว่าต้องรีบกลับ
        path = resource_path("alert_break_voice.mp3")
        if os.path.exists(path):
            if ctypes.windll.winmm.mciSendStringW(
                    f'open "{path}" type mpegvideo alias odol_break_voice', None, 0, None) == 0:
                _break_voice = "odol_break_voice"
        # เสียงที่บอกกิจกรรมด้วย — โหลดเท่าที่มีไฟล์ ขาดตัวไหนก็ถอยไปใช้เสียงกลาง
        for i, (activity, filename) in enumerate(_break_voice_files.items()):
            path = resource_path(filename)
            if not os.path.exists(path):
                continue
            alias = f"odol_break_voice_{i}"
            if ctypes.windll.winmm.mciSendStringW(
                    f'open "{path}" type mpegvideo alias {alias}', None, 0, None) == 0:
                _break_voices[activity] = alias
    except:
        pass


def play_break_voice(activity=""):
    # เลือกเสียงที่บอกกิจกรรมนั้นก่อน ("ปวดน้อย ใกล้หมดเวลาแล้ว...") ไม่มีค่อยใช้เสียงกลาง
    alias = _break_voices.get(activity) or _break_voice
    try:
        if alias and _volume > 0:
            ctypes.windll.winmm.mciSendStringW(
                f"setaudio {alias} volume to {_volume * 10}", None, 0, None)
            ctypes.windll.winmm.mciSendStringW(f"play {alias} from 0", None, 0, None)
    except:
        pass


def play_break_alert(activity=""):
    """เสียงป้ายใกล้หมดเวลา = เสียงพูดอย่างเดียว เช่น "ปวดหนัก ใกล้หมดเวลาแล้ว อย่าลืมกดกลับที่นั่งด้วยนะ"
    (ไม่เอาเสียงเตือนเช็คชื่อมาเล่นนำแล้ว — คนละเรื่องกัน ฟังแล้วสับสน)"""
    play_break_voice(activity)


def stop_break_alert():
    try:
        for alias in list(_break_voices.values()) + ([_break_voice] if _break_voice else []):
            ctypes.windll.winmm.mciSendStringW(f"stop {alias}", None, 0, None)
    except:
        pass


def play_checkin_alert():
    # เสียงเตือนถึงรอบเช็คชื่อ — ใช้ระดับเสียงเดียวกับที่ผู้ใช้ตั้งไว้
    try:
        if _checkin_sound and _volume > 0:
            ctypes.windll.winmm.mciSendStringW(
                f"setaudio {_checkin_sound} volume to {_volume * 10}", None, 0, None)
            ctypes.windll.winmm.mciSendStringW(f"play {_checkin_sound} from 0", None, 0, None)
        elif _volume > 0:
            ctypes.windll.user32.MessageBeep(0x30)
    except:
        pass


def stop_checkin_alert():
    try:
        if _checkin_sound:
            ctypes.windll.winmm.mciSendStringW(f"stop {_checkin_sound}", None, 0, None)
    except:
        pass


# 🔊 ระดับเสียงแจ้งเตือน 0-100 (จำค่าไว้ให้ เปิดโปรแกรมใหม่ก็ยังเป็นค่าเดิม)
_volume = max(0, min(100, prefs.get("volume", 80)))


def apply_volume(vol):
    # MCI ใช้สเกล 0-1000 และตั้งแยกทีละเสียง — ต้องตั้งใหม่ทุกครั้งที่เปิดเสียงเพิ่ม
    global _volume
    _volume = max(0, min(100, int(vol)))
    try:
        for alias in _alert_sounds:
            ctypes.windll.winmm.mciSendStringW(
                f"setaudio {alias} volume to {_volume * 10}", None, 0, None)
    except:
        pass


def play_alert():
    try:
        if _sound_ready and _alert_sounds:
            import random
            alias = random.choice(_alert_sounds)  # ✅ สุ่มเลือกเสียงแจ้ง
            ctypes.windll.winmm.mciSendStringW(f"play {alias} from 0", None, 0, None)
        elif _volume > 0:
            ctypes.windll.user32.MessageBeep(0x30)  # เสียงระบบสำรอง — ต้องมีเสียงทุกครั้ง
    except:
        pass


def stop_alert():
    # ✅ หยุดเสียงแจ้งทั้งหมดทันที เมื่อพนักงานกดยืนยัน
    try:
        if _sound_ready and _alert_sounds:
            for alias in _alert_sounds:
                ctypes.windll.winmm.mciSendStringW(f"stop {alias}", None, 0, None)
    except:
        pass


# ========== ธีมสี — มืด น้ำเงิน ขอบทอง หรูหรา ==========
theme.init(theme.load_saved())  # โหลดธีมที่ผู้ใช้เลือกไว้ก่อนสร้างหน้าต่าง
C = theme.C  # ชุดสีปัจจุบัน — เปลี่ยนค่าในตัวเองเมื่อสลับธีม

F_TITLE = ("Segoe UI", 18, "bold")
F_HEAD = ("Segoe UI", 14, "bold")
F_NORMAL = ("Segoe UI", 12)
F_BOLD = ("Segoe UI", 12, "bold")
F_SMALL = ("Segoe UI", 10)


def round_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class GoldButton(tk.Canvas):
    """ปุ่มขอบมน มีเงาให้ความรู้สึกมีมิติ กดแล้วยุบตัวลง"""

    _all = []  # ปุ่มทุกตัวที่สร้างไว้ — ใช้ทาสีใหม่ตอนสลับธีม

    def __init__(self, master, text, command=None, w=190, h=46, kind="blue",
                 font=F_BOLD, bg=None):
        super().__init__(master, width=w, height=h + 4, bg=bg or master["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.kind = kind
        self.k = theme.BUTTON_KINDS[kind]
        self.w, self.h = w, h
        r = h // 2 - 4
        self.create_polygon(round_points(3, 7, w - 3, h + 1, r),
                            smooth=True, fill=C["shadow"], outline="")
        self.body = self.create_polygon(round_points(3, 3, w - 3, h - 3, r),
                                        smooth=True, fill=self.k["fill"],
                                        outline=self.k["outline"], width=1.5)
        self.label = self.create_text(w // 2, h // 2, text=text, font=font, fill=self.k["fg"])
        self.bind("<Enter>", lambda e: self.itemconfig(self.body, fill=self.k["hover"]))
        self.bind("<Leave>", lambda e: self._reset())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        GoldButton._all.append(self)

    def restyle(self):
        # ทาสีใหม่ตามธีมปัจจุบัน (Canvas วาดเอง ระบบธีมจึงเปลี่ยนให้ไม่ได้)
        self.k = theme.BUTTON_KINDS[self.kind]
        self.itemconfig(self.body, fill=self.k["fill"], outline=self.k["outline"])
        self.itemconfig(self.label, fill=self.k["fg"])
        try:
            self.configure(bg=self.master["bg"])
        except Exception:
            pass

    def _reset(self):
        self.itemconfig(self.body, fill=self.k["fill"])
        self.moveto(self.body, 3, 3)
        self.coords(self.label, self.w // 2, self.h // 2)

    def _press(self, _):
        self.moveto(self.body, 3, 6)
        self.coords(self.label, self.w // 2, self.h // 2 + 3)

    def _release(self, e):
        self._reset()
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h and self.command:
            self.command()


class RoundedCard(tk.Canvas):
    """การ์ดขอบมน ขอบทอง — วางวิดเจ็ตลูกใน .inner"""

    def __init__(self, master, w, h, fill=None, bg=None):
        super().__init__(master, width=w, height=h, bg=bg or master["bg"],
                         highlightthickness=0, bd=0)
        fill = fill or C["card"]
        self.create_polygon(round_points(4, 8, w - 2, h - 1, 18),
                            smooth=True, fill=C["shadow"], outline="")
        self.create_polygon(round_points(2, 2, w - 4, h - 5, 18),
                            smooth=True, fill=fill, outline=C["gold"], width=1.5)
        self.inner = tk.Frame(self, bg=fill)
        self.create_window(w // 2, h // 2 - 1, window=self.inner,
                           width=w - 40, height=h - 40)


STATUS_TH = {
    "wait": "⏳ ยังไม่เช็คชื่อ",
    "pending": "🔔 รอยืนยัน...",
    "checked": "✅ เข้างานแล้ว",
}

# ========== หน้าต่างหลัก ==========
root = tk.Tk()
root.title(f"🔔 {APP_NAME} — พนักงาน")
root.resizable(True, True)  # ขนาดจริงคำนวณจากเนื้อหาใน refit()
root.configure(bg=C["bg"])

try:
    _icon = tk.PhotoImage(file=resource_path("logo_small.png"))
    root.iconphoto(True, _icon)
except:
    _icon = None

sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=1)
state = {"connected": False, "room": None, "name": "", "popup": None, "manual_ip": "",
         "worker_running": False, "watchdog": False, "confirm_waiting": False}

# ---------- ส่วนหัว ----------
header = tk.Frame(root, bg=C["panel"], height=80)
header.pack(fill="x")
header.pack_propagate(False)

if _icon is not None:
    # โลโก้กระดิ่งทองเส้นสีอ่อน — วางบนป้ายพื้นเข้มขอบทองให้เด่น
    logo_chip = tk.Canvas(header, width=60, height=56, bg=C["panel"],
                          highlightthickness=0, bd=0)
    logo_chip.pack(side="left", padx=(16, 8), pady=12)
    logo_chip.create_polygon(round_points(2, 2, 58, 54, 14), smooth=True,
                             fill="#0A1228", outline=C["gold"], width=2)
    logo_chip.create_image(30, 28, image=_icon)

_title_box = tk.Frame(header, bg=C["panel"])
_title_box.pack(side="left", padx=6)
tk.Label(_title_box, text=APP_NAME, font=F_TITLE, bg=C["panel"],
         fg=C["gold"]).pack(anchor="w", pady=(12, 0))
conn_label = tk.Label(_title_box, text="🔍 กำลังค้นหาเซิร์ฟเวอร์...", font=F_SMALL,
                      bg=C["panel"], fg=C["muted"])
conn_label.pack(anchor="w")

tk.Frame(root, bg=C["gold"], height=2).pack(fill="x")

body = tk.Frame(root, bg=C["bg"])
body.pack(fill="both", expand=True)

status_label = tk.Label(root, text="", font=F_SMALL, bg=C["bg"], fg=C["muted"])
status_label.pack(side="bottom", pady=(0, 6))

# ✅ แถบเวอร์ชัน + ปุ่มอัพเดทโปรแกรม (แถวล่างสุด)
_update_bar = tk.Frame(root, bg=C["bg"])
_update_bar.pack(side="bottom", pady=(0, 2))
tk.Label(_update_bar, text=f"เวอร์ชัน {updater.APP_VERSION}", font=F_SMALL,
         bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 12))
update_btn = tk.Button(_update_bar, text="🔄 อัพเดทโปรแกรม", font=F_SMALL,
                       bg=C["bg"], fg=C["gold_light"], activebackground=C["bg"],
                       activeforeground=C["gold"], relief="flat", bd=0, cursor="hand2",
                       command=lambda: run_update())
update_btn.pack(side="left")


def run_update():
    update_btn.config(state="disabled")  # กันกดซ้ำระหว่างเช็ค/ดาวน์โหลด
    updater.start_update_flow(
        root, "golden-bell-employee.exe", set_status,
        ask_confirm=messagebox.askyesno,
        show_error=messagebox.showerror,
        show_info=messagebox.showinfo,
        on_finish=lambda: update_btn.config(state="normal"),
    )


# ✅ ปุ่มสลับธีม มืด/สว่าง — จำค่าที่เลือกไว้ให้เอง
def _theme_label():
    return "☀️ ธีมสว่าง" if theme.current() == "dark" else "🌙 ธีมมืด"


def toggle_theme():
    theme.apply(root, "light" if theme.current() == "dark" else "dark")
    theme_btn.config(text=_theme_label())
    refit()


theme_btn = tk.Button(_update_bar, text="", font=F_SMALL, bg=C["bg"], fg=C["muted"],
                      activebackground=C["bg"], activeforeground=C["gold"],
                      relief="flat", bd=0, cursor="hand2", command=lambda: toggle_theme())
theme_btn.pack(side="left", padx=(14, 0))
theme_btn.config(text=_theme_label())

# ✅ แถบปรับระดับเสียงเรียกเช็คชื่อ — กด −/+ หรือลากแถบก็ได้ จำค่าไว้ให้เอง
_vol_bar = tk.Frame(root, bg=C["bg"])
_vol_bar.pack(side="bottom", pady=(0, 2))


def _vol_icon(v):
    return "🔇" if v == 0 else ("🔈" if v < 34 else ("🔉" if v < 67 else "🔊"))


def _refresh_vol_ui():
    vol_icon.config(text=_vol_icon(_volume))
    vol_value.config(text=f"{_volume}%" if _volume else "ปิดเสียง")


def change_volume(v, play_sample=True):
    apply_volume(v)
    prefs.set("volume", _volume)
    vol_scale.set(_volume)
    _refresh_vol_ui()
    if play_sample and _volume > 0:
        play_alert()  # ให้ได้ยินทันทีว่าดังแค่ไหน


vol_icon = tk.Label(_vol_bar, text="", font=F_SMALL, bg=C["bg"], fg=C["gold_light"])
vol_icon.pack(side="left", padx=(0, 2))
tk.Label(_vol_bar, text="เสียงเรียก", font=F_SMALL, bg=C["bg"],
         fg=C["muted"]).pack(side="left", padx=(0, 6))
tk.Button(_vol_bar, text="−", font=F_BOLD, bg=C["bg"], fg=C["gold_light"],
          activebackground=C["bg"], activeforeground=C["gold"], relief="flat", bd=0,
          cursor="hand2", command=lambda: change_volume(_volume - 10)).pack(side="left", padx=2)
vol_scale = tk.Scale(_vol_bar, from_=0, to=100, orient="horizontal", showvalue=False,
                     length=120, sliderlength=16, width=8, resolution=5,
                     bg=C["bg"], fg=C["text"], troughcolor=C["card_dark"],
                     activebackground=C["gold"], highlightthickness=0, bd=0,
                     command=lambda v: change_volume(int(float(v)), play_sample=False))
vol_scale.pack(side="left")
vol_scale.bind("<ButtonRelease-1>", lambda e: change_volume(_volume))  # ปล่อยเมาส์แล้วลองเสียง
tk.Button(_vol_bar, text="+", font=F_BOLD, bg=C["bg"], fg=C["gold_light"],
          activebackground=C["bg"], activeforeground=C["gold"], relief="flat", bd=0,
          cursor="hand2", command=lambda: change_volume(_volume + 10)).pack(side="left", padx=2)
vol_value = tk.Label(_vol_bar, text="", font=F_SMALL, bg=C["bg"], fg=C["muted"], width=8)
vol_value.pack(side="left", padx=(4, 0))
tk.Button(_vol_bar, text="▶ ทดสอบ", font=F_SMALL, bg=C["bg"], fg=C["gold_light"],
          activebackground=C["bg"], activeforeground=C["gold"], relief="flat", bd=0,
          cursor="hand2", command=lambda: play_alert()).pack(side="left", padx=(10, 0))

vol_scale.set(_volume)
_refresh_vol_ui()


def _restyle_tables():
    # ttk เปลี่ยนสีผ่าน style เท่านั้น — ต้องตั้งใหม่ทุกครั้งที่สลับธีม
    style.configure("Odol.Treeview", background=C["card_dark"], fieldbackground=C["card_dark"],
                    foreground=C["text"])
    style.configure("Odol.Treeview.Heading", background=C["card_dark"], foreground=C["gold_light"])
    style.map("Odol.Treeview", background=[("selected", C["blue_hover"])])
    style.map("Odol.Treeview.Heading", background=[("active", C["card_dark"])])


theme.on_change(_restyle_tables)
theme.on_change(lambda: [b.restyle() for b in GoldButton._all])

# ---------- สไตล์ตาราง ----------
style = ttk.Style()
style.theme_use("clam")
style.configure("Odol.Treeview", background=C["card_dark"], fieldbackground=C["card_dark"],
                foreground=C["text"], rowheight=36, font=F_NORMAL, borderwidth=0)
style.configure("Odol.Treeview.Heading", background="#0A1228", foreground=C["gold_light"],
                font=F_BOLD, borderwidth=0, relief="flat")
style.map("Odol.Treeview", background=[("selected", C["blue_hover"])],
          foreground=[("selected", "#FFFFFF")])
style.map("Odol.Treeview.Heading", background=[("active", "#0A1228")])

# ========== หน้าเลือกห้อง ==========
lobby = tk.Frame(body, bg=C["bg"])

name_card = RoundedCard(lobby, 560, 100, fill=C["panel"])
name_card.pack(pady=(16, 4))
tk.Label(name_card.inner, text="👤 ชื่อ:", font=F_BOLD,
         bg=C["panel"], fg=C["text"]).pack(side="left", padx=(4, 10))
name_entry = tk.Entry(name_card.inner, font=F_NORMAL, width=26, bg=C["field"],
                      fg=C["text"], insertbackground=C["gold"], relief="flat", bd=10)
name_entry.pack(side="left")
_saved_name = load_saved_name()
if _saved_name:
    name_entry.insert(0, _saved_name)  # ✅ เติมชื่อที่เคยใช้ให้อัตโนมัติ


def _announce_identity(*_args):
    # พิมพ์ชื่อแล้วบอกเซิร์ฟเวอร์เลย — ระบบจะรู้ว่าต้องเตือนเช็คชื่อคนนี้ไหม
    try:
        who = name_entry.get().strip()
        if who and sio.connected:
            sio.emit("set_identity", {"name": who, "version": updater.APP_VERSION})
    except Exception:
        pass


name_entry.bind("<FocusOut>", _announce_identity)
name_entry.bind("<Return>", _announce_identity)

rooms_card = RoundedCard(lobby, 560, 280)
rooms_card.pack(pady=6)
tk.Label(rooms_card.inner, text="🏠 เลือกห้องที่จะเข้า", font=F_HEAD,
         bg=C["card"], fg=C["gold_light"]).pack(anchor="w", pady=(0, 6))
room_tree = ttk.Treeview(rooms_card.inner, columns=("name", "members"),
                         show="headings", height=5, style="Odol.Treeview")
room_tree.heading("name", text="🏷️ ชื่อห้อง")
room_tree.heading("members", text="👥 พนักงานในห้อง")
room_tree.column("name", width=320)
room_tree.column("members", width=170, anchor="center")
room_tree.pack(fill="both", expand=True)

join_btns = tk.Frame(lobby, bg=C["bg"])
join_btns.pack(pady=8)
GoldButton(join_btns, "✅ เข้าห้องที่เลือก", w=220, kind="gold",
           command=lambda: join_selected(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(join_btns, "🔄 รีเฟรช", w=130, kind="blue",
           command=lambda: refresh_now(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(join_btns, "📊 สถิติของฉัน", w=180, kind="dark",
           command=lambda: request_my_stats(), bg=C["bg"]).pack(side="left", padx=6)

net_row = tk.Frame(lobby, bg=C["bg"])
net_row.pack()
tk.Label(net_row, text="🌐 ไม่เจอเซิร์ฟ? ใส่ IP หรือลิงก์:", font=F_SMALL,
         bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 8))
ip_entry = tk.Entry(net_row, font=F_SMALL, width=22, bg=C["field"], fg=C["text"],
                    insertbackground=C["gold"], relief="flat", bd=6)
ip_entry.pack(side="left", padx=(0, 8))
ip_entry.bind("<KeyRelease>", lambda e: state.update(manual_ip=ip_entry.get().strip()))
GoldButton(net_row, "🔌 เชื่อมต่อ", w=120, h=34, kind="gold", font=F_SMALL,
           command=lambda: manual_connect(), bg=C["bg"]).pack(side="left")
ip_entry.bind("<Return>", lambda e: manual_connect())

# ========== หน้าในห้อง ==========
room_view = tk.Frame(body, bg=C["bg"])
room_name_label = tk.Label(room_view, text="", font=F_TITLE, bg=C["bg"], fg=C["gold"])
room_name_label.pack(pady=(14, 2))
me_label = tk.Label(room_view, text="", font=F_NORMAL, bg=C["bg"], fg=C["muted"])
me_label.pack()

member_card = RoundedCard(room_view, 560, 300)
member_card.pack(pady=8)
tk.Label(member_card.inner, text="👥 พนักงานในห้องนี้", font=F_HEAD,
         bg=C["card"], fg=C["gold_light"]).pack(anchor="w", pady=(0, 6))
member_tree = ttk.Treeview(member_card.inner, columns=("name", "status", "activity", "today"),
                           show="headings", height=5, style="Odol.Treeview")
member_tree.heading("name", text="👤 ชื่อ")
member_tree.heading("status", text="📊 สถานะ")
member_tree.heading("activity", text="🏃 ตอนนี้")
member_tree.heading("today", text="📊 ออกไปวันนี้")  # รวมเวลาออกไปข้างนอกทั้งวัน (ตัดรอบ 02:00)
member_tree.column("name", width=160)
member_tree.column("status", width=130, anchor="center")
member_tree.column("activity", width=130, anchor="center")
member_tree.column("today", width=100, anchor="center")
member_tree.pack(fill="both", expand=True)
member_tree.tag_configure("me", foreground=C["gold_light"])
member_tree.tag_configure("over", foreground=C["red"])  # ออกไปเกินเวลาที่กำหนด

room_btns = tk.Frame(room_view, bg=C["bg"])
room_btns.pack(pady=10)
GoldButton(room_btns, "🚪 ออกจากห้อง / ย้ายห้อง", w=250, kind="dark",
           command=lambda: leave_room(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(room_btns, "📊 สถิติของฉัน", w=180, kind="gold",
           command=lambda: request_my_stats(), bg=C["bg"]).pack(side="left", padx=6)
tk.Label(room_view, text="🔔 เมื่อแอดมินเรียกเช็คชื่อ จะมีเสียงและหน้าต่างเด้งขึ้นมา",
         font=F_SMALL, bg=C["bg"], fg=C["muted"]).pack()


def refit():
    # ปรับขนาดหน้าต่างให้พอดีกับหน้าที่กำลังแสดง (เนื้อหาแต่ละหน้าสูงไม่เท่ากัน)
    theme.fit_window(root, min_w=600, min_h=560, pad_h=8)


def show_lobby():
    room_view.pack_forget()
    lobby.pack(fill="both", expand=True)
    refit()


def show_room(room):
    lobby.pack_forget()
    room_view.pack(fill="both", expand=True)
    room_name_label.config(text=f"📌 ห้อง: {room}")
    me_label.config(text=f"👤 {state['name']}")
    refit()


# ========== 🔔 ป๊อปอัพเตือน "ถึงรอบเช็คชื่อในกลุ่ม" (คนละตัวกับการเรียกของแอดมิน) ==========
# กติกา: เด้งเฉพาะตอนระบบประกาศรอบแล้วแต่คนนี้ยังไม่เช็ค
#   - ยังไม่เช็ค : เสียงดัง 1 ครั้ง แล้วรูปค้างบนจอ ไม่หายเอง จนกว่าจะกดปิด
#   - เช็คชื่อสำเร็จ : ไม่ต้องทำอะไร (กว่าจะไปกดเช็คได้ เขาปิดป้ายไปก่อนแล้ว)
#   - กดปิดแล้ว : จบ ไม่เตือนซ้ำอีกในรอบนั้น ไม่ว่าจะเช็คแล้วหรือยัง
#   - ขึ้นรอบใหม่ : เริ่มเตือนใหม่ตามปกติ

# acked = เลขรอบที่กดปิดไปแล้ว (รอบใหม่ค่อยเตือนอีกครั้ง)
checkin_state = {"win": None, "img": None, "alert": None,
                 "acked": None, "cleared": None}


def close_checkin_popup(clear_alert=False, acked=False):
    """ปิดป๊อปอัพ — acked=True คือผู้ใช้กดรับทราบเอง (จะไม่เตือนซ้ำอีกในรอบนั้น)"""
    if acked:
        alert = checkin_state["alert"] or {}
        checkin_state["acked"] = alert.get("round") or 1
    stop_checkin_alert()
    win = checkin_state["win"]
    checkin_state["win"] = None
    if clear_alert:
        checkin_state["alert"] = None
        checkin_state["acked"] = None  # เช็คชื่อแล้ว รอบหน้าเตือนได้ตามปกติ
    if win is not None:
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass


def show_checkin_popup(alert):
    rnd = alert.get("round") or 1
    if checkin_state["acked"] == rnd:
        return  # กดปิดรอบนี้ไปแล้ว — ไม่กวนซ้ำ
    # เพิ่งเช็คชื่อรอบนี้ไปหมาดๆ — ข้อมูลฝั่งระบบอาจแกว่งอยู่ครู่หนึ่ง อย่าเพิ่งเด้งซ้ำ
    cleared = checkin_state.get("cleared") or {}
    if cleared.get("round") == rnd and time.time() - cleared.get("at", 0) < 300:
        return

    win = checkin_state["win"]
    if win is not None and win.winfo_exists():
        # ป้ายของรอบนี้อยู่บนจออยู่แล้ว — ปล่อยไว้เฉยๆ ไม่ต้องทำอะไรทั้งนั้น
        # (เขากดอิโมจิหรือเปลี่ยนสถานะระหว่างนั้น ก็ไม่ต้องไปยุ่งกับป้าย)
        if (checkin_state["alert"] or {}).get("round") == rnd:
            return
        close_checkin_popup()  # เป็นรอบใหม่ — เก็บป้ายเก่าทิ้งก่อนขึ้นป้ายใหม่

    checkin_state["alert"] = alert
    away = bool(alert.get("away"))

    win = tk.Toplevel(root)
    checkin_state["win"] = win
    win.title(f"🔔 ถึงเวลาเช็คชื่อรอบที่ {rnd}")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    win.overrideredirect(True)  # ไม่เอาแถบหัวหน้าต่าง — ให้เหลือแต่ป้ายแจ้งเตือนล้วนๆ
    win.attributes("-topmost", True)
    win.protocol("WM_DELETE_WINDOW", lambda: close_checkin_popup(acked=True))
    try:
        if _icon is not None:
            win.iconphoto(False, _icon)
    except Exception:
        pass

    img = None
    try:
        img = tk.PhotoImage(file=resource_path("alert_checkin.png"))
        if img.width() > root.winfo_screenwidth() - 120:
            img = img.subsample(2, 2)  # จอเล็กก็ยังเห็นทั้งรูป
    except Exception:
        img = None
    checkin_state["img"] = img  # ต้องอ้างอิงค้างไว้ ไม่งั้นรูปหาย

    if img is not None:
        tk.Label(win, image=img, bg=C["bg"], bd=0).pack(padx=10, pady=(10, 4))
    else:  # ไม่มีรูปก็ยังต้องเตือนได้
        tk.Label(win, text="🔔 มีการเช็คชื่อนะ", font=("Segoe UI", 22, "bold"),
                 bg=C["bg"], fg=C["gold"]).pack(padx=40, pady=(24, 8))

    info = tk.Label(win, text="", font=F_BOLD, bg=C["bg"], fg=C["gold_light"])
    info.pack(pady=(0, 4))
    win.info_label = info
    GoldButton(win, "✅ รับทราบ", w=240, kind="gold",
               command=lambda: close_checkin_popup(acked=True), bg=C["bg"]).pack(pady=(2, 14))

    # จัดกลางจอ — ต้องให้ Tk คำนวณขนาดจริงก่อน ไม่งั้นได้ขนาดหลอกแล้ววางเบี้ยว
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    base_x, base_y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
    win.geometry(f"{w}x{h}+{base_x}+{base_y}")

    # สั่นเรียกความสนใจ — จังหวะเดียวกับป๊อปอัพเรียกเช็คชื่อของแอดมิน
    def shake(n=0):
        if checkin_state["win"] is not win or not win.winfo_exists():
            return  # ปิดไปแล้วหรือถูกแทนที่ — หยุดสั่น
        dx = int(9 * math.sin(n * 0.9)) if n % 90 < 30 else 0  # สั่นเป็นชุด เว้นจังหวะ
        win.geometry(f"{w}x{h}+{base_x + dx}+{base_y}")
        win.lift()
        win.after(35, shake, n + 1)

    shake()

    note = "อย่าลืมไปเช็คชื่อในกลุ่มด้วยนะ"
    if away:
        note = f"ตอนนี้คุณ{alert.get('activity') or 'ไม่อยู่ที่นั่ง'} — กลับมาแล้วรีบไปเช็คชื่อนะ"
    try:
        win.info_label.config(text=f"📋 ถึงเวลาเช็คชื่อรอบที่ {rnd} — {note}")
    except Exception:
        pass

    play_checkin_alert()  # เสียงครั้งเดียวตอนป้ายขึ้น จากนั้นปล่อยรูปค้างไว้เฉยๆ


@sio.on("checkin_alert")
def on_checkin_alert(data):
    root.after(0, show_checkin_popup, data if isinstance(data, dict) else {})


@sio.on("do_update")
def on_do_update(data=None):
    # เซิร์ฟเวอร์สั่งให้อัพเดทเดี๋ยวนี้ — โหลดเวอร์ชันใหม่แล้วเปิดโปรแกรมใหม่ให้เอง
    root.after(0, updater.force_update, root, "golden-bell-employee.exe", set_status)


@sio.on("checkin_alert_clear")
def on_checkin_alert_clear(data=None):
    """เช็คชื่อเรียบร้อยแล้ว — ไม่ต้องทำอะไรกับหน้าจอ
    เพราะกว่าจะไปกดเช็คชื่อได้ เขาต้องปิดป้ายไปก่อนอยู่แล้ว
    แค่จำรอบไว้เฉยๆ กันข้อมูลที่แกว่งกลับมาทำให้เด้งซ้ำ"""
    rnd = (data or {}).get("round") if isinstance(data, dict) else None
    if rnd is None:
        rnd = (checkin_state.get("alert") or {}).get("round")
    if rnd:
        checkin_state["cleared"] = {"round": rnd, "at": time.time()}


# ========== ⏰ ป้ายเตือน "ใกล้หมดเวลาออกไปข้างนอก" ==========
# เซิร์ฟเวอร์เฝ้าเวลาให้จากระบบ check-status แล้วส่ง break_warning มาเมื่อเหลือไม่ถึง 1 นาที
# (ส่งซ้ำอีกครั้งตอนเกินเวลาจริง) — ป้ายขึ้นที่เครื่องของคนนั้นคนเดียว ไม่มีข้อความเข้ากลุ่ม Telegram
# ป้ายค้างบนจอจนกดรับทราบ หรือจนกดกลับที่นั่งในกลุ่ม (เซิร์ฟเวอร์ส่ง break_warning_clear มาเอง)
break_state = {"win": None, "img": None, "tick": None, "deadline": 0.0,
               "activity": "", "key": None, "acked": None}


def _fmt_mmss(sec):
    sec = int(abs(int(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def _fmt_span(sec):
    sec = int(sec or 0)
    if sec >= 3600:
        return f"{sec // 3600} ชม. {sec % 3600 // 60} นาที"
    if sec >= 60:
        return f"{sec // 60} นาที {sec % 60} วิ"
    return f"{sec} วิ"


def close_break_popup(acked=False):
    """เก็บป้าย — acked=True คือผู้ใช้กดรับทราบเอง (รอบนั้นจะไม่เด้งซ้ำจนกว่าจะเกินเวลาจริง)"""
    if acked:
        break_state["acked"] = break_state.get("key")
    stop_break_alert()  # เก็บป้ายแล้วต้องเงียบทันที ทั้งเสียงเตือนและเสียงพูดที่ตั้งคิวไว้
    if break_state.get("tick") is not None:
        try:
            root.after_cancel(break_state["tick"])
        except Exception:
            pass
        break_state["tick"] = None
    win = break_state["win"]
    break_state["win"] = None
    if win is not None:
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass


def _break_tick():
    """นับถอยหลังเองที่เครื่อง — ไม่ต้องรอเซิร์ฟเวอร์ส่งทุกวินาที ตัวเลขจึงเดินลื่นและตรง"""
    win = break_state["win"]
    if win is None or not win.winfo_exists():
        break_state["tick"] = None
        return
    left = break_state["deadline"] - time.time()
    act = break_state["activity"]
    if left >= 0:
        text = f"⏳ {act} — เหลืออีก {_fmt_mmss(left)} นาที รีบกดกลับที่นั่งด่วน"
        color = C["amber"]
    else:
        text = f"🔴 {act} — เกินเวลามาแล้ว {_fmt_mmss(left)} นาที กดกลับที่นั่งด่วน"
        color = C["red"]
    try:
        win.info_label.config(text=text, fg=color)
    except Exception:
        pass
    break_state["tick"] = root.after(1000, _break_tick)


def show_break_popup(alert):
    activity = str(alert.get("activity") or "ออกไปข้างนอก")
    key = f"{activity}|{alert.get('since') or ''}"
    over = bool(alert.get("over"))
    if break_state.get("acked") == key and not over:
        return  # กดรับทราบรอบนี้ไปแล้ว — จะกวนอีกทีก็ต่อเมื่อเกินเวลาจริงเท่านั้น
    try:
        remaining = int(alert.get("remaining") or 0)
    except (TypeError, ValueError):
        remaining = 0
    break_state.update({"deadline": time.time() + remaining, "activity": activity, "key": key})

    win = break_state["win"]
    if win is not None and win.winfo_exists():
        _break_tick()          # ป้ายอยู่บนจอแล้ว — อัพเดทข้อความพอ ไม่ต้องสร้างใหม่
        if over:
            play_break_alert(activity)  # เพิ่งเปลี่ยนเป็น "เกินเวลา" — ส่งเสียงย้ำอีกครั้งหนึ่ง
        return

    win = tk.Toplevel(root)
    break_state["win"] = win
    win.title("⏰ ใกล้หมดเวลา")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    win.overrideredirect(True)  # ป้ายล้วนๆ ไม่มีแถบหัวหน้าต่าง — แบบเดียวกับป้ายเตือนเช็คชื่อ
    win.attributes("-topmost", True)
    win.protocol("WM_DELETE_WINDOW", lambda: close_break_popup(acked=True))
    try:
        if _icon is not None:
            win.iconphoto(False, _icon)
    except Exception:
        pass

    # ปุ่มปิดมุมขวาบน — กดปิดได้เลยเหมือนกดรับทราบ (ป้ายไม่มีแถบหัวหน้าต่างจึงไม่มีปุ่ม X ของ Windows)
    top_bar = tk.Frame(win, bg=C["bg"])
    top_bar.pack(fill="x")
    tk.Button(top_bar, text="✕", font=("Segoe UI", 12, "bold"), bg=C["bg"], fg=C["muted"],
              activebackground=C["bg"], activeforeground=C["red"], relief="flat", bd=0,
              cursor="hand2", command=lambda: close_break_popup(acked=True)
              ).pack(side="right", padx=(0, 10), pady=(6, 0))

    img = None
    try:
        img = tk.PhotoImage(file=resource_path("alert_break.png"))
        if img.width() > root.winfo_screenwidth() - 120:
            img = img.subsample(2, 2)  # จอเล็กก็ยังเห็นทั้งรูป
    except Exception:
        img = None
    break_state["img"] = img  # ต้องอ้างอิงค้างไว้ ไม่งั้นรูปหาย

    if img is not None:
        tk.Label(win, image=img, bg=C["bg"], bd=0).pack(padx=10, pady=(10, 4))
    else:  # ไม่มีรูปก็ยังต้องเตือนได้
        tk.Label(win, text="⏰ ใกล้หมดเวลาแล้ว!", font=("Segoe UI", 22, "bold"),
                 bg=C["bg"], fg=C["red"]).pack(padx=40, pady=(24, 8))

    info = tk.Label(win, text="", font=("Segoe UI", 14, "bold"), bg=C["bg"], fg=C["amber"])
    info.pack(pady=(0, 4))
    win.info_label = info
    GoldButton(win, "✅ รับทราบ", w=240, kind="red",
               command=lambda: close_break_popup(acked=True), bg=C["bg"]).pack(pady=(2, 14))

    # จัดกลางจอ — ต้องให้ Tk คำนวณขนาดจริงก่อน ไม่งั้นได้ขนาดหลอกแล้ววางเบี้ยว
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    base_x, base_y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
    win.geometry(f"{w}x{h}+{base_x}+{base_y}")

    def shake(n=0):
        if break_state["win"] is not win or not win.winfo_exists():
            return  # ปิดไปแล้วหรือถูกแทนที่ — หยุดสั่น
        dx = int(9 * math.sin(n * 0.9)) if n % 90 < 30 else 0  # สั่นเป็นชุด เว้นจังหวะ
        win.geometry(f"{w}x{h}+{base_x + dx}+{base_y}")
        win.lift()
        win.after(35, shake, n + 1)

    shake()
    _break_tick()
    play_break_alert(activity)  # เสียงเช็คชื่อ แล้วตามด้วยเสียงพูดว่ากิจกรรมนี้ใกล้หมดเวลา ให้รีบกดกลับ


@sio.on("break_warning")
def on_break_warning(data):
    root.after(0, show_break_popup, data if isinstance(data, dict) else {})


@sio.on("break_warning_clear")
def on_break_warning_clear(data=None):
    # กลับที่นั่งแล้ว (หรือเปลี่ยนกิจกรรม) — เก็บป้ายให้เอง และพร้อมเตือนรอบใหม่ได้อีก
    def _apply():
        break_state["acked"] = None
        close_break_popup()
    root.after(0, _apply)


# ========== 📊 สถิติของฉันวันนี้ (ตัดรอบ 02:00 น.) ==========
stats_state = {"win": None}


def request_my_stats():
    """ขอสถิติของตัวเองจากเซิร์ฟเวอร์ — เห็นเฉพาะของตัวเอง ไม่เห็นของคนอื่น"""
    if not state["connected"]:
        messagebox.showwarning("⚠️ ยังไม่เชื่อมต่อ",
                               "ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — รอสักครู่แล้วลองใหม่")
        return
    who = name_entry.get().strip() or state.get("name") or ""
    if not who:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาใส่ชื่อก่อน แล้วค่อยกดดูสถิติ")
        return
    set_status("📊 กำลังโหลดสถิติของคุณ...", C["muted"])
    try:
        sio.emit("get_my_stats", {"name": who})
    except Exception:
        set_status("⚠️ ส่งคำขอไม่สำเร็จ — ลองใหม่อีกครั้ง", C["amber"])


def show_my_stats(data):
    if not data.get("ok"):
        set_status("")
        messagebox.showwarning("📊 สถิติของฉัน", data.get("msg") or "ยังดูสถิติไม่ได้ตอนนี้")
        return

    row = data.get("row") or {}
    acts = data.get("activities") or []
    limits = data.get("limits") or {}
    reset_hour = data.get("reset_hour")
    reset_txt = f"{int(reset_hour):02d}:00 น." if isinstance(reset_hour, (int, float)) else "02:00 น."

    old = stats_state.get("win")
    if old is not None:
        try:
            if old.winfo_exists():
                old.destroy()
        except Exception:
            pass

    win = tk.Toplevel(root)
    stats_state["win"] = win
    win.title("📊 สถิติของฉันวันนี้")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    try:
        if _icon is not None:
            win.iconphoto(False, _icon)
    except Exception:
        pass

    tk.Label(win, text=f"📊 {data.get('username') or ''}", font=F_TITLE,
             bg=C["bg"], fg=C["gold"]).pack(pady=(14, 0))
    tk.Label(win, text=f"วันทำงาน {data.get('day') or ''} · เริ่มนับรอบใหม่ทุกวันเวลา {reset_txt}",
             font=F_SMALL, bg=C["bg"], fg=C["muted"]).pack(pady=(2, 10))

    table = ttk.Treeview(win, columns=("act", "count", "total", "over"), show="headings",
                         height=max(3, len(acts) + 1), style="Odol.Treeview")
    table.heading("act", text="🚪 ออกไปทำอะไร")
    table.heading("count", text="จำนวนครั้ง")
    table.heading("total", text="⏱️ ใช้เวลารวม")
    table.heading("over", text="⚠️ เกินเวลา")
    table.column("act", width=210)
    table.column("count", width=100, anchor="center")
    table.column("total", width=150, anchor="center")
    table.column("over", width=150, anchor="center")
    table.tag_configure("over", foreground=C["red"])
    table.tag_configure("total", foreground=C["gold_light"])
    table.pack(padx=18, fill="x")

    for act in acts:
        st = (row.get("activities") or {}).get(act) or {}
        limit = limits.get(act)
        name = f"{act} (ครั้งละ {int(limit) // 60} นาที)" if limit else act
        over_txt = "—"
        if st.get("over_count"):
            over_txt = f"{st['over_count']} ครั้ง · {_fmt_span(st.get('over_seconds'))}"
        table.insert("", "end", tags=("over",) if st.get("over_count") else (),
                     values=(name, f"{int(st.get('count') or 0)} ครั้ง",
                             _fmt_span(st.get("seconds")), over_txt))

    over_all = "—"
    if row.get("over_count"):
        over_all = f"{row['over_count']} ครั้ง · {_fmt_span(row.get('over_seconds'))}"
    table.insert("", "end", tags=("total",),
                 values=("รวมทั้งหมด", f"{int(row.get('total_count') or 0)} ครั้ง",
                         _fmt_span(row.get("total_seconds")), over_all))

    cur = row.get("current") or None
    if cur:
        limit = cur.get("limit")
        left = (int(limit) - int(cur.get("seconds") or 0)) if limit else None
        if left is None:
            note = f"🚪 ตอนนี้ออกไป{cur.get('activity')} มาแล้ว {_fmt_span(cur.get('seconds'))}"
            color = C["amber"]
        elif left >= 0:
            note = (f"🚪 ตอนนี้ออกไป{cur.get('activity')} มาแล้ว {_fmt_span(cur.get('seconds'))}"
                    f" — เหลืออีก {_fmt_mmss(left)} นาที")
            color = C["amber"]
        else:
            note = (f"🔴 ตอนนี้ออกไป{cur.get('activity')} มาแล้ว {_fmt_span(cur.get('seconds'))}"
                    f" — เกินเวลามาแล้ว {_fmt_mmss(left)} นาที")
            color = C["red"]
        tk.Label(win, text=note, font=F_BOLD, bg=C["bg"], fg=color).pack(pady=(10, 0))
    else:
        tk.Label(win, text="✅ ตอนนี้อยู่ที่นั่ง", font=F_BOLD,
                 bg=C["bg"], fg=C["green"]).pack(pady=(10, 0))

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(pady=12)
    GoldButton(btns, "🔄 โหลดใหม่", w=150, kind="blue",
               command=lambda: request_my_stats(), bg=C["bg"]).pack(side="left", padx=8)
    GoldButton(btns, "ปิด", w=110, kind="dark",
               command=win.destroy, bg=C["bg"]).pack(side="left", padx=8)

    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 30)}")
    set_status("")


@sio.on("my_stats")
def on_my_stats(data):
    root.after(0, show_my_stats, data if isinstance(data, dict) else {})


# ========== popup เช็คชื่อ — สั่นเรียกความสนใจ + มีเสียง ==========
def close_popup():
    stop_alert()  # ✅ หยุดเสียงแจ้งทันทีเมื่อปิด popup
    popup = state["popup"]
    state["popup"] = None
    if popup is not None:
        try:
            if popup.winfo_exists():
                popup.destroy()
        except Exception:
            pass


def open_check_popup():
    if state["popup"] is not None and state["popup"].winfo_exists():
        popup = state["popup"]
        popup.deiconify()
        popup.lift()
        play_alert()
        return
    popup = tk.Toplevel(root)
    state["popup"] = popup
    popup.title("🔔 เรียกเช็คชื่อ")
    popup.configure(bg=C["bg"], highlightbackground=C["gold"], highlightthickness=3)
    popup.attributes("-topmost", True)
    popup.resizable(False, False)
    # ✅ ปิดด้วยปุ่ม X ไม่ได้ — ต้องกดยืนยันเท่านั้น กันเผลอปิดแล้วไม่ได้เช็คชื่อ
    popup.protocol("WM_DELETE_WINDOW", lambda: None)
    w, h = 460, 320
    sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()
    base_x, base_y = (sw - w) // 2, (sh - h) // 2
    popup.geometry(f"{w}x{h}+{base_x}+{base_y}")

    tk.Label(popup, text="🔔", font=("Segoe UI Emoji", 44), bg=C["bg"],
             fg=C["gold"]).pack(pady=(24, 0))
    tk.Label(popup, text="ถึงเวลาเช็คชื่อแล้ว!", font=("Segoe UI", 20, "bold"),
             bg=C["bg"], fg=C["gold_light"]).pack(pady=(4, 2))
    tk.Label(popup, text=f"คุณ {state['name']} กรุณายืนยันการเข้างาน",
             font=F_NORMAL, bg=C["bg"], fg=C["text"]).pack()

    def confirm():
        # ✅ บั๊ก #1 แก้: เพิ่ม re-entrancy guard — กันกดสองครั้งส่ง confirm สองครั้ง
        if state.get("confirm_waiting"):
            return  # ถ้ากำลังรอ ack อยู่แล้ว ไม่ทำอะไร
        # ✅ ปิด popup เฉพาะเมื่อเซิร์ฟเวอร์ตอบรับ (ack) จริง — กันแจ้ง "สำเร็จ" ทั้งที่ส่งไม่ถึง
        def on_ack(*args):
            def _apply():
                state["confirm_waiting"] = False
                res = args[0] if args and isinstance(args[0], dict) else {}
                close_popup()
                if res.get("ok"):
                    set_status("✅ เช็คชื่อเรียบร้อยแล้ว", C["green"])
                else:
                    messagebox.showwarning("⚠️ แจ้งเตือน",
                                           res.get("msg") or "ยืนยันไม่สำเร็จ กรุณารอแอดมินเรียกใหม่")
            root.after(0, _apply)

        def on_timeout():
            if state.get("confirm_waiting"):
                state["confirm_waiting"] = False
                set_status("⚠️ ส่งไม่ถึงเซิร์ฟเวอร์ กรุณากดยืนยันอีกครั้ง", C["amber"])

        try:
            state["confirm_waiting"] = True
            sio.emit("confirm_checkin", callback=on_ack)
            popup.after(8000, on_timeout)
        except Exception:
            state["confirm_waiting"] = False
            messagebox.showwarning("⚠️ ส่งไม่สำเร็จ",
                                   "การเชื่อมต่อขัดข้อง กรุณากดยืนยันอีกครั้งในอีกสักครู่")

    GoldButton(popup, "✅ ยืนยันเข้างาน", w=260, h=56, kind="green",
               font=("Segoe UI", 15, "bold"), command=confirm, bg=C["bg"]).pack(pady=22)

    # 🫨 สั่นซ้าย-ขวาต่อเนื่องจนกว่าจะกดยืนยัน — กันมองไม่เห็น
    def shake(n=0):
        if not popup.winfo_exists():
            return
        dx = int(9 * math.sin(n * 0.9)) if n % 90 < 30 else 0  # สั่นเป็นชุด เว้นจังหวะ
        popup.geometry(f"{w}x{h}+{base_x + dx}+{base_y}")
        popup.lift()
        popup.after(35, shake, n + 1)

    # 🔊 เสียงเล่นวนซ้ำจนกว่าจะกดยืนยัน (popup ถูกปิด) — กันไม่ได้ยินรอบเดียว
    # ✅ เลือกเสียงสุ่มครั้งแรก แล้วเล่นเสียงเดิมซ้ำทุก 3-5 วินาที ไม่ใช่สุ่มครั้งละ
    selected_sound = None

    def play_selected_sound():
        nonlocal selected_sound
        try:
            if _sound_ready and _alert_sounds:
                if selected_sound is None:
                    import random
                    selected_sound = random.choice(_alert_sounds)  # เลือกครั้งแรก
                # เล่นเสียงเดิมซ้ำทุกครั้ง
                ctypes.windll.winmm.mciSendStringW(f"play {selected_sound} from 0", None, 0, None)
            else:
                ctypes.windll.user32.MessageBeep(0x30)
        except:
            pass

    def alert_loop():
        if state["popup"] is None or not popup.winfo_exists():
            return
        play_selected_sound()
        popup.after(3500, alert_loop)

    alert_loop()
    shake()


def set_status(txt, color=None):
    status_label.config(text=txt, fg=color or C["muted"])


# ========== การกระทำ ==========
def join_selected():
    if not state["connected"]:
        messagebox.showwarning("⚠️ ยังไม่เชื่อมต่อ", "ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้\nตรวจสอบว่าเปิดเซิร์ฟเวอร์แล้ว และอยู่เครือข่ายเดียวกัน")
        return
    name = name_entry.get().strip()
    if not name:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาใส่ชื่อก่อน")
        return
    sel = room_tree.selection()
    if not sel:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาเลือกห้องจากตารางก่อน")
        return
    state["name"] = name
    sio.emit("join_room_member", {"room": room_tree.item(sel[0], "values")[0], "name": name})


def leave_room():
    if state["connected"]:
        sio.emit("leave_room")


def force_rescan():
    def _work():
        try:
            if sio.connected:
                try:
                    sio.disconnect()
                except Exception:
                    pass
            else:
                try:
                    sio.shutdown()
                except Exception:
                    pass
            connect_worker()
        except Exception:
            pass
    threading.Thread(target=_work, daemon=True).start()


def refresh_now():
    if sio.connected:
        try:
            sio.emit("list_rooms")
        except Exception:
            pass
        set_status("🔄 รีเฟรชรายการห้องแล้ว", C["green"])
    else:
        set_status("🔄 กำลังค้นหาเซิร์ฟเวอร์อีกครั้ง...", C["amber"])
        force_rescan()


def manual_connect():
    addr = ip_entry.get().strip()
    if not addr:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาใส่ IP หรือลิงก์เซิร์ฟเวอร์ก่อน")
        return
    state["manual_ip"] = addr
    set_status(f"🔌 กำลังเชื่อมต่อไปที่ {addr} ...", C["amber"])
    force_rescan()


# ========== แสดงผล (main thread เท่านั้น) ==========
def render_rooms(rooms):
    selected = room_tree.selection()
    keep = room_tree.item(selected[0], "values")[0] if selected else None
    room_tree.delete(*room_tree.get_children())
    for r in rooms:
        iid = room_tree.insert("", "end", values=(r["name"], f"{r['members']} คน"))
        if r["name"] == keep:
            room_tree.selection_set(iid)


# ข้อมูลจากระบบ check-status ที่เซิร์ฟเวอร์ส่งมาให้ทั้งห้อง (ใครออกไปทำอะไร ใช้เวลาไปเท่าไหร่แล้ววันนี้)
status_info = {"people": {}}
ACTIVITY_SHORT = {"กลับที่นั่ง": "✅ อยู่ที่นั่ง", "ปวดหนัก": "🚻 ปวดหนัก",
                  "ปวดน้อย": "🚻 ปวดน้อย", "กินข้าว": "🍚 กินข้าว"}


def _member_extra(name):
    """คืน (ตอนนี้ทำอะไร, ออกไปวันนี้รวมเท่าไหร่, เกินเวลาไหม) ของคนหนึ่งในห้อง"""
    info = status_info["people"].get(name) or {}
    if info.get("match") != "ok":
        return "—", "—", False
    act = info.get("activity") or ""
    label = ACTIVITY_SHORT.get(act, act or "—")
    if act and act != "กลับที่นั่ง":
        label += f" · {_fmt_span(info.get('duration'))}"
    total = int(info.get("total_today") or 0)
    return label, (_fmt_span(total) if total else "—"), bool(info.get("over"))


def render_members(data):
    if data["room"] != state["room"]:
        return
    state["members_cache"] = data  # เก็บไว้วาดใหม่ตอนข้อมูลสถานะอัปเดต
    member_tree.delete(*member_tree.get_children())
    for m in data["members"]:
        act_txt, today_txt, over = _member_extra(m["name"])
        tags = ("over",) if over else (("me",) if m["name"] == state["name"] else ())
        member_tree.insert("", "end", tags=tags,
                           values=(m["name"], STATUS_TH.get(m["status"], m["status"]),
                                   act_txt, today_txt))


@sio.on("members_status")
def on_members_status(data):
    """เซิร์ฟเวอร์ส่งสถานะจากระบบ check-status มาให้ทั้งห้อง — เอามาเติมสองคอลัมน์ขวา"""
    def _apply():
        if not isinstance(data, dict) or data.get("room") != state["room"]:
            return
        status_info["people"] = data.get("people") or {}
        cached = state.get("members_cache")
        if cached:
            render_members(cached)
    root.after(0, _apply)


# ========== เหตุการณ์จากเซิร์ฟเวอร์ ==========
@sio.on("rooms_updated")
def on_rooms(data):
    root.after(0, render_rooms, data)


@sio.on("room_state")
def on_room_state(data):
    root.after(0, render_members, data)


@sio.on("joined_room")
def on_joined(data):
    def _apply():
        close_popup()  # popup ค้างจากห้องเก่า/รอบเก่า ใช้ไม่ได้แล้ว
        state["room"] = data["room"]
        show_room(data["room"])
        set_status(f"✅ เข้าห้อง {data['room']} แล้ว — รอแอดมินเรียกเช็คชื่อ")
        save_name(state["name"])  # ✅ จำชื่อไว้สำหรับครั้งต่อไป
    root.after(0, _apply)


@sio.on("left_room")
def on_left(_):
    def _apply():
        close_popup()
        state["room"] = None
        show_lobby()
        set_status("ออกจากห้องแล้ว — เลือกห้องใหม่ได้เลย")
    root.after(0, _apply)


@sio.on("check_request")
def on_check_request(_):
    root.after(0, open_check_popup)


@sio.on("config_data")
def on_config_data(data):
    # ✅ ได้ config จากเซิร์ฟเวอร์ (IP ที่แอดมินตั้ง) → บันทึกไว้
    state["server_config"] = data  # {"server_ip": "...", "server_port": ...}


@sio.on("config_updated")
def on_config_updated(data):
    # ✅ เซิร์ฟเวอร์แจ้งว่า config เปลี่ยน (แอดมินอัปเดต IP)
    state["server_config"] = data


@sio.on("error_msg")
def on_error(data):
    root.after(0, lambda: messagebox.showwarning("⚠️ แจ้งเตือน", data.get("msg", "เกิดข้อผิดพลาด")))


@sio.event
def disconnect():
    def _apply():
        state["connected"] = False
        conn_label.config(text="⚠️ หลุดการเชื่อมต่อ กำลังต่อใหม่...")
    root.after(0, _apply)
    # ✅ ถ้าไลบรารีต่อ URL เดิมไม่ติดใน 12 วิ → สแกนหาทุกช่องทางใหม่ (LAN/ลิงก์/ช่องกรอก)
    if not state.get("watchdog"):
        state["watchdog"] = True
        threading.Thread(target=reconnect_watchdog, daemon=True).start()


@sio.event
def connect_error(data):
    # เซิร์ฟเวอร์ปฏิเสธพร้อมเหตุผล (เช่น รหัสเข้าระบบไม่ตรง) — ต้องบอกความจริง ไม่ใช่ "หาไม่เจอ"
    msg = data.get("message") if isinstance(data, dict) else (data if isinstance(data, str) else "")
    if msg:
        root.after(0, conn_label.config, {"text": f"⛔ เซิร์ฟเวอร์ปฏิเสธ: {msg}"})


@sio.event
def connect():
    def _apply():
        state["connected"] = True
        conn_label.config(text="✅ เชื่อมต่อเซิร์ฟเวอร์แล้ว")
    root.after(0, _apply)
    # 🔔 บอกชื่อให้เซิร์ฟเวอร์รู้ทันที — จะได้เตือนเช็คชื่อแม้ยังไม่ได้เข้าห้อง
    try:
        who = (state["name"] or name_entry.get() or "").strip()
        if who:
            sio.emit("set_identity", {"name": who, "version": updater.APP_VERSION})
    except Exception:
        pass
    # ✅ เน็ตสะดุดแล้วต่อกลับมา — เข้าห้องเดิมคืนอัตโนมัติ (เซิร์ฟเวอร์ล้างสถานะตอนหลุด)
    if state["room"] and state["name"]:
        try:
            sio.emit("join_room_member", {"room": state["room"], "name": state["name"]})
        except Exception:
            pass


# ========== เชื่อมต่อ — ทำงานเบื้องหลัง ลองใหม่เรื่อย ๆ จนกว่าจะเจอ ==========
def candidate_urls():
    urls = []
    # 🧪 ทดสอบกับเซิร์ฟเวอร์ตัวอื่น: ตั้ง env ODOL_URL แล้วเปิดโปรแกรม (ใช้ชื่อเดียวกับใน tests/)
    #    ปกติไม่มีใครตั้ง ค่านี้จึงไม่กระทบการใช้งานจริงเลย
    test_url = os.environ.get("ODOL_URL", "").strip()
    if test_url:
        urls.append(normalize_target(test_url))
    # ✅ โดเมนคลาวด์ Railway ขึ้นมาเป็นอันดับแรก (remote-first สำหรับต่างจังหวัด)
    #    เซิร์ฟเวอร์ส่ง server_domain มาใน config (key ngrok_domain เดิมก็ชี้ที่เดียวกัน)
    cfg = state.get("server_config", {})
    server_domain = cfg.get("server_domain") or cfg.get("ngrok_domain") or SERVER_DOMAIN
    if server_domain:
        urls.append(f"https://{server_domain}")
    if state["manual_ip"]:
        urls.append(normalize_target(state["manual_ip"]))
    if PINNED:
        urls.append(normalize_target(PINNED))  # ที่อยู่ปักไว้ในไฟล์ตั้งค่า
    for ip in discover_servers():
        urls.append(f"http://{ip}:{PORT}")
    urls.append(f"http://127.0.0.1:{PORT}")
    for ip in server_candidates():
        urls.append(f"http://{ip}:{PORT}")
    return [u for u in dict.fromkeys(urls) if u]


def connect_worker():
    if state.get("worker_running"):
        return  # มีตัวสแกนทำงานอยู่แล้ว
    state["worker_running"] = True
    try:
        while not sio.connected:
            for url in candidate_urls():
                if sio.connected:
                    return
                try:
                    root.after(0, conn_label.config, {"text": f"🔍 กำลังลอง {url} ..."})
                    sio.connect(url, auth={"code": ACCESS_CODE}, wait_timeout=10)
                    # ✅ เชื่อมต่อสำเร็จแล้ว → ถาม server ว่า IP config ที่แอดมินตั้ง
                    sio.emit("get_config")
                    return
                except Exception:
                    continue
            root.after(0, conn_label.config,
                       {"text": "❌ ยังไม่พบเซิร์ฟเวอร์ — ตรวจสอบอินเทอร์เน็ต หรือใส่ IP/ลิงก์ด้านล่าง (กำลังลองใหม่...)"})
            time.sleep(3)
    except Exception:
        pass  # หน้าต่างถูกปิดระหว่างรอ — จบ thread เงียบ ๆ
    finally:
        state["worker_running"] = False


def reconnect_watchdog():
    # เปิดโอกาสให้ไลบรารีต่อ URL เดิมก่อน — ถ้าไม่สำเร็จ หยุดมันแล้วกลับไปสแกนทุกช่องทาง
    try:
        time.sleep(12)
        if not sio.connected:
            try:
                sio.shutdown()
            except Exception:
                pass
            connect_worker()
    except Exception:
        pass
    finally:
        state["watchdog"] = False


init_sound()
apply_volume(_volume)  # ใช้ระดับเสียงที่ผู้ใช้ตั้งไว้ครั้งก่อน
show_lobby()
threading.Thread(target=connect_worker, daemon=True).start()
root.after(60, refit)  # จัดขนาดหน้าต่างให้พอดีเนื้อหาหลัง widget วางตัวเสร็จ
# 🔄 อัพเดทอัตโนมัติ — เช็คเงียบๆ ตอนเปิด ถ้ามีเวอร์ชันใหม่ก็โหลดและเปิดใหม่ให้เอง
updater.auto_update(root, "golden-bell-employee.exe", set_status)
# เครื่องที่เปิดค้างทั้งวัน — คอยดูเป็นระยะ เจอแล้วบอกให้รู้ (ไม่รีสตาร์ทกลางคัน)
# อัพเดทเองระหว่างเปิดค้างได้ ถ้าไม่มีป๊อปอัพค้างอยู่ (ไม่รีสตาร์ทกลางการเช็คชื่อ)
updater.watch_for_updates(root, "golden-bell-employee.exe", set_status,
                          can_update=lambda: state.get("popup") is None
                          and checkin_state["win"] is None)
root.mainloop()

try:
    sio.disconnect()
except:
    pass
