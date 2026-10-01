"""Cascade auto-failover decision logic.

The panel runs the health checks and applies the result; this module keeps
the decision stateless and testable. Only the catch-all ("Все VLESS и
Hysteria2") cascade is watched: that is the record whose outage actually
drops every client. Per-user cascades stay manual.

Consecutive failures are tracked by the caller; after FAILURE_LIMIT bad
checks the active cascade is swapped for the first disabled catch-all
standby. When the active cascade is healthy again the counter just resets —
the panel never switches back automatically (the admin chooses the primary).
"""
FAILURE_LIMIT = 2


def active_cascade(cascades):
    for record in (cascades or []):
        if record.get("enabled") and record.get("mode") == "all":
            return record
    return None


def standby_cascade(cascades):
    for record in (cascades or []):
        if not record.get("enabled") and record.get("mode") == "all":
            return record
    return None


def note_result(failures, record_id, ok):
    failures = failures if isinstance(failures, dict) else {}
    if ok:
        failures.pop(record_id, None)
    else:
        failures[record_id] = failures.get(record_id, 0) + 1
    return failures


def decide(cascades, failures):
    """Return {'disable': id, 'enable': id} when a switch must happen, else None."""
    active = active_cascade(cascades)
    if active is None:
        return None
    if failures.get(active["id"], 0) < FAILURE_LIMIT:
        return None
    standby = standby_cascade(cascades)
    if standby is None:
        return None
    return {"disable": active["id"], "enable": standby["id"]}
