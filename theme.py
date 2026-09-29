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


class FitTable:
    """ตารางที่ตัวหนังสือยืด-หดตามความกว้างของหน้าต่าง และไม่ถูกตัดท้าย

    - ขนาดตัวหนังสือตามความกว้าง: กว้างเท่าตอนออกแบบ (base_width) = base_size
      ยืดหน้าต่างออกตัวหนังสือใหญ่ขึ้น หดลงก็เล็กลง (อยู่ในช่วง min_size..max_size)
    - ถ้าข้อความในตารางยาวจนใส่ไม่พอ ลดขนาดลงอีกจนใส่ได้ครบ (ไม่ต่ำกว่า min_size)
    - ความกว้างคอลัมน์วัดจากข้อความจริง + ระยะขอบ แล้วแบ่งที่เหลือให้ทุกคอลัมน์ตามสัดส่วน
    เปลี่ยนข้อมูลในตารางแล้วเรียก refresh() — ขนาดหน้าต่างเปลี่ยน ตารางปรับเอง"""

    _count = 0

    def __init__(self, tree, base_width, base_size=11, min_size=9, max_size=15,
                 family="Segoe UI", row_ratio=2.0):
        import tkinter.font as tkfont
        from tkinter import ttk
        FitTable._count += 1
        self.tree = tree
        self.style = ttk.Style(tree)
        self.name = f"Fit{FitTable._count}.Odol.Treeview"  # สืบสี/ธีมจาก Odol.Treeview
        self.base_width, self.base_size = base_width, base_size
        self.min_size, self.max_size = min_size, max_size
        self.row_ratio = row_ratio
        self.font = tkfont.Font(tree, family=family, size=base_size)
        self.head_font = tkfont.Font(tree, family=family, size=base_size, weight="bold")
        self._m = tkfont.Font(tree, family=family, size=base_size)                   # ไว้วัดเท่านั้น
        self._mb = tkfont.Font(tree, family=family, size=base_size, weight="bold")
        self.size = self.pad = None
        self._heads, self._cells, self._fixed = {}, {}, {}
        self._cache = {}   # ขนาดตัวหนังสือ -> ความกว้างที่ต้องใช้ของแต่ละคอลัมน์
        self._width = 0
        self._job = None
        tree.configure(style=self.name)
        self._apply_size(base_size, self._full_pad(base_size))
        tree.bind("<Configure>", self._on_configure, add="+")
        self.refresh()

    def _columns(self):
        cols = list(self.tree["columns"])
        if "tree" in str(self.tree.cget("show")):
            cols.insert(0, "#0")
        return cols

    def refresh(self):
        """เก็บข้อความในตารางใหม่ (เรียกหลังใส่/เปลี่ยนแถว) แล้วจัดขนาดใหม่"""
        tree = self.tree
        cols = self._columns()
        offset = 1 if cols and cols[0] == "#0" else 0
        heads = {c: str(tree.heading(c, "text") or "") for c in cols}
        cells = {c: set() for c in cols}
        fixed = {c: 0 for c in cols}
        for iid in tree.get_children():
            values = list(tree.item(iid, "values") or ())
            for i, c in enumerate(cols):
                if c == "#0":
                    cells[c].add(str(tree.item(iid, "text") or ""))
                    img = tree.item(iid, "image")
                    if img:
                        try:
                            fixed[c] = max(fixed[c], int(tree.tk.call("image", "width", img[0])) + 6)
                        except Exception:
                            pass
                else:
                    j = i - offset
                    cells[c].add(str(values[j]) if j < len(values) else "")
        if (heads, cells, fixed) != (self._heads, self._cells, self._fixed):
            self._heads, self._cells, self._fixed = heads, cells, fixed
            self._cache = {}
            self._schedule()

    def _on_configure(self, e):
        if e.width != self._width:
            self._width = e.width
            self._schedule()

    def _schedule(self):
        if self._job is None:
            self._job = self.tree.after_idle(self._fit)

    INSET = 4       # ตารางของ ttk เว้นขอบในช่องให้เองข้างละประมาณนี้ (วัดจากภาพจริง)
    MIN_PAD = 12    # ระยะขอบรวมซ้าย-ขวาที่น้อยที่สุด ตอนหน้าต่างแคบมาก (รวมที่ ttk เว้นเองแล้ว)
    FLOOR = 8       # ขนาดตัวหนังสือเล็กสุดจริงๆ — ใช้เมื่อลดระยะขอบจนสุดแล้วยังไม่พอ

    @staticmethod
    def _full_pad(size):
        return size + 16  # ระยะขอบรวมซ้าย-ขวาของแต่ละช่องตอนมีที่พอ — ตัวหนังสือไม่ชิดเส้น

    def _text(self, size):
        """ความกว้างข้อความที่ยาวสุดของแต่ละคอลัมน์ (ยังไม่รวมระยะขอบ)"""
        got = self._cache.get(size)
        if got is None:
            self._m.configure(size=size)
            self._mb.configure(size=size)
            got = {}
            for c in self._columns():
                text_w = max([self._mb.measure(self._heads.get(c, ""))]
                             + [self._m.measure(t) for t in self._cells.get(c, ())])
                got[c] = text_w + self._fixed.get(c, 0)
            self._cache[size] = got
        return dict(got)

    def _fits(self, size, pad, avail):
        text = self._text(size)
        return sum(text.values()) + pad * len(text) <= avail

    def _apply_size(self, size, pad):
        if (size, pad) == (self.size, self.pad):
            return
        self.size, self.pad = size, pad
        self.font.configure(size=size)
        self.head_font.configure(size=size)
        row = int(self.font.metrics("linespace") * self.row_ratio)
        # ระยะขอบที่เพิ่มเองต่อข้าง = ครึ่งหนึ่งของ pad หักส่วนที่ ttk เว้นให้แล้ว (เผื่อไว้อีก 1-2px กันตัวท้ายโดนตัด)
        edge = max(0, (pad - 2 * self.INSET - 2) // 2)
        self.style.configure(self.name, font=self.font, rowheight=row)
        self.style.configure(self.name + ".Cell", padding=(edge, 0))
        self.style.configure(self.name + ".Item", padding=(edge, 0))
        self.style.configure(self.name + ".Heading", font=self.head_font,
                             padding=(edge, int(size * 0.6)))

    def _fit(self):
        self._job = None
        try:
            avail = self.tree.winfo_width() - 4
        except Exception:
            return  # ตารางถูกปิดไปแล้ว
        if avail < 50:
            return
        # 1) ขนาดตัวหนังสือตามความกว้างหน้าต่าง — ใส่ไม่พอก็ลดลงทีละขั้น (ระยะขอบเต็ม)
        size = int(round(self.base_size * avail / float(self.base_width)))
        size = max(self.min_size, min(self.max_size, size))
        while size > self.min_size and not self._fits(size, self._full_pad(size), avail):
            size -= 1
        pad = self._full_pad(size)
        if not self._fits(size, pad, avail):
            # 2) ตัวเล็กสุดแล้วยังไม่พอ — ลดระยะขอบลงก่อน แล้วค่อยลดตัวหนังสืออีกขั้นเป็นทางสุดท้าย
            while size > self.FLOOR and not self._fits(size, self.MIN_PAD, avail):
                size -= 1
            spare = avail - sum(self._text(size).values())
            pad = max(self.MIN_PAD, min(self._full_pad(size), spare // max(1, len(self._text(size)))))
        widths = {c: w + pad for c, w in self._text(size).items()}
        total = sum(widths.values()) or 1
        # เหลือที่ = แบ่งให้ทุกคอลัมน์ตามสัดส่วน (ตารางเต็มกรอบพอดี)
        # หน้าต่างแคบเกินจริงๆ = บีบทุกคอลัมน์ตามสัดส่วน ดีกว่าคอลัมน์ขวาสุดหายไปทั้งคอลัมน์
        ratio = avail / float(total)
        for c in widths:
            widths[c] = int(widths[c] * ratio)
        self._apply_size(size, pad)
        for c, w in widths.items():
            self.tree.column(c, width=max(10, w), minwidth=10, stretch=False)
