"""Traffic routing controls: direct IPs/domains, IPv4-only domains, torrent block.

The rules are injected into the generated Xray config BEFORE the cascade rules
so that matched traffic always leaves the panel directly, never through an
upstream server. Torrent blocking relies on Xray's sniffed-protocol routing
matcher ("bittorrent") pointed at a blackhole outbound, the same approach 3x-ui
uses.
"""
import json
import os
import re
import time

MAX_ENTRIES = 64
MAX_ENTRY_LEN = 120

# Values must survive JSON-encoding into the Xray config; anything beyond this
# charset would only ever break the config parse, which xray -test then
# rejects. Cyrillic is allowed for IDN entries such as "domain:рф".
ENTRY_RE = re.compile(r'^[^\s"\'`<>{};\\]{1,%d}$' % MAX_ENTRY_LEN)

LISTS = ('direct_ips', 'direct_domains', 'ipv4_domains')

DEFAULTS = {key: [] for key in LISTS}
DEFAULTS['block_torrents'] = False

class RoutingError(ValueError):
    pass


def _clean_entry(value):
    entry = str(value or '').strip()
    if not entry:
        return ''
    if len(entry) > MAX_ENTRY_LEN or not ENTRY_RE.match(entry):
        raise RoutingError('Некорректное значение маршрутизации: %s' % entry[:60])
    return entry


def _clean_list(values):
    if not isinstance(values, list):
        return []
    cleaned, seen = [], set()
    for value in values:
        entry = _clean_entry(value)
        if entry and entry.lower() not in seen:
            seen.add(entry.lower())
            cleaned.append(entry)
        if len(cleaned) >= MAX_ENTRIES:
            break
    return cleaned


def normalize(data):
    data = data if isinstance(data, dict) else {}
    result = {key: _clean_list(data.get(key)) for key in LISTS}
    result['block_torrents'] = bool(data.get('block_torrents'))
    return result


def load(path):
    """Tolerant read: a damaged file degrades to defaults, never to a broken config."""
    try:
        with open(path, encoding='utf-8') as stream:
            return normalize(json.load(stream))
    except (OSError, ValueError):
        return normalize({})


def save(path, data):
    normalized = normalize(data)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = path + '.tmp'
    payload = dict(normalized, updated_at=int(time.time()))
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return normalized


def xray_additions(data):
    """Outbounds and routing rules to merge into the generated Xray config.

    Rules are ordered: torrent block, direct IPs, direct domains, IPv4-only
    domains. The panel's sync_xray appends cascade rules after these, so any
    match here keeps the traffic off the upstream server.
    """
    data = normalize(data)
    outbounds, rules = [], []
    if data['block_torrents']:
        outbounds.append({'tag': 'blocked', 'protocol': 'blackhole'})
        rules.append({'type': 'field', 'protocol': ['bittorrent'], 'outboundTag': 'blocked'})
    if data['direct_ips']:
        rules.append({'type': 'field', 'ip': data['direct_ips'], 'outboundTag': 'direct'})
    if data['direct_domains']:
        rules.append({'type': 'field', 'domain': data['direct_domains'], 'outboundTag': 'direct'})
    if data['ipv4_domains']:
        outbounds.append({'tag': 'ipv4', 'protocol': 'freedom',
                          'settings': {'domainStrategy': 'UseIPv4'}})
        rules.append({'type': 'field', 'domain': data['ipv4_domains'], 'outboundTag': 'ipv4'})
    return outbounds, rules
