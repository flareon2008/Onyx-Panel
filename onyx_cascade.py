"""VLESS cascade: outbound chaining between Onyx panels and compatible Xray servers.

A cascade record stores the parsed form of a pasted vless:// link. The manager
turns enabled cascades into Xray outbounds plus routing rules; the panel owns
the file, the UI actions and the through-tunnel reachability test.
"""
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.parse

MAX_CASCADES = 16
XRAY_BIN = '/opt/onyx-panel/xray/xray'
PING_URL = 'https://www.gstatic.com/generate_204'

UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
UID_RE = re.compile(r'[a-f0-9]{16}')

# Transport query aliases and the stream settings block each one produces.
# "raw" is the modern name of "tcp"; "splithttp" predates the xhttp rename.
NETWORK_ALIASES = {
    'tcp': 'tcp', 'raw': 'tcp',
    'ws': 'ws', 'websocket': 'ws',
    'httpupgrade': 'httpupgrade',
    'wsupgrade': 'httpupgrade',
    'grpc': 'grpc',
    'xhttp': 'xhttp', 'splithttp': 'xhttp',
    'http': 'http', 'h2': 'http',
}


class CascadeError(ValueError):
    pass


def user_email(uid):
    """Match the manager's inbound client email scheme exactly."""
    return 'panel:' + str(uid)


def _first(query, *names, default=''):
    for name in names:
        value = query.get(name)
        if value:
            return value
    return default


def _host_header(value):
    return [part.strip() for part in str(value).split(',') if part.strip()]


def _websocket_path(value):
    """Split an early-data suffix (path?ed=2048) the way ws clients emit it."""
    path, _, tail = str(value).partition('?')
    params = urllib.parse.parse_qs(tail)
    early = params.get('ed', [None])[0]
    if not early or not str(early).isdigit():
        return path or '/', {}
    return path or '/', {'maxEarlyData': min(int(early), 1024 ** 2),
                         'earlyDataHeaderName': 'Sec-WebSocket-Protocol'}


def parse_link(link):
    """Parse a vless:// share link into a normalized cascade payload."""
    raw = str(link or '').strip().strip('"\'')
    if not raw:
        raise CascadeError('Вставьте vless:// ключ верхней панели.')
    scheme, _, remainder = raw.partition('://')
    if scheme.lower() != 'vless' or not remainder:
        raise CascadeError('Поддерживаются только vless:// ключи, а не этот формат.')
    if '@' not in remainder:
        raise CascadeError('В ключе нет разделителя «@» — это не клиентский vless:// ключ.')
    userinfo, _, hostport = remainder.rpartition('@')
    userinfo = urllib.parse.unquote(userinfo)
    if not UUID_RE.fullmatch(userinfo):
        raise CascadeError('В ключе нет корректного UUID пользователя.')
    # The fragment label and the query never contain the final "@": split the
    # authority from the parameters before parsing host and port.
    authority, _, tail = hostport.partition('?')
    query_string, _, fragment = tail.partition('#')
    authority = authority.rsplit('/', 1)[0]
    try:
        parsed = urllib.parse.urlsplit('vless://' + authority)
        port = parsed.port
        host = (parsed.hostname or '').strip().strip('[]')
    except ValueError as exc:
        raise CascadeError('Некорректный адрес или порт в ключе.') from exc
    if not host:
        raise CascadeError('В ключе не указан адрес сервера.')
    if port is None:
        port = 443
    if not 1 <= int(port) <= 65535:
        raise CascadeError('Некорректный порт в ключе.')
    if host.lower() in ('localhost', '::1') or host.startswith('127.'):
        raise CascadeError('Каскад должен указывать на удалённый сервер, а не на саму панель.')
    try:
        address_ip = ipaddress.ip_address(host)
    except ValueError:
        address_ip = None
    else:
        if not address_ip.is_global:
            raise CascadeError('Каскад должен указывать на публичный IP-адрес или домен.')
    query = {key: values[0] for key, values in urllib.parse.parse_qs(query_string, keep_blank_values=True).items()}
    network = NETWORK_ALIASES.get(_first(query, 'type', 'network', 'obfs', default='tcp').lower())
    if network is None:
        raise CascadeError('Тип транспорта «%s» в каскаде не поддерживается.' % _first(query, 'type', 'network'))
    security = _first(query, 'security').lower()
    if not security and (query.get('sni') or query.get('fp') or query.get('pbk')):
        security = 'tls'
    if security not in ('', 'none', 'tls', 'reality'):
        raise CascadeError('Тип защиты «%s» в каскаде не поддерживается.' % security)
    security = 'none' if security in ('', 'none') else security
    flow = _first(query, 'flow')
    if flow and flow != 'xtls-rprx-vision':
        raise CascadeError('Flow «%s» в каскаде не поддерживается.' % flow)
    if flow and security == 'none':
        raise CascadeError('Flow требует TLS или Reality — в ключе защита отключена.')
    stream = {}
    if network == 'tcp':
        tcp = {}
        if _first(query, 'headerType').lower() == 'http':
            tcp['header'] = {'type': 'http',
                             'request': {'path': _host_header(_first(query, 'path', default='/') or '/'),
                                         'headers': {'Host': _host_header(_first(query, 'host'))}}}
        if tcp:
            stream['tcpSettings'] = tcp
    elif network == 'ws':
        ws = {}
        path, early = _websocket_path(_first(query, 'path', default='/') or '/')
        ws['path'] = path
        ws_host = _first(query, 'host')
        if ws_host:
            ws['headers'] = {'Host': ws_host}
        ws.update(early)
        stream['wsSettings'] = ws
    elif network == 'httpupgrade':
        upgrade = {'path': _first(query, 'path', default='/') or '/'}
        if _first(query, 'host'):
            upgrade['host'] = _first(query, 'host')
        stream['httpupgradeSettings'] = upgrade
    elif network == 'grpc':
        service = _first(query, 'serviceName', 'path')
        if not service:
            raise CascadeError('В gRPC-ключе не указано имя сервиса (serviceName).')
        stream['grpcSettings'] = {'serviceName': service,
                                  'multiMode': _first(query, 'mode').lower() == 'multi'}
    elif network == 'xhttp':
        stream['xhttpSettings'] = {'path': _first(query, 'path', default='/') or '/',
                                   'mode': _first(query, 'mode', default='auto') or 'auto'}
        if _first(query, 'host'):
            stream['xhttpSettings']['host'] = _first(query, 'host')
    else:  # http / h2
        http = {'path': _first(query, 'path', default='/') or '/'}
        hosts = _host_header(_first(query, 'host'))
        if hosts:
            http['host'] = hosts
        stream['httpSettings'] = http
    if security == 'tls':
        tls = {'serverName': _first(query, 'sni', 'peer', default=host) or host}
        if _first(query, 'fp'):
            tls['fingerprint'] = _first(query, 'fp')
        alpn = _host_header(_first(query, 'alpn'))
        if alpn:
            tls['alpn'] = alpn
        if _first(query, 'allowInsecure', 'allowinsecure').lower() in ('1', 'true'):
            tls['allowInsecure'] = True
        stream['tlsSettings'] = tls
    elif security == 'reality':
        public = _first(query, 'pbk', 'publicKey')
        if not public:
            raise CascadeError('В Reality-ключе нет публичного ключа (pbk).')
        reality = {'serverName': _first(query, 'sni', default=host) or host,
                   'publicKey': public,
                   'shortId': _first(query, 'sid', 'shortId'),
                   'fingerprint': _first(query, 'fp', default='chrome') or 'chrome'}
        if _first(query, 'spx', 'spiderX'):
            reality['spiderX'] = _first(query, 'spx', 'spiderX')
        stream['realitySettings'] = reality
    return {'uuid': userinfo.lower(), 'address': host, 'port': int(port),
            'network': network, 'security': security, 'flow': flow,
            'stream': stream, 'label': urllib.parse.unquote(fragment).strip()[:120]}


def transport_label(record):
    names = {'tcp': 'TCP', 'ws': 'WebSocket', 'httpupgrade': 'HTTPUpgrade',
             'grpc': 'gRPC', 'xhttp': 'XHTTP', 'http': 'HTTP/2'}
    parts = [names.get(record.get('network'), record.get('network', '?'))]
    if record.get('security') == 'tls':
        parts.append('TLS')
    elif record.get('security') == 'reality':
        parts.append('Reality')
    return ' · '.join(parts)


def _normalize(record):
    if not isinstance(record, dict) or not UUID_RE.fullmatch(str(record.get('uuid', ''))):
        return None
    if not isinstance(record.get('address'), str) or not record.get('address'):
        return None
    try:
        port = int(record.get('port'))
    except (TypeError, ValueError):
        return None
    if not 1 <= port <= 65535 or record.get('network') not in NETWORK_ALIASES.values():
        return None
    if record.get('security') not in ('none', 'tls', 'reality'):
        return None
    if not isinstance(record.get('stream'), dict):
        return None
    mode = record.get('mode')
    users = record.get('users') if isinstance(record.get('users'), list) else []
    check = record.get('last_check')
    return {'id': str(record.get('id') or secrets.token_hex(8)),
            'name': str(record.get('name') or record.get('address'))[:80],
            'uuid': record['uuid'].lower(), 'address': record['address'], 'port': port,
            'network': record['network'], 'security': record['security'],
            'flow': record.get('flow') or '', 'stream': record['stream'],
            'enabled': bool(record.get('enabled', False)),
            'mode': mode if mode in ('all', 'users') else 'all',
            'users': [uid for uid in users if isinstance(uid, str) and UID_RE.fullmatch(uid)],
            'created_at': int(record.get('created_at') or 0),
            'last_check': check if isinstance(check, dict) else None,
            # Background operation bookkeeping: a job in flight and its error.
            'pending': bool(record.get('pending')),
            'op_error': str(record.get('op_error') or '')}


def load_cascades(path):
    """Tolerant read: a damaged file degrades to "no cascades", never to a broken config."""
    try:
        with open(path, encoding='utf-8') as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [record for record in (_normalize(item) for item in value) if record]


def save_cascades(path, cascades):
    normalized = []
    for record in cascades:
        item = _normalize(record)
        if item is None:
            raise CascadeError('Внутренняя ошибка: повреждённая запись каскада.')
        normalized.append(item)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(normalized, stream, ensure_ascii=True, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _is_own_address(host, own_domain):
    host = str(host or '').strip().lower().rstrip('.')
    own = str(own_domain or '').strip().lower().rstrip('.')
    return bool(host and own and host == own)


def prepare(link, name, own_domain, cascades):
    """Validate a pasted link against the panel itself and existing cascades."""
    if len(cascades) >= MAX_CASCADES:
        raise CascadeError('Достигнут лимит из %d каскадов.' % MAX_CASCADES)
    payload = parse_link(link)
    if _is_own_address(payload['address'], own_domain):
        raise CascadeError('Ключ ведёт на эту же панель — каскадировать панель саму на себя нельзя.')
    if any(item['uuid'] == payload['uuid'] and item['address'].lower() == payload['address'].lower()
           and item['port'] == payload['port'] and item['network'] == payload['network']
           and item['stream'].get('xhttpSettings', {}).get('path') == payload['stream'].get('xhttpSettings', {}).get('path')
           and item['stream'].get('wsSettings', {}).get('path') == payload['stream'].get('wsSettings', {}).get('path')
           for item in cascades):
        raise CascadeError('Такой каскад уже добавлен.')
    name = str(name or '').strip() or payload['label'] or payload['address']
    if len(name) > 80 or any(ord(char) < 32 for char in name):
        raise CascadeError('Название каскада: до 80 видимых символов.')
    return {'id': secrets.token_hex(8), 'name': name, 'enabled': True, 'mode': 'all',
            'users': [], 'created_at': int(time.time()), 'last_check': None, **payload}


def build_outbound(record, tag):
    user = {'id': record['uuid'], 'encryption': 'none', 'level': 0}
    if record.get('flow'):
        user['flow'] = record['flow']
    return {'tag': tag, 'protocol': 'vless',
            'settings': {'vnext': [{'address': record['address'], 'port': int(record['port']),
                                    'users': [user]}]},
            'streamSettings': {'network': record['network'], 'security': record['security'],
                               **record.get('stream', {})}}


def _cascadable_uids(users):
    """Profiles whose traffic enters Xray and can be routed to a cascade:
    VLESS and Hysteria2 share the same inbound email scheme."""
    return [user for user in (users or [])
            if user.get('protocol') in ('vless', 'hysteria') and user.get('enabled', True)
            and UID_RE.fullmatch(str(user.get('id', '')))]


def route_assignment(cascades, users):
    """Resolve which enabled cascade carries each VLESS client.

    Returns ({tag: [emails]}, all_tag, {cascade_id: carries_bool}). Per-user
    rules always win over a catch-all, and among equal scopes the cascade
    higher in the list wins.
    """
    enabled = [record for record in (cascades or []) if record.get('enabled')]
    tags = {record['id']: 'cascade-' + record['id'] for record in enabled}
    eligible = {user['id'] for user in _cascadable_uids(users)}
    owner = {}
    carries = {record['id']: False for record in enabled}
    for record in enabled:
        if record.get('mode') != 'users':
            continue
        for uid in record.get('users', []):
            if uid in eligible and uid not in owner:
                owner[uid] = tags[record['id']]
                carries[record['id']] = True
    all_tag = None
    for record in enabled:
        if record.get('mode') == 'all':
            all_tag = tags[record['id']]
            carries[record['id']] = True
            break
    by_tag = {}
    for uid, tag in owner.items():
        by_tag.setdefault(tag, []).append(user_email(uid))
    return by_tag, all_tag, carries


def xray_additions(cascades, users):
    """Outbounds and routing rules to merge into the generated Xray config."""
    enabled = [record for record in (cascades or []) if record.get('enabled')]
    if not enabled:
        return [], []
    by_tag, all_tag, _ = route_assignment(cascades, users)
    outbounds = [build_outbound(record, 'cascade-' + record['id']) for record in enabled]
    rules = []
    for record in enabled:
        emails = by_tag.get('cascade-' + record['id'])
        if emails:
            rules.append({'type': 'field', 'user': emails, 'outboundTag': 'cascade-' + record['id']})
    if all_tag:
        # VLESS and Hysteria2 inbounds both cascade; UDP inside Hysteria2
        # rides XHTTP UDP-over-TCP, which needs a modern Xray on the upstream.
        rules.append({'type': 'field', 'inboundTag': ['vless-xhttp', 'hysteria2'],
                      'outboundTag': all_tag})
    return outbounds, rules


def wait_for_port(port, process, deadline=5.0):
    limit = time.monotonic() + deadline
    while time.monotonic() < limit:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def ping(record, xray_bin=XRAY_BIN, curl_bin='curl'):
    """Reachability test through the full cascade chain: Xray to the upstream,
    then an HTTP request exiting on the far side. Measures round-trip time."""
    checked_at = int(time.time())
    outbound = build_outbound(record, 'cascade-probe')
    probe = {'ok': False, 'ms': 0, 'message': '', 'checked_at': checked_at}
    process = None
    try:
        with socket.socket() as holder:
            holder.bind(('127.0.0.1', 0))
            port = holder.getsockname()[1]
        config = {'log': {'loglevel': 'warning'},
                  'inbounds': [{'tag': 'probe', 'listen': '127.0.0.1', 'port': port,
                                'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': False}}],
                  'outbounds': [outbound, {'tag': 'direct', 'protocol': 'freedom'}]}
        with tempfile.TemporaryDirectory(prefix='onyx-cascade-') as directory:
            path = os.path.join(directory, 'probe.json')
            with open(path, 'w', encoding='utf-8') as stream:
                json.dump(config, stream, ensure_ascii=True)
            try:
                process = subprocess.Popen([xray_bin, 'run', '-config', path],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except OSError:
                probe['message'] = 'Не удалось запустить Xray для проверки каскада.'
                return probe
            if not wait_for_port(port, process):
                stderr = b''
                try:
                    stderr = process.stderr.read() or b''
                except Exception:
                    pass
                detail = stderr.decode('utf-8', 'replace').strip()[-300:]
                probe['message'] = 'Xray не поднял туннель проверки: ' + (detail or 'процесс завершился без ошибок.')
                return probe
            try:
                result = subprocess.run(
                    [curl_bin, '-sS', '-o', os.devnull, '--socks5-hostname', '127.0.0.1:%d' % port,
                     '--max-time', '9', '-w', '%{http_code} %{time_total}', PING_URL],
                    capture_output=True, text=True, timeout=12)
            except subprocess.TimeoutExpired:
                probe['message'] = 'Трафик не прошёл через каскад за отведённое время.'
                return probe
            if result.returncode:
                probe['message'] = 'Каскад не отвечает: ' + (result.stderr or '').strip()[-200:]
                return probe
            fields = (result.stdout or '').split()
            code = int(fields[0]) if fields and fields[0].isdigit() else 0
            seconds = float(fields[1]) if len(fields) > 1 and fields[1].replace('.', '', 1).isdigit() else 0.0
            if not 200 <= code < 400:
                probe['message'] = 'Через каскад пришёл ответ HTTP %s.' % (code or '?')
                return probe
            probe.update({'ok': True, 'ms': int(seconds * 1000)})
            # Report the exit IP the upstream gives out: admins check it against
            # whatismyip-style sites to confirm the cascade is really applied.
            try:
                ipresult = subprocess.run(
                    [curl_bin, '-sS', '--max-time', '6', '--socks5-hostname', '127.0.0.1:%d' % port,
                     'https://api.ipify.org'], capture_output=True, text=True, timeout=9)
                exit_ip = (ipresult.stdout or '').strip()
                if ipresult.returncode == 0 and re.fullmatch(r'[0-9.]{7,15}', exit_ip):
                    probe['exit_ip'] = exit_ip
            except Exception:
                pass
            return probe
    finally:
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
