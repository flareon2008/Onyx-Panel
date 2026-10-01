"""External REST API: bearer keys and payload validation.

Keys are stored in the panel state as SHA-256 hashes, never in plain text —
the token is shown once at creation. The HTTP handlers live in the panel
server; this module keeps everything testable without it: token format,
hashing, lookup and the request payload checks with user-facing messages.
"""
import hashlib
import hmac
import secrets
import time

PROTOCOLS = ("web", "vless", "hysteria", "mtproto", "awg20", "awg31")
MAX_KEYS = 20


def create_token():
    return "onx_" + secrets.token_hex(20)


def key_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def new_key(name, token=None):
    token = token or create_token()
    return {"id": secrets.token_hex(8), "name": str(name or "").strip()[:60],
            "hash": key_hash(token), "created": int(time.time()), "last_used": 0}, token


def find_key(keys, token):
    """Constant-time comparison per stored hash; returns the record or None."""
    if not str(token or ""):
        return None
    digest = key_hash(token)
    for key in (keys or []):
        if isinstance(key, dict) and hmac.compare_digest(str(key.get("hash", "")), digest):
            return key
    return None


def public_keys(keys):
    out = []
    for key in (keys or []):
        if isinstance(key, dict):
            out.append({"id": key.get("id", ""), "name": key.get("name", ""),
                        "created": key.get("created", 0), "last_used": key.get("last_used", 0)})
    return out


def check_create(payload):
    payload = payload if isinstance(payload, dict) else {}
    name = str(payload.get("name") or "").strip()
    protocol = str(payload.get("protocol") or "").strip().lower()
    devices = payload.get("devices", 1)
    if not name or len(name) > 80:
        raise ValueError("Имя клиента обязательно: от 1 до 80 символов.")
    if protocol not in PROTOCOLS:
        raise ValueError("Протокол не поддерживается: " + ", ".join(PROTOCOLS))
    try:
        devices = int(devices)
    except (TypeError, ValueError):
        devices = 1
    if not 1 <= devices <= 8:
        raise ValueError("Устройств: от 1 до 8.")
    return name, protocol, devices


def check_renew(payload):
    payload = payload if isinstance(payload, dict) else {}
    try:
        days = int(payload.get("days"))
    except (TypeError, ValueError):
        raise ValueError("Передайте количество дней: от 1 до 3650.")
    if not 1 <= days <= 3650:
        raise ValueError("Дней: от 1 до 3650.")
    return days


def normalize_uid(uid):
    uid = str(uid or "").strip()
    if not uid or len(uid) > 64 or not all(ch.isalnum() or ch == "-" for ch in uid):
        raise ValueError("Некорректный идентификатор клиента.")
    return uid


def touch_key(keys, key):
    key["last_used"] = int(time.time())
    return keys
