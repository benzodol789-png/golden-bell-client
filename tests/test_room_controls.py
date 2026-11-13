"""Hermetic admin room-control tests; importing admin.py would start Tk/network.

Run with: py -3 -m unittest discover -s tests -p test_room_controls.py -v
Only the selected function definitions are compiled. No window, server, thread,
preferences, or updater is started by this suite.
"""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "admin.py"
FUNCTIONS = {
    "require_connection", "require_admin_name", "_selected_manage_members",
    "_member_names_text", "_send_member_action", "kick_selected_members",
    "move_selected_members", "render_members",
}


class FakeTree:
    def __init__(self, members):
        self.rows = {m["sid"]: m for m in members}
        self.selected = list(self.rows)

    def selection(self):
        return tuple(self.selected)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *sids):
        for sid in sids:
            self.rows.pop(sid, None)
            if sid in self.selected:
                self.selected.remove(sid)

    def insert(self, parent, position, iid, **kwargs):
        self.rows[iid] = kwargs

    def selection_add(self, sid):
        if sid not in self.selected:
            self.selected.append(sid)


class FakeStringVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class RequestTimeout(Exception):
    pass


class RoomControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        functions = [node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
        if {node.name for node in functions} != FUNCTIONS:
            raise AssertionError("A tested admin control was removed or renamed")
        cls.code = compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec")

    def setUp(self):
        self.members = [
            {"sid": "m1", "name": "One", "status": "wait", "time": ""},
            {"sid": "m2", "name": "Two", "status": "pending", "time": ""},
        ]
        self.state = {
            "connected": True, "room": "Source", "admin_name": "Admin",
            "rooms": [{"name": name} for name in ("Source", "Room B", "Room C")],
            "members_cache": {"room": "Source", "admins": 1,
                              "members": copy.deepcopy(self.members)},
        }
        self.tree = FakeTree(self.members)
        self.messagebox = Mock()
        self.messagebox.askyesno.return_value = True
        self.sio = Mock()
        self.sio.call.return_value = {"ok": True, "count": 2}
        self.root = Mock()
        self.thread = Mock()
        self.tk = Mock()
        self.tk.StringVar.side_effect = FakeStringVar
        self.ttk = Mock()
        self.status = Mock()
        self.admin_name_entry = Mock()
        self.ns = {
            "state": self.state, "member_tree": self.tree,
            "messagebox": self.messagebox, "sio": self.sio, "root": self.root,
            "threading": SimpleNamespace(Thread=self.thread),
            "socketio": SimpleNamespace(exceptions=SimpleNamespace(TimeoutError=RequestTimeout)),
            "set_status": self.status, "admin_name_entry": self.admin_name_entry,
            "tk": self.tk, "ttk": self.ttk,
            "sorted_rooms": lambda rooms: sorted(rooms, key=lambda room: room.get("name", "")),
            "C": {key: key for key in ("amber", "red", "green", "bg", "text", "gold_light")},
            "F_HEAD": (), "F_NORMAL": (), "F_BOLD": (),
            "room_info_label": Mock(), "member_fit": Mock(),
            "STATUS_TH": {"wait": ("Waiting", "muted"), "pending": ("Pending", "amber")},
            "_status_cells": lambda name: (None, "", "", False, ""),
            "_pending_label": lambda member: "Pending",
        }
        exec(self.code, self.ns)

    def call(self, name, *args):
        return self.ns[name](*args)

    def finish_request(self):
        """Simulate worker completion, then a separate Tk event-loop callback."""
        target = self.thread.call_args.kwargs["target"]
        target()
        delay, callback, *args = self.root.after.call_args.args
        self.assertEqual(delay, 0)
        callback(*args)

    def open_move_dialog(self):
        self.call("move_selected_members")
        self.tk.Toplevel.assert_called_once_with(self.root)
        kwargs = self.ttk.Combobox.call_args.kwargs
        submit = next(call.kwargs["command"] for call in self.ttk.Button.call_args_list
                      if call.kwargs.get("text") == "ย้ายสมาชิก")
        return kwargs, submit

    def test_disconnected_action_does_not_confirm_or_send(self):
        self.state["connected"] = False
        self.call("kick_selected_members")
        self.messagebox.showwarning.assert_called_once()
        self.messagebox.askyesno.assert_not_called()
        self.thread.assert_not_called()

    def test_admin_name_required_before_confirmation(self):
        self.state["admin_name"] = ""
        self.call("kick_selected_members")
        self.admin_name_entry.focus_set.assert_called_once()
        self.messagebox.askyesno.assert_not_called()
        self.thread.assert_not_called()

    def test_empty_selection_does_not_send(self):
        self.tree.selected = []
        self.call("kick_selected_members")
        self.messagebox.showwarning.assert_called_once()
        self.thread.assert_not_called()

    def test_offline_or_stale_member_rejects_whole_selection(self):
        self.tree.selected.append("orphan:1")
        self.call("kick_selected_members")
        self.messagebox.showwarning.assert_called_once()
        self.messagebox.askyesno.assert_not_called()
        self.thread.assert_not_called()

    def test_members_cache_from_another_room_is_rejected(self):
        self.state["members_cache"]["room"] = "Old room"
        self.call("move_selected_members")
        self.messagebox.showwarning.assert_called_once()
        self.tk.Toplevel.assert_not_called()

    def test_declining_kick_never_sends(self):
        self.messagebox.askyesno.return_value = False
        self.call("kick_selected_members")
        self.messagebox.askyesno.assert_called_once()
        self.thread.assert_not_called()
        self.sio.call.assert_not_called()

    def test_kick_runs_in_background_and_waits_for_ui_ack(self):
        self.call("kick_selected_members")
        self.assertTrue(self.state["member_action_pending"])
        self.thread.return_value.start.assert_called_once()
        self.assertTrue(self.thread.call_args.kwargs["daemon"])
        self.sio.call.assert_not_called()
        self.finish_request()
        self.sio.call.assert_called_once_with(
            "kick_members", {"targets": ["m1", "m2"], "room": "Source", "by": "Admin"}, timeout=10)
        self.assertFalse(self.state["member_action_pending"])
        self.assertEqual(self.status.call_args.args[1], "green")

    def test_busy_request_prevents_duplicate_operation(self):
        self.call("kick_selected_members")
        self.call("kick_selected_members")
        self.thread.assert_called_once()
        self.messagebox.askyesno.assert_called_once()
        self.messagebox.showwarning.assert_called_once()

    def test_move_picker_excludes_source_and_keeps_multiple_targets(self):
        kwargs, submit = self.open_move_dialog()
        self.assertEqual(kwargs["values"], ["Room B", "Room C"])
        self.assertEqual(kwargs["state"], "readonly")
        kwargs["textvariable"].set("Room C")
        submit()
        self.messagebox.askyesno.assert_called_once()
        self.finish_request()
        self.sio.call.assert_called_once_with(
            "move_members", {"targets": ["m1", "m2"], "room": "Source",
                             "by": "Admin", "destination": "Room C"}, timeout=10)

    def test_move_does_not_offer_nonexistent_destination(self):
        self.state["rooms"] = [{"name": "Source"}]
        self.call("move_selected_members")
        self.tk.Toplevel.assert_not_called()
        self.messagebox.showwarning.assert_called_once()

    def test_deleted_destination_is_rechecked_before_move(self):
        kwargs, submit = self.open_move_dialog()
        self.state["rooms"] = [{"name": "Source"}, {"name": "Room C"}]
        submit()
        self.messagebox.showwarning.assert_called_once()
        self.messagebox.askyesno.assert_not_called()
        self.thread.assert_not_called()

    def test_leaving_source_room_while_choosing_destination_stops_move(self):
        kwargs, submit = self.open_move_dialog()
        self.state["room"] = None
        submit()
        self.tk.Toplevel.return_value.destroy.assert_called_once()
        self.messagebox.showwarning.assert_called_once()
        self.thread.assert_not_called()

    def test_declining_move_keeps_dialog_without_request(self):
        kwargs, submit = self.open_move_dialog()
        self.messagebox.askyesno.return_value = False
        submit()
        self.thread.assert_not_called()
        self.tk.Toplevel.return_value.destroy.assert_not_called()

    def test_submit_rechecks_source_room_and_connection(self):
        self.state["room"] = "Changed room"
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.thread.assert_not_called()
        self.state["room"] = "Source"
        self.state["connected"] = False
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.thread.assert_not_called()

    def test_partial_success_reports_warning_and_unlocks_ui(self):
        self.sio.call.return_value = {"ok": True, "count": 1, "msg": "Moved one member",
                                      "skipped": [{"sid": "m2", "reason": "offline"}]}
        self.call("_send_member_action", "move_members", "Source", self.members, "Room B")
        self.finish_request()
        self.assertFalse(self.state["member_action_pending"])
        self.assertEqual(self.status.call_args.args, ("Moved one member", "amber"))
        self.messagebox.showwarning.assert_called_once()

    def test_server_permission_rejection_is_shown_without_claiming_success(self):
        self.sio.call.return_value = {"ok": False, "msg": "Admin no longer belongs to source room"}
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.finish_request()
        self.assertFalse(self.state["member_action_pending"])
        self.assertEqual(self.status.call_args.args[1], "red")
        self.assertEqual(self.messagebox.showwarning.call_args.args[1], self.sio.call.return_value["msg"])

    def test_timeout_explains_uncertainty_without_automatically_retrying(self):
        self.sio.call.side_effect = RequestTimeout()
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.finish_request()
        self.sio.call.assert_called_once()
        self.assertFalse(self.state["member_action_pending"])
        self.assertIn("อาจดำเนินการไปแล้ว", self.messagebox.showwarning.call_args.args[1])

    def test_connection_failure_unlocks_ui(self):
        self.sio.call.side_effect = OSError("connection lost")
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.finish_request()
        self.assertFalse(self.state["member_action_pending"])
        self.assertEqual(self.status.call_args.args[1], "red")
        self.messagebox.showwarning.assert_called_once()

    def test_old_server_invalid_ack_is_not_treated_as_success(self):
        self.sio.call.return_value = None
        self.call("_send_member_action", "kick_members", "Source", self.members)
        self.finish_request()
        self.assertFalse(self.state["member_action_pending"])
        self.assertIn("ยังไม่รองรับ", self.messagebox.showwarning.call_args.args[1])

    def test_refresh_preserves_surviving_selection_not_removed_members(self):
        self.call("render_members", copy.deepcopy(self.state["members_cache"]))
        self.assertEqual(set(self.tree.selection()), {"m1", "m2"})
        next_snapshot = {"room": "Source", "admins": 1, "members": [
            copy.deepcopy(self.members[1]),
            {"sid": "m3", "name": "New member", "status": "wait", "time": ""},
        ]}
        self.call("render_members", next_snapshot)
        self.assertEqual(self.tree.selection(), ("m2",))
        selected_room, members = self.call("_selected_manage_members", "move")
        self.assertEqual(selected_room, "Source")
        self.assertEqual([member["sid"] for member in members], ["m2"])

    def test_other_room_update_does_not_replace_selection(self):
        snapshot = copy.deepcopy(self.state["members_cache"])
        snapshot["room"] = "Another room"
        self.call("render_members", snapshot)
        self.assertEqual(set(self.tree.selection()), {"m1", "m2"})
        self.assertEqual(self.state["members_cache"]["room"], "Source")


if __name__ == "__main__":
    unittest.main()
