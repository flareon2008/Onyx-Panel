"""Login journal and the observer role.

The journal lives in the panel state (data.json): every successful login is
appended with its IP, user agent and whether the device (user agent hash) was
seen before. The observer role is a second, read-only account: the allowlist
below is the single source of truth for what an observer session may open.
"""
import hashlib
import time

MAX_LOGINS = 100
MAX_DEVICES = 50

# GET pages an observer may open (path suffixes after PANEL_PATH). Static
# assets and /login never reach this check; everything else redirects to the
# dashboard. POSTs are denied server-side except /logout.
OBSERVER_PAGES = ("/", "/dashboard", "/dashboard-data", "/clients-state",
                  "/users", "/nodes", "/cascade", "/cascade-state",
                  "/routing", "/updates", "/restart-status", "/logout")


def device_hash(user_agent):
    return hashlib.sha256(str(user_agent or "").encode("utf-8")).hexdigest()[:16]


def record_login(state, user, role, ip, user_agent):
    """Append one successful login; returns True when the device is new."""
    state = state if isinstance(state, dict) else {}
    devices = state.setdefault("seen_devices", [])
    digest = device_hash(user_agent)
    fresh = digest not in devices
    if fresh:
        devices.append(digest)
        del devices[:-MAX_DEVICES]
    logins = state.setdefault("logins", [])
    logins.append({"ts": int(time.time()), "user": str(user or "")[:64],
                   "role": role if role in ("admin", "observer") else "admin",
                   "ip": str(ip or "")[:64], "device": str(user_agent or "")[:120],
                   "new_device": fresh})
    del logins[:-MAX_LOGINS]
    return fresh


def last_logins(state, count=10):
    logins = state.get("logins") if isinstance(state.get("logins"), list) else []
    return list(reversed(logins))[:count]


def observer_can_get(suffix):
    return suffix in OBSERVER_PAGES


def observer_can_post(suffix):
    return suffix == "/logout"
