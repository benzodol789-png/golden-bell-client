# -*- coding: utf-8 -*-
# ลบห้องทดสอบ "ทีมทดสอบ" ทิ้งหลังรัน e2e — กันห้องค้างบนเซิร์ฟเวอร์จริง
import os
import time

import socketio

URL = os.environ.get("ODOL_URL", "http://127.0.0.1:5000")
c = socketio.Client()
c.connect(URL, auth={"code": "ODOL-2569"}, wait_timeout=10)
c.emit("delete_room", "ทีมทดสอบ")
time.sleep(1)
c.disconnect()
print("cleanup done: ลบห้อง 'ทีมทดสอบ' แล้ว")
