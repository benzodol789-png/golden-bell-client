# -*- coding: utf-8 -*-
# E2E ทดสอบโปรโตคอลการเรียกเช็คชื่อ (v3.4.0)
#   • "ไม่ตอบ" = เรียกครบ call_timeout แล้วไม่กดยืนยันเท่านั้น (กดเรียกซ้ำ / หลุดเน็ต ไม่นับทันที)
#   • แอดมินยกเลิกการเรียกได้ (cancel_check) — ไม่นับว่าไม่ตอบ สถานะกลับเหมือนก่อนเรียก
#
# รันกับเซิร์ฟเวอร์ทดสอบที่ตั้งเวลาสั้นๆ:
#   (ที่ golden-bell-server)  CALL_TIMEOUT=4 STATUS_API_URL= PORT=5061 py -3 app.py
#   (ที่ golden-bell-client)  ODOL_URL=http://127.0.0.1:5061 py -3 tests/e2e_calls.py
# ถ้า call_timeout ของเซิร์ฟเวอร์ยาวเกิน 30 วินาที (เช่น เซิร์ฟเวอร์จริง 10 นาที)
# ส่วนที่ต้องรอให้หมดเวลาจะถูกข้าม (SKIP) — รันกับเซิร์ฟเวอร์จริงได้ ห้องทดสอบถูกลบทิ้งตอนจบ
import os
import re
import sys
import time
import traceback
import uuid
from collections import Counter

import socketio

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL = os.environ.get("ODOL_URL", "http://127.0.0.1:5000")
AUTH = {"code": "ODOL-2569"}
MAX_EXPIRY_WAIT = 30  # call_timeout ยาวกว่านี้ = ไม่รอให้หมดเวลา (ข้ามส่วนนั้น)
RUN = uuid.uuid4().hex[:4]  # ต่อท้ายชื่อห้อง — ประวัติจากการรันครั้งก่อนจะได้ไม่ปนกัน
ROOM = f"ทีมทดสอบ-เรียก-{RUN}"
ROOM_OTHER = f"ทีมทดสอบ-เรียก-{RUN}-อื่น"
ROOM_DEL = f"ทีมทดสอบ-เรียก-{RUN}-ลบ"
ADMIN = "แอดมินทดสอบ"
ADMIN_DEL = "แอดมินห้องลบ"
NEW_VERSION = "3.4.0"  # พนักงานในการทดสอบเป็นโปรแกรมรุ่นใหม่ (ยกเว้นข้อที่ทดสอบรุ่นเก่าโดยเฉพาะ)

N_CANCEL = "ทดสอบ ยกเลิก"          # a b c d g j
N_BACK = "ทดสอบ หลุดแล้วกลับ"      # h
N_EXPIRE = "ทดสอบ ไม่ตอบ"          # e f l
N_GONE = "ทดสอบ หลุดไม่กลับ"       # i
N_DOUBLE = "ทดสอบ ดับเบิลคลิก"     # l m
N_DEL = "ทดสอบ ลบห้อง"             # k
N_DEL_GONE = "ทดสอบ ลบห้องตอนหลุด"  # k
N_SWITCH = "ทดสอบ ย้ายห้อง"         # h2
N_PROBE = "ทดสอบ จับจังหวะ"         # n — หาจังหวะรอบตรวจของเซิร์ฟเวอร์
N_RACE_CONFIRM = "ทดสอบ ยืนยันตอนครบ"  # n
N_RACE_CANCEL = "ทดสอบ ยกเลิกตอนครบ"   # n
N_RACE_RECALL = "ทดสอบ เรียกซ้ำตอนครบ"  # n
N_RACE_REJOIN = "ทดสอบ กลับเข้าตอนครบ"  # n

print("target:", URL, "| room:", ROOM, flush=True)
results = []
made = []
sid_info = {}      # sid -> (room, name)
calls = Counter()  # (room, name) -> จำนวนการเรียกใหม่ (ไม่นับการกดซ้ำ) — ต้องเท่ากับจำนวนแถวประวัติ


def report(name, ok, detail=""):
    tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    results.append(tag)
    print(f"[{tag}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def wait_for(fn, timeout=5.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


def make_client(label, identity=None):
    # identity = ข้อมูลที่ส่งผ่าน set_identity (มี "version" = โปรแกรมรุ่นใหม่ / ไม่ส่ง = รุ่นเก่า 3.3.x)
    c = socketio.Client(reconnection=False)
    c.label = label
    c.data = {"room_state": None, "rs_n": 0, "joined": None, "left": 0, "check_requests": [],
              "closed": [], "errors": [], "history": None, "rooms": None, "events": []}

    def stamp(ev):
        c.data["events"].append((time.time(), ev))

    @c.on("room_state")
    def _s(d):
        c.data["room_state"] = d
        c.data["rs_n"] += 1

    @c.on("rooms_updated")
    def _r(d):
        c.data["rooms"] = d

    @c.on("joined_room")
    def _j(d):
        stamp("joined_room")
        c.data["joined"] = d

    @c.on("left_room")
    def _l(d=None):
        stamp("left_room")
        c.data["left"] += 1

    @c.on("check_request")
    def _c(d=None):
        stamp("check_request")
        c.data["check_requests"].append(time.time())

    @c.on("check_closed")
    def _x(d=None):
        stamp("check_closed")
        c.data["closed"].append((time.time(), d if isinstance(d, dict) else {}))

    @c.on("error_msg")
    def _e(d):
        c.data["errors"].append((d or {}).get("msg", ""))

    @c.on("history_data")
    def _h(d):
        c.data["history"] = d

    c.connect(URL, auth=AUTH, wait_timeout=10)
    if identity:
        c.emit("set_identity", identity)
    made.append(c)
    return c


def members(admin):
    return (admin.data["room_state"] or {}).get("members") or []


def row(admin, sid=None, name=None):
    for m in members(admin):
        if (sid and m.get("sid") == sid) or (name and m.get("name") == name):
            return m
    return None


def status_of(m):
    # เซิร์ฟเวอร์บางรุ่นส่ง "ไม่ตอบ" เป็น status "wait" + missed=True (ให้โปรแกรมแอดมินรุ่นเก่าไม่ขึ้นคำอังกฤษดิบ)
    if not m:
        return None
    if m.get("status") == "wait" and m.get("missed"):
        return "no_response"
    return m.get("status")


def wait_row(admin, sid=None, name=None, status=None, timeout=5.0):
    def f():
        m = row(admin, sid, name)
        if m and (status is None or status_of(m) == status):
            return m
        return None
    return wait_for(f, timeout)


def join_member(admin, name, room, version=NEW_VERSION):
    e = make_client(name, {"name": name, "version": version} if version else None)
    e.emit("join_room_member", {"room": room, "name": name, **({"version": version} if version else {})})
    wait_for(lambda: e.data["joined"])
    sid = e.get_sid()
    sid_info[sid] = (room, name)
    return e, sid, wait_row(admin, sid=sid)


def call(admin, sid, who=ADMIN, new=True):
    # new=False = กดซ้ำระหว่างที่การเรียกเดิมยังรออยู่ (ต้องไม่เกิดแถวประวัติใหม่)
    if new:
        calls[sid_info[sid]] += 1
    admin.emit("check_member", {"target_sid": sid, "checker_name": who})


def ack(client, event, data=None, timeout=5):
    try:
        if data is None:
            return client.call(event, timeout=timeout)
        return client.call(event, data, timeout=timeout)
    except Exception as e:  # ไม่มี ack กลับมา (เช่น เซิร์ฟเวอร์รุ่นเก่า)
        return {"_error": repr(e)}


def history(admin, opts="none"):
    # opts="none" = แบบโปรแกรมแอดมินรุ่นเก่า (emit("get_history") ไม่ส่งอะไรมา)
    admin.data["history"] = None
    if opts == "none":
        admin.emit("get_history")
    else:
        admin.emit("get_history", opts)
    got = wait_for(lambda: admin.data["history"], 5)
    return got.get("records") if isinstance(got, dict) else None


def rows_of(recs, room, name):
    return [r for r in (recs or []) if r.get("room") == room and r.get("name") == name]


def is_ok(res):
    return isinstance(res, dict) and res.get("ok") is True


def is_refused(res, needle=None):
    return (isinstance(res, dict) and res.get("ok") is False
            and (needle is None or needle in (res.get("msg") or "")))


def brief(rows):
    keys = ("result", "checker", "called", "confirmed", "elapsed", "cancelled_by", "note")
    return [{k: r.get(k) for k in keys if r.get(k) not in (None, "")} for r in rows or []]


# ========================================================================
def main():
    A = make_client("admin")
    A.emit("create_room", ROOM)
    j = wait_for(lambda: A.data["joined"])
    report("ตั้งค่า: แอดมินสร้างห้องทดสอบ", bool(j) and j.get("room") == ROOM and j.get("role") == "admin",
           f"errors={A.data['errors']}" if not j else "")
    rs = wait_for(lambda: A.data["room_state"] if (A.data["room_state"] or {}).get("room") == ROOM else None)
    T = (rs or {}).get("call_timeout")
    report("a. room_state มี call_timeout (วินาที)", isinstance(T, int) and T >= 1, f"call_timeout={T}")
    if not isinstance(T, int) or T < 1:
        print("หยุด: เซิร์ฟเวอร์ไม่ส่ง call_timeout มา — น่าจะยังเป็นรุ่นก่อน 3.4.0", flush=True)
        return
    can_expire = T <= MAX_EXPIRY_WAIT
    roomy = T >= 3  # เวลาพอให้ทำหลายขั้นก่อนการเรียกจะหมดเวลา
    why_expire = f"call_timeout={T}s > {MAX_EXPIRY_WAIT}s — ไม่รอให้หมดเวลา"
    why_roomy = f"call_timeout={T}s สั้นเกินไปสำหรับขั้นนี้ (ต้อง ≥ 3)"

    # ---------------- a/b/c/d: เรียก → กดซ้ำ → ยกเลิก → ยืนยันหลังยกเลิก ----------------
    E1, s1, m = join_member(A, N_CANCEL, ROOM)
    report("ตั้งค่า: พนักงานเข้าห้อง → wait, left=None",
           bool(m) and status_of(m) == "wait" and "left" in m and m["left"] is None, f"row={m}")
    if not roomy:
        for n in "abcdgj":
            report(f"{n}. (ข้าม)", None, why_roomy)
    else:
        call(A, s1)
        got = wait_for(lambda: E1.data["check_requests"])
        m = wait_row(A, sid=s1, status="pending")
        report("a. กดเรียก → พนักงานได้ check_request", bool(got))
        report("a. กดเรียก → pending, left ≈ call_timeout",
               bool(m) and isinstance(m.get("left"), int) and T - 1 <= m["left"] <= T,
               f"left={m and m.get('left')} timeout={T}")

        time.sleep(1.3)
        n_req, n_rs = len(E1.data["check_requests"]), A.data["rs_n"]
        call(A, s1, new=False)
        got = wait_for(lambda: len(E1.data["check_requests"]) > n_req)
        wait_for(lambda: A.data["rs_n"] > n_rs)
        time.sleep(0.2)
        m = row(A, sid=s1)
        report("b. กดซ้ำระหว่างรอ → พนักงานได้ check_request อีกรอบ", bool(got),
               f"check_request={len(E1.data['check_requests'])}")
        report("b. กดซ้ำ → ยัง pending และตัวนับไม่เริ่มใหม่ (left ≤ timeout-1)",
               bool(m) and status_of(m) == "pending" and isinstance(m.get("left"), int)
               and m["left"] <= T - 1, f"left={m and m.get('left')}")
        report("b. กดซ้ำ → พนักงานไม่ได้ check_closed", not E1.data["closed"], f"closed={E1.data['closed']}")
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_CANCEL)
        report("b. กดซ้ำ → ไม่มีแถวประวัติ (ไม่มี 'ไม่ตอบ' ปลอม)", recs is not None and not rr, f"rows={brief(rr)}")

        res = ack(A, "cancel_check", {"target_sid": s1, "checker_name": ADMIN})
        report("c. cancel_check → ack ok=True พร้อมชื่อพนักงาน",
               is_ok(res) and res.get("name") == N_CANCEL, f"ack={res}")
        cl = wait_for(lambda: E1.data["closed"])
        d = cl[-1][1] if cl else {}
        report("c. พนักงานได้ check_closed reason=cancelled by=ชื่อแอดมิน",
               d.get("reason") == "cancelled" and d.get("by") == ADMIN, f"payload={d}")
        m = wait_row(A, sid=s1, status="wait")
        report("c. สถานะกลับเป็น wait เหมือนก่อนเรียก (time/elapsed ว่าง, left=None)",
               bool(m) and m.get("time") == "" and m.get("elapsed") == "" and m.get("left") is None,
               f"row={m or row(A, sid=s1)}")
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_CANCEL)
        r0 = rr[0] if len(rr) == 1 else {}
        report("c. get_history({cancelled:True}) มีแถว cancelled 1 แถว + cancelled_by/cancelled_at",
               len(rr) == 1 and r0.get("result") == "cancelled" and r0.get("cancelled_by") == ADMIN
               and bool(r0.get("cancelled_at")) and r0.get("checker") == ADMIN
               and r0.get("confirmed") == "", f"rows={brief(rr)}")
        plain = history(A)
        report("c. get_history() แบบรุ่นเก่า (ไม่ส่ง opts) ไม่มีแถว cancelled",
               plain is not None and not any(r.get("result") == "cancelled" for r in plain),
               f"cancelled rows={sum(1 for r in plain or [] if r.get('result') == 'cancelled')}")
        falsy = history(A, {"cancelled": False})
        report("c. get_history({cancelled:False}) ไม่มีแถว cancelled",
               falsy is not None and not any(r.get("result") == "cancelled" for r in falsy))

        res = ack(E1, "confirm_checkin")
        report("d. พนักงานกดยืนยันหลังถูกยกเลิก → ok=False + บอกว่าแอดมินยกเลิก",
               is_refused(res, "ยกเลิก"), f"ack={res}")
        time.sleep(0.3)
        m = row(A, sid=s1)
        recs = history(A, {"cancelled": True})
        report("d. หลังยืนยันที่ถูกปฏิเสธ → ยัง wait และประวัติยัง 1 แถว",
               bool(m) and status_of(m) == "wait" and len(rows_of(recs, ROOM, N_CANCEL)) == 1,
               f"status={m and m.get('status')} rows={len(rows_of(recs, ROOM, N_CANCEL))}")

        # ---------------- g: เรียกคนที่เช็คแล้ว → ยกเลิก → กลับเป็น checked เวลาเดิม ----------------
        n_req = len(E1.data["check_requests"])
        call(A, s1)
        wait_for(lambda: len(E1.data["check_requests"]) > n_req)
        wait_row(A, sid=s1, status="pending")
        res = ack(E1, "confirm_checkin")
        m = wait_row(A, sid=s1, status="checked")
        report("g. ตั้งค่า: เรียกแล้วพนักงานยืนยัน → checked", is_ok(res) and bool(m), f"ack={res}")
        old_time, old_elapsed = (m or {}).get("time"), (m or {}).get("elapsed")
        time.sleep(1.1)  # ถ้าเซิร์ฟเวอร์ประทับเวลาใหม่ตอนยกเลิก จะเห็นว่าเวลาไม่ตรง
        n_closed = len(E1.data["closed"])
        call(A, s1)
        m = wait_row(A, sid=s1, status="pending")
        report("g. เรียกคนที่ checked แล้ว → pending (ระหว่างรอ time ว่าง)",
               bool(m) and m.get("time") == "", f"row={m}")
        res = ack(A, "cancel_check", {"target_sid": s1, "checker_name": ADMIN})
        m = wait_row(A, sid=s1, status="checked")
        report("g. ยกเลิก → กลับเป็น checked พร้อมเวลา/elapsed เดิม",
               is_ok(res) and bool(m) and m.get("time") == old_time and m.get("elapsed") == old_elapsed,
               f"ack={res} before={old_time}/{old_elapsed} after={m and (m.get('time'), m.get('elapsed'))}")
        got = wait_for(lambda: len(E1.data["closed"]) > n_closed)
        report("g. พนักงานได้ check_closed reason=cancelled",
               bool(got) and E1.data["closed"][-1][1].get("reason") == "cancelled")
        res = ack(E1, "confirm_checkin")
        time.sleep(0.2)
        m = row(A, sid=s1)
        report("g. กดยืนยันหลังยกเลิก → ok=False และสถานะ/เวลาเดิมไม่เปลี่ยน",
               is_refused(res, "ยกเลิก") and bool(m) and status_of(m) == "checked"
               and m.get("time") == old_time, f"ack={res} row={m}")

        # ---------------- j: คนที่ไม่มีสิทธิ์ยกเลิก / ยกเลิกคนที่ไม่ได้รอยืนยัน ----------------
        n_closed = len(E1.data["closed"])
        call(A, s1)
        wait_row(A, sid=s1, status="pending")
        res = ack(E1, "cancel_check", {"target_sid": s1, "checker_name": "ปลอม"})
        report("j. พนักงาน (ไม่ใช่แอดมิน) ส่ง cancel_check → ok=False", is_refused(res), f"ack={res}")
        O = make_client("outsider")
        res = ack(O, "cancel_check", {"target_sid": s1, "checker_name": "คนนอก"})
        report("j. เครื่องที่ไม่ได้อยู่ในห้องใด ส่ง cancel_check → ok=False", is_refused(res), f"ack={res}")
        B = make_client("admin-other")
        B.emit("create_room", ROOM_OTHER)
        wait_for(lambda: B.data["joined"])
        res = ack(B, "cancel_check", {"target_sid": s1, "checker_name": "แอดมินห้องอื่น"})
        report("j. แอดมินห้องอื่นยกเลิกคนในห้องนี้ → ok=False", is_refused(res), f"ack={res}")
        res = ack(A, "cancel_check")
        report("j. cancel_check ไม่ส่งข้อมูล → ok=False (ไม่พัง)", is_refused(res), f"ack={res}")
        res = ack(A, "cancel_check", {"target_sid": "no-such-sid", "checker_name": ADMIN})
        report("j. cancel_check sid ที่ไม่มีในห้อง → ok=False", is_refused(res), f"ack={res}")
        time.sleep(0.2)
        m = row(A, sid=s1)
        report("j. หลังคำขอที่ถูกปฏิเสธ → ยังรอยืนยันอยู่ ไม่มี check_closed",
               bool(m) and status_of(m) == "pending" and len(E1.data["closed"]) == n_closed,
               f"row={m}")
        res = ack(A, "cancel_check", {"target_sid": s1, "checker_name": ADMIN})
        m = wait_row(A, sid=s1, status="checked")
        report("j. แอดมินในห้องยกเลิกได้ → กลับเป็น checked", is_ok(res) and bool(m), f"ack={res}")
        res = ack(A, "cancel_check", {"target_sid": s1, "checker_name": ADMIN})
        report("j. ยกเลิกคนที่ไม่ได้รอยืนยัน (checked) → ok=False + บอกเหตุผล",
               is_refused(res, "ไม่ได้อยู่ระหว่างรอยืนยัน"), f"ack={res}")

    # ---------------- h: หลุดระหว่างรอ → กลับเข้าห้องเดิมชื่อเดิม → เรียกต่อ ----------------
    if not roomy:
        report("h. (ข้าม)", None, why_roomy)
    else:
        E3, s3, _ = join_member(A, N_BACK, ROOM)
        t_call3 = time.time()
        call(A, s3)
        wait_for(lambda: E3.data["check_requests"])
        wait_row(A, sid=s3, status="pending")
        time.sleep(1.0)
        E3.disconnect()
        gone = wait_for(lambda: row(A, name=N_BACK) is None)
        report("h. พนักงานหลุดระหว่างรอ → หายจากตารางแอดมิน", bool(gone))
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_BACK)
        report("h. หลุดระหว่างรอ → ยังไม่มีแถวประวัติ (ไม่นับไม่ตอบทันที)",
               recs is not None and not rr, f"rows={brief(rr)}")
        E3b = make_client(N_BACK + " (ต่อใหม่)")
        E3b.emit("join_room_member", {"room": ROOM, "name": N_BACK})
        wait_for(lambda: E3b.data["joined"])
        s3b = E3b.get_sid()
        sid_info[s3b] = (ROOM, N_BACK)
        got = wait_for(lambda: E3b.data["check_requests"], 3)
        report("h. เข้าห้องเดิมด้วยชื่อเดิม → ได้ check_request (เรียกต่อ)", bool(got))
        evs = [ev for _, ev in sorted(E3b.data["events"])]
        report("h. check_request มาหลัง joined_room (ป๊อปอัพไม่โดนปิดทิ้ง)",
               "joined_room" in evs and "check_request" in evs
               and evs.index("joined_room") < evs.index("check_request"), f"events={evs}")
        m = wait_row(A, sid=s3b, status="pending")
        report("h. กลับมาเป็น pending และนับเวลาต่อจากเดิม (left ≤ timeout-1)",
               bool(m) and isinstance(m.get("left"), int) and m["left"] <= T - 1,
               f"row={m or row(A, name=N_BACK)}")
        t_confirm = time.time()
        res = ack(E3b, "confirm_checkin")
        m = wait_row(A, sid=s3b, status="checked")
        expect = t_confirm - t_call3
        try:
            el = float((m or {}).get("elapsed"))
        except (TypeError, ValueError):
            el = -1.0
        report("h. ยืนยัน → checked, elapsed นับจากการเรียกครั้งแรก",
               is_ok(res) and bool(m) and abs(el - expect) <= 0.6,
               f"ack={res} elapsed={el} expected≈{expect:.1f}")
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_BACK)
        try:
            hel = float(rr[0].get("elapsed")) if len(rr) == 1 else -1.0
        except (TypeError, ValueError):
            hel = -1.0
        report("h. ประวัติมี 1 แถว checked ชื่อผู้เรียกเดิม elapsed นับจากครั้งแรก",
               len(rr) == 1 and rr[0].get("result") == "checked" and rr[0].get("checker") == ADMIN
               and abs(hel - expect) <= 0.6, f"rows={brief(rr)}")

    # ---------------- h2: ออกจากห้องระหว่างรอ → ไปห้องอื่น (ไม่เรียกต่อ) → กลับห้องเดิม (เรียกต่อ) ----------------
    if not roomy:
        report("h2. (ข้าม)", None, why_roomy)
    else:
        E9, s9, _ = join_member(A, N_SWITCH, ROOM)
        call(A, s9)
        wait_for(lambda: E9.data["check_requests"])
        wait_row(A, sid=s9, status="pending")
        E9.emit("leave_room")
        wait_for(lambda: E9.data["left"] >= 1)
        wait_for(lambda: row(A, name=N_SWITCH) is None)
        E9.data["joined"] = None
        n_req = len(E9.data["check_requests"])
        E9.emit("join_room_member", {"room": ROOM_OTHER, "name": N_SWITCH})
        wait_for(lambda: E9.data["joined"])
        time.sleep(0.5)
        recs = history(A, {"cancelled": True})
        report("h2. กดออกจากห้องระหว่างรอแล้วเข้าห้องอื่น → ห้องอื่นไม่เรียกต่อ และยังไม่มีแถวประวัติ",
               len(E9.data["check_requests"]) == n_req and not rows_of(recs, ROOM, N_SWITCH)
               and not rows_of(recs, ROOM_OTHER, N_SWITCH),
               f"check_request={len(E9.data['check_requests']) - n_req} rows={brief(rows_of(recs, ROOM, N_SWITCH))}")
        E9.data["joined"] = None
        E9.emit("join_room_member", {"room": ROOM, "name": N_SWITCH})
        wait_for(lambda: E9.data["joined"])
        got = wait_for(lambda: len(E9.data["check_requests"]) > n_req, 3)
        m = wait_row(A, sid=s9, status="pending")
        report("h2. กลับเข้าห้องเดิม (เครื่องเดิม) → เรียกต่อ pending เวลานับต่อ",
               bool(got) and bool(m) and isinstance(m.get("left"), int) and m["left"] <= T - 1,
               f"row={m or row(A, name=N_SWITCH)}")
        res = ack(A, "cancel_check", {"target_sid": s9, "checker_name": ADMIN})
        m = wait_row(A, sid=s9, status="wait")
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_SWITCH)
        report("h2. ยกเลิกการเรียกที่ต่อมา → wait และประวัติ 1 แถว cancelled",
               is_ok(res) and bool(m) and len(rr) == 1 and rr[0].get("result") == "cancelled",
               f"ack={res} rows={brief(rr)}")

    # ---------------- e/f/i/l: หมดเวลา → ไม่ตอบ ----------------
    if not can_expire:
        for n in "efil":
            report(f"{n}. (ข้าม — ต้องรอหมดเวลา)", None, why_expire)
    else:
        E2, s2, _ = join_member(A, N_EXPIRE, ROOM)
        E4, s4, _ = join_member(A, N_GONE, ROOM)
        E7, s7, _ = join_member(A, N_DOUBLE, ROOM)
        t_call2 = time.time()
        call(A, s2)
        call(A, s4)
        wait_for(lambda: E2.data["check_requests"] and E4.data["check_requests"])
        wait_for(lambda: status_of((row(A, sid=s2) or {})) == "pending"
                 and status_of((row(A, sid=s4) or {})) == "pending")
        E4.disconnect()
        wait_for(lambda: row(A, name=N_GONE) is None)
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_GONE)
        report("i. หลุดแล้วยังไม่กลับ → ไม่มีแถวประวัติทันที", recs is not None and not rr, f"rows={brief(rr)}")

        # การเรียกที่ใหม่กว่า (เรียกหลัง N_EXPIRE) — กดเบิ้ลแบบในภาพ 05:25:57/05:25:58 แล้วยืนยัน
        if roomy:
            time.sleep(1.0)
        call(A, s7)
        call(A, s7, new=False)
        got = wait_for(lambda: len(E7.data["check_requests"]) >= 2, 3)
        wait_row(A, sid=s7, status="pending")
        res = ack(E7, "confirm_checkin")
        m = wait_row(A, sid=s7, status="checked")
        time.sleep(0.2)
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_DOUBLE)
        report("m. กดเรียกเบิ้ล 2 ครั้งติด → ได้เสียงเรียก 2 ครั้ง ยืนยันได้",
               bool(got) and is_ok(res) and bool(m), f"check_request={len(E7.data['check_requests'])} ack={res}")
        report("m. กดเรียกเบิ้ล → ประวัติ 1 แถว checked ไม่มี 'ไม่ตอบ' ปลอม",
               len(rr) == 1 and rr[0].get("result") == "checked", f"rows={brief(rr)}")

        # e: ยังไม่ครบเวลา ต้องยังไม่ขึ้นไม่ตอบ
        early = t_call2 + T - 0.8 - time.time()
        if early > 0:
            time.sleep(early)
        m = row(A, sid=s2)
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_EXPIRE)
        report("e. ก่อนครบเวลา (timeout-0.8 วิ) ยัง pending ยังไม่บันทึกไม่ตอบ",
               bool(m) and status_of(m) == "pending" and not E2.data["closed"] and not rr,
               f"after {time.time() - t_call2:.2f}s row={m} closed={E2.data['closed']} rows={brief(rr)}")
        cl = wait_for(lambda: E2.data["closed"], T + 4)
        t_closed, d = cl[0] if cl else (None, {})
        report("e. ครบเวลา → พนักงานได้ check_closed reason=expired (+called, timeout)",
               d.get("reason") == "expired" and d.get("timeout") == T
               and bool(re.match(r"^\d\d:\d\d:\d\d$", str(d.get("called") or ""))), f"payload={d}")
        lag = (t_closed - t_call2) if t_closed else None
        report("e. หมดเวลาหลังครบ timeout เท่านั้น (ไม่ก่อน, ช้าไม่เกิน ~2.5 วิ)",
               lag is not None and T - 0.3 <= lag <= T + 2.5,
               f"closed after {lag:.2f}s" if lag is not None else "ไม่ได้ check_closed")
        m = wait_row(A, sid=s2, status="no_response")
        report("e. ตารางแอดมินเปลี่ยนเป็น no_response เอง (left=None)",
               bool(m) and m.get("left") is None, f"row={m or row(A, sid=s2)}")
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_EXPIRE)
        report("e. ประวัติมี no_response 1 แถว (checker ถูก, confirmed ว่าง)",
               len(rr) == 1 and rr[0].get("result") == "no_response" and rr[0].get("checker") == ADMIN
               and rr[0].get("confirmed") == "", f"rows={brief(rr)}")
        plain = history(A)
        report("e. แถว no_response แสดงใน get_history() แบบรุ่นเก่าด้วย",
               len(rows_of(plain, ROOM, N_EXPIRE)) == 1)

        # i: หลุดแล้วไม่กลับจนครบเวลา
        got = wait_for(lambda: rows_of(history(A, {"cancelled": True}), ROOM, N_GONE), 4, step=0.3)
        report("i. หลุดแล้วไม่กลับจนครบเวลา → no_response 1 แถว (ชื่อผู้เรียกถูก)",
               bool(got) and len(got) == 1 and got[0].get("result") == "no_response"
               and got[0].get("checker") == ADMIN, f"rows={brief(got)}")

        # f: ยืนยัน / ยกเลิก หลังหมดเวลา
        res = ack(E2, "confirm_checkin")
        report("f. กดยืนยันหลังหมดเวลา → ok=False บอกว่าบันทึกไม่ตอบแล้ว", is_refused(res, "ไม่ตอบ"), f"ack={res}")
        # ยกเลิกหลังหมดเวลา — เซิร์ฟเวอร์มีได้ 2 แบบ: ปฏิเสธ (สเปกแรก) หรือยอมให้ยกเลิก
        # (แอดมินเพิ่งรู้ทีหลังว่าคนนั้นไปกินข้าว → แถว "ไม่ตอบ" เปลี่ยนเป็น "ยกเลิก") — ตรวจให้สอดคล้องกับแบบที่เจอ
        n_closed = len(E2.data["closed"])
        res = ack(A, "cancel_check", {"target_sid": s2, "checker_name": ADMIN})
        time.sleep(0.3)
        m = row(A, sid=s2)
        recs = history(A, {"cancelled": True})
        rr = rows_of(recs, ROOM, N_EXPIRE)
        if is_refused(res):
            report("f. (ข้อมูล) ยกเลิกหลังหมดเวลา → เซิร์ฟเวอร์ปฏิเสธ (ok=False)", True, f"ack={res}")
            report("f. ยกเลิกถูกปฏิเสธ → ยัง no_response และประวัติยัง 1 แถว no_response",
                   status_of(m) == "no_response" and len(rr) == 1 and rr[0].get("result") == "no_response",
                   f"row={m} rows={brief(rr)}")
        elif is_ok(res):
            report("f. (ข้อมูล) ยกเลิกหลังหมดเวลา → เซิร์ฟเวอร์ยอม (เปลี่ยนแถวไม่ตอบเป็นยกเลิก)", True, f"ack={res}")
            report("f. ยกเลิกหลังหมดเวลา → แถวเดิมเปลี่ยนเป็น cancelled (ไม่เพิ่มแถว) พร้อม cancelled_by",
                   len(rr) == 1 and rr[0].get("result") == "cancelled" and rr[0].get("cancelled_by") == ADMIN,
                   f"rows={brief(rr)}")
            report("f. ยกเลิกหลังหมดเวลา → สถานะกลับเป็นก่อนเรียก (wait ไม่ติดธงไม่ตอบ)",
                   status_of(m) == "wait", f"row={m}")
            got = wait_for(lambda: len(E2.data["closed"]) > n_closed, 2)
            report("f. ยกเลิกหลังหมดเวลา → พนักงานได้ check_closed reason=cancelled",
                   bool(got) and E2.data["closed"][-1][1].get("reason") == "cancelled",
                   f"closed={[c[1] for c in E2.data['closed']]}")
            plain = history(A)
            report("f. แถวที่เปลี่ยนเป็น cancelled ไม่ถูกส่งให้แอดมินรุ่นเก่า", not rows_of(plain, ROOM, N_EXPIRE),
                   f"rows={brief(rows_of(plain, ROOM, N_EXPIRE))}")
            res = ack(A, "cancel_check", {"target_sid": s2, "checker_name": ADMIN})
            report("f. ยกเลิกซ้ำครั้งที่สอง → ok=False", is_refused(res), f"ack={res}")
            res = ack(E2, "confirm_checkin")
            report("f. พนักงานกดยืนยันหลังถูกยกเลิก → ok=False", is_refused(res), f"ack={res}")
        else:
            report("f. ยกเลิกหลังหมดเวลา → ได้ ack", False, f"ack={res}")
        prev = status_of(row(A, sid=s2))
        call(A, s2)
        m = wait_row(A, sid=s2, status="pending")
        report("f. เรียกใหม่หลังหมดเวลา → pending เริ่มนับใหม่ (left≈timeout)",
               bool(m) and isinstance(m.get("left"), int) and T - 1 <= m["left"] <= T, f"row={m}")
        res = ack(A, "cancel_check", {"target_sid": s2, "checker_name": ADMIN})
        m = wait_row(A, sid=s2, status=prev)
        report(f"f. ยกเลิกการเรียกใหม่ → กลับเป็นสถานะก่อนเรียก ({prev})",
               is_ok(res) and bool(m), f"ack={res} row={m or row(A, sid=s2)}")

        # l: เรียงตามเวลาที่กดเรียก ใหม่สุดก่อน
        recs = history(A, {"cancelled": True}) or []

        def idx(name, result=None):
            return next((i for i, r in enumerate(recs) if r.get("room") == ROOM and r.get("name") == name
                         and (result is None or r.get("result") == result)), None)
        # N_GONE เรียกก่อน N_DOUBLE แต่แถว no_response ถูกบันทึกทีหลัง (ตอนครบเวลา) — ต้องอยู่ใต้ N_DOUBLE
        # การเรียกล่าสุดของ N_EXPIRE (เรียกใหม่แล้วยกเลิก ข้อ f) ใหม่กว่าทุกอัน — ต้องอยู่บนสุด
        i_new, i_nr, i_last = idx(N_DOUBLE, "checked"), idx(N_GONE, "no_response"), idx(N_EXPIRE)
        report("l. no_response ที่บันทึกทีหลังไม่แซงขึ้นเหนือการเรียกที่ใหม่กว่า",
               None not in (i_new, i_nr, i_last) and i_last < i_new < i_nr,
               f"index: {N_EXPIRE}(ล่าสุด)={i_last} {N_DOUBLE}/checked={i_new} {N_GONE}/no_response={i_nr}")
        cts = [r["called_ts"] for r in recs if isinstance(r.get("called_ts"), (int, float))]
        report("l. ทั้งรายการเรียงตาม called_ts ใหม่ → เก่า",
               bool(cts) and all(a >= b for a, b in zip(cts, cts[1:])), f"{len(cts)} records")

    # ---------------- n: ช่วงที่ "ครบเวลาแล้ว" แต่ตัวตรวจ (ทุก 1 วิ) ยังไม่ทันเก็บ ----------------
    # ยืนยัน / ยกเลิก / กดเรียกซ้ำ / กลับเข้าห้อง ในช่วงนั้น ต้องได้ผลเหมือนหมดเวลาไปแล้ว
    if not can_expire:
        report("n. (ข้าม — ต้องรอหมดเวลา)", None, why_expire)
    else:
        P, sP, _ = join_member(A, N_PROBE, ROOM)
        R1, r1, _ = join_member(A, N_RACE_CONFIRM, ROOM)
        R2, r2, _ = join_member(A, N_RACE_CANCEL, ROOM)
        R3, r3, _ = join_member(A, N_RACE_RECALL, ROOM)
        R4, r4, _ = join_member(A, N_RACE_REJOIN, ROOM)
        R4b = make_client(N_RACE_REJOIN + " (ต่อใหม่)")  # ต่อไว้ก่อน ลงมือแค่ join ในช่วงแคบ
        call(A, sP)
        cl = wait_for(lambda: P.data["closed"], T + 4)
        t_tick = cl[0][0] if cl else time.time()  # ≈ เวลาที่ตัวตรวจทำงานรอบหนึ่ง
        # เรียกให้ "ครบเวลา" ตกหลังรอบตรวจ ~0.35 วิ แล้วลงมือตอน ~0.55 วิ (ก่อนรอบถัดไป)
        pause = t_tick + 0.35 - time.time()
        if pause > 0:
            time.sleep(pause)
        t_c = time.time()
        for s in (r1, r2, r3, r4):
            call(A, s)
        wait_for(lambda: all(status_of((row(A, sid=s) or {})) == "pending" for s in (r1, r2, r3, r4)))
        R4.disconnect()
        wait_for(lambda: row(A, name=N_RACE_REJOIN) is None)
        pause = t_c + T + 0.2 - time.time()
        if pause > 0:
            time.sleep(pause)
        t_act = time.time()
        res1 = ack(R1, "confirm_checkin")
        res2 = ack(A, "cancel_check", {"target_sid": r2, "checker_name": ADMIN})
        n_req3 = len(R3.data["check_requests"])
        call(A, r3)  # การเรียกเดิมครบเวลาแล้ว = การเรียกใหม่
        R4b.emit("join_room_member", {"room": ROOM, "name": N_RACE_REJOIN})
        wait_for(lambda: R4b.data["joined"])
        t_done = time.time()
        hit = "ยกเลิกไม่ได้" in ((res2 or {}).get("msg") or "")
        report("n. (ข้อมูล) ลงมือทันก่อนตัวตรวจรอบถัดไป — ทดสอบทางที่ event จัดการหมดเวลาเอง",
               True if hit else None,
               f"เริ่ม {t_act - t_c:.2f}s จบ {t_done - t_c:.2f}s หลังเรียก (timeout={T}); "
               + ("ตัวตรวจเก็บไปก่อน — ข้อที่เหลือยังตรวจผลได้" if not hit else "ทัน"))
        report("n. ยืนยันตอนครบเวลาพอดี → ok=False บอกว่าไม่ตอบ", is_refused(res1, "ไม่ตอบ"), f"ack={res1}")
        # ครบเวลาพอดี = ขึ้นไม่ตอบก่อน แต่แอดมินยังยกเลิกการเรียกล่าสุดที่เพิ่งไม่ตอบได้ (3.4.0)
        report("n. ยกเลิกตอนครบเวลาพอดี → ยกเลิกได้ (เปลี่ยนแถวไม่ตอบเป็นยกเลิก)", is_ok(res2), f"ack={res2}")
        got = wait_for(lambda: len(R3.data["check_requests"]) > n_req3 and R3.data["closed"], 3)
        m = wait_row(A, sid=r3, status="pending")
        report("n. กดเรียกซ้ำตอนครบเวลาพอดี → ของเดิมเป็นไม่ตอบ (check_closed expired) แล้วเริ่มเรียกใหม่",
               bool(got) and R3.data["closed"][0][1].get("reason") == "expired" and bool(m)
               and isinstance(m.get("left"), int) and T - 1 <= m["left"] <= T,
               f"closed={[c[1].get('reason') for c in R3.data['closed']]} row={m or row(A, sid=r3)}")
        seq = [ev for _, ev in sorted(R3.data["events"]) if ev in ("check_closed", "check_request")]
        report("n. เครื่องพนักงานได้ check_closed ก่อน check_request ใหม่ (ป๊อปอัพใหม่ไม่โดนปิด)",
               seq[-2:] == ["check_closed", "check_request"], f"seq={seq}")
        time.sleep(0.8)
        report("n. กลับเข้าห้องตอนครบเวลาพอดี → ไม่เรียกต่อ สถานะ wait",
               not R4b.data["check_requests"] and status_of((row(A, name=N_RACE_REJOIN) or {})) == "wait",
               f"check_request={len(R4b.data['check_requests'])} row={row(A, name=N_RACE_REJOIN)}")
        recs = history(A, {"cancelled": True})
        for nm in (N_RACE_CONFIRM, N_RACE_CANCEL, N_RACE_RECALL, N_RACE_REJOIN):
            rr = rows_of(recs, ROOM, nm)
            want = "cancelled" if nm == N_RACE_CANCEL else "no_response"
            report(f"n. {nm} → {want} 1 แถว",
                   len(rr) == 1 and rr[0].get("result") == want, f"rows={brief(rr)}")
        res = ack(A, "cancel_check", {"target_sid": r3, "checker_name": ADMIN})
        m = wait_row(A, sid=r3, status="no_response")
        report("n. ยกเลิกการเรียกใหม่ → กลับเป็น no_response", is_ok(res) and bool(m), f"ack={res}")
        sid_info[R4b.get_sid()] = (ROOM, N_RACE_REJOIN)

    # ---------------- k: ลบห้องตอนมีคนรอยืนยัน ----------------
    if not roomy:
        report("k. (ข้าม)", None, why_roomy)
    else:
        K = make_client("admin-del")
        K.emit("create_room", ROOM_DEL)
        wait_for(lambda: K.data["joined"])
        E5, s5, _ = join_member(K, N_DEL, ROOM_DEL)
        E6, s6, _ = join_member(K, N_DEL_GONE, ROOM_DEL)
        call(K, s5, who=ADMIN_DEL)
        call(K, s6, who=ADMIN_DEL)
        wait_for(lambda: E5.data["check_requests"] and E6.data["check_requests"])
        wait_for(lambda: status_of((row(K, sid=s5) or {})) == "pending"
                 and status_of((row(K, sid=s6) or {})) == "pending")
        E6.disconnect()
        wait_for(lambda: row(K, name=N_DEL_GONE) is None)
        t_del = time.time()
        K.emit("delete_room", ROOM_DEL)
        left = wait_for(lambda: E5.data["left"] >= 1)
        cl = E5.data["closed"]
        report("k. ลบห้อง → คนที่รอยืนยันได้ check_closed reason=cancelled และ left_room",
               bool(left) and bool(cl) and cl[-1][1].get("reason") == "cancelled",
               f"closed={[c[1] for c in cl]} left={E5.data['left']}")
        recs = history(A, {"cancelled": True})
        r5, r6 = rows_of(recs, ROOM_DEL, N_DEL), rows_of(recs, ROOM_DEL, N_DEL_GONE)
        report("k. ลบห้อง → คนที่รอยืนยันอยู่ได้แถว cancelled note='ลบห้อง'",
               len(r5) == 1 and r5[0].get("result") == "cancelled" and r5[0].get("note") == "ลบห้อง"
               and r5[0].get("checker") == ADMIN_DEL, f"rows={brief(r5)}")
        report("k. ลบห้อง → คนที่หลุดระหว่างรอ (orphan) ได้แถว cancelled note='ลบห้อง'",
               len(r6) == 1 and r6[0].get("result") == "cancelled" and r6[0].get("note") == "ลบห้อง",
               f"rows={brief(r6)}")
        plain = history(A)
        report("k. แถวยกเลิกจากการลบห้องไม่ถูกส่งให้โปรแกรมแอดมินรุ่นเก่า",
               not rows_of(plain, ROOM_DEL, N_DEL) and not rows_of(plain, ROOM_DEL, N_DEL_GONE))
        if can_expire:
            wait = t_del + T + 1.5 - time.time()
            if wait > 0:
                time.sleep(wait)
            recs = history(A, {"cancelled": True})
            r6 = rows_of(recs, ROOM_DEL, N_DEL_GONE)
            report("k. การเรียกที่ค้างของคนหลุดถูกเก็บตอนลบห้อง — ครบเวลาแล้วไม่เกิด no_response ซ้ำ",
                   len(r6) == 1, f"rows={brief(r6)}")
        else:
            report("k. ไม่เกิด no_response ซ้ำหลังลบห้อง (ข้าม)", None, why_expire)

    # ---------------- m: ทุกการเรียก = ประวัติ 1 แถว ----------------
    time.sleep(0.3)
    recs = history(A, {"cancelled": True})
    for (room, name), n in sorted(calls.items()):
        rr = rows_of(recs, room, name)
        report(f"m. เรียก {n} ครั้ง = ประวัติ {n} แถว: {name}", len(rr) == n,
               f"rows={len(rr)} {[r.get('result') for r in rr]}")


def cleanup():
    try:
        c = next((x for x in made if x.connected), None) or make_client("cleanup")
        for room in (ROOM, ROOM_OTHER, ROOM_DEL):
            c.emit("delete_room", room)
        gone = wait_for(lambda: c.data["rooms"] is not None and not any(
            r.get("name") in (ROOM, ROOM_OTHER, ROOM_DEL) for r in c.data["rooms"]), 5)
        report("เก็บงาน: ลบห้องทดสอบแล้ว", bool(gone))
    except Exception as e:
        report("เก็บงาน: ลบห้องทดสอบแล้ว", False, repr(e))
    for x in made:
        try:
            if x.connected:
                x.disconnect()
        except Exception:
            pass


try:
    main()
except Exception:
    traceback.print_exc()
    report("สคริปต์ทดสอบทำงานจนจบ", False, "exception")
finally:
    cleanup()

n_fail, n_pass, n_skip = results.count("FAIL"), results.count("PASS"), results.count("SKIP")
print("E2E_CALLS_RESULT:", "FAIL" if n_fail else "PASS",
      f"(pass {n_pass}, fail {n_fail}, skip {n_skip})", flush=True)
sys.exit(1 if n_fail else 0)
