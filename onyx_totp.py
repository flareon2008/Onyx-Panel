"""TOTP two-factor authentication for the panel login (RFC 6238, stdlib only).

The secret is generated on the panel, shown once as an otpauth:// URI (QR in
the settings UI) and stored inside data.json next to the password hash. Any
authenticator app that speaks the standard 6-digit/30s scheme works.
"""
import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

PERIOD = 30
DIGITS = 6


def generate_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode(secret):
    text = "".join(str(secret).split()).upper()
    if not text:
        raise ValueError("Пустой секрет TOTP.")
    text += "=" * (-len(text) % 8)
    return base64.b32decode(text)


def totp_at(secret, timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    counter = int(timestamp // PERIOD)
    digest = hmac.new(_decode(secret), counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(value).zfill(DIGITS)


def verify(secret, code, window=1, timestamp=None):
    code = str(code or "").strip()
    if len(code) != DIGITS or not code.isdigit():
        return False
    if timestamp is None:
        timestamp = time.time()
    # Any match inside the window counts; compare_digest keeps timing flat.
    for shift in range(-window, window + 1):
        if hmac.compare_digest(totp_at(secret, timestamp + shift * PERIOD), code):
            return True
    return False


def provisioning_uri(secret, account, issuer="Onyx Panel"):
    query = urllib.parse.urlencode({"secret": secret, "issuer": issuer,
                                    "algorithm": "SHA1", "digits": str(DIGITS),
                                    "period": str(PERIOD)})
    return "otpauth://totp/%s:%s?%s" % (urllib.parse.quote(issuer),
                                        urllib.parse.quote(str(account)), query)
