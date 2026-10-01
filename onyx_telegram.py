"""Telegram notifications: a small outbound-only Bot API client plus config.

Config lives in the panel state (data.json) under the "telegram" key and is
written through atomic_text-like helpers on the server side; this module owns
validation, defaults and the network calls (message + file upload). All calls
are plain urllib so the panel keeps its zero-dependency install.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot%s/%s"
TIMEOUT = 15
TOKEN_RE_CHARS = set("0123456789ABCDEFabcdef_-")

EVENT_KEYS = ("expiry", "logins", "cascades", "backups")


def default_config():
    return {"token": "", "chat": "", "events": {key: True for key in EVENT_KEYS}}


def normalize_config(data):
    data = data if isinstance(data, dict) else {}
    events = data.get("events") if isinstance(data.get("events"), dict) else {}
    return {"token": str(data.get("token") or "").strip(),
            "chat": str(data.get("chat") or "").strip(),
            "events": {key: bool(events.get(key, True)) for key in EVENT_KEYS}}


def configured(cfg):
    cfg = normalize_config(cfg)
    return bool(cfg["token"]) and bool(cfg["chat"])


def _post(token, method, body, headers):
    request = urllib.request.Request(API % (token, method), data=body,
                                     headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description", "неверный ответ") if isinstance(payload, dict) else "неверный ответ"
        raise RuntimeError(str(description)[:120])
    return payload


def get_me(token):
    """Cheap credential check: returns the bot profile from the API."""
    return _post(token, "getMe", b"", {"Content-Type": "application/x-www-form-urlencoded"})


def send_message(token, chat, text):
    """Plain-text message (no parse mode: names come from user input)."""
    payload = urllib.parse.urlencode({"chat_id": str(chat).strip(),
                                      "text": str(text)[:3500],
                                      "disable_web_page_preview": "true"}).encode()
    return _post(token, "sendMessage", payload,
                 {"Content-Type": "application/x-www-form-urlencoded"})


def send_document(token, chat, filename, data):
    boundary = "onyx" + str(int(time.time() * 1000))
    parts = [("--%s\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n%s\r\n"
              % (boundary, str(chat).strip())).encode(),
             ("--%s\r\nContent-Disposition: form-data; name=\"document\"; filename=\"%s\"\r\n"
              "Content-Type: application/gzip\r\n\r\n" % (boundary, os.path.basename(filename))).encode(),
             data,
             ("\r\n--%s--\r\n" % boundary).encode()]
    body = b"".join(parts)
    return _post(token, "sendDocument", body,
                 {"Content-Type": "multipart/form-data; boundary=" + boundary})


def notify(cfg, event, text):
    """Send when the channel is configured and the event kind is enabled."""
    cfg = normalize_config(cfg)
    if not configured(cfg) or not cfg["events"].get(event, False):
        return False
    send_message(cfg["token"], cfg["chat"], text)
    return True
