# -*- coding: utf-8 -*-
# E2E ทดสอบโปรโตคอล ODOL v3: ประวัติ checker name + no_response
# v3.4.0: "ไม่ตอบ" = เรียกครบ call_timeout แล้วไม่กดยืนยันเท่านั้น
#   พนักงานหลุดระหว่างรอ → ยังไม่บันทึกไม่ตอบ, กลับเข้าห้องเดิมชื่อเดิม → เรียกต่อ (เวลานับจากครั้งแรก)
# ไฟล์นี้ไม่รอให้หมดเวลา — รันกับเซิร์ฟเวอร์ที่ตั้ง CALL_TIMEOUT เท่าไหร่ก็ได้
# (การทดสอบที่ต้องรอหมดเวลาอยู่ใน tests/e2e_calls.py)
import os
import sys
import time

import socketio

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL = os.environ.get("ODOL_URL", "http://127.0.0.1:5000")
ROOM = "ทีมทดสอบ"
NAME = "สมชาย ใจดี"
print("target:", URL)
results = []


def report(name, ok, detail=""):
    # ok=None = ข้าม (เงื่อนไขของเซิร์ฟเวอร์ไม่เอื้อให้ตรวจข้อนี้)
    tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    if ok is not None:
        results.append(bool(ok))
    print(f"[{tag}] {name}" + (f"  ({detail})" if detail else ""))


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
    c = socketio.Client(reconnection=False)
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


def member_row(admin):
    for m in (admin.data["room_state"] or {}).get("members") or []:
        if m.get("name") == NAME:
            return m
    return None


def my_records(admin, since):
    # ประวัติของการทดสอบรอบนี้เท่านั้น (ไม่ปนกับที่รันไว้ก่อน)
    admin.data["history"] = None
    admin.emit("get_history")
    wait_for(lambda: admin.data["history"] is not None)
    records = (admin.data["history"] or {}).get("records", [])
    return [r for r in records if r.get("room") == ROOM and r.get("name") == NAME
            and (r.get("called_ts") or 0) >= since - 1]


T_START = time.time()
admin1 = make_client()
admin2 = make_client()
emp1 = make_client()

# 1) สร้างห้องและเข้าห้อง (ห้องค้างจากรอบก่อน → เข้าห้องเดิมแทน)
admin1.emit("create_room", ROOM)
j = wait_for(lambda: admin1.data["joined"], 2)
if not j:
    admin1.emit("join_room_admin", ROOM)
    j = wait_for(lambda: admin1.data["joined"])
report("admin1 สร้างห้อง", bool(j) and j["room"] == ROOM)

# 2) emp1 เข้าห้อง
emp1.emit("join_room_member", {"room": ROOM, "name": NAME})
wait_for(lambda: emp1.data["joined"])
report("emp1 เข้าห้อง", emp1.data["joined"] and emp1.data["joined"]["room"] == ROOM)

# 3) admin1 กดเรียก 1 (ส่ง data dict พร้อม checker_name)
target_sid = wait_for(lambda: member_row(admin1))["sid"]
t_call = time.time()
admin1.emit("check_member", {"target_sid": target_sid, "checker_name": "แอดมิน1"})
got = wait_for(lambda: emp1.data["check_requests"] >= 1)
report("admin1 เรียก 1 ครั้ง", bool(got))
timeout = (admin1.data["room_state"] or {}).get("call_timeout") or 600
print(f"call_timeout ของเซิร์ฟเวอร์ = {timeout} วินาที")

# 4) emp1 หลุดการเชื่อมต่อตอนเป็น pending (รอสักครู่ก่อน — เวลาที่ใช้ตอนยืนยันจะได้ต่างจากตอนกลับเข้าห้องชัดๆ)
if timeout >= 3:
    time.sleep(0.8)
emp1.disconnect()
gone = wait_for(lambda: member_row(admin1) is None)
report("emp1  disconnect", not emp1.connected and bool(gone))

# 5) v3.4.0: หลุดระหว่างรอยังไม่นับว่า "ไม่ตอบ" — ต้องยังไม่มีแถวประวัติของการเรียกนี้
records = my_records(admin1, T_START)
if time.time() - t_call < timeout - 0.5:
    report("หลุดระหว่างรอ → ยังไม่บันทึก no_response ทันที (รอให้ครบเวลาก่อน)",
           not records, f"records={[r.get('result') for r in records]}")
else:
    report("หลุดระหว่างรอ → ยังไม่บันทึก no_response ทันที", None,
           f"call_timeout={timeout}s สั้นกว่าเวลาที่ใช้ตรวจ")

# 6) emp1 เข้าห้องเดิมด้วยชื่อเดิม (client ตัวใหม่ — ตัวนับเริ่มจาก 0)
#    ยังไม่ครบเวลา → เซิร์ฟเวอร์เรียกต่อเอง (ส่ง check_request) โดยแอดมินไม่ต้องกดใหม่
emp1 = make_client()
restored_expected = time.time() - t_call < timeout - 1.0
emp1.emit("join_room_member", {"room": ROOM, "name": NAME})
wait_for(lambda: emp1.data["joined"])
if restored_expected:
    got = wait_for(lambda: emp1.data["check_requests"] >= 1, 3)
    row = wait_for(lambda: (member_row(admin1) or {}).get("status") == "pending" and member_row(admin1))
    report("เข้าห้องเดิมชื่อเดิม → เรียกต่อจากเดิม (ได้ check_request, pending)",
           bool(got) and bool(row) and isinstance(row.get("left"), int) and row["left"] < timeout,
           f"row={row or member_row(admin1)}")
else:
    # call_timeout สั้นมาก การเรียกเดิมอาจหมดเวลาไปแล้ว — เรียกใหม่แบบโปรแกรมแอดมินรุ่นเก่า (ส่ง sid เป็น string)
    report("เข้าห้องเดิมชื่อเดิม → เรียกต่อจากเดิม", None, f"call_timeout={timeout}s สั้นเกินไป")
    wait_for(lambda: emp1.data["check_requests"] >= 1, 1.5)
    if emp1.data["check_requests"] < 1:
        admin1.emit("check_member", wait_for(lambda: member_row(admin1))["sid"])
        wait_for(lambda: emp1.data["check_requests"] >= 1)
    report("admin1 เรียกครั้งที่ 2", emp1.data["check_requests"] >= 1)

# 7) emp1 ยืนยัน
t_confirm = time.time()
try:
    ack = emp1.call("confirm_checkin", timeout=5)
except Exception:
    ack = None
checked = wait_for(lambda: (member_row(admin1) or {}).get("status") == "checked")
report("emp1 ยืนยัน", checked and isinstance(ack, dict) and ack.get("ok"), f"ack={ack}")

# 8) ประวัติ: การเรียกที่หลุดแล้วกลับมายืนยัน = แถวเดียว "checked" ชื่อผู้เรียกตัวจริง ไม่มี "ไม่ตอบ" แทรก
records = my_records(admin1, T_START)
if restored_expected:
    ok = (len(records) == 1 and records[0].get("result") == "checked"
          and records[0].get("checker") == "แอดมิน1"
          # เวลาที่ใช้ต้องนับจากตอนแอดมินเรียกครั้งแรก ไม่ใช่ตอนกลับเข้าห้อง
          and float(records[0].get("elapsed") or 0) >= (t_confirm - t_call) - 0.3)
    report("ประวัติบันทึก checked 1 แถว พร้อมชื่อผู้เรียกตัวจริง (ไม่มี no_response ปลอม)", ok,
           f"records={[(r.get('result'), r.get('checker'), r.get('elapsed')) for r in records]} "
           f"call→confirm={t_confirm - t_call:.1f}s")
else:
    report("ประวัติบันทึก checked พร้อมชื่อผู้เรียก",
           any(r.get("result") == "checked" and r.get("checker") for r in records),
           f"records={[(r.get('result'), r.get('checker')) for r in records]}")

# 9) โปรแกรมแอดมินรุ่นเก่าส่ง target_sid เป็น string (ไม่มีชื่อผู้เรียก) → ต้องเรียกได้ และเดาชื่อผู้เรียกให้
n_before = len(records)
n_req = emp1.data["check_requests"]
admin1.emit("check_member", member_row(admin1)["sid"])
wait_for(lambda: emp1.data["check_requests"] > n_req)
report("admin1 เรียกแบบรุ่นเก่า (string sid)", emp1.data["check_requests"] > n_req)
try:
    ack = emp1.call("confirm_checkin", timeout=5)
except Exception:
    ack = None
wait_for(lambda: (member_row(admin1) or {}).get("status") == "checked")
records = my_records(admin1, T_START)
has_checked_with_checker = all(r.get("result") == "checked" and r.get("checker") for r in records)
report("ประวัติบันทึก checked พร้อม checker name",
       isinstance(ack, dict) and ack.get("ok") and has_checked_with_checker
       and len(records) == n_before + 1 and len(records) >= 2,
       f"records={len(records)} {[(r.get('result'), r.get('checker')) for r in records]}")

# 10) เก็บงาน — ลบห้องทดสอบ
admin1.emit("delete_room", ROOM)
wait_for(lambda: admin1.data["left"] >= 1)
admin1.disconnect()
admin2.disconnect()
if emp1.connected:
    emp1.disconnect()

ok = all(results)
print("E2E_V3_RESULT:", "PASS" if ok else "FAIL", f"({sum(results)}/{len(results)})")
sys.exit(0 if ok else 1)
