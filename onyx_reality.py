"""VLESS + Reality inbound: TLS handshake masqueraded as a whitelisted site.

Reality state lives in /var/lib/onyx-panel/reality.json (0600): port, dest
(the masquerade target host:443), server names, an X25519 key pair and short
ids. The inbound is appended to the generated Xray config only while enabled
and only when there are enabled vless users to serve — disabled, the config is
byte-identical to a panel without the feature.

The mask check verifies the target site satisfies Reality's requirements
(TLS 1.3, HTTP/2, X25519 key exchange); the self test walks the whole chain
through a throwaway socks probe into our own inbound, like the WARP check.
"""
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlencode, quote

import onyx_warp

XRAY_BIN = onyx_warp.XRAY_BIN
IP_URL = onyx_warp.IP_URL
DEFAULT_PORT = 2053
DEFAULT_DEST = 'www.wildberries.ru:443'
DEST_RE = re.compile(r'^[a-zA-Z0-9._\-]+:\d{1,5}$')
SHORT_ID_RE = re.compile(r'^[0-9a-f]{0,16}$')
KEY_RE = re.compile(r'^[A-Za-z0-9+/]{43}=?$')
_lock = onyx_warp._lock


class RealityError(ValueError):
    pass


def load(path):
    try:
        with open(path, encoding='utf-8') as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return value


def save(path, state):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.reality-', dir=directory)
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


def validate(state):
    port = int(state.get('port', 0) or 0)
    if not 1024 <= port <= 65535:
        raise RealityError('Порт Reality должен быть в диапазоне 1024–65535.')
    state['port'] = port
    dest = str(state.get('dest', '') or '')
    if not DEST_RE.match(dest):
        raise RealityError('Маска должна иметь вид host:443, например ' + DEFAULT_DEST + '.')
    state['dest'] = dest
    names = state.get('server_names') or [dest.rsplit(':', 1)[0]]
    if not isinstance(names, list) or not names or any(not re.match(r'^[a-zA-Z0-9._\-]+$', str(n)) for n in names):
        raise RealityError('SNI маски указан некорректно.')
    state['server_names'] = [str(n).lower() for n in names]
    # Xray 26+ принимает X25519-ключи Reality только без base64-padding (43 символа).
    state['private_key'] = str(state.get('private_key', '')).rstrip('=')
    state['public_key'] = str(state.get('public_key', '')).rstrip('=')
    if not KEY_RE.match(state['private_key']):
        raise RealityError('Приватный ключ Reality должен быть X25519-ключом в base64.')
    if not KEY_RE.match(state['public_key']):
        raise RealityError('Публичный ключ Reality должен быть X25519-ключом в base64.')
    ids = state.get('short_ids')
    if not isinstance(ids, list) or not ids or any(not SHORT_ID_RE.match(str(i)) for i in ids):
        raise RealityError('Short IDs Reality должны быть hex-строками до 16 символов.')
    state['short_ids'] = [str(i) for i in ids]
    return state


def setup(path, port=DEFAULT_PORT, dest=DEFAULT_DEST):
    """Generate keys and short ids, enable the inbound."""
    if not DEST_RE.match(str(dest or '')):
        raise RealityError('Маска должна иметь вид host:443, например ' + DEFAULT_DEST + '.')
    private_key, public_key = onyx_warp.keypair()
    state = validate({'enabled': True, 'port': port, 'dest': dest,
                      'server_names': [dest.rsplit(':', 1)[0]],
                      'private_key': private_key, 'public_key': public_key,
                      'short_ids': [secrets.token_hex(4) for _ in range(4)],
                      'enabled_at': int(time.time())})
    with _lock:
        save(path, state)
    return state


def enabled(state):
    return bool(state.get('enabled')) and bool(state.get('private_key'))


def eligible_users(users):
    """Enabled vless profiles (direct users and subscription devices)."""
    return [u for u in users or []
            if isinstance(u, dict) and u.get('enabled', True)
            and u.get('protocol', 'web') == 'vless' and u.get('secret')]


def inbound(state, users):
    """The vless-reality inbound dict, or None while disabled / without users."""
    if not enabled(state):
        return None
    clients = [{'id': u['secret'], 'email': onyx_warp.EMAIL_PREFIX + str(u['id']),
                'level': 0, 'flow': 'xtls-rprx-vision'} for u in eligible_users(users)]
    if not clients:
        return None
    return {'tag': 'vless-reality', 'listen': '0.0.0.0', 'port': int(state['port']),
            'protocol': 'vless',
            'settings': {'clients': clients, 'decryption': 'none'},
            'streamSettings': {'network': 'tcp', 'security': 'reality',
                               'realitySettings': {'show': False, 'dest': state['dest'],
                                                   'xver': 0, 'serverNames': state['server_names'],
                                                   'privateKey': state['private_key'],
                                                   'shortIds': state['short_ids']}},
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls', 'quic'], 'routeOnly': True}}


def link(state, secret, name='Proxy', host=''):
    """vless:// client link for this Reality inbound; '' while disabled."""
    if not enabled(state):
        return ''
    query = urlencode({'encryption': 'none', 'security': 'reality', 'flow': 'xtls-rprx-vision',
                       'pbk': state.get('public_key', ''), 'fp': 'chrome',
                       'sni': state['server_names'][0], 'sid': state['short_ids'][0],
                       'spx': '/', 'type': 'tcp'})
    from urllib.parse import quote
    label = quote(name or 'Proxy', safe='')
    if not host:
        raise RealityError('Не указан адрес для ссылки Reality.')
    return ('vless://' + quote(str(secret), safe='-') + '@' + host + ':' + str(state['port'])
            + '?' + query + '#' + label)


def check_dest(dest, timeout=10, curl_bin='curl'):
    """Verify the masquerade target supports TLS 1.3 + h2 + X25519.

    HTTP/2 is probed with curl (site WAFs often withhold ALPN from a bare
    openssl handshake), TLS 1.3 and the X25519 key exchange with openssl."""
    host = str(dest).rsplit(':', 1)[0]
    result = {'ok': False, 'message': '', 'checked_at': int(time.time())}
    try:
        tls = subprocess.run(['openssl', 's_client', '-connect', str(dest), '-servername', host,
                              '-tls1_3', '-brief'], input='', capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        result['message'] = 'Не удалось запустить openssl: ' + str(exc)
        return result
    output = (tls.stdout or '') + (tls.stderr or '')
    if 'TLSv1.3' not in output:
        result['message'] = 'Сайт ' + host + ' не поддерживает TLS 1.3 — маска Reality не подойдёт.'
        return result
    x25519 = 'X25519' in output
    try:
        http = subprocess.run([curl_bin, '-sI', '--http2', '-o', os.devnull,
                               '-w', '%{http_version}', '--max-time', str(timeout), 'https://' + host],
                              capture_output=True, text=True, timeout=timeout + 2)
    except (OSError, subprocess.SubprocessError) as exc:
        result['message'] = 'Не удалось запустить curl: ' + str(exc)
        return result
    h2 = (http.stdout or '').strip().startswith('2')
    missing = [name for name, ok in (('HTTP/2', h2), ('X25519', x25519)) if not ok]
    if missing:
        result['message'] = ('Сайт ' + host + ' не подходит для маски Reality: нет ' +
                             ', '.join(missing) + '.')
        return result
    result.update(ok=True, message='Маска подходит: ' + host + ' отвечает TLS 1.3, HTTP/2, X25519.')
    return result


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


def selftest(state, uuid, host='127.0.0.1', xray_bin=XRAY_BIN, curl_bin='curl'):
    """End-to-end probe: socks -> vless-reality outbound -> this inbound."""
    result = {'ok': False, 'message': '', 'checked_at': int(time.time())}
    if not enabled(state):
        result['message'] = 'Reality не включён.'
        return result
    try:
        holder = socket.socket()
        holder.bind(('127.0.0.1', 0))
        port = holder.getsockname()[1]
        holder.close()
    except OSError:
        result['message'] = 'Не удалось занять локальный порт для проверки.'
        return result
    outbound = {'protocol': 'vless',
                'settings': {'vnext': [{'address': host, 'port': int(state['port']),
                                        'users': [{'id': uuid, 'encryption': 'none',
                                                   'flow': 'xtls-rprx-vision', 'level': 0}]}]},
                'streamSettings': {'network': 'tcp', 'security': 'reality',
                                   'realitySettings': {'serverName': state['server_names'][0],
                                                       'fingerprint': 'chrome',
                                                       'publicKey': state.get('public_key', ''),
                                                       'shortId': state['short_ids'][0],
                                                       'spiderX': '/'}},
                'tag': 'reality-probe'}
    config = {'log': {'loglevel': 'warning'},
              'inbounds': [{'tag': 'probe', 'listen': '127.0.0.1', 'port': port,
                            'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': False}}],
              'outbounds': [outbound, {'tag': 'direct', 'protocol': 'freedom'}]}
    tmpdir = tempfile.TemporaryDirectory(prefix='onyx-reality-')
    process = None
    try:
        path = os.path.join(tmpdir.name, 'probe.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(config, stream, ensure_ascii=True)
        try:
            process = subprocess.Popen([xray_bin, 'run', '-config', path],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError:
            result['message'] = 'Не удалось запустить Xray для проверки Reality.'
            return result
        if not _wait_port(port, process):
            stderr = b''
            try:
                stderr = process.stderr.read() or b''
            except Exception:
                pass
            detail = stderr.decode('utf-8', 'replace').strip()[-260:]
            result['message'] = 'Xray не поднял пробу Reality: ' + (detail or 'процесс завершился.')
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
        result['message'] = ('Подключение через Reality не прошло за отведённое время — '
                             'проверьте маску, порт и ключи.')
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
