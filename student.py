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
    except:
        pass


def play_alert():
    try:
        if _sound_ready and _alert_sounds:
            import random
            alias = random.choice(_alert_sounds)  # ✅ สุ่มเลือกเสียงแจ้ง
            ctypes.windll.winmm.mciSendStringW(f"play {alias} from 0", None, 0, None)
        else:
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
member_tree = ttk.Treeview(member_card.inner, columns=("name", "status"),
                           show="headings", height=5, style="Odol.Treeview")
member_tree.heading("name", text="👤 ชื่อ")
member_tree.heading("status", text="📊 สถานะ")
member_tree.column("name", width=300)
member_tree.column("status", width=190, anchor="center")
member_tree.pack(fill="both", expand=True)
member_tree.tag_configure("me", foreground=C["gold_light"])

GoldButton(room_view, "🚪 ออกจากห้อง / ย้ายห้อง", w=250, kind="dark",
           command=lambda: leave_room(), bg=C["bg"]).pack(pady=10)
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


def render_members(data):
    if data["room"] != state["room"]:
        return
    member_tree.delete(*member_tree.get_children())
    for m in data["members"]:
        tags = ("me",) if m["name"] == state["name"] else ()
        member_tree.insert("", "end", values=(m["name"], STATUS_TH.get(m["status"], m["status"])), tags=tags)


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
    # ✅ เน็ตสะดุดแล้วต่อกลับมา — เข้าห้องเดิมคืนอัตโนมัติ (เซิร์ฟเวอร์ล้างสถานะตอนหลุด)
    if state["room"] and state["name"]:
        try:
            sio.emit("join_room_member", {"room": state["room"], "name": state["name"]})
        except Exception:
            pass


# ========== เชื่อมต่อ — ทำงานเบื้องหลัง ลองใหม่เรื่อย ๆ จนกว่าจะเจอ ==========
def candidate_urls():
    urls = []
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
show_lobby()
threading.Thread(target=connect_worker, daemon=True).start()
root.after(60, refit)  # จัดขนาดหน้าต่างให้พอดีเนื้อหาหลัง widget วางตัวเสร็จ
# 🔄 อัพเดทอัตโนมัติ — เช็คเงียบๆ ตอนเปิด ถ้ามีเวอร์ชันใหม่ก็โหลดและเปิดใหม่ให้เอง
updater.auto_update(root, "golden-bell-employee.exe", set_status)
# เครื่องที่เปิดค้างทั้งวัน — คอยดูเป็นระยะ เจอแล้วบอกให้รู้ (ไม่รีสตาร์ทกลางคัน)
updater.watch_for_updates(root, "golden-bell-employee.exe", set_status)
root.mainloop()

try:
    sio.disconnect()
except:
    pass
