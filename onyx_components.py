#!/usr/bin/env python3
"""Component version manager for the local Onyx Panel server.

Xray and OpenFlux update from their release binaries. AmneziaWG builds from
the selected tag source with the Go toolchain shipped by the panel. MTProto
has no upstream releases: "refresh" re-runs the pinned bundled installer,
which rebuilds the binary and refreshes Telegram's public config.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from onyx_metrics import atomic_json, read_state

ROOT = Path("/var/lib/onyx-panel-components")
STATUS = ROOT / "status.json"
UNIT = "onyx-panel-component-update.service"
PACKAGE_DIR = Path("/opt/onyx-panel-package")
RELAY_PREFIX = "tproxy-server-52a5feb7fac38f68da5afef9cedd9b3bfc8473ca"
SPECS = {
    "xray": {
        "name": "Xray",
        "repo": "https://github.com/XTLS/Xray-core.git",
        "asset": "https://github.com/XTLS/Xray-core/releases/download/{tag}/Xray-linux-64.zip",
        "binary": Path("/opt/onyx-panel/xray/xray"),
        "service": "onyx-panel-xray.service",
        "mode": "asset",
    },
    "openflux": {
        "name": "OpenFlux",
        "repo": "https://github.com/damnurmum/OpenFlux-Android.git",
        "asset": "https://github.com/damnurmum/OpenFlux-Android/releases/download/{tag}/openflux-linux-amd64",
        "binary": Path("/opt/onyx-panel/openflux/openflux"),
        "service": "onyx-panel-openflux.service",
        "mode": "asset",
    },
    "awg": {
        "name": "AmneziaWG",
        "repo": "https://github.com/amnezia-vpn/amneziawg-go.git",
        "binary": Path("/usr/local/bin/amneziawg-go"),
        "mode": "source",
    },
    "mtproto": {
        "name": "MTProto",
        "binary": Path("/opt/MTProxy/objs/bin/mtproto-proxy"),
        "mode": "refresh",
    },
}


def _run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=kwargs.pop("timeout", 30), check=False, **kwargs)


def _version_tuple(value):
    numbers = re.findall(r"\d+", str(value))
    return tuple(int(x) for x in numbers[:4])


def _version_file(component):
    """Version stamp next to the binary; OpenFlux cannot report its own."""
    return SPECS[component]["binary"].parent / "version"


def _current(component):
    if component == "mtproto":
        marker = Path("/opt/MTProxy/.tproxy-commit")
        try:
            return marker.read_text(encoding="ascii").strip()[:8]
        except OSError:
            return "неизвестно"
    binary = SPECS[component]["binary"]
    if not binary.is_file():
        return "не установлен"
    commands = [[str(binary), "version"], [str(binary), "--version"], [str(binary), "-version"]]
    for command in commands:
        try:
            result = _run(command, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        value = (result.stdout + " " + result.stderr).strip().splitlines()
        if value:
            match = re.search(r"v?(\d+(?:\.\d+){1,3})", " ".join(value[:2]))
            if match:
                return match.group(1)
    # OpenFlux has no version flag: fall back to the install-time stamp, then
    # to the tag recorded by the last successful component install.
    fallbacks = []
    try:
        fallbacks.append(_version_file(component).read_text(encoding="ascii").strip())
    except OSError:
        pass
    fallbacks.append(str((read_state(STATUS).get("installed") or {}).get(component, "")))
    for source in fallbacks:
        if re.fullmatch(r"v?\d+(?:\.\d+){1,3}", source or ""):
            return source.lstrip("v")
    return "установлен"


def _tags(component):
    spec = SPECS[component]
    if spec.get("mode") == "refresh":
        return ["refresh"]
    if component == "openflux":
        # Mobile-only releases (no openflux-linux-amd64 asset) cannot be
        # installed — offer only tags whose release ships the server binary.
        api = spec["repo"][:-4] + "/releases?per_page=30" if spec["repo"].endswith(".git") else spec["repo"] + "/releases?per_page=30"
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        result = _run(["curl", "-fsSL", "--connect-timeout", "20", "--max-time", "40", api],
                      timeout=60, env=env)
        if result.returncode == 0:
            try:
                releases = json.loads(result.stdout)
            except ValueError:
                releases = None
            if isinstance(releases, list):
                tags = [str(item.get("tag_name", "")) for item in releases
                        if re.fullmatch(r"v\d+(?:\.\d+){1,3}", str(item.get("tag_name", "")))
                        and any(a.get("name") == "openflux-linux-amd64" for a in (item.get("assets") or []))]
                return sorted(tags, key=_version_tuple, reverse=True)[:30]
        # API unavailable — fall back to the plain tag list below.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = _run(["git", "ls-remote", "--tags", "--refs", spec["repo"], "v[0-9]*"],
                  timeout=25, env=env)
    if result.returncode:
        raise ValueError("Репозиторий компонента недоступен. Повторите позже.")
    tags = set(re.findall(r"refs/tags/(v\d+(?:\.\d+){1,3})\s*$", result.stdout, re.M))
    return sorted(tags, key=_version_tuple, reverse=True)[:30]


def catalog(force=False):
    state = read_state(STATUS)
    cached = state.get("catalog", {})
    if force or time.time() - int(state.get("checked", 0)) > 300 or not cached:
        cached = {name: _tags(name) for name in SPECS}
        state.update(catalog=cached, checked=int(time.time()), phase="checked",
                     message="Версии компонентов загружены.")
        atomic_json(STATUS, state)
    return {"current": {name: _current(name) for name in SPECS}, "catalog": cached,
            "phase": state.get("phase", "idle"), "message": state.get("message", "")}


_VERIFY_CACHE = {}


def verify(component, tag):
    """Immediate check that a release actually ships the server binary."""
    if component not in SPECS:
        raise ValueError("Некорректный компонент.")
    spec = SPECS[component]
    if spec.get("mode") == "refresh":
        return {"ok": True, "message": "Пересборка из исходников панели."}
    if not re.fullmatch(r"v\d+(?:\.\d+){1,3}", str(tag)):
        raise ValueError("Некорректная версия.")
    key = (component, str(tag))
    cached = _VERIFY_CACHE.get(key)
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    url = spec["asset"].format(tag=str(tag))
    result = _run(["curl", "-sIL", "-o", "/dev/null", "-w", "%{http_code}",
                   "--connect-timeout", "15", "--max-time", "30", url], timeout=40)
    output = (result.stdout or "").strip().splitlines()
    code = output[-1] if output else ""
    ok = result.returncode == 0 and code == "200"
    payload = {"ok": ok, "message": "" if ok else
               "В релизе " + str(tag) + " нет сборки для Linux — установка невозможна. Выберите другую версию."}
    _VERIFY_CACHE[key] = (time.time(), payload)
    return payload


def status():
    state = read_state(STATUS)
    state["current"] = {name: _current(name) for name in SPECS}
    return state


def start(component, tag):
    if component not in SPECS:
        raise ValueError("Некорректный компонент.")
    if SPECS[component].get("mode") == "refresh":
        if str(tag) != "refresh":
            raise ValueError("Для MTProto доступна только пересборка из исходников панели.")
    else:
        if not re.fullmatch(r"v\d+(?:\.\d+){1,3}", str(tag)):
            raise ValueError("Некорректная версия.")
        info = catalog()
        if tag not in info["catalog"].get(component, []):
            raise ValueError("Эта версия отсутствует среди опубликованных релизов.")
    state = read_state(STATUS)
    if state.get("phase") in ("queued", "running"):
        raise ValueError("Другая операция с компонентами уже выполняется.")
    state.update(phase="queued", component=component, target=tag, started=int(time.time()),
                 message=f"Подготовка {component} {tag}…")
    atomic_json(STATUS, state)
    result = _run(["systemctl", "start", "--no-block", UNIT], timeout=10)
    if result.returncode:
        state.update(phase="failed", message="Не удалось запустить обновление компонента.")
        atomic_json(STATUS, state)
        raise ValueError(state["message"])
    return state


def _download(url, destination):
    result = _run(["curl", "-fL", "--retry", "3", "--retry-all-errors", "--connect-timeout", "20",
                   "--max-time", "300", "-o", str(destination), url], timeout=360)
    if result.returncode or not destination.is_file() or destination.stat().st_size < 100000:
        raise RuntimeError("Не удалось скачать выбранный релиз. Возможно, в нём нет сборки для Linux — попробуйте другую версию.")


def _safe_extract_sources(archive, destination, expected_prefix):
    """Extract a source tarball whose members all live under expected_prefix."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.name != expected_prefix and not member.name.startswith(expected_prefix + "/"):
                raise RuntimeError("Архив исходников имеет неожиданную структуру.")
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination.resolve()) + os.sep):
                raise RuntimeError("Небезопасный путь внутри архива.")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            parent = target.parent
            parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _find_go():
    candidates = sorted(Path("/opt").glob("go*/bin/go"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    which = shutil.which("go")
    if which:
        return Path(which)
    raise RuntimeError("Go не найден. Переустановите панель — toolchain входит в пакет.")


def _active_awg_units():
    result = _run(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend",
                   "onyx-panel-awg@*.service"])
    return [line.split()[0] for line in result.stdout.splitlines()
            if line.split() and re.fullmatch(r"onyx-panel-awg(?:-[a-f0-9]{16})?\.service", line.split()[0])]


def _active_openflux_units():
    result = _run(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend",
                   "onyx-panel-openflux.service"])
    return [line.split()[0] for line in result.stdout.splitlines()
            if line.split() and re.fullmatch(r"onyx-panel-openflux\.service", line.split()[0])]


def _install(component, tag, directory):
    spec = SPECS[component]
    binary = spec["binary"]
    candidate = directory / "candidate"
    download = directory / "download"

    if spec.get("mode") == "asset":
        _download(spec["asset"].format(tag=tag), download)
        if component == "xray":
            result = subprocess.run(["unzip", "-q", str(download), "xray", "-d", str(directory)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
            if result.returncode:
                raise RuntimeError("Не удалось распаковать Xray.")
            (directory / "xray").replace(candidate)
        else:
            download.replace(candidate)
        os.chmod(candidate, 0o755)
        if _run(["readelf", "-h", str(candidate)], timeout=10).returncode:
            raise RuntimeError("Загруженный файл не является исполняемым Linux-бинарником.")
        if component == "xray":
            test = _run([str(candidate), "run", "-test", "-config", "/etc/onyx-panel-xray/config.json"], timeout=20)
            if test.returncode:
                raise RuntimeError("Выбранная версия Xray не принимает текущую конфигурацию.")
            active = [spec["service"]] if _run(["systemctl", "is-active", "--quiet", spec["service"]]).returncode == 0 else []
        else:
            test = _run([str(candidate), "--help"], timeout=10)
            if test.returncode not in (0, 1, 2):
                raise RuntimeError("Выбранный бинарник OpenFlux не запускается.")
            active = _active_openflux_units()
    elif spec.get("mode") == "source":
        go = _find_go()
        archive = directory / "awg-src.tar.gz"
        result = _run(["curl", "-fsSL", "--retry", "3", "--retry-all-errors", "--connect-timeout", "20",
                       "--max-time", "300", "-o", str(archive),
                       "https://codeload.github.com/amnezia-vpn/amneziawg-go/archive/" + tag + ".tar.gz"],
                      timeout=360)
        if result.returncode or not archive.is_file() or archive.stat().st_size < 10000:
            raise RuntimeError("Не удалось скачать исходники AmneziaWG.")
        srcdir = directory / "src"
        _safe_extract_sources(archive, srcdir, "amneziawg-go-" + tag[1:])
        env = {**os.environ, "PATH": str(go.parent) + ":" + os.environ.get("PATH", "")}
        build = _run(["make", "-C", str(srcdir)], timeout=900, env=env)
        if build.returncode or not (srcdir / "amneziawg-go").is_file():
            tail = (build.stderr or build.stdout or "")[-400:]
            raise RuntimeError("Сборка AmneziaWG не удалась. " + tail)
        shutil.copy2(srcdir / "amneziawg-go", candidate)
        os.chmod(candidate, 0o755)
        if _run(["readelf", "-h", str(candidate)], timeout=10).returncode:
            raise RuntimeError("Собранный файл не является исполняемым Linux-бинарником.")
        if _run([str(candidate), "--version"], timeout=10).returncode not in (0, 1):
            raise RuntimeError("Собранный бинарник AmneziaWG не запускается.")
        active = _active_awg_units()
    else:
        bundle = PACKAGE_DIR / "assets" / "tproxy-server-52a5feb.tar.gz"
        if not bundle.is_file():
            raise RuntimeError("Локальный пакет панели не найден (/opt/onyx-panel-package).")
        srcdir = directory / "relay"
        _safe_extract_sources(bundle, srcdir, RELAY_PREFIX)
        installer = srcdir / "deploy" / "install-mtproxy.sh"
        if not installer.is_file():
            raise RuntimeError("В пакете нет установщика MTProxy.")
        os.chmod(installer, 0o700)
        result = _run(["bash", str(installer)], timeout=1800)
        if result.returncode:
            tail = (result.stderr or result.stdout or "")[-400:]
            raise RuntimeError("Пересборка MTProto не удалась. " + tail)
        if not binary.is_file():
            raise RuntimeError("Бинарник MTProxy не появился после сборки.")
        restart = _run(["systemctl", "restart", "mtproxy.service"], timeout=60)
        if restart.returncode or _run(["systemctl", "is-active", "--quiet", "mtproxy.service"], timeout=10).returncode:
            raise RuntimeError("mtproxy.service не запустился после пересборки.")
        return

    backup = directory / "previous"
    shutil.copy2(binary, backup)
    try:
        for service in active:
            _run(["systemctl", "stop", service], timeout=30)
        shutil.copy2(candidate, binary)
        os.chmod(binary, 0o755)
        for service in active:
            result = _run(["systemctl", "restart", service], timeout=40)
            if result.returncode or _run(["systemctl", "is-active", "--quiet", service], timeout=10).returncode:
                raise RuntimeError("Служба не запустилась с выбранной версией.")
    except Exception:
        shutil.copy2(backup, binary)
        os.chmod(binary, 0o755)
        for service in active:
            _run(["systemctl", "restart", service], timeout=40)
        raise


def run():
    import fcntl
    lock_path = Path("/run/lock/onyx-panel.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("a")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        state = read_state(STATUS)
        state.update(phase="failed", message="Установка или другое обновление уже выполняется.")
        atomic_json(STATUS, state)
        return
    state = read_state(STATUS)
    component, tag = state.get("component"), state.get("target")
    if state.get("phase") != "queued" or component not in SPECS:
        raise SystemExit("No queued component update")
    state.update(phase="running", message=f"Устанавливается {component} {tag}. Создана резервная копия.")
    atomic_json(STATUS, state)
    try:
        with tempfile.TemporaryDirectory(prefix="onyx-component-") as directory:
            _install(component, tag, Path(directory))
        state.update(phase="done", message=f"{component} {tag} установлен. Проверка службы пройдена.")
        try:
            stamp = _version_file(component)
            stamp.write_text(tag + "\n", encoding="ascii")
            os.chmod(stamp, 0o644)
        except OSError:
            pass
        state["installed"] = {**(state.get("installed") or {}), component: tag}
    except Exception as exc:
        state.update(phase="failed", message="Изменение отменено: " + str(exc)[:600])
    state["finished"] = int(time.time())
    atomic_json(STATUS, state)


if __name__ == "__main__":
    if sys.argv[1:] != ["run"]:
        raise SystemExit("Usage: onyx_components.py run")
    run()
