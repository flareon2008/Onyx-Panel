"""Cloudflare WARP as a per-client exit: WireGuard outbound inside Xray.

The state lives in /var/lib/onyx-panel/warp.json (0600): keys, endpoint,
reserved bytes from the Cloudflare client_id and the list of Xray user ids
whose traffic must leave through WARP. Nothing here touches interfaces,
routes or firewall — the tunnel is a userspace Xray outbound, so the config
still goes through the regular xray -test + atomic replace + rollback path.

Setup comes in two flavours: register a fresh WARP device through Cloudflare's
API (the same call wgcf makes), or paste an existing WireGuard/wgcf config.
The paste path is the safety net for the day Cloudflare changes the API.
"""
import base64
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

API_URL = 'https://api.cloudflareclient.com/v0a2158/reg'
PEER_PUBLIC_KEY = 'bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo='
DEFAULT_ENDPOINT = 'engage.cloudflareclient.com:2408'
DEFAULT_ADDRESS = '172.16.0.2'
MTU = 1280
EMAIL_PREFIX = 'panel:'   # same scheme sync_xray uses for client emails
IP_URL = 'https://api.ipify.org'
KEY_RE = re.compile(r'^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$')
ENDPOINT_RE = re.compile(r'^[a-zA-Z0-9._\-]+:\d{1,5}$')

_lock = threading.Lock()


class WarpError(ValueError):
    pass


def configured(state):
    return bool(state.get('private_key')) and bool(state.get('peer_public_key', PEER_PUBLIC_KEY))


def load(path):
    try:
        with open(path, encoding='utf-8') as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    if not isinstance(value.get('users'), list):
        value['users'] = []
    return value


def save(path, state):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.warp-', dir=directory)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(state, stream, ensure_ascii=True, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def reset(path):
    with _lock:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _validate_keys(state):
    if not KEY_RE.match(str(state.get('private_key', ''))):
        raise WarpError('Приватный ключ WARP должен быть WireGuard-ключом в base64 (44 символа).')
    if not KEY_RE.match(str(state.get('peer_public_key', ''))):
        raise WarpError('Публичный ключ пира WARP должен быть WireGuard-ключом в base64 (44 символа).')
    endpoint = str(state.get('endpoint', DEFAULT_ENDPOINT))
    if not ENDPOINT_RE.match(endpoint):
        raise WarpError('Endpoint WARP должен иметь вид host:port, например ' + DEFAULT_ENDPOINT + '.')
    state['endpoint'] = endpoint
    reserved = state.get('reserved')
    if reserved is not None:
        if (not isinstance(reserved, list) or
                any(not isinstance(b, int) or not 0 <= b <= 255 for b in reserved) or
                not 1 <= len(reserved) <= 3):
            state['reserved'] = []
    return state


_P = 2 ** 255 - 19
_A24 = 121665  # (A - 2) / 4 for Curve25519, A = 486662


def _x25519_base(scalar32):
    """RFC 7748 X25519 with u=9: returns the raw 32-byte public key."""
    def cswap(swap, a, b):
        return (b, a) if swap else (a, b)
    k = bytearray(scalar32)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    k = int.from_bytes(k, 'little')
    x_1, x_2, z_2, x_3, z_3 = 9, 1, 0, 9, 1
    swap = 0
    for t in reversed(range(255)):
        k_t = (k >> t) & 1
        swap ^= k_t
        if swap:
            x_2, x_3 = x_3, x_2
            z_2, z_3 = z_3, z_2
        swap = k_t
        a = (x_2 + z_2) % _P
        aa = a * a % _P
        b = (x_2 - z_2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x_3 + z_3) % _P
        d = (x_3 - z_3) % _P
        da = d * a % _P
        cb = c * b % _P
        x_3 = (da + cb) ** 2 % _P
        z_3 = x_1 * (da - cb) ** 2 % _P
        x_2 = aa * bb % _P
        z_2 = e * (aa + _A24 * e) % _P
    if swap:
        x_2, x_3 = x_3, x_2
        z_2, z_3 = z_3, z_2
    return ((x_2 * pow(z_2, _P - 2, _P)) % _P).to_bytes(32, 'little')


def keypair():
    """WireGuard keypair: pure-python X25519, no external dependencies."""
    private = bytearray(os.urandom(32))
    private[0] &= 248
    private[31] &= 127
    private[31] |= 64
    private_key = bytes(private)
    public_key = _x25519_base(private_key)
    return base64.b64encode(private_key).decode(), base64.b64encode(public_key).decode()


def register(path):
    """Create a fresh WARP device via Cloudflare's API (wgcf-compatible call)."""
    private_key, public_key = keypair()
    body = json.dumps({'key': public_key, 'install_id': '', 'fcm_token': '',
                       'tos': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
                       'model': 'Linux', 'locale': 'en_US',
                       'serial_number': __import__('uuid').uuid4().hex.upper()}).encode()
    request = urllib.request.Request(API_URL, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'User-Agent': 'okhttp/3.12.1'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read(65537).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read(300).decode('utf-8', 'replace')
        except Exception:
            pass
        raise WarpError('Cloudflare отклонил регистрацию (HTTP %d). Используйте ручной режим: вставьте конфиг от wgcf. %s'
                        % (exc.code, detail[:120])) from exc
    except (OSError, ValueError) as exc:
        raise WarpError('Не удалось связаться с API Cloudflare. Используйте ручной режим: вставьте конфиг от wgcf.') from exc
    config = payload.get('config') if isinstance(payload.get('config'), dict) else payload
    interface = config.get('interface') if isinstance(config.get('interface'), dict) else {}
    peers = config.get('peers') if isinstance(config.get('peers'), list) else []
    peer = peers[0] if peers and isinstance(peers[0], dict) else {}
    endpoints = peer.get('endpoint') if isinstance(peer.get('endpoint'), dict) else {}
    address = str((interface.get('addresses') or {}).get('v4', DEFAULT_ADDRESS)).split('/')[0] or DEFAULT_ADDRESS
    client_id = str(config.get('client_id', '') or '')
    reserved = []
    if re.fullmatch(r'[0-9a-fA-F]{2,6}', client_id):
        reserved = list(bytes.fromhex(client_id))[:3]
    state = _validate_keys({'private_key': private_key,
                            'peer_public_key': str(peer.get('public_key', '') or PEER_PUBLIC_KEY),
                            'address': address,
                            'endpoint': str(endpoints.get('v4', '') or DEFAULT_ENDPOINT),
                            'reserved': reserved, 'client_id': client_id,
                            'registered_at': int(time.time()), 'exit_ip': '', 'checked_at': 0})
    with _lock:
        current = load(path)
        state['users'] = current.get('users', [])
        save(path, state)
    return state


def import_config(path, text):
    """Parse a pasted WireGuard/wgcf profile: the manual setup fallback."""
    sections = {}
    section = None
    for line in str(text or '').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('['):
            section = line.strip('[]').strip().lower()
            sections.setdefault(section, {})
            continue
        if '=' not in line or section is None:
            continue
        key, _, value = line.partition('=')
        sections[section][key.strip().lower()] = value.strip()
    interface = sections.get('interface', {})
    peer = sections.get('peer', {})
    address = (interface.get('address', '').split(',')[0] or DEFAULT_ADDRESS).split('/')[0]
    state = _validate_keys({'private_key': interface.get('privatekey', ''),
                            'peer_public_key': peer.get('publickey', '') or PEER_PUBLIC_KEY,
                            'address': address or DEFAULT_ADDRESS,
                            'endpoint': peer.get('endpoint', '') or DEFAULT_ENDPOINT,
                            'reserved': [], 'client_id': '',
                            'registered_at': 0, 'exit_ip': '', 'checked_at': 0})
    if not configured(state):
        raise WarpError('В конфиге не хватает PrivateKey или PublicKey пира.')
    with _lock:
        current = load(path)
        state['users'] = current.get('users', [])
        save(path, state)
    return state


def xray_outbound(state):
    settings = {'secretKey': state.get('private_key', ''),
                'address': [state.get('address', DEFAULT_ADDRESS)],
                'peers': [{'publicKey': state.get('peer_public_key', PEER_PUBLIC_KEY),
                           'endpoint': state.get('endpoint', DEFAULT_ENDPOINT)}],
                'mtu': MTU}
    if state.get('reserved'):
        settings['reserved'] = state['reserved']
    return {'tag': 'warp', 'protocol': 'wireguard', 'settings': settings}


def xray_additions(state, uids):
    """Outbound + per-user routing rule; empty lists when off for everyone."""
    ids = []
    for uid in uids or []:
        uid = str(uid)
        if uid and uid not in ids:
            ids.append(uid)
    if not configured(state) or not ids:
        return [], []
    return [xray_outbound(state)], [{'type': 'field',
                                     'user': [EMAIL_PREFIX + uid for uid in ids],
                                     'outboundTag': 'warp'}]


def set_users(path, uids, enabled):
    """Add or remove Xray user ids from the WARP rule; returns updated list."""
    with _lock:
        state = load(path)
        users = [u for u in state.get('users', []) if isinstance(u, str)]
        for uid in uids:
            uid = str(uid)
            if enabled and uid not in users:
                users.append(uid)
            if not enabled and uid in users:
                users.remove(uid)
        state['users'] = users
        save(path, state)
    return users


def has_users(path, uids):
    ids = set(uids or [])
    return bool(ids.intersection(load(path).get('users', [])))


def record_check(path, result):
    with _lock:
        state = load(path)
        state['exit_ip'] = str(result.get('exit_ip', ''))
        state['checked_at'] = int(result.get('checked_at', 0) or time.time())
        save(path, state)


def _wait_port(port, process, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def check(state, xray_bin='xray', curl_bin='curl'):
    """Throwaway socks probe through the WARP outbound; reports the exit IP."""
    result = {'ok': False, 'exit_ip': '', 'message': '', 'checked_at': int(time.time())}
    if not configured(state):
        result['message'] = 'WARP не настроен: сначала зарегистрируйте устройство или вставьте конфиг.'
        return result
    try:
        holder = socket.socket()
        holder.bind(('127.0.0.1', 0))
        port = holder.getsockname()[1]
        holder.close()
    except OSError:
        result['message'] = 'Не удалось занять локальный порт для проверки.'
        return result
    config = {'log': {'loglevel': 'warning'},
              'inbounds': [{'tag': 'probe', 'listen': '127.0.0.1', 'port': port,
                            'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': False}}],
              'outbounds': [xray_outbound(state), {'tag': 'direct', 'protocol': 'freedom'}]}
    tmpdir = tempfile.TemporaryDirectory(prefix='onyx-warp-')
    process = None
    try:
        path = os.path.join(tmpdir.name, 'probe.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(config, stream, ensure_ascii=True)
        try:
            process = subprocess.Popen([xray_bin, 'run', '-config', path],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError:
            result['message'] = 'Не удалось запустить Xray для проверки WARP.'
            return result
        if not _wait_port(port, process):
            stderr = b''
            try:
                stderr = process.stderr.read() or b''
            except Exception:
                pass
            detail = stderr.decode('utf-8', 'replace').strip()[-260:]
            result['message'] = 'Xray не поднял WARP-туннель: ' + (detail or 'процесс завершился без ошибок.')
            return result
        for _ in range(2):
            try:
                run = subprocess.run([curl_bin, '-sS', '--socks5-hostname', '127.0.0.1:%d' % port,
                                      '--max-time', '12', IP_URL],
                                     capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                continue
            exit_ip = (run.stdout or '').strip()
            if run.returncode == 0 and re.fullmatch(r'[0-9.]{7,15}', exit_ip):
                result.update(ok=True, exit_ip=exit_ip)
                return result
        result['message'] = ('Трафик не прошёл через WARP за отведённое время — проверьте ключи '
                             'и доступность ' + state.get('endpoint', DEFAULT_ENDPOINT) + ' с сервера.')
        return result
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
        tmpdir.cleanup()
