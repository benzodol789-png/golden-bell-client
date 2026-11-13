"""Day-off startup checks without production requests, Tk, or real registry writes."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlsplit


CLIENT_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("startup_policy_under_test", CLIENT_ROOT / "startup_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class Response:
    def __init__(self, payload):
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.raw[:limit]


def functions_from(filename, names, namespace):
    tree = ast.parse((CLIENT_ROOT / filename).read_text(encoding="utf-8-sig"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=functions, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class StartupPolicyTests(unittest.TestCase):
    def should_skip(self, args=("--tray", "--autostart"), name="Employee", urls=None, **kwargs):
        return policy.should_skip_startup(args, name, urls or ["https://server.invalid"], "test-access", **kwargs)

    def test_explicit_day_off_suppresses_automatic_start(self):
        with patch.object(policy, "urlopen", return_value=Response(
                {"ok": True, "allow_start": False, "reason": "day_off", "schedule_date": "2026-11-14"})) as fetch:
            self.assertTrue(self.should_skip())
        self.assertEqual(fetch.call_count, 1)

    def test_manual_launch_bypasses_all_policy_requests(self):
        with patch.object(policy, "urlopen") as fetch:
            self.assertFalse(self.should_skip(args=[]))
        fetch.assert_not_called()

    def test_legacy_tray_and_hidden_updater_restart_bypass_day_off_gate(self):
        # Updater 3.6.0 treats an early child exit as failure and rolls back.
        # --tray must remain running; only Windows' explicit --autostart is gated.
        with patch.object(policy, "urlopen") as fetch:
            self.assertFalse(self.should_skip(args=["--tray"]))
        fetch.assert_not_called()

    def test_blank_or_unsaved_name_starts_normally_without_request(self):
        with patch.object(policy, "urlopen") as fetch:
            for name in (None, "", "   "):
                with self.subTest(name=name):
                    self.assertFalse(self.should_skip(name=name))
        fetch.assert_not_called()

    def test_working_or_unknown_policy_allows_start(self):
        for value, reason in ((True, "working"), (None, "unknown")):
            with self.subTest(reason=reason), patch.object(policy, "urlopen", return_value=Response(
                    {"ok": True, "allow_start": value, "reason": reason})):
                self.assertFalse(self.should_skip())

    def test_only_boolean_false_and_day_off_reason_can_suppress_start(self):
        for payload in ({"ok": True, "allow_start": "false", "reason": "day_off"},
                        {"ok": True, "allow_start": 0, "reason": "day_off"},
                        {"ok": False, "allow_start": False, "reason": "day_off"},
                        {"ok": True, "allow_start": False, "reason": "unknown"}):
            with self.subTest(payload=payload), patch.object(policy, "urlopen", return_value=Response(payload)):
                self.assertFalse(self.should_skip())

    def test_unknown_employee_on_authoritative_server_does_not_try_other_servers(self):
        with patch.object(policy, "urlopen", return_value=Response(
                {"ok": True, "allow_start": None, "reason": "unknown"})) as fetch:
            self.assertFalse(self.should_skip(urls=["https://first.invalid", "https://second.invalid"]))
        self.assertEqual(fetch.call_count, 1)

    def test_request_has_encoded_name_auth_header_and_bounded_timeout(self):
        name = "ODOL TEST/ชื่อ+คน?"
        with patch.object(policy, "urlopen", return_value=Response(
                {"ok": True, "allow_start": True, "reason": "working"})) as fetch:
            self.assertFalse(self.should_skip(name=name))
        request = fetch.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(urlsplit(request.full_url).path, "/api/startup-policy")
        self.assertEqual(parse_qs(urlsplit(request.full_url).query), {"name": [name]})
        self.assertEqual({key.lower(): value for key, value in request.header_items()}["x-access-code"], "test-access")
        self.assertLessEqual(fetch.call_args.kwargs["timeout"], policy.REQUEST_TIMEOUT_SECONDS)

    def test_unavailable_first_server_tries_next_and_deduplicates_candidates(self):
        with patch.object(policy, "urlopen", side_effect=[OSError("offline"), Response(
                {"ok": True, "allow_start": False, "reason": "day_off"})]) as fetch:
            self.assertTrue(self.should_skip(urls=["https://first.invalid", "https://first.invalid/", "https://second.invalid"]))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(urlsplit(fetch.call_args.args[0].full_url).hostname, "second.invalid")

    def test_network_errors_old_servers_and_invalid_json_fail_open(self):
        for response in (OSError("network down"), Response(b"Server online"), Response([]), Response(b"x" * 65537)):
            with self.subTest(kind=type(response).__name__):
                options = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
                with patch.object(policy, "urlopen", **options):
                    self.assertFalse(self.should_skip())

    def test_malformed_or_non_http_urls_do_not_crash_or_send_requests(self):
        with patch.object(policy, "urlopen") as fetch:
            self.assertFalse(self.should_skip(urls=["", "file:///private", "http://[broken", "https://user:pass@server.invalid"]))
        fetch.assert_not_called()

    def test_dns_or_socket_stall_does_not_block_foreground_startup(self):
        release = threading.Event()
        finished = threading.Event()

        def stall(*args, **kwargs):
            release.wait(2)
            finished.set()
            return Response({"ok": True, "allow_start": False, "reason": "day_off"})

        with patch.object(policy, "urlopen", side_effect=stall):
            started = time.monotonic()
            try:
                self.assertFalse(self.should_skip(timeout=0.05))
                self.assertLess(time.monotonic() - started, 0.75)
            finally:
                release.set()
                self.assertTrue(finished.wait(1))

    def test_saved_name_read_does_not_create_profile_on_first_launch(self):
        namespace = functions_from("student.py", {"name_store_path", "load_saved_name"},
                                   {"os": os, "app_dir": lambda: "unused"})
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            self.assertEqual(namespace["load_saved_name"](), "")
            self.assertFalse((Path(folder) / "GoldenBellCheckin").exists())
            saved = Path(folder) / "GoldenBellCheckin" / "user.txt"
            saved.parent.mkdir()
            saved.write_text("Employee", encoding="utf-8")
            self.assertEqual(namespace["load_saved_name"](), "Employee")

    def test_policy_exit_precedes_window_socket_tray_mutex_and_update_cleanup(self):
        tree = ast.parse((CLIENT_ROOT / "student.py").read_text(encoding="utf-8-sig"))
        gate = next(node for node in tree.body if isinstance(node, ast.If)
                    and isinstance(node.test, ast.Call) and isinstance(node.test.func, ast.Attribute)
                    and node.test.func.attr == "should_skip_startup")
        start_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute)
                       and node.func.attr in {"Tk", "Client", "SingleInstance", "Tray", "cleanup_old"}]
        self.assertTrue(start_calls)
        self.assertTrue(all(node.lineno > gate.lineno for node in start_calls))
        skip = Mock(return_value=True)
        exit_process = Mock(side_effect=SystemExit(0))
        namespace = {"startup_policy": SimpleNamespace(should_skip_startup=skip),
                     "sys": SimpleNamespace(argv=["employee.exe", "--tray", "--autostart"], exit=exit_process),
                     "load_saved_name": lambda: "Employee", "_startup_urls": ["https://server.invalid"],
                     "ACCESS_CODE": "test-access"}
        with self.assertRaises(SystemExit) as stopped:
            exec(compile(ast.Module(body=[gate], type_ignores=[]), "startup-gate", "exec"), namespace)
        self.assertEqual(stopped.exception.code, 0)

    def test_legacy_registry_entry_migrates_without_disabling_next_workday_start(self):
        registry = MagicMock()
        registry.QueryValueEx.return_value = ('"C:\\Apps\\employee.exe" --tray', registry.REG_SZ)
        namespace = functions_from("tray.py", {"_run_value", "autostart_command", "set_autostart"}, {
            "sys": SimpleNamespace(frozen=True, executable="C:\\Apps\\employee.exe"),
            "os": SimpleNamespace(path=os.path, environ={}),
            "tempfile": SimpleNamespace(gettempdir=lambda: "C:\\Temp"),
            "winreg": registry, "_RUN_KEY": "Software/Test/Run",
        })
        self.assertTrue(namespace["set_autostart"]("GoldenBellEmployee", True))
        command = registry.SetValueEx.call_args.args[-1]
        self.assertTrue(command.endswith(" --tray --autostart"))
        registry.DeleteValue.assert_not_called()

    def test_development_run_does_not_write_registry(self):
        registry = MagicMock()
        namespace = functions_from("tray.py", {"_run_value", "autostart_command", "set_autostart"}, {
            "sys": SimpleNamespace(frozen=False), "os": SimpleNamespace(path=os.path, environ={}),
            "tempfile": tempfile, "winreg": registry, "_RUN_KEY": "Software/Test/Run",
        })
        self.assertFalse(namespace["set_autostart"]("GoldenBellEmployee", True))
        registry.SetValueEx.assert_not_called()
        registry.DeleteValue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
