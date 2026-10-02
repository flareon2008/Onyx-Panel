"""Admin-triggered updates run outside the panel's cgroup."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from onyx_metrics import atomic_json, read_state

ROOT = Path('/var/lib/onyx-panel-update')
STATUS = ROOT / 'status.json'
NOTES = ROOT / 'notifications.json'
VERSION = Path('/etc/onyx-panel/version')
UNIT = 'onyx-panel-web-update.service'
# Onyx Panel ships self-contained: the updater normally reinstalls from the
# package already unpacked on this server. Set ONYX_UPDATE_REPOSITORY to check
# and pull releases from your own Git repository instead.
REPO = os.environ.get('ONYX_UPDATE_REPOSITORY', 'https://github.com/xCodeOn/Onyx-Panel.git')
PACKAGE_DIR = Path('/opt/onyx-panel-package')
UPDATER = '/usr/local/sbin/onyx-panel-update'


def package_available():
    """A usable local update package: both installers must be present."""
    return (PACKAGE_DIR / 'install-final.sh').is_file() and (PACKAGE_DIR / 'install-panel.sh').is_file()


def failure_message(log_path):
    """Return a safe, useful diagnosis without exposing URLs or credentials."""
    try:
        tail = log_path.read_text(encoding='utf-8', errors='replace')[-24000:].lower()
    except OSError:
        return 'Обновление завершилось ошибкой. Журнал обновления недоступен.'
    cases = (
        (('ssl connection timeout', 'connection timed out', 'could not resolve host'),
         'Не удалось скачать файлы релиза: репозиторий недоступен или соединение прервано.'),
        (('openflux-linux-amd64 is missing', 'missing assets/openflux-linux-amd64', 'openflux checksum verification failed'),
         'Пакет OpenFlux отсутствует или повреждён.'),
        (('xray checksum verification failed',), 'Архив Xray не прошёл проверку целостности.'),
        (('port 80 is occupied', 'port 443 is occupied', 'port 8080 is occupied'),
         'Один из обязательных портов занят другой программой.'),
        (('caddy reload failed', 'could not configure caddy', 'caddy diagnostic'),
         'Не удалось применить конфигурацию HTTPS/Caddy.'),
        (('no supported web proxy installation was found',),
         'Установленная версия панели не распознана безопасным обновлением.'),
    )
    for needles, message in cases:
        if any(needle in tail for needle in needles): return message
    return 'Обновление завершилось ошибкой. Откройте журнал через Onyx или SSH.'


def current_version():
    try: return VERSION.read_text(encoding='ascii').strip()
    except OSError: return 'unknown'


def version_tuple(value):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[~.-](rc\d+))?', value)
    if not m: return None
    return (*map(int, m.group(1, 2, 3)), 0 if m[4] else 1, int(m[4][2:]) if m[4] else 0)


def newer(tag, current):
    a, b = version_tuple(tag), version_tuple(current)
    return bool(a and b and a > b and re.fullmatch(r'v\d+\.\d+\.\d+', tag))


def unit_running():
    r = subprocess.run(['systemctl', 'show', UNIT, '-p', 'ActiveState', '--value'], capture_output=True, text=True, timeout=5)
    return r.stdout.strip() in ('active', 'activating', 'reloading')


def get_status():
    data = read_state(STATUS)
    # A killed/rebooted updater cannot remain "running" forever in the UI.
    if data.get('phase') in ('running', 'queued') and time.time() - data.get('started', 0) > 60:
        try:
            if not unit_running(): data.update(phase='interrupted', message='Обновление прервано. Проверьте журнал через Onyx/SSH.')
        except (OSError, subprocess.TimeoutExpired): pass
    data['current'] = current_version()
    data['available'] = newer(data.get('latest', ''), data['current'])
    data['can_install'] = bool(data.get('releases'))
    announce_finished(data)
    return data


# ---- Bell notifications -----------------------------------------------------
# The appbar bell keeps version events on disk: an "available" note appears
# when check_release finds a newer published tag; once an update finishes and
# the panel is back with the new code, the note is replaced by the release
# changelog. Notes survive restarts and are wiped only by "Очистить все".

MAX_NOTES = 50


def load_notes():
    items = read_state(NOTES).get('items')
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def save_notes(items):
    atomic_json(NOTES, {'items': items[-MAX_NOTES:]})


def notes_public():
    items = load_notes()
    return {'items': items, 'unread': sum(1 for item in items if not item.get('read'))}


def add_note(kind, version, changes=None, link=''):
    """Append or refresh an event; one note per (kind, version), read flag kept."""
    items = load_notes()
    record = {'kind': kind, 'version': version, 'created': int(time.time()), 'read': False,
              'changes': [str(change) for change in (changes or [])], 'link': str(link or ''),
              'current': current_version()}
    for index, item in enumerate(items):
        if item.get('kind') == kind and item.get('version') == version:
            record['read'] = bool(item.get('read'))
            record['created'] = item.get('created', record['created'])
            items[index] = record
            break
    else:
        items.append(record)
    save_notes(items)
    return record


def mark_notes_read():
    items = load_notes()
    for item in items: item['read'] = True
    save_notes(items)


def clear_notes():
    save_notes([])


def prune_available(current=''):
    """Drop "available" notes for versions that are already installed."""
    current = current or current_version()
    save_notes([item for item in load_notes()
                if not (item.get('kind') == 'available' and not newer(item.get('version', ''), current))])


def repo_slug():
    """owner/repo for GitHub API calls; empty for non-GitHub repositories."""
    match = re.fullmatch(r'https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?', str(REPO).strip())
    return f'{match.group(1)}/{match.group(2)}' if match else ''


def parse_notes(body):
    """Release markdown -> plain lines: drop headers, keep bullet items."""
    items = []
    for line in str(body or '').splitlines():
        text = line.strip()
        if not text or text.startswith('#'): continue
        if text.startswith(('- ', '* ')): text = text[2:].strip()
        if text: items.append(text[:500])
        if len(items) >= 50: break
    return items


def release_notes(tag):
    """Changelog lines and the release URL from the GitHub release of `tag`."""
    slug = repo_slug()
    if not slug: return [], ''
    try:
        import urllib.request
        request = urllib.request.Request(
            f'https://api.github.com/repos/{slug}/releases/tags/{tag}',
            headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Onyx-Panel'})
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.load(response)
    except Exception:
        return [], ''
    link = str(data.get('html_url') or f'https://github.com/{slug}/releases/tag/{tag}')
    return parse_notes(data.get('body')), link


def announce_finished(data):
    """A finished update becomes one bell note with the release changelog."""
    target = str(data.get('target', '') or '')
    if data.get('phase') != 'done' or not target or data.get('announced') == target: return
    if target.lstrip('v') != current_version().lstrip('v'):
        # The panel came back on a different version (rollback or manual fix):
        # nothing to announce, but stop re-checking this target forever.
        data['announced'] = target
        atomic_json(STATUS, data)
        return
    changes, link = release_notes(target)
    add_note('changelog', target, changes=changes, link=link)
    prune_available()
    data['announced'] = target
    atomic_json(STATUS, data)


def _lock(blocking=False):
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (ROOT / 'action.lock').open('a')
    os.chmod(lock.name, 0o600)
    try: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        lock.close()
        raise ValueError('Другая операция обновления уже выполняется.')
    return lock


def check_release():
    with _lock():
        state = get_status()
        if state.get('phase') in ('running', 'queued'): return state
        if time.time() - state.get('checked', 0) < 60: return state
        if not REPO:
            # Local package mode: the complete update package was copied to
            # /opt/onyx-panel-package during installation.
            local_version = ''
            try:
                local_version = (PACKAGE_DIR / 'version').read_text(encoding='ascii').strip()
            except OSError:
                pass
            if local_version and package_available():
                tags = ['v' + local_version.lstrip('v')]
                latest = tags[0]
                installed = current_version().lstrip('v')
                message = ('В пакете на сервере доступна версия ' + latest.lstrip('v') + '.'
                           if installed and version_tuple(latest) > version_tuple(installed)
                           else 'Установлена версия из пакета на сервере. Проверка внешних релизов не настроена.')
                state.update(latest=latest, releases=tags, checked=int(time.time()), phase='checked', message=message)
            else:
                state.update(latest='', releases=[], checked=int(time.time()), phase='checked',
                             message='Внешний источник обновлений не настроен (ONYX_UPDATE_REPOSITORY). '
                                     'Используйте onyx-panel-update из папки пакета Onyx Panel.')
            prune_available()
            if newer(latest, current_version()): add_note('available', latest)
            atomic_json(STATUS, state)
            return get_status()
        env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
        try:
            r = subprocess.run(['git', 'ls-remote', '--tags', '--refs', REPO, 'v[0-9]*'], capture_output=True, text=True, timeout=20, env=env)
            if r.returncode: raise ValueError('Репозиторий недоступен. Повторите позже.')
            tags = re.findall(r'refs/tags/(v\d+\.\d+\.\d+)\s*$', r.stdout, re.M)
            if not tags: raise ValueError('Опубликованные стабильные теги не найдены.')
            tags = sorted(set(tags), key=version_tuple, reverse=True)[:30]
            latest = tags[0]
            # Offer a short window around the installed release: up to two
            # newer ones (so an update can be selected), the installed one and
            # two previous ones for rollback; older tags stay in the repository.
            installed = 'v' + current_version().lstrip('v')
            if installed in tags:
                idx = tags.index(installed)
                window = tags[max(0, idx - 2):idx + 3]
                if latest not in window:
                    window = ([latest] + window)[:5]
                tags = window
            else:
                tags = tags[:3]
            state.update(latest=latest, releases=tags, checked=int(time.time()), phase='checked', message='Версии загружены.')
            prune_available()
            if newer(latest, current_version()): add_note('available', latest)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('Не удалось проверить репозиторий. Повторите позже.')
        atomic_json(STATUS, state)
        return get_status()


def start_update(target=''):
    with _lock():
        state = get_status()
        if state.get('phase') in ('running', 'queued') or unit_running():
            raise ValueError('Обновление уже выполняется.')
        releases=state.get('releases',[])
        target=str(target or state.get('latest',''))
        if time.time() - state.get('checked', 0) > 600 or target not in releases:
            raise ValueError('Сначала обновите список и выберите опубликованный стабильный релиз.')
        if target.lstrip('v') == current_version().lstrip('v'):
            raise ValueError('Эта версия уже установлена.')
        target_version, installed_version = version_tuple(target), version_tuple(current_version())
        action = 'Откат' if target_version and installed_version and target_version < installed_version else 'Обновление'
        state.update(phase='queued', target=target, started=int(time.time()),
                     message=action+' запускается. Панель временно отключится.')
        atomic_json(STATUS, state)
        r = subprocess.run(['systemctl', 'start', '--no-block', UNIT], capture_output=True, text=True, timeout=10)
        if r.returncode:
            state.update(phase='failed', message='Не удалось запустить службу обновления.')
            atomic_json(STATUS, state)
            raise ValueError(state['message'])
        return state


def run_update():
    # The service may start before the HTTP request releases action.lock.
    with _lock(blocking=True):
        state = read_state(STATUS)
        tag = state.get('target', '')
        if (state.get('phase') != 'queued' or time.time() - state.get('started', 0) > 120 or
                tag not in state.get('releases',[]) or not version_tuple(tag) or tag.lstrip('v')==current_version().lstrip('v')):
            raise ValueError('Нет подтверждённого релиза для установки.')
        state.update(phase='running', message='Создание резервной копии и обновление. Подождите несколько минут.')
        atomic_json(STATUS, state)
    # Preserve status outside panel backup paths; run in a separate systemd unit.
    env = {**os.environ, 'ONYX_PANEL_REF': tag, 'GIT_TERMINAL_PROMPT': '0', 'DEBIAN_FRONTEND': 'noninteractive'}
    try:
        with (ROOT / 'update.log').open('w', encoding='utf-8') as log:
            os.chmod(log.name, 0o600)
            result = subprocess.run(['/usr/bin/bash', UPDATER], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env)
        state.update(phase='done' if result.returncode == 0 else 'failed', code=result.returncode,
                     message='Обновление завершено. Войдите в панель заново.' if result.returncode == 0 else failure_message(ROOT / 'update.log'))
    except OSError:
        state.update(phase='failed', message='Не удалось выполнить установщик. Проверьте журнал через SSH.')
    state['finished'] = int(time.time())
    atomic_json(STATUS, state)


if __name__ == '__main__':
    if sys.argv[1:] != ['run']: raise SystemExit('Usage: onyx_update.py run')
    run_update()
