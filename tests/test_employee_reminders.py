"""Employee alert/room-event checks without Tk, network, audio, or registry access.

Run with: py -3 -m unittest discover -s tests -p test_employee_reminders.py -v
Uses the actual student.py in this repository.
Only selected AST function definitions are loaded; application startup is never
executed. GUI timer callbacks are recorded rather than run automatically.
"""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


CLIENT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = CLIENT_ROOT / "student.py"
FUNCTIONS = {
    "_checkin_alert_key", "close_checkin_popup", "show_checkin_popup",
    "on_checkin_alert", "on_checkin_alert_clear", "close_popup",
    "open_check_popup", "on_joined", "on_left", "on_check_request",
}


class EmployeeReminderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise RuntimeError("Employee source student.py is missing")
        source = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        functions = [node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
        if {node.name for node in functions} != FUNCTIONS:
            raise AssertionError(f"Expected reminder functions missing from {SOURCE}")
        for node in functions:
            node.decorator_list = []  # Avoid Socket.IO registration at definition time.
        cls.code = compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec")

    def setUp(self):
        self.windows = []
        self.ui_callbacks = []
        self.root = Mock()
        self.root.winfo_screenwidth.return_value = 1920
        self.root.winfo_screenheight.return_value = 1080
        self.root.state.return_value = "normal"
        self.root.after.side_effect = lambda delay, callback, *args: self.ui_callbacks.append((callback, args))
        self.tk = Mock()
        self.tk.Toplevel.side_effect = self.make_window
        self.tk.PhotoImage.side_effect = OSError("No image needed for this test")
        self.tk.Label.side_effect = lambda *args, **kwargs: Mock()
        self.clock = SimpleNamespace(time=lambda: 1000.0, monotonic=lambda: 200.0,
                                     strftime=lambda fmt: "2026-11-13")
        self.state = {"room": "Room A", "name": "Employee", "popup": None,
                      "members_cache": {"room": "Room A"}, "confirm_waiting": False}
        self.checkin_state = {"win": None, "img": None, "alert": None,
                              "acked": None, "cleared": None, "seen": {}}
        self.autojoin = {"room": "Room A", "tried": False}
        self.status_info = {"people": {"Employee": {"match": "ok"}}, "round": 1}
        self.play_checkin = Mock()
        self.stop_checkin = Mock()
        self.play_alert = Mock()
        self.stop_alert = Mock()
        self.ns = {
            "root": self.root, "tk": self.tk, "math": math, "time": self.clock,
            "state": self.state, "checkin_state": self.checkin_state,
            "autojoin": self.autojoin, "status_info": self.status_info,
            "play_checkin_alert": self.play_checkin, "stop_checkin_alert": self.stop_checkin,
            "play_alert": self.play_alert, "stop_alert": self.stop_alert,
            "C": {key: key for key in ("bg", "gold", "gold_light", "text", "amber", "green")},
            "F_BOLD": (), "F_NORMAL": (), "_icon": None,
            "GoldButton": Mock(), "resource_path": lambda name: name,
            "prefs": Mock(), "show_room": Mock(), "show_lobby": Mock(),
            "set_status": Mock(), "save_name": Mock(), "render_my_checkin": Mock(),
            "update_tray": Mock(), "show_window": Mock(), "close_missed_notice": Mock(),
        }
        exec(self.code, self.ns)

    def make_window(self, *args, **kwargs):
        window = Mock()
        window.winfo_exists.return_value = True
        window.winfo_reqwidth.return_value = 600
        window.winfo_reqheight.return_value = 400
        window.winfo_screenwidth.return_value = 1920
        window.winfo_screenheight.return_value = 1080
        window.destroy.side_effect = lambda: setattr(window.winfo_exists, "return_value", False)
        self.windows.append(window)
        return window

    def call(self, name, *args, **kwargs):
        return self.ns[name](*args, **kwargs)

    def drain_ui(self):
        while self.ui_callbacks:
            callback, args = self.ui_callbacks.pop(0)
            callback(*args)

    @staticmethod
    def alert(reminder=False, identifier="round-1-cycle-1", **extra):
        return {"round": 1, "alert_id": identifier, "reminder": reminder,
                "remaining": 180 if reminder else 600, "away": False, **extra}

    def test_initial_dismissal_does_not_suppress_three_minute_reminder(self):
        self.call("show_checkin_popup", self.alert())
        first = self.checkin_state["win"]
        self.call("close_checkin_popup", acked=True)
        self.assertEqual(self.checkin_state["acked"], ("round-1-cycle-1", False))
        first.destroy.assert_called_once()
        self.call("show_checkin_popup", self.alert(reminder=True))
        self.assertEqual(len(self.windows), 2)
        self.assertEqual(self.play_checkin.call_count, 2)
        self.assertIs(self.checkin_state["win"], self.windows[1])
        self.assertEqual(self.checkin_state["alert"]["remaining"], 180)

    def test_duplicate_initial_and_reminder_after_reconnect_are_ignored(self):
        for reminder in (False, True):
            alert = self.alert(reminder=reminder)
            self.call("show_checkin_popup", alert)
            self.call("close_checkin_popup", acked=True)
            # The server resends the same payload after a reconnect.
            self.call("on_checkin_alert", alert)
            self.drain_ui()
        self.assertEqual(len(self.windows), 2)
        self.assertEqual(self.play_checkin.call_count, 2)
        self.assertIsNone(self.checkin_state["win"])

    def test_initial_replayed_after_reminder_cannot_replace_reminder(self):
        self.call("show_checkin_popup", self.alert())
        self.call("show_checkin_popup", self.alert(reminder=True))
        current = self.checkin_state["win"]
        self.call("show_checkin_popup", self.alert())
        self.assertIs(self.checkin_state["win"], current)
        self.assertEqual(self.play_checkin.call_count, 2)

    def test_new_cycle_same_round_is_allowed(self):
        self.call("show_checkin_popup", self.alert())
        self.call("close_checkin_popup", acked=True)
        self.call("show_checkin_popup", self.alert(identifier="round-1-cycle-2"))
        self.assertEqual(len(self.windows), 2)
        self.assertEqual(self.checkin_state["alert"]["alert_id"], "round-1-cycle-2")

    def test_away_announcement_plays_sound_without_starting_countdown(self):
        waiting = self.alert(identifier="round-1-waiting", away=True, activity="ปวดน้อย",
                             waiting_for_return=True, remaining=None, deadline=None)
        self.call("show_checkin_popup", waiting)
        window = self.checkin_state["win"]
        self.play_checkin.assert_called_once()
        self.assertIn("กลับมาแล้ว", window.info_label.config.call_args.kwargs["text"])
        self.assertNotIn("เหลือเวลาเช็คชื่อ", window.info_label.config.call_args.kwargs["text"])
        # The attention animation may run, but no 1-second countdown is queued.
        self.assertNotIn(1000, [invocation.args[0] for invocation in window.after.call_args_list])

    def test_return_to_seat_starts_new_ten_minute_alert_after_waiting_dismissal(self):
        self.call("show_checkin_popup", self.alert(identifier="round-1-waiting", away=True,
                  waiting_for_return=True, remaining=None, deadline=None))
        self.call("close_checkin_popup", acked=True)
        self.call("show_checkin_popup", self.alert(identifier="round-1-returned",
                  waiting_for_return=False, remaining=600))
        window = self.checkin_state["win"]
        self.assertEqual(self.play_checkin.call_count, 2)
        self.assertEqual(len(self.windows), 2)
        self.assertEqual(self.checkin_state["alert"]["alert_id"], "round-1-returned")
        self.assertIn("10:00", window.info_label.config.call_args.kwargs["text"])
        self.assertIn(1000, [invocation.args[0] for invocation in window.after.call_args_list])

    def test_returned_member_gets_one_three_minute_reminder_despite_replays(self):
        self.call("show_checkin_popup", self.alert(identifier="round-1-waiting", away=True,
                  waiting_for_return=True, remaining=None, deadline=None))
        self.call("close_checkin_popup", acked=True)
        running = self.alert(identifier="round-1-returned", waiting_for_return=False)
        self.call("show_checkin_popup", running)
        self.call("close_checkin_popup", acked=True)
        reminder = self.alert(identifier="round-1-returned", reminder=True,
                              waiting_for_return=False, remaining=180)
        self.call("show_checkin_popup", reminder)
        window = self.checkin_state["win"]
        self.assertIn("3:00", window.info_label.config.call_args.kwargs["text"])
        self.call("close_checkin_popup", acked=True)
        for payload in (running, reminder, reminder):
            self.call("on_checkin_alert", payload)
        self.drain_ui()
        self.assertEqual(self.play_checkin.call_count, 3)
        self.assertEqual(len(self.windows), 3)
        self.assertIsNone(self.checkin_state["win"])

    def test_reminder_replaces_visible_initial_popup_and_replays_audio_once(self):
        self.call("show_checkin_popup", self.alert())
        initial_window = self.checkin_state["win"]
        self.call("show_checkin_popup", self.alert(reminder=True))
        initial_window.destroy.assert_called_once()
        self.stop_checkin.assert_called_once()
        self.assertIsNot(self.checkin_state["win"], initial_window)
        self.assertEqual(self.play_checkin.call_count, 2)
        self.assertIn("3:00", self.checkin_state["win"].info_label.config.call_args.kwargs["text"])
        self.call("show_checkin_popup", self.alert(reminder=True))
        self.assertEqual(self.play_checkin.call_count, 2)

    def test_old_popup_timer_does_nothing_after_reminder_replaces_it(self):
        self.call("show_checkin_popup", self.alert())
        initial_window = self.checkin_state["win"]
        old_callbacks = list(initial_window.after.call_args_list)
        self.call("show_checkin_popup", self.alert(reminder=True))
        old_geometry_calls = initial_window.geometry.call_count
        old_label_calls = initial_window.info_label.config.call_count
        for invocation in old_callbacks:
            _, callback, *args = invocation.args
            callback(*args)
        self.assertEqual(initial_window.geometry.call_count, old_geometry_calls)
        self.assertEqual(initial_window.info_label.config.call_count, old_label_calls)

    def test_legacy_payload_still_deduplicates_without_alert_id(self):
        alert = {"round": 2, "away": False}
        self.call("show_checkin_popup", alert)
        self.call("close_checkin_popup", acked=True)
        self.call("show_checkin_popup", {**alert, "away": True})
        self.assertEqual(self.play_checkin.call_count, 1)

    def test_checkin_clear_remembers_round_without_new_popup_or_audio(self):
        self.call("show_checkin_popup", self.alert())
        self.call("close_checkin_popup", acked=True)
        self.call("on_checkin_alert_clear", {"round": 1})
        self.assertEqual(self.checkin_state["cleared"], {"round": 1, "at": 1000.0})
        self.assertIsNone(self.checkin_state["win"])
        self.assertEqual(self.play_checkin.call_count, 1)

    def test_kicked_member_clears_saved_room_and_prevents_autojoin(self):
        popup = self.make_window()
        self.state["popup"] = popup
        self.call("on_left", {"reason": "kicked"})
        self.assertEqual(self.state["room"], "Room A")  # Runs on Tk's thread only.
        self.drain_ui()
        self.assertIsNone(self.state["room"])
        self.assertIsNone(self.state["popup"])
        popup.destroy.assert_called_once()
        self.ns["prefs"].set.assert_called_once_with("last_room", "")
        self.assertEqual(self.autojoin, {"room": "", "tried": True})
        self.assertEqual(self.status_info["people"], {})
        self.assertIsNone(self.state["members_cache"])
        self.ns["show_lobby"].assert_called_once()
        self.ns["update_tray"].assert_called_once()
        self.assertEqual(self.ns["set_status"].call_args.args[1], "amber")

    def test_kicked_hidden_member_is_shown_room_picker(self):
        self.root.state.return_value = "withdrawn"
        self.call("on_left", {"reason": "kicked"})
        self.drain_ui()
        self.ns["show_window"].assert_called_once()

    def test_move_saves_destination_and_forwards_pending_deadline_metadata(self):
        open_popup = self.ns["open_check_popup"] = Mock()
        metadata = {"room": "Room B", "remaining": 179, "called_at": 123.0,
                    "timeout": 600, "reminder": True}
        self.call("on_joined", {"room": "Room B", "reason": "moved", "pending": True, "call": metadata})
        self.drain_ui()
        self.assertEqual(self.state["room"], "Room B")
        self.ns["prefs"].set.assert_called_once_with("last_room", "Room B")
        self.assertEqual(self.autojoin, {"room": "Room B", "tried": True})
        self.ns["show_room"].assert_called_once_with("Room B")
        open_popup.assert_called_once_with(metadata)
        self.assertEqual(self.status_info["people"], {})
        self.assertIsNone(self.state["members_cache"])

    def test_move_without_pending_call_does_not_create_call_popup(self):
        open_popup = self.ns["open_check_popup"] = Mock()
        self.call("on_joined", {"room": "Room B", "reason": "moved", "pending": False})
        self.drain_ui()
        open_popup.assert_not_called()
        self.assertEqual(self.state["room"], "Room B")

    def test_stale_check_request_from_previous_room_is_ignored(self):
        open_popup = self.ns["open_check_popup"] = Mock()
        self.call("on_check_request", {"room": "Old room", "reminder": True, "remaining": 180})
        self.drain_ui()
        open_popup.assert_not_called()
        self.ns["close_missed_notice"].assert_not_called()
        self.ns["set_status"].assert_not_called()

    def test_check_request_queued_before_move_checks_current_room_at_delivery(self):
        open_popup = self.ns["open_check_popup"] = Mock()
        self.call("on_check_request", {"room": "Room A", "remaining": 180})
        self.state["room"] = "Room B"
        self.drain_ui()
        open_popup.assert_not_called()

    def test_current_room_reminder_forwards_metadata(self):
        open_popup = self.ns["open_check_popup"] = Mock()
        payload = {"room": "Room A", "remaining": 180, "reminder": True, "called_at": 123.0}
        self.call("on_check_request", payload)
        self.drain_ui()
        self.ns["close_missed_notice"].assert_called_once()
        open_popup.assert_called_once_with(payload)
        self.assertEqual(self.ns["set_status"].call_args.args[1], "amber")

    def test_existing_manual_popup_updates_deadline_without_recreating_window(self):
        popup = self.make_window()
        self.state["popup"] = popup
        self.call("open_check_popup", {"room": "Room A", "remaining": 180, "reminder": True})
        self.assertEqual(self.state["call_deadline"], 380.0)
        self.tk.Toplevel.assert_not_called()
        popup.deiconify.assert_called_once()
        popup.lift.assert_called_once()
        self.play_alert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
