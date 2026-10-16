# -*- coding: utf-8 -*-
# 🖥️ ทำงานเบื้องหลังที่ถาดไอคอน (มุมขวาล่างของจอ) + เปิดเองตอนเปิดเครื่อง + กันเปิดโปรแกรมซ้อน
#
# - ไอคอนถาด   : pystray ทำงานใน thread ของตัวเอง — คำสั่งจากเมนูต้องส่งกลับเข้า Tk ผ่าน root.after เสมอ
# - เปิดเอง    : เขียนค่าไว้ที่ HKCU\...\Run (ระดับผู้ใช้ ไม่ต้องใช้สิทธิ์แอดมิน) เฉพาะตอนรันเป็น .exe
# - กันเปิดซ้อน : named mutex ของ Windows — ตัวที่เปิดซ้ำส่งสัญญาณ (named event) ให้ตัวแรกโชว์หน้าต่าง แล้วปิดตัวเอง
import ctypes
import os
import sys
import tempfile
import threading
import winreg
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_k32.WaitForSingleObject.restype = wintypes.DWORD
for _fn in ("ReleaseMutex", "SetEvent", "ResetEvent", "CloseHandle"):
    getattr(_k32, _fn).argtypes = (wintypes.HANDLE,)
    getattr(_k32, _fn).restype = wintypes.BOOL

_WAIT_OBJECT_0, _WAIT_ABANDONED, _WAIT_TIMEOUT = 0x0, 0x80, 0x102


class SingleInstance:
    """ให้โปรแกรมเปิดได้ทีละตัวต่อผู้ใช้ — key ต่างกันนับแยกกัน"""

    def __init__(self, key):
        self.key = key
        self._mutex = None
        self._event = None

    def acquire(self, wait_ms=0):
        """ได้เป็นตัวหลักไหม — รอตัวเดิมปิดได้ไม่เกิน wait_ms (เช่น ตัวเก่ากำลังปิดเพื่ออัพเดท)"""
        if self._mutex:
            return True
        h = _k32.CreateMutexW(None, False, f"Local\\{self.key}.lock")
        if not h:
            return True  # สร้างตัวล็อกไม่ได้ (ไม่น่าเกิด) — ยอมให้เปิดซ้อน ดีกว่าเปิดไม่ขึ้นเลย
        if _k32.WaitForSingleObject(h, wait_ms) in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            self._mutex = h
            ev = self._event_handle()
            if ev:
                _k32.ResetEvent(ev)  # สัญญาณค้างจากตอนที่ยังไม่มีใครรับ — ไม่ต้องเด้งหน้าต่างตามนั้น
            return True
        _k32.CloseHandle(h)
        return False

    def release(self):
        """ปล่อยตัวล็อก — ต้องเรียกจาก thread เดียวกับที่ acquire (thread หลักของ Tk)"""
        h, self._mutex = self._mutex, None
        if h:
            _k32.ReleaseMutex(h)
            _k32.CloseHandle(h)

    def _event_handle(self):
        if self._event is None:
            self._event = _k32.CreateEventW(None, False, False, f"Local\\{self.key}.show") or None
        return self._event

    def signal_existing(self):
        """บอกตัวที่เปิดอยู่แล้วให้โชว์หน้าต่าง"""
        ev = self._event_handle()
        if ev:
            _k32.SetEvent(ev)

    def listen(self, on_signal):
        """รอสัญญาณจากตัวที่เปิดซ้ำ — ได้เมื่อไหร่ก็เรียก on_signal() (ถูกเรียกจาก thread อื่น)"""
        ev = self._event_handle()
        if not ev:
            return

        def loop():
            while True:
                r = _k32.WaitForSingleObject(ev, 1000)
                if r == _WAIT_OBJECT_0:
                    if self._mutex:  # ปล่อยตัวล็อกไปแล้ว (กำลังรีสตาร์ทอัพเดท) — ไม่ใช่หน้าที่เราแล้ว
                        try:
                            on_signal()
                        except Exception:
                            pass
                elif r != _WAIT_TIMEOUT:
                    return  # handle ใช้ไม่ได้แล้ว — เลิกฟัง ดีกว่าวนรอบเปล่าจน CPU เต็ม

        threading.Thread(target=loop, daemon=True).start()


# ========== เปิดเองตอนเปิดเครื่อง ==========
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _run_value(value_name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            return winreg.QueryValueEx(k, value_name)[0]
    except OSError:
        return None


def autostart_command(args=("--tray",)):
    """คำสั่งที่ Windows ใช้เปิดโปรแกรมตอนเข้าเครื่อง — None ถ้าลงทะเบียนไม่ได้"""
    if not getattr(sys, "frozen", False):
        return None  # รันจาก source — ห้ามแตะการตั้งค่าเปิดเครื่องของตัว .exe ที่ใช้งานจริง
    exe = os.path.abspath(sys.executable)
    # รันจากใน .zip (ถูกแตกไปไว้ใน temp) — ไฟล์จะหายไปเอง ลงทะเบียนไว้ก็เปิดไม่ขึ้น
    if os.path.dirname(exe).lower().startswith(tempfile.gettempdir().lower()):
        return None
    return " ".join([f'"{exe}"', *args])


def set_autostart(value_name, enabled):
    """เปิด/ปิดการเปิดเองตอนเข้าเครื่อง — ชี้ไปที่ .exe ตัวนี้เสมอ (ย้ายโฟลเดอร์ก็ตามไปให้เอง)"""
    if not getattr(sys, "frozen", False) or os.environ.get("ODOL_NO_AUTOSTART"):
        return False  # โหมด dev / โหมดทดสอบ — ไม่แตะการตั้งค่าของเครื่อง
    cmd = autostart_command() if enabled else None
    if enabled and not cmd:
        return False
    try:
        current = _run_value(value_name)
        if cmd and current != cmd:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, value_name, 0, winreg.REG_SZ, cmd)
        elif not cmd and current is not None:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, value_name)
        return True
    except OSError:
        return False


# ========== ไอคอนที่ถาด ==========
class Tray:
    """ไอคอนกระดิ่งที่ถาดมุมขวาล่าง — คลิกซ้าย = รายการ default (เปิดหน้าต่าง) / คลิกขวา = เมนู"""

    def __init__(self, icon_path, title):
        self.icon_path = icon_path
        self.title = title
        self._icon = None
        self._base = None
        self._badge = None

    @property
    def running(self):
        return self._icon is not None

    def start(self, items):
        """items = [(ข้อความ, ฟังก์ชัน, {"default": True} หรือ {"checked": ฟังก์ชันคืน bool}), None = เส้นคั่น]
        คืน False ถ้าสร้างไอคอนไม่ได้ (โปรแกรมต้องไม่ซ่อนหน้าต่างจนหาไม่เจอ)"""
        try:
            import pystray
            from PIL import Image
            self._base = Image.open(self.icon_path).convert("RGBA").resize((64, 64), Image.LANCZOS)
            entries = []
            for it in items:
                if it is None:
                    entries.append(pystray.Menu.SEPARATOR)
                    continue
                text, action = it[0], it[1]
                opts = it[2] if len(it) > 2 else {}
                checked = opts.get("checked")
                entries.append(pystray.MenuItem(
                    text, self._action(action),
                    checked=self._checked(checked) if checked else None,
                    default=bool(opts.get("default"))))
            self._icon = pystray.Icon("golden-bell", self._render(), self._tip(self.title),
                                      pystray.Menu(*entries))
            threading.Thread(target=self._icon.run, daemon=True).start()
            return True
        except Exception:
            self._icon = None
            try:
                import traceback
                traceback.print_exc()  # โหมด dev เห็นสาเหตุ (ตัว .exe ไม่มี stderr ก็ข้ามไปเงียบๆ)
            except Exception:
                pass
            return False

    # pystray นับจำนวนพารามิเตอร์ของฟังก์ชัน (นับตัวที่มีค่าเริ่มต้นด้วย) แล้วเลือกวิธีเรียกตามนั้น
    # จึงต้องห่อให้เหลือพารามิเตอร์ตามที่มันรับพอดี — ห้ามใช้ลูกเล่น lambda f=...
    @staticmethod
    def _action(fn):
        return lambda: fn()

    @staticmethod
    def _checked(fn):
        return lambda item: bool(fn())

    @staticmethod
    def _tip(text):
        return str(text)[:120]  # Windows รับข้อความไอคอนถาดได้ไม่เกิน 127 ตัวอักษร

    def _render(self):
        img = self._base.copy()
        if self._badge:
            from PIL import ImageDraw
            ImageDraw.Draw(img).ellipse((36, 36, 63, 63), fill=self._badge,
                                        outline="#FFFFFF", width=4)
        return img

    def set_title(self, text):
        text = self._tip(text)
        if self._icon is not None and text != self.title:
            self.title = text
            try:
                self._icon.title = text
            except Exception:
                pass

    def set_badge(self, color):
        """จุดสีที่มุมไอคอน (เช่น แดง = ยังไม่เช็คชื่อรอบนี้) — None = ไม่มีจุด"""
        if self._icon is not None and color != self._badge:
            self._badge = color
            try:
                self._icon.icon = self._render()
            except Exception:
                pass

    def notify(self, message, title=None):
        try:
            if self._icon is not None:
                self._icon.notify(message, title)
        except Exception:
            pass

    def update_menu(self):
        try:
            if self._icon is not None:
                self._icon.update_menu()
        except Exception:
            pass

    def hide_now(self):
        """เอาไอคอนออกทันที (ใช้ก่อนปิดโปรเซสแบบกะทันหัน — กันไอคอนผีค้างที่ถาด)"""
        try:
            if self._icon is not None:
                self._icon.visible = False
        except Exception:
            pass

    def show_again(self):
        try:
            if self._icon is not None:
                self._icon.visible = True
        except Exception:
            pass

    def stop(self):
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
