# -*- coding: utf-8 -*-
# 🔔 กระดิ่งทอง มรณะ — โปรแกรมแอดมิน
import csv
import math
import ctypes
import os
import socket
import sys
import threading
import time
import tkinter as tk
import zipfile
from tkinter import ttk, messagebox, filedialog

import socketio

import theme    # 🎨 ระบบธีม มืด/สว่าง
import updater  # 🔄 ระบบอัพเดทโปรแกรมจาก GitHub Releases

updater.cleanup_old()  # ลบไฟล์ .old ที่ค้างจากการอัพเดทรอบก่อน

APP_NAME = "กระดิ่งทอง มรณะ"


# ========== หาไฟล์ที่ bundle มากับ .exe ==========
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


# ========== อ่านที่อยู่เซิร์ฟเวอร์จากไฟล์ ถ้ามี ==========
def get_server_address():
    addr_file = os.path.join(app_dir(), "server_address.txt")
    if os.path.exists(addr_file):
        try:
            with open(addr_file, "r", encoding="utf-8") as f:
                addr = f.read().strip()
                if ":" in addr:
                    ip, port = addr.split(":")
                    return ip, int(port)
        except:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip, 5000
    except:
        return "127.0.0.1", 5000


MY_IP, PORT = get_server_address()
SERVER_URLS_TO_TRY = [
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
    f"http://{MY_IP}:{PORT}",
]

SERVER_DOMAIN = "goldenbell.jed89.com"  # ☁️ โดเมนถาวร (custom domain บน Railway)
ACCESS_CODE = "ODOL-2569"  # รหัสเข้าระบบ — ต้องตรงกับเซิร์ฟเวอร์


def pinned_address():
    # ✅ ถ้ามีไฟล์ "เซิร์ฟเวอร์.txt" วางข้าง .exe (มาในชุด .zip) → ใช้ที่อยู่นั้นก่อนเสมอ
    #    ทำให้ต่อเซิร์ฟเวอร์ติดทันที ไม่ต้องเดา แก้ปัญหา "ไม่เจอเซิร์ฟ"
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

# ========== เสียงแจ้งเตือน (MCI ของ Windows — เล่น mp3 ได้โดยไม่ต้องลงอะไรเพิ่ม) ==========
_sound_ready = False


def init_sound():
    global _sound_ready
    try:
        path = resource_path("alert_thai.mp3")
        if os.path.exists(path):
            ret = ctypes.windll.winmm.mciSendStringW(
                f'open "{path}" type mpegvideo alias odol_alert', None, 0, None
            )
            _sound_ready = ret == 0  # MCI แจ้งพลาดผ่านค่าที่คืน ไม่ใช่ exception
    except:
        pass


def play_alert():
    try:
        if _sound_ready:
            ctypes.windll.winmm.mciSendStringW("play odol_alert from 0", None, 0, None)
        else:
            ctypes.windll.user32.MessageBeep(0x30)  # เสียงระบบสำรอง — ต้องมีเสียงทุกครั้ง
    except:
        pass


# ========== ธีมสี — มืด น้ำเงิน ขอบทอง หรูหรา ==========
theme.init(theme.load_saved())  # โหลดธีมที่ผู้ใช้เลือกไว้ก่อนสร้างหน้าต่าง
C = theme.C  # ชุดสีปัจจุบัน — เปลี่ยนค่าในตัวเองเมื่อสลับธีม

F_TITLE = ("Segoe UI", 20, "bold")
F_HEAD = ("Segoe UI", 15, "bold")
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
                           width=w - 44, height=h - 44)


STATUS_TH = {
    "wait": ("⏳ ยังไม่เช็คชื่อ", "muted"),
    "pending": ("🔔 รอยืนยัน...", "amber"),
    "checked": ("✅ เข้างานแล้ว", "green"),
}

# ========== หน้าต่างหลัก ==========
root = tk.Tk()
root.title(f"🔔 {APP_NAME} — แอดมิน")
root.resizable(True, True)  # ขนาดจริงคำนวณจากเนื้อหาใน refit()
root.configure(bg=C["bg"])

try:
    _icon = tk.PhotoImage(file=resource_path("logo_small.png"))
    root.iconphoto(True, _icon)
except:
    _icon = None

sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=1)
state = {"connected": False, "room": None, "rooms": [], "members": [],
         "manual_ip": "", "last_url": "", "worker_running": False, "watchdog": False,
         "admin_name": ""}  # ✅ เพิ่มชื่อแอดมิน

# ---------- ส่วนหัว ----------
header = tk.Frame(root, bg=C["panel"], height=86)
header.pack(fill="x")
header.pack_propagate(False)

if _icon is not None:
    # โลโก้กระดิ่งทองเส้นสีอ่อน — วางบนป้ายพื้นเข้มขอบทองให้เด่น
    logo_chip = tk.Canvas(header, width=66, height=62, bg=C["panel"],
                          highlightthickness=0, bd=0)
    logo_chip.pack(side="left", padx=(18, 10), pady=12)
    logo_chip.create_polygon(round_points(2, 2, 64, 60, 16), smooth=True,
                             fill="#0A1228", outline=C["gold"], width=2)
    logo_chip.create_image(33, 31, image=_icon)

_title_box = tk.Frame(header, bg=C["panel"])
_title_box.pack(side="left", padx=6)
tk.Label(_title_box, text=APP_NAME, font=F_TITLE, bg=C["panel"],
         fg=C["gold"]).pack(anchor="w", pady=(14, 0))
addr_label = tk.Label(_title_box, text="📍 กำลังค้นหาเซิร์ฟเวอร์อัตโนมัติ...",
                      font=F_SMALL, bg=C["panel"], fg=C["muted"])
addr_label.pack(anchor="w")

# ✅ เพิ่ม UI ชื่อแอดมิน ด้านขวา header เท่านั้น (IP ไปด้านล่าง)
admin_box = tk.Frame(header, bg=C["panel"])
admin_box.pack(side="right", padx=18, pady=12)

tk.Label(admin_box, text="🛡️ ชื่อแอดมิน", font=F_BOLD, bg=C["panel"],
         fg=C["gold"]).pack(anchor="e", pady=(0, 3))
# ✅ ใส่กรอบทองรอบช่อง — ของเดิมสีกลืนกับพื้นหลังจนไม่รู้ว่าเป็นช่องให้กรอก
admin_entry_frame = tk.Frame(admin_box, bg=C["gold"], padx=2, pady=2)
admin_entry_frame.pack(anchor="e")
admin_name_entry = tk.Entry(admin_entry_frame, font=F_BOLD, bg=C["field"],
                            fg=C["text"], insertbackground=C["gold"],
                            width=20, bd=0, relief="flat", justify="center")
admin_name_entry.pack(ipady=5, ipadx=4)

# ✅ ไม่ใส่ค่าเริ่มต้น — บังคับให้แอดมินพิมพ์ชื่อตัวเองก่อนเรียกเช็คชื่อ ประวัติจะได้บอกว่าใครกด
#    แต่ใส่ข้อความจางๆ บอกว่าต้องพิมพ์อะไร แล้วหายเองตอนคลิก
ADMIN_HINT = "พิมพ์ชื่อของคุณ"


def _hint_on():
    if not admin_name_entry.get():
        admin_name_entry.insert(0, ADMIN_HINT)
        admin_name_entry.config(fg=C["muted"])


def _hint_off(*_a):
    if admin_name_entry.get() == ADMIN_HINT:
        admin_name_entry.delete(0, "end")
    admin_name_entry.config(fg=C["text"])


def update_admin_name(*args):
    value = admin_name_entry.get().strip()
    state["admin_name"] = "" if value == ADMIN_HINT else value


admin_name_entry.bind("<FocusIn>", _hint_off)
admin_name_entry.bind("<FocusOut>", lambda e: (update_admin_name(), _hint_on()))
admin_name_entry.bind("<KeyRelease>", update_admin_name)
_hint_on()
update_admin_name()  # ตั้งค่าเบื้องต้น

tk.Frame(root, bg=C["gold"], height=2).pack(fill="x")

body = tk.Frame(root, bg=C["bg"])
body.pack(fill="both", expand=True)

status_label = tk.Label(root, text="", font=F_SMALL, bg=C["bg"], fg=C["muted"])
status_label.pack(side="bottom", pady=(0, 6))


def set_status(txt, color=None):
    status_label.config(text=txt, fg=color or C["muted"])


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
        root, "golden-bell-admin.exe", set_status,
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
                foreground=C["text"], rowheight=40, font=F_NORMAL, borderwidth=0)
style.configure("Odol.Treeview.Heading", background="#0A1228", foreground=C["gold_light"],
                font=F_BOLD, borderwidth=0, relief="flat")
style.map("Odol.Treeview", background=[("selected", C["blue_hover"])],
          foreground=[("selected", "#FFFFFF")])
style.map("Odol.Treeview.Heading", background=[("active", "#0A1228")])

# ========== หน้ารายชื่อห้อง (ล็อบบี้) ==========
lobby = tk.Frame(body, bg=C["bg"])

lobby_card = RoundedCard(lobby, 860, 350)
lobby_card.pack(pady=(18, 6))
tk.Label(lobby_card.inner, text="🏠 ห้องทั้งหมดในระบบ", font=F_HEAD,
         bg=C["card"], fg=C["gold_light"]).pack(anchor="w", pady=(0, 8))

room_tree = ttk.Treeview(lobby_card.inner, columns=("name", "members", "admins"),
                         show="headings", height=6, style="Odol.Treeview")
room_tree.heading("name", text="🏷️ ชื่อห้อง")
room_tree.heading("members", text="👥 พนักงาน")
room_tree.heading("admins", text="🛡️ แอดมิน")
room_tree.column("name", width=430)
room_tree.column("members", width=170, anchor="center")
room_tree.column("admins", width=170, anchor="center")
room_tree.pack(fill="both", expand=True)

lobby_btns = tk.Frame(lobby, bg=C["bg"])
lobby_btns.pack(pady=8)
GoldButton(lobby_btns, "🚪 เข้าห้องที่เลือก", w=200, kind="gold",
           command=lambda: enter_selected_room(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(lobby_btns, "🔄 รีเฟรช", w=130, kind="blue",
           command=lambda: refresh_now(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(lobby_btns, "📜 ประวัติการเช็ค", w=190, kind="dark",
           command=lambda: open_history(), bg=C["bg"]).pack(side="left", padx=6)
GoldButton(lobby_btns, "🗑️ ลบห้อง", w=140, kind="red",
           command=lambda: delete_selected_room(), bg=C["bg"]).pack(side="left", padx=6)

create_card = RoundedCard(lobby, 860, 108, fill=C["panel"])
create_card.pack(pady=6)
tk.Label(create_card.inner, text="➕ สร้างห้องใหม่:", font=F_BOLD,
         bg=C["panel"], fg=C["text"]).pack(side="left", padx=(4, 10))
new_room_entry = tk.Entry(create_card.inner, font=F_NORMAL, width=28, bg=C["field"],
                          fg=C["text"], insertbackground=C["gold"], relief="flat", bd=10)
new_room_entry.pack(side="left", padx=(0, 14))
GoldButton(create_card.inner, "✨ สร้างห้อง", w=170, kind="blue",
           command=lambda: create_room(), bg=C["panel"]).pack(side="left")

# ✅ แสดงโดเมนเซิร์ฟเวอร์คลาวด์ (Railway) — อ่านอย่างเดียว โดเมนถาวรไม่ต้องแก้
config_row = tk.Frame(lobby, bg=C["bg"])
config_row.pack(pady=(8, 4))
tk.Label(config_row, text="☁️ เซิร์ฟเวอร์คลาวด์:", font=F_SMALL, bg=C["bg"],
         fg=C["gold_light"]).pack(side="left", padx=(0, 8))
domain_entry = tk.Entry(config_row, font=F_SMALL, width=44, bg=C["field"],
                        fg=C["text"], insertbackground=C["gold"], relief="flat", bd=6)
domain_entry.pack(side="left", padx=(0, 8))
domain_entry.insert(0, SERVER_DOMAIN)
domain_entry.config(state="readonly")

net_row = tk.Frame(lobby, bg=C["bg"])
net_row.pack(pady=(4, 0))
tk.Label(net_row, text="🌐 เชื่อมต่อเองไม่ได้? ใส่ IP หรือลิงก์เซิร์ฟเวอร์:", font=F_SMALL,
         bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 8))
ip_entry = tk.Entry(net_row, font=F_SMALL, width=26, bg=C["field"], fg=C["text"],
                    insertbackground=C["gold"], relief="flat", bd=6)
ip_entry.pack(side="left", padx=(0, 8))
ip_entry.bind("<KeyRelease>", lambda e: state.update(manual_ip=ip_entry.get().strip()))
GoldButton(net_row, "🔌 เชื่อมต่อ", w=130, h=34, kind="gold", font=F_SMALL,
           command=lambda: manual_connect(), bg=C["bg"]).pack(side="left")
ip_entry.bind("<Return>", lambda e: manual_connect())

# ========== หน้าในห้อง ==========
room_view = tk.Frame(body, bg=C["bg"])

room_head = tk.Frame(room_view, bg=C["bg"])
room_head.pack(fill="x", padx=32, pady=(16, 4))
room_name_label = tk.Label(room_head, text="", font=F_TITLE, bg=C["bg"], fg=C["gold"])
room_name_label.pack(side="left")
room_info_label = tk.Label(room_head, text="", font=F_NORMAL, bg=C["bg"], fg=C["muted"])
room_info_label.pack(side="left", padx=16, pady=(6, 0))

member_card = RoundedCard(room_view, 980, 360)  # กว้างพอให้ทุกคอลัมน์แสดงครบไม่โดนตัด
member_card.pack(pady=6)
member_tree = ttk.Treeview(member_card.inner,
                           columns=("name", "status", "time", "elapsed", "activity"),
                           show="tree headings", height=7, style="Odol.Treeview")
# คอลัมน์ #0 ใช้โชว์จุดสีของการเช็คชื่อ 3 รอบ — Treeview ใส่รูปได้เฉพาะคอลัมน์นี้
member_tree.heading("#0", text="🔔 เช็คชื่อ")           # หัวคอลัมน์เปลี่ยนตามรอบปัจจุบันเอง
member_tree.heading("name", text="👤 ชื่อ")
member_tree.heading("status", text="📊 สถานะ")
member_tree.heading("time", text="🕐 เวลาเข้างาน")
member_tree.heading("elapsed", text="⏱️ ใช้เวลา")
member_tree.heading("activity", text="🏃 สถานะตอนนี้")
# ความกว้างรวม 930 พอดีกับพื้นที่ในการ์ด (980 - ขอบ 44) — ไม่มีคอลัมน์ไหนโดนตัด
member_tree.column("#0", width=150, minwidth=140, stretch=False, anchor="w")
member_tree.column("name", width=215, stretch=False)
member_tree.column("status", width=150, anchor="center", stretch=False)
member_tree.column("time", width=115, anchor="center", stretch=False)
member_tree.column("elapsed", width=95, anchor="center", stretch=False)
member_tree.column("activity", width=205, anchor="w")  # คอลัมน์สุดท้ายยืดเก็บที่ว่าง
member_tree.pack(fill="both", expand=True)
member_tree.tag_configure("over", foreground=C["red"])  # ออกไปเกินเวลาที่กำหนด
member_tree.tag_configure("muted", foreground=C["muted"])
member_tree.tag_configure("amber", foreground=C["amber"])
member_tree.tag_configure("green", foreground=C["green"])

room_btns = tk.Frame(room_view, bg=C["bg"])
room_btns.pack(pady=12)
GoldButton(room_btns, "🔔 เช็คชื่อคนที่เลือก", w=250, kind="gold",
           command=lambda: check_selected(), bg=C["bg"]).pack(side="left", padx=10)
GoldButton(room_btns, "🚪 ออกจากห้อง", w=190, kind="dark",
           command=lambda: leave_room(), bg=C["bg"]).pack(side="left", padx=10)
tk.Label(room_view, text="💡 เลือกชื่อในตารางแล้วกดปุ่มเช็คชื่อ หรือดับเบิลคลิกที่ชื่อได้เลย",
         font=F_SMALL, bg=C["bg"], fg=C["muted"]).pack()


def refit():
    # ปรับขนาดหน้าต่างให้พอดีกับหน้าที่กำลังแสดง (เนื้อหาแต่ละหน้าสูงไม่เท่ากัน)
    theme.fit_window(root, min_w=900, min_h=640, pad_h=8)


def show_lobby():
    status_info["people"] = {}  # ออกจากห้องแล้วล้างข้อมูลสถานะของห้องเก่า
    state["members_cache"] = None
    room_view.pack_forget()
    lobby.pack(fill="both", expand=True)
    root.title(f"🔔 {APP_NAME} — แอดมิน")
    refit()


def show_room(room):
    lobby.pack_forget()
    room_view.pack(fill="both", expand=True)
    room_name_label.config(text=f"📌 ห้อง: {room}")
    root.title(f"🔔 {APP_NAME} — ห้อง {room}")
    refit()


# ========== การกระทำ ==========
def require_connection():
    if not state["connected"]:
        messagebox.showwarning("⚠️ ยังไม่เชื่อมต่อ", "ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้\nกรุณาเปิดเซิร์ฟเวอร์แล้วเปิดโปรแกรมนี้ใหม่")
        return False
    return True


def create_room():
    if not require_connection():
        return
    name = new_room_entry.get().strip()
    if not name:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาใส่ชื่อห้อง")
        return
    sio.emit("create_room", name)


def enter_selected_room():
    if not require_connection():
        return
    sel = room_tree.selection()
    if not sel:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาเลือกห้องจากตารางก่อน")
        return
    sio.emit("join_room_admin", room_tree.item(sel[0], "values")[0])


def delete_selected_room():
    if not require_connection():
        return
    sel = room_tree.selection()
    if not sel:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาเลือกห้องที่จะลบก่อน")
        return
    room = room_tree.item(sel[0], "values")[0]
    if messagebox.askyesno("🗑️ ยืนยันการลบห้อง",
                           f"ลบห้อง '{room}' ถาวรหรือไม่?\nทุกคนที่อยู่ในห้องจะถูกพาออกทันที"):
        sio.emit("delete_room", room)


def leave_room():
    if not require_connection():
        return
    sio.emit("leave_room")


def check_selected():
    if not require_connection():
        return
    # ✅ ต้องใส่ชื่อแอดมินก่อนเรียก — ประวัติจะได้ระบุได้ว่าใครเป็นคนกด
    if not state.get("admin_name"):
        messagebox.showwarning("⚠️ แจ้งเตือน",
                               "กรุณาใส่ชื่อแอดมิน (ช่องมุมขวาบน) ก่อนเรียกเช็คชื่อ\n"
                               "ประวัติจะบันทึกว่าใครเป็นคนกดเรียก")
        admin_name_entry.focus_set()
        return
    sel = member_tree.selection()
    if not sel:
        messagebox.showwarning("⚠️ แจ้งเตือน", "กรุณาเลือกพนักงานที่จะเช็คชื่อก่อน")
        return
    # ✅ แอดมินไม่มีเสียง เฉพาะพนักงานเท่านั้นที่ได้ยินเสียงแจ้ง
    for sid in sel:
        # ✅ ส่ง data dict พร้อม target_sid และ checker_name (ชื่อแอดมิน)
        sio.emit("check_member", {"target_sid": sid, "checker_name": state.get("admin_name", "")})
    set_status("🔔 ส่งเช็คชื่อแล้ว — รอพนักงานกดยืนยัน", C["amber"])


def force_rescan():
    # หยุดการเชื่อมต่อเดิม แล้วเริ่มสแกนหาเซิร์ฟเวอร์ใหม่ทุกช่องทางทันที
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


# ========== หน้าประวัติการเช็คชื่อ ==========
def open_history():
    if not require_connection():
        return
    sio.emit("get_history")
    set_status("📜 กำลังโหลดประวัติ...", C["muted"])


def show_history_window(payload):
    records = payload.get("records", [])
    days = payload.get("days", 2)
    win = tk.Toplevel(root)
    win.title(f"📜 ประวัติการเช็คชื่อ (ย้อนหลัง {days} วัน)")
    win.geometry("940x560")
    win.configure(bg=C["bg"])
    try:
        if _icon is not None:
            win.iconphoto(False, _icon)
    except Exception:
        pass

    tk.Label(win, text=f"📜 ประวัติการเช็คชื่อ — ทั้งหมด {len(records)} รายการ (ย้อนหลัง {days} วัน)",
             font=F_HEAD, bg=C["bg"], fg=C["gold_light"]).pack(pady=(14, 8))

    table_wrap = tk.Frame(win, bg=C["card_dark"])
    table_wrap.pack(fill="both", expand=True, padx=16)
    cols = ("date", "room", "name", "checker", "called", "confirmed", "elapsed", "result")
    tree = ttk.Treeview(table_wrap, columns=cols, show="headings", style="Odol.Treeview")
    heads = {"date": "📅 วันที่", "room": "🏷️ ห้อง", "name": "👤 ชื่อ",
             "checker": "🛡️ ผู้เรียก", "called": "🔔 กดเรียก", "confirmed": "✅ ยืนยัน",
             "elapsed": "⏱️ ใช้เวลา", "result": "📊 ผล"}
    widths = {"date": 100, "room": 120, "name": 145, "checker": 120, "called": 90,
              "confirmed": 90, "elapsed": 85, "result": 115}
    for c in cols:
        tree.heading(c, text=heads[c])
        tree.column(c, width=widths[c], anchor="center" if c != "name" else "w")
    tree.column("room", anchor="w")
    tree.tag_configure("green", foreground=C["green"])
    tree.tag_configure("amber", foreground=C["amber"])
    vs = ttk.Scrollbar(table_wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vs.set)
    vs.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    result_th = {"checked": ("✅ เข้างานแล้ว", "green"), "no_response": ("⌛ ไม่ตอบ", "amber")}
    for r in records:
        label, tag = result_th.get(r.get("result"), (r.get("result", ""), "amber"))
        tree.insert("", "end", tags=(tag,), values=(
            r.get("date", ""), r.get("room", ""), r.get("name", ""),
            r.get("checker", "") or "—",
            r.get("called", ""), r.get("confirmed", "") or "—",
            f"{r['elapsed']} วิ" if r.get("elapsed") else "—", label,
        ))

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(pady=12)
    GoldButton(btns, "💾 บันทึกเป็นไฟล์ .zip", w=230, kind="gold",
               command=lambda: export_history_zip(records), bg=C["bg"]).pack(side="left", padx=8)
    GoldButton(btns, "🔄 โหลดใหม่", w=150, kind="blue",
               command=lambda: (win.destroy(), open_history()), bg=C["bg"]).pack(side="left", padx=8)


def export_history_zip(records):
    import tempfile
    default = f"ประวัติเช็คชื่อ_{time.strftime('%Y%m%d_%H%M')}.zip"
    path = filedialog.asksaveasfilename(
        title="บันทึกประวัติการเช็คชื่อ", defaultextension=".zip",
        initialfile=default, filetypes=[("ไฟล์บีบอัด ZIP", "*.zip")])
    if not path:
        return
    tmp_csv = None
    try:
        csv_name = "ประวัติเช็คชื่อ.csv"
        # ✅ บั๊ก #2 แก้: สร้างไฟล์ชั่วคราวในโฟลเดอร์ชั่วคราวระบบ (ชื่อไม่ซ้ำ) เสร็จแล้วลบเสมอ
        fd, tmp_csv = tempfile.mkstemp(suffix=".csv", text=True)
        os.close(fd)  # ปิด file descriptor ก่อนเขียน
        with open(tmp_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["วันที่", "ห้อง", "ชื่อ", "ผู้เรียก", "เวลากดเรียก", "เวลายืนยัน", "ใช้เวลา(วินาที)", "ผล"])
            for r in records:
                res = "เข้างานแล้ว" if r.get("result") == "checked" else "ไม่ตอบ"
                w.writerow([r.get("date", ""), r.get("room", ""), r.get("name", ""),
                            r.get("checker", ""), r.get("called", ""), r.get("confirmed", ""),
                            r.get("elapsed", ""), res])
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_csv, csv_name)
        messagebox.showinfo("✅ บันทึกสำเร็จ", f"บันทึกประวัติแล้วที่:\n{path}")
    except Exception as e:
        messagebox.showerror("❌ บันทึกไม่สำเร็จ", f"เกิดข้อผิดพลาด:\n{e}")
    finally:
        # ✅ ลบไฟล์ชั่วคราวเสมอ แม้การเขียนหรือ zip ล้มเหลว
        if tmp_csv and os.path.exists(tmp_csv):
            try:
                os.remove(tmp_csv)
            except:
                pass


member_tree.bind("<Double-1>", lambda e: check_selected())
new_room_entry.bind("<Return>", lambda e: create_room())


# ========== แสดงผลข้อมูลจากเซิร์ฟเวอร์ (เรียกใน main thread เท่านั้น) ==========
def render_rooms(rooms):
    state["rooms"] = rooms
    selected = room_tree.selection()
    keep = room_tree.item(selected[0], "values")[0] if selected else None
    room_tree.delete(*room_tree.get_children())
    for r in rooms:
        iid = room_tree.insert("", "end", values=(r["name"], r["members"], r["admins"]))
        if r["name"] == keep:
            room_tree.selection_set(iid)


# ========== 🔗 ข้อมูลจากระบบ check-status (เซิร์ฟเวอร์ส่งมาให้สดๆ) ==========
# สีของจุดเช็คชื่อแต่ละรอบ — ใช้ชุดสีเดียวกับหน้าเว็บของระบบสถานะ
ROUND_COLOR = {"green": "#4ADE80",   # เช็คแล้ว
               "red": "#F87171",     # ประกาศรอบแล้วแต่ยังไม่เช็ค
               "gray": "#4A4463",    # ยังไม่ประกาศรอบนี้
               "offshift": "#3A3550",
               "holiday": "#FBBF24",
               "dayoff": "#FBBF24"}
ACTIVITY_ICON = {"กลับที่นั่ง": "✅ อยู่ที่นั่ง", "ปวดหนัก": "🚻 ปวดหนัก",
                 "ปวดน้อย": "🚻 ปวดน้อย", "กินข้าว": "🍚 กินข้าว"}
_dot_images = {}  # เก็บรูปที่วาดแล้วไว้ใช้ซ้ำ (และกัน Tkinter ลบรูปทิ้งเพราะไม่มีใครอ้างอิง)


def _dots_image(rounds):
    """วาดจุดสี 3 วงเป็นรูปเล็กๆ — พื้นหลังโปร่งใส เลยใช้ได้ทั้งธีมมืดและสว่าง"""
    key = tuple(rounds)
    img = _dot_images.get(key)
    if img is not None:
        return img
    d, gap, pad = 13, 7, 3                       # ขนาดจุด, ระยะห่าง, ขอบ
    w = pad * 2 + d * 3 + gap * 2
    h = d + pad * 2
    img = tk.PhotoImage(width=w, height=h)       # รูปใหม่ = โปร่งใสทั้งหมด
    r = d / 2.0
    for i, st in enumerate(list(rounds)[:3]):
        color = ROUND_COLOR.get(st, ROUND_COLOR["gray"])
        cx = pad + i * (d + gap) + r
        cy = pad + r
        for y in range(h):                        # ไล่ทีละแถวให้ออกมาเป็นวงกลม
            dy = y + 0.5 - cy
            if abs(dy) > r:
                continue
            dx = math.sqrt(max(0.0, r * r - dy * dy))
            x0, x1 = int(round(cx - dx)), int(round(cx + dx))
            if x1 > x0:
                img.put(color, to=(x0, y, x1, y + 1))
    _dot_images[key] = img
    return img

status_info = {"people": {}, "round": 1}  # ข้อมูลล่าสุดของห้องที่กำลังดูอยู่


def _fmt_dur(seconds):
    seconds = int(seconds or 0)
    if seconds >= 3600:
        return f"{seconds // 3600} ชม. {seconds % 3600 // 60} น."
    return f"{seconds // 60} นาที" if seconds >= 60 else f"{seconds} วิ"


def _rounds_cell(info):
    """คืน (รูปจุดสี, ข้อความต่อท้าย) ของช่องเช็คชื่อ — เวลาโชว์เฉพาะรอบปัจจุบัน"""
    rounds = info.get("rounds") or []
    if not rounds:
        return None, "—"
    # ไม่ใช่กะนี้ / วันหยุด → เป็นข้อความไปเลย ไม่ต้องมีจุด (เหมือนหน้าเว็บของเขา)
    if rounds[0] in ("offshift", "holiday", "dayoff"):
        return None, {"offshift": "ไม่ใช่กะนี้", "holiday": "วันหยุด",
                      "dayoff": "วันหยุด (ลา)"}[rounds[0]]
    cur = status_info["round"]
    times = info.get("times") or []
    at = times[cur - 1] if len(times) >= cur else ""
    return _dots_image(rounds), ("  " + at if at else "")


def _activity_text(info):
    act = info.get("activity") or ""
    label = ACTIVITY_ICON.get(act, act or "—")
    if act and act != "กลับที่นั่ง":
        label += f" · {_fmt_dur(info.get('duration'))}"
        if info.get("over"):
            label += " ⚠️"
    return label


def _status_cells(name):
    """คืน (รูปจุดสี, ข้อความช่องเช็คชื่อ, ข้อความสถานะ, เกินเวลาไหม) ของพนักงานคนหนึ่ง"""
    info = status_info["people"].get(name)
    if not info:
        return None, "—", "—", False
    if info.get("match") == "ambiguous":
        return None, "—", "❓ ชื่อซ้ำหลายคน", False
    if info.get("match") != "ok":
        return None, "—", "❓ ไม่พบในระบบ", False
    img, txt = _rounds_cell(info)
    return img, txt, _activity_text(info), bool(info.get("over"))


@sio.on("do_update")
def on_do_update(data=None):
    # เซิร์ฟเวอร์สั่งให้อัพเดทเดี๋ยวนี้
    root.after(0, updater.force_update, root, "golden-bell-admin.exe", set_status)


@sio.on("members_status")
def on_members_status(data):
    def _apply():
        if data.get("room") != state["room"]:
            return
        status_info["people"] = data.get("people") or {}
        status_info["round"] = data.get("current_round") or 1
        member_tree.heading("#0", text=f"🔔 เช็คชื่อ (รอบ {status_info['round']})")
        if state.get("members_cache"):
            render_members(state["members_cache"])
    root.after(0, _apply)


def render_members(data):
    if data["room"] != state["room"]:
        return
    room_info_label.config(text=f"👥 พนักงาน {len(data['members'])} คน  •  🛡️ แอดมิน {data['admins']} คน")
    state["members_cache"] = data  # เก็บไว้วาดใหม่ตอนข้อมูลสถานะอัปเดต
    selected = set(member_tree.selection())
    member_tree.delete(*member_tree.get_children())
    for m in data["members"]:
        label, tag = STATUS_TH.get(m["status"], (m["status"], "muted"))
        elapsed = f"{m['elapsed']} วิ" if m.get("elapsed") else "—"
        dots_img, rounds_txt, act_txt, over = _status_cells(m["name"])
        member_tree.insert("", "end", iid=m["sid"],
                           text=rounds_txt, image=dots_img or "",
                           values=(m["name"], label, m["time"] or "—", elapsed, act_txt),
                           tags=("over",) if over else (tag,))
        if m["sid"] in selected:
            member_tree.selection_add(m["sid"])


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
        state["room"] = data["room"]
        show_room(data["room"])
        set_status(f"✅ เข้าห้อง {data['room']} แล้ว")
    root.after(0, _apply)


@sio.on("left_room")
def on_left(_):
    def _apply():
        state["room"] = None
        show_lobby()
        set_status("ออกจากห้องแล้ว")
    root.after(0, _apply)


@sio.on("error_msg")
def on_error(data):
    root.after(0, lambda: messagebox.showwarning("⚠️ แจ้งเตือน", data.get("msg", "เกิดข้อผิดพลาด")))


@sio.on("history_data")
def on_history(data):
    root.after(0, show_history_window, data)


@sio.event
def disconnect():
    def _apply():
        state["connected"] = False
        shown = state["last_url"] or "เซิร์ฟเวอร์"
        addr_label.config(text=f"📍 {shown}  •  ⚠️ หลุดการเชื่อมต่อ กำลังต่อใหม่...")
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
        root.after(0, set_status, f"⛔ เซิร์ฟเวอร์ปฏิเสธ: {msg}", C["red"])


@sio.event
def connect():
    def _apply():
        state["connected"] = True
        shown = state["last_url"] or f"{MY_IP}:{PORT}"
        addr_label.config(text=f"📍 เซิร์ฟเวอร์: {shown}  •  ✅ เชื่อมต่อแล้ว")
        set_status("✅ เชื่อมต่อเซิร์ฟเวอร์แล้ว")
        if state["room"] is None:
            show_lobby()
    root.after(0, _apply)
    # ✅ เน็ตสะดุดแล้วต่อกลับมา — เข้าห้องเดิมคืนอัตโนมัติ (เซิร์ฟเวอร์ล้างสถานะตอนหลุด)
    if state["room"]:
        try:
            sio.emit("join_room_admin", state["room"])
        except Exception:
            pass


# ========== เชื่อมต่อ — ทำงานเบื้องหลัง ลองใหม่เรื่อย ๆ จนกว่าจะเจอ ==========
def candidate_urls():
    urls = []
    if state["manual_ip"]:
        urls.append(normalize_target(state["manual_ip"]))  # ที่ผู้ใช้พิมพ์เอง มาก่อน
    if PINNED:
        urls.append(normalize_target(PINNED))  # ที่อยู่ปักไว้ในไฟล์ตั้งค่า (ชุด .zip)
    urls.append(f"https://{SERVER_DOMAIN}")  # ☁️ เซิร์ฟเวอร์คลาวด์ Railway — ช่องทางหลัก
    for ip in discover_servers():
        urls.append(f"http://{ip}:{PORT}")
    urls.append(f"http://127.0.0.1:{PORT}")
    urls.extend(SERVER_URLS_TO_TRY)
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
                    root.after(0, set_status, f"🔍 กำลังเชื่อมต่อ: {url}")
                    state["last_url"] = url
                    sio.connect(url, auth={"code": ACCESS_CODE}, wait_timeout=10)
                    return
                except Exception:
                    continue
            root.after(0, set_status,
                       "❌ ยังไม่พบเซิร์ฟเวอร์ — เปิดโปรแกรมเซิร์ฟเวอร์ก่อน หรือใส่ IP/ลิงก์ในช่องด้านล่าง (กำลังลองใหม่อัตโนมัติ...)",
                       C["red"])
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
show_lobby()
threading.Thread(target=connect_worker, daemon=True).start()
root.after(60, refit)  # จัดขนาดหน้าต่างให้พอดีเนื้อหาหลัง widget วางตัวเสร็จ
# 🔄 อัพเดทอัตโนมัติ — เช็คเงียบๆ ตอนเปิด ถ้ามีเวอร์ชันใหม่ก็โหลดและเปิดใหม่ให้เอง
updater.auto_update(root, "golden-bell-admin.exe", set_status)
# เครื่องที่เปิดค้างทั้งวัน — คอยดูเป็นระยะ เจอแล้วบอกให้รู้ (ไม่รีสตาร์ทกลางคัน)
# อัพเดทเองระหว่างเปิดค้างได้ ถ้าไม่มีใครค้างสถานะ "รอยืนยัน" อยู่
updater.watch_for_updates(root, "golden-bell-admin.exe", set_status,
                          can_update=lambda: not any(
                              m.get("status") == "pending"
                              for m in ((state.get("members_cache") or {}).get("members") or [])))
root.mainloop()

try:
    sio.disconnect()
except:
    pass
