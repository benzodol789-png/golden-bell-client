# -*- coding: utf-8 -*-
# 🔄 ระบบอัพเดทโปรแกรม — เช็คเวอร์ชันใหม่จาก GitHub Releases แล้วอัพเดทตัวเองอัตโนมัติ
#
# หลักการ:
#   1. เทียบ APP_VERSION กับ tag ล่าสุดของ GitHub Releases (repo ด้านล่าง)
#   2. ดาวน์โหลด asset ชื่อ ASCII (golden-bell-admin.exe / golden-bell-employee.exe)
#      ลงไฟล์ .part ข้างๆ exe ปัจจุบัน — ตรวจขนาด + sha256 ครบแล้วค่อยเปลี่ยนเป็น .new
#      (ชื่อ asset บน GitHub ต้องเป็น ASCII เพราะ GitHub จะเปลี่ยนอักขระไทยในชื่อไฟล์)
#   3. "rename dance": ย้าย exe ที่กำลังรันไปเป็น .old-<pid>-<เวลา> (Windows อนุญาตให้
#      rename exe ที่กำลังรัน แต่ลบไม่ได้) แล้วย้าย .new มาใช้ชื่อเดิม → ชื่อไทยคงเดิม
#      ทุกขั้นมี retry (กัน antivirus/OneDrive ล็อกไฟล์ชั่วคราว) และ rollback ถ้าล้มเหลว
#   4. เปิด exe ตัวใหม่ (ล้างตัวแปร env ภายในของ PyInstaller ก่อน — กันชี้ไป temp เก่า)
#      รอดูว่าเปิดติดจริง แล้วค่อยปิดตัวเอง — โปรแกรมเปิดครั้งถัดไปลบ .old ทิ้งให้เอง
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time

import requests

APP_VERSION = "3.2.2"
GITHUB_REPO = "benzodol789-png/golden-bell-client"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "golden-bell-updater"}


class UpdateError(Exception):
    # ข้อความใน exception นี้แสดงให้ผู้ใช้เห็นตรงๆ — เขียนเป็นภาษาคน ไม่ใช่ technical dump
    pass


def parse_version(text):
    # "v3.1.0" / "3.1.0" → (3, 1, 0) — ส่วนที่ไม่ใช่ตัวเลขตัดทิ้ง กัน tag รูปแบบแปลกๆ
    parts = []
    for p in str(text).lstrip("vV").split("."):
        num = ""
        for ch in p:  # เอาเฉพาะเลขนำหน้า — "0-beta2" ต้องได้ 0 ไม่ใช่ 02
            if not ch.isdigit():
                break
            num += ch
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def current_exe():
    # path จริงของ exe ตัวเอง — None ถ้ารันจาก source (โหมด dev อัพเดทตัวเองไม่ได้)
    # ห้ามใช้ __file__ (ใน onefile จะชี้เข้าโฟลเดอร์ temp _MEIxxxx) และห้ามพึ่ง cwd
    return sys.executable if getattr(sys, "frozen", False) else None


def _retry(fn, *args, tries=10, delay=0.25):
    # antivirus/OneDrive เปิดไฟล์แว้บๆ ทำให้ rename/ลบ ล้มแบบสุ่ม — ลองซ้ำแบบถอยหลังทีละนิด
    for i in range(tries):
        try:
            return fn(*args)
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(delay * (i + 1))


def cleanup_old():
    # ลบไฟล์ .old*/.new*/.part* ที่ค้างจากการอัพเดทรอบก่อน — ลบไม่ได้ก็ข้าม (ค่อยลบรอบหน้า)
    exe = current_exe()
    if not exe:
        return
    folder, name = os.path.dirname(exe), os.path.basename(exe)
    try:
        entries = os.listdir(folder)
    except OSError:
        return
    for fn in entries:
        if fn.startswith(name + ".old") or fn.startswith(name + ".new") or fn.startswith(name + ".part"):
            try:
                os.remove(os.path.join(folder, fn))
            except OSError:
                pass


def _preflight(exe):
    # 1) รันจากใน .zip โดยไม่แตกไฟล์ → exe ถูก extract ไป temp อัพเดทแล้วหายเปล่า
    tmp = tempfile.gettempdir().lower()
    if os.path.dirname(exe).lower().startswith(tmp):
        raise UpdateError("โปรแกรมกำลังรันจากในไฟล์ .zip โดยตรง\n"
                          "กรุณาแตกไฟล์ .zip ออกมาก่อน (คลิกขวา → Extract All) แล้วค่อยอัพเดท")
    # 2) ตรวจสิทธิ์เขียนด้วยการเขียนจริง — os.access เชื่อถือไม่ได้บน Windows ACL
    probe = os.path.join(os.path.dirname(exe), f".wtest-{os.getpid()}")
    try:
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
    except OSError:
        raise UpdateError("เขียนไฟล์ในโฟลเดอร์โปรแกรมไม่ได้\n"
                          "ถ้าโปรแกรมอยู่ใน Program Files ให้ย้ายไปโฟลเดอร์ปกติ (เช่น Desktop)\n"
                          "หรือถ้าเปิด Controlled Folder Access ใน Windows Security\n"
                          "ให้เพิ่มโปรแกรมนี้ในรายการที่อนุญาต")


def check_latest(timeout=15):
    r = requests.get(API_LATEST, timeout=timeout, headers=_HEADERS)
    if r.status_code in (403, 429):
        raise UpdateError("เช็คอัพเดทถี่เกินไป (GitHub จำกัดจำนวนครั้ง) — รอสักพักแล้วลองใหม่")
    r.raise_for_status()
    data = r.json()
    assets = {}
    for a in data.get("assets", []):
        digest = a.get("digest") or ""  # GitHub ให้ sha256 มาในรูป "sha256:<hex>"
        assets[a["name"]] = {"url": a["browser_download_url"], "size": a.get("size") or 0,
                             "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    return {
        "tag": data.get("tag_name", ""),
        "version": parse_version(data.get("tag_name", "")),
        "assets": assets,
        "notes": (data.get("body") or "").strip(),
    }


def download(asset, dest, progress_cb=None, timeout=30):
    # ดาวน์โหลดลง .part (ชื่อไม่ซ้ำกันต่อโปรเซส — กันสอง instance เขียนชนกัน)
    # ครบตามขนาด + sha256 ตรง แล้วค่อยย้ายไป dest — กันติดตั้งไฟล์ครึ่งเดียว/ถูก AV กัก
    part = dest + f".part-{os.getpid()}"
    try:
        with requests.get(asset["url"], stream=True, timeout=timeout, headers=_HEADERS) as r:
            r.raise_for_status()
            total = asset["size"] or int(r.headers.get("Content-Length") or 0)
            done = 0
            sha = hashlib.sha256()
            with open(part, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(done, total)
        if not os.path.exists(part):
            raise UpdateError("ไฟล์อัพเดทหายระหว่างดาวน์โหลด (อาจถูก antivirus กักไว้)\n"
                              "เพิ่มข้อยกเว้นให้โฟลเดอร์นี้ใน Windows Security แล้วลองใหม่")
        if total and os.path.getsize(part) != total:
            raise UpdateError(f"ดาวน์โหลดไม่ครบ ({os.path.getsize(part)}/{total} bytes) — ลองใหม่อีกครั้ง")
        if asset["sha256"] and sha.hexdigest() != asset["sha256"]:
            raise UpdateError("ไฟล์ที่ดาวน์โหลดมาไม่ถูกต้อง (checksum ไม่ตรง) — ลองใหม่อีกครั้ง")
        if os.path.exists(dest):
            _retry(os.remove, dest)
        _retry(os.replace, part, dest)
    except BaseException:
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass
        raise


def apply_and_restart(new_path):
    # rename dance — .old ชื่อไม่ซ้ำ (Windows rename ทับไฟล์เดิมไม่ได้ และ .old เก่าอาจยังถูกล็อก)
    exe = current_exe()
    old = exe + f".old-{os.getpid()}-{int(time.time())}"
    _retry(os.rename, exe, old)
    try:
        _retry(os.rename, new_path, exe)
    except OSError:
        _retry(os.rename, old, exe)  # ย้อนกลับ — โปรแกรมเดิมต้องยังเปิดได้เสมอ
        raise
    # ล้างตัวแปรภายในของ PyInstaller — กัน exe ใหม่ไปใช้โฟลเดอร์ temp ของตัวเก่าที่กำลังถูกลบ
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for k in [k for k in env if k.startswith("_PYI_") or k == "_MEIPASS2"]:
        del env[k]
    p = subprocess.Popen([exe], cwd=os.path.dirname(exe) or None, env=env, close_fds=True)
    time.sleep(1.5)  # รอดูว่า bootloader ของตัวใหม่ไม่ตายทันที
    if p.poll() is not None:
        _retry(os.rename, exe, new_path)  # ตัวใหม่เปิดไม่ติด — สลับตัวเดิมกลับมา
        _retry(os.rename, old, exe)
        raise UpdateError("เวอร์ชันใหม่เปิดไม่ติด — ระบบสลับกลับเป็นเวอร์ชันเดิมให้แล้ว\n"
                          "(อาจถูก antivirus บล็อก — แจ้งผู้ดูแลระบบ)")
    os._exit(0)


def start_update_flow(root, asset_name, status_cb, ask_confirm, show_error, show_info, on_finish=None):
    """เช็ค + ดาวน์โหลด + ติดตั้ง ใน background thread (UI ไม่ค้าง)

    root         : Tk root (callback ทุกตัวถูกเรียกผ่าน root.after — อยู่ใน UI thread เสมอ)
    asset_name   : ชื่อไฟล์ ASCII ใน GitHub Release เช่น "golden-bell-admin.exe"
    status_cb(txt), ask_confirm(title, msg) -> bool, show_error(title, msg), show_info(title, msg)
    on_finish()  : เรียกเมื่อ flow จบโดยไม่ได้รีสตาร์ท (เอาไว้ปลดล็อกปุ่ม)
    """
    def ui(fn, *args):
        root.after(0, fn, *args)

    def fail(title, msg):
        ui(show_error, title, msg)
        ui(status_cb, "")
        if on_finish:
            ui(on_finish)

    def work():
        exe = current_exe()
        if not exe:
            ui(show_info, "โหมดนักพัฒนา", "รันจาก source โดยตรง — อัพเดทได้เฉพาะตัว .exe")
            ui(status_cb, "")
            if on_finish:
                ui(on_finish)
            return
        try:
            ui(status_cb, "🔍 กำลังเช็คเวอร์ชันล่าสุด...")
            info = check_latest()
        except UpdateError as e:
            fail("เช็คอัพเดทไม่สำเร็จ", str(e))
            return
        except Exception:
            fail("เช็คอัพเดทไม่สำเร็จ", "เชื่อมต่อ GitHub ไม่ได้ — ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่")
            return
        if info["version"] <= parse_version(APP_VERSION):
            ui(show_info, "เป็นเวอร์ชันล่าสุดแล้ว", f"โปรแกรมเป็นเวอร์ชันล่าสุดอยู่แล้ว (v{APP_VERSION})")
            ui(status_cb, "")
            if on_finish:
                ui(on_finish)
            return
        asset = info["assets"].get(asset_name)
        if not asset:
            fail("ไม่พบไฟล์อัพเดท", f"เวอร์ชัน {info['tag']} ไม่มีไฟล์ {asset_name} — แจ้งผู้ดูแลระบบ")
            return
        try:
            _preflight(exe)
        except UpdateError as e:
            fail("อัพเดทไม่ได้", str(e))
            return

        # ถามยืนยันใน UI thread แล้วรอคำตอบ
        answer = {}
        ev = threading.Event()

        def ask():
            msg = f"มีเวอร์ชันใหม่ {info['tag']} (ปัจจุบัน v{APP_VERSION})\n"
            if info["notes"]:
                msg += f"\nมีอะไรใหม่:\n{info['notes'][:500]}\n"
            msg += "\nดาวน์โหลดและอัพเดทเลยไหม? (โปรแกรมจะรีสตาร์ทเอง)"
            answer["yes"] = ask_confirm("พบเวอร์ชันใหม่", msg)
            ev.set()

        root.after(0, ask)
        ev.wait()
        if not answer.get("yes"):
            ui(status_cb, "")
            if on_finish:
                ui(on_finish)
            return

        new_path = exe + f".new-{os.getpid()}"
        try:
            def prog(done, total):
                ui(status_cb, f"⬇️ กำลังดาวน์โหลดเวอร์ชันใหม่... {done * 100 // total}% "
                              f"({done // 1048576}/{total // 1048576} MB)")
            ui(status_cb, "⬇️ กำลังดาวน์โหลดเวอร์ชันใหม่...")
            download(asset, new_path, prog)
        except UpdateError as e:
            fail("ดาวน์โหลดไม่สำเร็จ", str(e))
            return
        except PermissionError:
            fail("อัพเดทไม่สำเร็จ", "เขียนไฟล์ในโฟลเดอร์นี้ไม่ได้ — ย้ายโปรแกรมไปโฟลเดอร์ปกติ "
                                    "(เช่น Desktop) แล้วลองใหม่")
            return
        except Exception as e:
            fail("ดาวน์โหลดไม่สำเร็จ", f"ดาวน์โหลดไฟล์อัพเดทไม่สำเร็จ:\n{e}\n\nลองใหม่อีกครั้ง")
            return

        def swap():
            # rename + restart ใน UI thread — งานสั้น และปิดโปรแกรมได้สะอาด
            try:
                status_cb("🔄 กำลังติดตั้งและรีสตาร์ท...")
                root.update_idletasks()
                apply_and_restart(new_path)  # สำเร็จ = ไม่ return (โปรเซสนี้จบ)
            except UpdateError as e:
                show_error("ติดตั้งไม่สำเร็จ", str(e))
            except Exception as e:
                show_error("ติดตั้งไม่สำเร็จ",
                           f"สลับไฟล์เวอร์ชันใหม่ไม่สำเร็จ (โปรแกรมเดิมยังใช้ได้ปกติ):\n{e}")
            status_cb("")
            if on_finish:
                on_finish()

        root.after(0, swap)

    threading.Thread(target=work, daemon=True).start()


def auto_update(root, asset_name, status_cb, delay_ms=2000):
    """อัพเดทอัตโนมัติตอนเปิดโปรแกรม — ไม่มีป๊อปอัพ ไม่ต้องกดอะไรเลย

    หลักคิด: การอัพเดทอัตโนมัติต้องไม่ขวางการทำงาน ถ้าติดขัดตรงไหน
    (เน็ตไม่มี / GitHub ล่ม / เขียนไฟล์ไม่ได้ / ดาวน์โหลดพัง) ให้เงียบแล้วใช้
    เวอร์ชันเดิมต่อไป ผู้ใช้ยังกดปุ่มอัพเดทเองได้ถ้าอยากรู้สาเหตุ
    """
    def work():
        exe = current_exe()
        if not exe:
            return  # โหมด dev
        try:
            info = check_latest(timeout=10)
            if info["version"] <= parse_version(APP_VERSION):
                return
            asset = info["assets"].get(asset_name)
            if not asset:
                return
            _preflight(exe)
        except Exception:
            return  # เช็คไม่ได้ก็ไม่เป็นไร — ไม่รบกวนผู้ใช้

        new_path = exe + f".new-{os.getpid()}"
        try:
            root.after(0, status_cb, f"⬇️ กำลังอัพเดทเป็น {info['tag']} อัตโนมัติ...")
            download(asset, new_path,
                     lambda d, t: root.after(0, status_cb,
                                             f"⬇️ อัพเดทอัตโนมัติ {d * 100 // t}%"))
        except Exception:
            root.after(0, status_cb, "")
            return

        def swap():
            try:
                status_cb(f"🔄 อัพเดทเป็น {info['tag']} สำเร็จ — กำลังเปิดใหม่...")
                root.update_idletasks()
                apply_and_restart(new_path)  # สำเร็จ = โปรเซสนี้จบ
            except Exception:
                status_cb("")
                try:
                    os.remove(new_path)
                except OSError:
                    pass

        root.after(0, swap)

    # หน่วงไว้ก่อน ให้หน้าต่างขึ้นและต่อเซิร์ฟเวอร์ก่อน แล้วค่อยเช็คเบื้องหลัง
    root.after(delay_ms, lambda: threading.Thread(target=work, daemon=True).start())


def watch_for_updates(root, asset_name, status_cb, every_ms=4 * 3600 * 1000):
    """เครื่องที่เปิดโปรแกรมค้างทั้งวัน — คอยดูว่ามีเวอร์ชันใหม่ไหมเป็นระยะ
    เจอแล้วแค่บอกให้รู้ ไม่รีสตาร์ทกลางคัน (กันหลุดตอนกำลังเช็คชื่อ)"""
    def check():
        try:
            info = check_latest(timeout=10)
            if info["version"] > parse_version(APP_VERSION):
                root.after(0, status_cb,
                           f"✨ มีเวอร์ชันใหม่ {info['tag']} — ปิดแล้วเปิดโปรแกรมใหม่ "
                           f"เพื่ออัพเดทอัตโนมัติ (หรือกดปุ่มอัพเดท)")
        except Exception:
            pass
        root.after(every_ms, lambda: threading.Thread(target=check, daemon=True).start())

    root.after(every_ms, lambda: threading.Thread(target=check, daemon=True).start())
