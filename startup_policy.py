"""Read the employee's startup policy without creating UI or changing startup settings."""
import json
import threading
import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


STARTUP_WAIT_SECONDS = 8.0
REQUEST_TIMEOUT_SECONDS = 7.0


def automatic_launch(args):
    # --tray also identifies updater restarts, which must finish successfully.
    # Old Run entries migrate to --autostart after this version starts once.
    return "--autostart" in args


def _policy_url(server_url, employee_name):
    try:
        parts = urlsplit(str(server_url or "").strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password:
        return None
    path = parts.path.rstrip("/") + "/api/startup-policy"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode({"name": employee_name}), ""))


def _fetch_policy(url, access_code, timeout):
    request = Request(url, headers={"X-Access-Code": access_code, "Accept": "application/json",
                                    "Cache-Control": "no-cache"})
    with urlopen(request, timeout=timeout) as response:
        # A startup-policy reply is tiny; do not read an arbitrary large page.
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Startup policy response is too large")
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def should_skip_startup(args, employee_name, server_urls, access_code, timeout=STARTUP_WAIT_SECONDS):
    """Only a confirmed day off suppresses automatic startup; uncertainty allows it.

    The daemon worker also bounds the foreground wait if DNS resolution stalls.
    It never changes preferences or the Windows Run registration, so the next
    working-day startup and a manual launch remain available.
    """
    if not automatic_launch(args):
        return False
    name = str(employee_name or "").strip()
    if not name or not access_code or timeout <= 0:
        return False
    urls = list(dict.fromkeys(url for candidate in server_urls
                             if (url := _policy_url(candidate, name))))
    if not urls:
        return False
    deadline = time.monotonic() + timeout
    result = {"skip": False}

    def check():
        for url in urls:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                payload = _fetch_policy(url, access_code, min(REQUEST_TIMEOUT_SECONDS, remaining))
            except Exception:
                continue  # Older/unreachable servers must not prevent workday startup.
            if payload.get("ok") is True:
                result["skip"] = payload.get("allow_start") is False and payload.get("reason") == "day_off"
                return  # A reachable server's unknown result is authoritative: fail open.

    worker = threading.Thread(target=check, name="startup-policy", daemon=True)
    worker.start()
    worker.join(timeout)
    return False if worker.is_alive() else result["skip"]
