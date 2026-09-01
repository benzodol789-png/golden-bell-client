# -*- coding: utf-8 -*-
# E2E ทดสอบโปรโตคอล ODOL v3: ประวัติ checker name + no_response
import os
import sys
import time

import socketio

URL = os.environ.get("ODOL_URL", "http://127.0.0.1:5000")
print("target:", URL)
results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def wait_for(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.05)
    return None


def make_client():
    c = socketio.Client()
    c.data = {"rooms": None, "room_state": None, "joined": None, "left": 0,
              "check_requests": 0, "errors": [], "history": None}

    @c.on("history_data")
    def _h(d):
        c.data["history"] = d

    @c.on("rooms_updated")
    def _r(d):
        c.data["rooms"] = d

    @c.on("room_state")
    def _s(d):
        c.data["room_state"] = d

    @c.on("joined_room")
    def _j(d):
        c.data["joined"] = d

    @c.on("left_room")
    def _l(d):
        c.data["left"] += 1

    @c.on("check_request")
    def _c(d):
        c.data["check_requests"] += 1

    @c.on("error_msg")
    def _e(d):
        c.data["errors"].append(d.get("msg", ""))

    c.connect(URL, auth={"code": "ODOL-2569"}, wait_timeout=10)
    return c


admin1 = make_client()
admin2 = make_client()
emp1 = make_client()

# 1) สร้างห้องและเข้าห้อง
admin1.emit("create_room", "ทีมทดสอบ")
j = wait_for(lambda: admin1.data["joined"])
report("admin1 สร้างห้อง", bool(j) and j["room"] == "ทีมทดสอบ")

# 2) emp1 เข้าห้อง
emp1.emit("join_room_member", {"room": "ทีมทดสอบ", "name": "สมชาย ใจดี"})
wait_for(lambda: emp1.data["joined"])
report("emp1 เข้าห้อง", emp1.data["joined"] and emp1.data["joined"]["room"] == "ทีมทดสอบ")

# 3) admin1 กดเรียก 1 (ส่ง data dict พร้อม checker_name)
target_sid = admin1.data["room_state"]["members"][0]["sid"]
admin1.emit("check_member", {"target_sid": target_sid, "checker_name": "แอดมิน1"})
got = wait_for(lambda: emp1.data["check_requests"] >= 1)
report("admin1 เรียก 1 ครั้ง", bool(got))

# 4) emp1 หลุดการเชื่อมต่อตอนเป็น pending — ต้องบันทึกเป็น "no_response"
emp1.disconnect()
time.sleep(0.5)
report("emp1  disconnect", not emp1.connected)

# 5) ดึงประวัติ — ต้องเห็นการเรียกครั้งที่ 1 ว่า "no_response"
admin1.data["history"] = None
admin1.emit("get_history")
hist = wait_for(lambda: admin1.data["history"] is not None)
records = (admin1.data["history"] or {}).get("records", [])
# ✅ ต้องบันทึกชื่อผู้เรียกตัวจริง ("แอดมิน1" จากขั้นที่ 3) ไม่ใช่ค่า default
has_no_response = any(r.get("result") == "no_response" and r.get("name") == "สมชาย ใจดี"
                      and r.get("checker") == "แอดมิน1" for r in records)
report("ประวัติบันทึก no_response พร้อมชื่อผู้เรียกตัวจริง เมื่อ emp1 disconnect ขณะ pending",
       bool(hist) and has_no_response, f"records={len(records)}")

# 6) emp1 เข้าใหม่ แล้ว admin1 เรียกอีกครั้ง
# ⚠️ emp1 เป็น client ตัวใหม่ — ตัวนับ check_requests เริ่มนับจาก 0 ใหม่ จึงรอแค่ >= 1
emp1 = make_client()
emp1.emit("join_room_member", {"room": "ทีมทดสอบ", "name": "สมชาย ใจดี"})
wait_for(lambda: emp1.data["joined"])
target_sid = admin1.data["room_state"]["members"][0]["sid"]
admin1.emit("check_member", target_sid)
wait_for(lambda: emp1.data["check_requests"] >= 1)
report("admin1 เรียกครั้งที่ 2", emp1.data["check_requests"] >= 1)

# 7) emp1 ยืนยัน
try:
    ack = emp1.call("confirm_checkin", timeout=5)
except Exception:
    ack = None
checked = wait_for(lambda: admin1.data["room_state"]["members"][0]["status"] == "checked")
report("emp1 ยืนยันครั้งที่ 2", checked and isinstance(ack, dict) and ack.get("ok"))

# 8) ดึงประวัติใหม่ — ต้องเห็นครั้งที่ 2 ว่า "checked" พร้อม checker name
admin1.data["history"] = None
admin1.emit("get_history")
hist = wait_for(lambda: admin1.data["history"] is not None)
records = (admin1.data["history"] or {}).get("records", [])
# ต้องมีรายการ "checked" ที่เป็นครั้งที่ 2 พร้อม checker name
has_checked_with_checker = any(
    r.get("result") == "checked" and r.get("name") == "สมชาย ใจดี" and r.get("checker")
    for r in records
)
report("ประวัติบันทึก checked พร้อม checker name", has_checked_with_checker and len(records) >= 2,
       f"records={len(records)}")

admin1.disconnect()
admin2.disconnect()
if emp1.connected:
    emp1.disconnect()

ok = all(results)
print("E2E_V3_RESULT:", "PASS" if ok else "FAIL", f"({sum(results)}/{len(results)})")
sys.exit(0 if ok else 1)
