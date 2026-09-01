# -*- coding: utf-8 -*-
# 🎨 ระบบธีม มืด/สว่าง + ปรับขนาดหน้าต่างให้พอดีกับเนื้อหา
#
# วิธีทำงาน: ทุกสีในโปรแกรมอ่านจาก dict C ตัวเดียว เวลาสลับธีมจะ
#   1) จำสีชุดเดิมไว้เป็น mapping (สีเก่า → สีใหม่)
#   2) เขียนทับค่าใน C แบบ in-place (โค้ดที่ถือ C อยู่จึงเห็นสีใหม่ทันที)
#   3) ไล่ทุก widget ที่สร้างไว้แล้ว เปลี่ยนสีที่ตรงกับ mapping เป็นสีใหม่
# ผลคือสลับธีมได้ทันทีโดยไม่ต้องปิดโปรแกรม และโค้ด UI เดิมไม่ต้องแก้
import os

PALETTES = {
    "dark": {
        "bg": "#0A0F1E",
        "panel": "#0E1730",
        "card": "#13214A",
        "card_dark": "#0D1838",
        "field": "#0A1228",       # พื้นช่องกรอกข้อความ
        "gold": "#D4AF37",
        "gold_light": "#F1D97C",
        "blue": "#1E3A8A",
        "blue_hover": "#2B4CC0",
        "text": "#F4F1E8",
        "muted": "#93A0C4",
        "green": "#34D399",
        "amber": "#FBBF24",
        "red": "#F87171",
        "shadow": "#04070F",
    },
    "light": {
        "bg": "#F4F6FB",
        "panel": "#FFFFFF",
        "card": "#FFFFFF",
        "card_dark": "#EEF1F8",
        "field": "#FFFFFF",
        "gold": "#A8801A",        # ทองเข้มขึ้น ให้อ่านออกบนพื้นสว่าง
        "gold_light": "#7A5D10",
        "blue": "#2B4CC0",
        "blue_hover": "#1E3A8A",
        "text": "#141A2B",
        "muted": "#5B6684",
        "green": "#0F9D63",
        "amber": "#B45309",
        "red": "#DC2626",
        "shadow": "#C9D0E0",
    },
}

# ชุดสีของปุ่ม GoldButton (วาดเองบน Canvas จึงต้องแยกชุดสีของตัวเอง)
BUTTON_PALETTES = {
    "dark": {
        "gold": {"fill": "#C9A227", "hover": "#E3BD3F", "fg": "#101A33", "outline": "#F1D97C"},
        "blue": {"fill": "#1E3A8A", "hover": "#2B4CC0", "fg": "#F4F1E8", "outline": "#D4AF37"},
        "dark": {"fill": "#152246", "hover": "#1D2F60", "fg": "#D8DCEA", "outline": "#5A6A96"},
        "red": {"fill": "#7F1D1D", "hover": "#A02B2B", "fg": "#FBEAEA", "outline": "#D4AF37"},
        "green": {"fill": "#166534", "hover": "#1E8A47", "fg": "#EBFBF1", "outline": "#F1D97C"},
    },
    "light": {
        "gold": {"fill": "#D9B531", "hover": "#EBC953", "fg": "#231A02", "outline": "#8A6D12"},
        "blue": {"fill": "#2B4CC0", "hover": "#3D5FD8", "fg": "#FFFFFF", "outline": "#1E3A8A"},
        "dark": {"fill": "#E3E8F3", "hover": "#D2DAEC", "fg": "#1B2440", "outline": "#9AA6C4"},
        "red": {"fill": "#DC2626", "hover": "#EF4444", "fg": "#FFFFFF", "outline": "#991B1B"},
        "green": {"fill": "#0F9D63", "hover": "#12B873", "fg": "#FFFFFF", "outline": "#0A6B44"},
    },
}
BUTTON_KINDS = {k: dict(v) for k, v in BUTTON_PALETTES["dark"].items()}

# ตัวเลือกสีของ widget ที่ต้องไล่เปลี่ยนตอนสลับธีม
_COLOR_OPTS = ("background", "bg", "foreground", "fg", "activebackground",
               "activeforeground", "disabledforeground", "highlightbackground",
               "highlightcolor", "insertbackground", "selectbackground",
               "selectforeground", "readonlybackground", "troughcolor")

C = dict(PALETTES["dark"])  # ชุดสีที่ใช้อยู่ — โปรแกรม import ตัวนี้ไปใช้
_state = {"name": "dark", "on_change": []}


def _pref_file():
    # เก็บที่ %APPDATA% — โฟลเดอร์โปรแกรมอาจเขียนไม่ได้ (Program Files / ไดรฟ์อ่านอย่างเดียว)
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "GoldenBell", "theme.txt")


def load_saved():
    try:
        with open(_pref_file(), encoding="utf-8") as f:
            name = f.read().strip()
        if name in PALETTES:
            return name
    except OSError:
        pass
    return "dark"


def save(name):
    try:
        path = _pref_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass  # บันทึกไม่ได้ก็ใช้ธีมนั้นได้ในรอบนี้ แค่ไม่ถูกจำไว้


def current():
    return _state["name"]


def init(name):
    # ตั้งชุดสีเริ่มต้นก่อนสร้าง widget ใดๆ (ยังไม่ต้องไล่เปลี่ยนอะไร)
    if name in PALETTES:
        C.clear()
        C.update(PALETTES[name])
        BUTTON_KINDS.clear()
        BUTTON_KINDS.update({k: dict(v) for k, v in BUTTON_PALETTES[name].items()})
        _state["name"] = name


def on_change(fn):
    # ลงทะเบียนงานที่ต้องทำเพิ่มตอนสลับธีม (เช่น ตั้งค่าสไตล์ ttk ใหม่)
    _state["on_change"].append(fn)


def _walk(widget, mapping):
    # เปลี่ยนสีของ widget ตัวนี้และลูกทั้งหมด ตาม mapping สีเก่า→สีใหม่
    try:
        keys = widget.keys()
    except Exception:
        keys = ()
    for opt in _COLOR_OPTS:
        if opt not in keys:
            continue
        try:
            cur = str(widget.cget(opt))
        except Exception:
            continue
        new = mapping.get(cur.lower())
        if new:
            try:
                widget.configure(**{opt: new})
            except Exception:
                pass
    # Canvas วาดรูปทรงเอง (การ์ดขอบมน/ปุ่ม) — ต้องเปลี่ยนสีของแต่ละชิ้นงานด้วย
    if widget.winfo_class() == "Canvas":
        try:
            for item in widget.find_all():
                for opt in ("fill", "outline"):
                    try:
                        cur = str(widget.itemcget(item, opt))
                    except Exception:
                        continue
                    new = mapping.get(cur.lower())
                    if new:
                        widget.itemconfig(item, **{opt: new})
        except Exception:
            pass
    for child in widget.winfo_children():
        _walk(child, mapping)


def apply(root, name):
    """สลับไปธีม name แล้วไล่เปลี่ยนสีทุก widget ที่สร้างไว้แล้วทันที"""
    if name not in PALETTES or name == _state["name"]:
        return
    mapping = {}
    for key, old in C.items():
        new = PALETTES[name].get(key)
        if new and old.lower() != new.lower():
            mapping[old.lower()] = new
    C.clear()
    C.update(PALETTES[name])
    BUTTON_KINDS.clear()
    BUTTON_KINDS.update({k: dict(v) for k, v in BUTTON_PALETTES[name].items()})
    _state["name"] = name
    for w in [root] + list(root.winfo_children()):
        _walk(w, mapping)
    for win in root.winfo_children():  # หน้าต่างลูก (เช่น หน้าประวัติ) ที่เปิดค้างอยู่
        if isinstance(win, type(root)) or win.winfo_class() == "Toplevel":
            _walk(win, mapping)
    for fn in _state["on_change"]:
        try:
            fn()
        except Exception:
            pass
    save(name)


def fit_window(root, min_w=520, min_h=420, pad_w=0, pad_h=0):
    """ปรับขนาดหน้าต่างให้พอดีกับเนื้อหาจริง แล้วจัดกลางจอ (ไม่ล้นจอ)"""
    root.update_idletasks()
    w = max(root.winfo_reqwidth() + pad_w, min_w)
    h = max(root.winfo_reqheight() + pad_h, min_h)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(w, sw - 60), min(h, sh - 100)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
    root.minsize(min(w, min_w), min(h, min_h))
