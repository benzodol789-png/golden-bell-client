# -*- coding: utf-8 -*-
# 💾 ที่เก็บค่าตั้งค่าของผู้ใช้ (ระดับเสียง ฯลฯ) — เก็บใน %APPDATA% ไม่ใช่โฟลเดอร์โปรแกรม
#    เพราะโฟลเดอร์โปรแกรมอาจเขียนไม่ได้ และไฟล์ .exe ถูกเขียนทับทุกครั้งที่อัพเดท
import json
import os

_FOLDER = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "GoldenBell")
_FILE = os.path.join(_FOLDER, "prefs.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_FILE, encoding="utf-8") as f:
                data = json.load(f)
            _cache = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            _cache = {}
    return _cache


def get(key, default=None):
    value = _load().get(key, default)
    # ค่าที่อ่านมาอาจเพี้ยน (ไฟล์ถูกแก้มือ) — ให้ค่าเริ่มต้นแทนถ้าชนิดไม่ตรงกัน
    if default is not None and not isinstance(value, type(default)):
        return default
    return value


def set(key, value):
    data = _load()
    data[key] = value
    try:
        os.makedirs(_FOLDER, exist_ok=True)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _FILE)  # เขียนแบบ atomic กันไฟล์พังถ้าปิดโปรแกรมกลางคัน
    except OSError:
        pass  # บันทึกไม่ได้ก็ยังใช้ค่านั้นได้ในรอบนี้
