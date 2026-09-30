#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/opt/onyx-panel"
DATA_DIR="/var/lib/onyx-panel"
DATA_FILE="${DATA_DIR}/data.json"
SERVICE_FILE="/etc/systemd/system/onyx-panel.service"
FIREWALL_SERVICE_FILE="/etc/systemd/system/onyx-panel-firewall.service"
APP_FILE="${APP_DIR}/panel.py"
LOGO_SOURCE="${BASE}/onyx-logo.png"
LOGO_FILE="${APP_DIR}/onyx-logo.png"
PORT=8090
DOMAIN="${ONYX_PANEL_DOMAIN:-$(sed -n 's/^Environment=TPROXY_HOSTNAME=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)}"
ACME_EMAIL="${ONYX_PANEL_ACME_EMAIL:-$(sed -n 's/^Environment=ACME_EMAIL=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)}"
MTPROTO_HOST="$(cat /etc/onyx-panel/mtproto-host 2>/dev/null || true)"
MTPROTO_HOST="${MTPROTO_HOST:-$DOMAIN}"
PANEL_PATH="/panel-$(openssl rand -hex 16)"
UPDATING="${ONYX_PANEL_UPDATE:-0}"
MANIFEST="/etc/onyx-panel/manifest"
PRIMARY_SECRET="/etc/onyx-panel/primary-secret"
USERS_FILE="/etc/onyx-panel/users.json"
SECRETS_FILE="/etc/onyx-panel/mtproxy-secrets"
MANAGER="/usr/local/sbin/onyx-panelctl"
QR_BIN="/usr/bin/qrencode"
XRAY_ROOT="/opt/onyx-panel/xray"
XRAY_BIN="${XRAY_ROOT}/xray"
XRAY_CONFIG_DIR="/etc/onyx-panel-xray"
XRAY_CONFIG="${XRAY_CONFIG_DIR}/config.json"
XRAY_PATH_FILE="/etc/onyx-panel/xray-path"
XRAY_VERSION="26.7.28"
XRAY_SHA256="8195d909f1109b8f3d99eefe401a3c451d7bf4af71f24d3815420f77e5dd2a40"
HYSTERIA_PORT=8443
OPENFLUX_ROOT="/opt/onyx-panel/openflux"
OPENFLUX_BIN="${OPENFLUX_ROOT}/openflux"
OPENFLUX_VERSION="1.0.0"
OPENFLUX_SHA256="c90cb197e4ba7c288a55e864f707f53dc82695c6f66ebc42418aba5e05ad7d58"
OPENFLUX_BUNDLED="${BASE}/assets/OpenFlux-linux-amd64"
# v2.3.6 was published with the bundled binary at the repository root while
# the installer expected assets/. Accept both layouts so an in-place update
# never falls back to a large external download solely because of packaging.
if [[ ! -s "$OPENFLUX_BUNDLED" && -s "${BASE}/OpenFlux-linux-amd64" ]]; then
    OPENFLUX_BUNDLED="${BASE}/OpenFlux-linux-amd64"
fi
AWG_GO_VERSION="v3.1.20260828"
AWG_GO_COMMIT="b5928efb6ca19f0153958460c3d141f04abc5c2e"
AWG_GO_BUNDLED="${BASE}/assets/amneziawg-go-linux-amd64"
AWG_GO_SHA256="9b8912d203ba7142c1957913047bb9efd6e02c173c1f3bf852c652b16aada60f"
AWG_TOOLS_VERSION="v3.1.20260812"
AWG_TOOLS_SHA256="919e9d0a367c7c72f9c16b7d0a9e4840b943628353b2210a33cb4b582785ba56"
AWG_BIN_BUNDLED="${BASE}/assets/awg-linux-amd64"
AWG_BIN_SHA256="23d29323258166183eeeb288c1f9f08b879f3707e54591b1bfb2402413f6d8d8"
AWG_QUICK_BUNDLED="${BASE}/assets/awg-quick-linux-amd64"
AWG_QUICK_SHA256="f4bb0f5d63665ade87f0cb9f2185c43515cff09868637eb311f98f65a318722c"
AWG_TOOLS_BUNDLED="${BASE}/assets/amneziawg-tools-ubuntu-22.04.zip"
AWG_GO_SOURCE_BUNDLED="${BASE}/assets/amneziawg-go-b5928ef.tar.gz"
AWG_GO_SOURCE_SHA256="10bf7458e090bf52f87df27adcd3904a60e4d17fab844d9415e46379147f1ab4"

die(){ echo "ERROR: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "Run as root."
. /etc/os-release
case "${ID:-}" in
    ubuntu)
        dpkg --compare-versions "${VERSION_ID:-0}" ge "22.04" ||
            die "Ubuntu 22.04 or newer is required."
        ;;
    debian)
        dpkg --compare-versions "${VERSION_ID:-0}" ge "12" ||
            die "Debian 12 or newer is required."
        ;;
    *)
        die "Supported systems: Ubuntu 22.04+ or Debian 12+."
        ;;
esac
echo "Platform: ${PRETTY_NAME:-${ID} ${VERSION_ID}}"
command -v python3 >/dev/null || die "python3 required."
command -v openssl >/dev/null || die "openssl required."
[[ "$(uname -m)" == "x86_64" ]] || die "x86_64 is required."

# Older releases did not always retain the Caddy systemd drop-in. Recover the
# hostname from other authoritative project files before asking the operator.
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"; DOMAIN="${DOMAIN,,}"
if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]]; then
    DOMAIN="$(sed -n 's/^Environment=ONYX_DOMAIN=//p' "$SERVICE_FILE" 2>/dev/null | head -n1 || true)"
fi
if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]] && [[ -s /etc/tproxy-server/config.json ]]; then
    DOMAIN="$(python3 - /etc/tproxy-server/config.json <<'PY' 2>/dev/null || true
import json,sys
try:
    value=json.load(open(sys.argv[1],encoding="utf-8")).get("public_hostname","")
    print(value if isinstance(value,str) else "")
except Exception:
    pass
PY
)"
fi
if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]] && [[ -s /etc/caddy/Caddyfile ]]; then
    DOMAIN="$(sed -n 's/^[[:space:]]*\([a-z0-9][a-z0-9.-]*\)[[:space:]]*{[[:space:]]*$/\1/p' /etc/caddy/Caddyfile |
        grep -vE '^(http|https|localhost)$' | head -n1 || true)"
fi
if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]]; then
    [[ -t 0 ]] || die "The domain could not be recovered. Re-run with ONYX_PANEL_DOMAIN=proxy.example.com."
    echo "Домен старой установки не найден автоматически."
    while true; do
        read -r -p "Введите действующий домен Onyx Panel: " DOMAIN
        DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"; DOMAIN="${DOMAIN,,}"
        [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]] && break
        echo "Некорректный домен. Пример: proxy.example.com"
    done
fi
MTPROTO_HOST="${MTPROTO_HOST:-$DOMAIN}"
[[ -s "$PRIMARY_SECRET" ]] || die "Primary install-time secret not found."
[[ -s "$LOGO_SOURCE" ]] || die "Panel logo file is missing: onyx-logo.png"
for module in onyx_subscriptions.py onyx_panel_extras.py onyx_ui.py onyx_metrics.py onyx_update.py onyx_nodes.py onyx_openflux.py onyx_awg.py onyx_firewall.py onyx_components.py; do
    [[ -s "$BASE/$module" ]] || die "Missing panel module: $module; extract the complete archive."
done
FLAG_ARCHIVE="$BASE/onyx-panel/flags.tar.gz"
[[ -s "$FLAG_ARCHIVE" ]] ||
    die "Panel flag bundle is missing; extract the complete archive."

# An update keeps the existing private panel address.  A new address would
# make an otherwise successful update look like a broken panel to its owner.
if [[ "$UPDATING" == "1" ]]; then
    [[ -s "$DATA_FILE" ]] || die "Existing panel data was not found. Run the full installer instead."
    EXISTING_PATH="$(sed -n 's/^Environment=ONYX_PANEL_PATH=//p' "$SERVICE_FILE" 2>/dev/null | head -n1 || true)"
    [[ "$EXISTING_PATH" =~ ^/[a-z0-9][a-z0-9-]{2,58}[a-z0-9]$ ]] || die "Existing panel address was not found. Run the full installer instead."
    PANEL_PATH="$EXISTING_PATH"
fi

echo "      Preparing AmneziaWG 2.0 / 3.1..."
AWG_INSTALLED_NOW=0
if ! command -v ip >/dev/null 2>&1; then
    apt-get -o DPkg::Lock::Timeout=600 update
    apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends iproute2
fi
if [[ ! -x /usr/local/bin/amneziawg-go ]] || ! /usr/local/bin/amneziawg-go --version 2>&1 | grep -Fq "$AWG_GO_VERSION"; then
    if [[ -s "$AWG_GO_BUNDLED" ]] && echo "${AWG_GO_SHA256}  ${AWG_GO_BUNDLED}" | sha256sum -c - >/dev/null; then
        install -o root -g root -m 0755 "$AWG_GO_BUNDLED" /usr/local/bin/amneziawg-go
    else
        if ! command -v git >/dev/null 2>&1 || ! command -v make >/dev/null 2>&1 || ! command -v gcc >/dev/null 2>&1; then
            apt-get -o DPkg::Lock::Timeout=600 update
            apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends git build-essential
        fi
        GO_BIN="$(find /opt -maxdepth 3 -type f -path '/opt/go*/bin/go' -print -quit 2>/dev/null || true)"
        [[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go || true)"
        [[ -x "$GO_BIN" ]] || die "Bundled AmneziaWG binary is missing or damaged and the Go compiler is unavailable."
        AWG_GO_SOURCE="$(mktemp -d /tmp/onyx-awg-go.XXXXXX)"
        if [[ -s "$AWG_GO_SOURCE_BUNDLED" ]] &&
           echo "$AWG_GO_SOURCE_SHA256  $AWG_GO_SOURCE_BUNDLED" | sha256sum -c - >/dev/null 2>&1; then
            echo "      Using the AmneziaWG Go source included with this release."
            tar -xzf "$AWG_GO_SOURCE_BUNDLED" -C "$AWG_GO_SOURCE" --strip-components=1 --no-same-owner
        else
            if ! command -v git >/dev/null 2>&1; then
                apt-get -o DPkg::Lock::Timeout=600 update
                apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends git
            fi
            git -C "$AWG_GO_SOURCE" init -q
            git -C "$AWG_GO_SOURCE" remote add origin https://github.com/amnezia-vpn/amneziawg-go.git
            git -C "$AWG_GO_SOURCE" fetch -q --depth 1 origin tag "$AWG_GO_VERSION"
            git -C "$AWG_GO_SOURCE" checkout -q --detach FETCH_HEAD
            [[ "$(git -C "$AWG_GO_SOURCE" rev-parse HEAD)" == "$AWG_GO_COMMIT" ]] || die "AmneziaWG Go source verification failed."
        fi
        (cd "$AWG_GO_SOURCE" && PATH="$(dirname "$GO_BIN"):$PATH" make amneziawg-go)
        install -o root -g root -m 0755 "$AWG_GO_SOURCE/amneziawg-go" /usr/local/bin/amneziawg-go
        rm -rf "$AWG_GO_SOURCE"
    fi
    AWG_INSTALLED_NOW=1
fi
if [[ ! -x /usr/local/bin/awg ]] || ! /usr/local/bin/awg --version 2>&1 | grep -Fq "${AWG_TOOLS_VERSION#v}"; then
    if [[ -s "$AWG_BIN_BUNDLED" && -s "$AWG_QUICK_BUNDLED" ]] && \
       echo "${AWG_BIN_SHA256}  ${AWG_BIN_BUNDLED}" | sha256sum -c - >/dev/null && \
       echo "${AWG_QUICK_SHA256}  ${AWG_QUICK_BUNDLED}" | sha256sum -c - >/dev/null; then
        install -o root -g root -m 0755 "$AWG_BIN_BUNDLED" /usr/local/bin/awg
        install -o root -g root -m 0755 "$AWG_QUICK_BUNDLED" /usr/local/bin/awg-quick
    else
        if ! command -v unzip >/dev/null 2>&1; then
            apt-get -o DPkg::Lock::Timeout=600 update
            apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends unzip
        fi
        AWG_TOOLS_ARCHIVE="$(mktemp /tmp/onyx-awg-tools.XXXXXX.zip)"
        AWG_TOOLS_DIR="$(mktemp -d /tmp/onyx-awg-tools.XXXXXX)"
        if [[ -s "$AWG_TOOLS_BUNDLED" ]]; then
            echo "      Using the AmneziaWG tools included with this release."
            cp "$AWG_TOOLS_BUNDLED" "$AWG_TOOLS_ARCHIVE"
        else
            echo "      AmneziaWG tools archive not found in assets/; downloading it..."
            curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
                --retry 3 --retry-all-errors --connect-timeout 20 --output "$AWG_TOOLS_ARCHIVE" \
                "https://github.com/amnezia-vpn/amneziawg-tools/releases/download/${AWG_TOOLS_VERSION}/ubuntu-22.04-amneziawg-tools.zip"
        fi
        echo "${AWG_TOOLS_SHA256}  ${AWG_TOOLS_ARCHIVE}" | sha256sum -c - >/dev/null || die "AmneziaWG tools checksum verification failed."
        unzip -q "$AWG_TOOLS_ARCHIVE" -d "$AWG_TOOLS_DIR"
        AWG_TOOLS_UNPACKED="$AWG_TOOLS_DIR/ubuntu-22.04-amneziawg-tools"
        (cd "$AWG_TOOLS_UNPACKED" && sha256sum -c awg.sha256 >/dev/null && sha256sum -c awg-quick.sha256 >/dev/null) || die "AmneziaWG tools files verification failed."
        install -o root -g root -m 0755 "$AWG_TOOLS_UNPACKED/awg" /usr/local/bin/awg
        install -o root -g root -m 0755 "$AWG_TOOLS_UNPACKED/awg-quick" /usr/local/bin/awg-quick
        rm -f "$AWG_TOOLS_ARCHIVE"
        rm -rf "$AWG_TOOLS_DIR"
    fi
    AWG_INSTALLED_NOW=1
fi
/usr/local/bin/awg --version >/dev/null || die "AmneziaWG tools verification failed."
if [[ "$AWG_INSTALLED_NOW" == 1 ]]; then
    : > /etc/onyx-panel/awg-owned
    chmod 0600 /etc/onyx-panel/awg-owned
fi
install -d -o root -g root -m 0700 /etc/onyx-panel/awg
cat > /usr/local/sbin/onyx-panel-awg-run <<'AWGRUN'
#!/usr/bin/env python3
import json,os,re,sys
uid=sys.argv[1] if len(sys.argv)>1 else ""
if not re.fullmatch(r"[a-f0-9]{16}",uid): raise SystemExit("invalid AWG profile id")
with open("/etc/onyx-panel/awg/"+uid+".json",encoding="ascii") as handle: meta=json.load(handle)
iface=str(meta.get("interface",""))
if not re.fullmatch(r"wa[a-f0-9]{11}",iface): raise SystemExit("invalid AWG interface")
os.execv("/usr/local/bin/amneziawg-go",["amneziawg-go","-f",iface])
AWGRUN
cat > /usr/local/sbin/onyx-panel-awg-up <<'AWGUP'
#!/usr/bin/env python3
import json,os,re,subprocess,sys,time
uid=sys.argv[1] if len(sys.argv)>1 else ""
if not re.fullmatch(r"[a-f0-9]{16}",uid): raise SystemExit("invalid AWG profile id")
base="/etc/onyx-panel/awg/"+uid
with open(base+".json",encoding="ascii") as handle: meta=json.load(handle)
iface=str(meta.get("interface","")); address=str(meta.get("address","")); mtu=int(meta.get("mtu",1280))
if not re.fullmatch(r"wa[a-f0-9]{11}",iface): raise SystemExit("invalid AWG interface")
if not 1024 <= mtu <= 1420: raise SystemExit("invalid AWG MTU")
for _ in range(80):
    if os.path.exists("/var/run/amneziawg/"+iface+".sock") or os.path.exists("/sys/class/net/"+iface): break
    time.sleep(.1)
else: raise SystemExit("AWG interface did not appear")
subprocess.run(["/usr/local/bin/awg","setconf",iface,base+".conf"],check=True)
subprocess.run(["/usr/sbin/ip","address","replace",address,"dev",iface],check=True)
subprocess.run(["/usr/sbin/ip","link","set","mtu",str(mtu),"up","dev",iface],check=True)
AWGUP
chmod 0755 /usr/local/sbin/onyx-panel-awg-run /usr/local/sbin/onyx-panel-awg-up
cat > /etc/systemd/system/onyx-panel-awg@.service <<'EOF'
[Unit]
Description=Onyx Panel independent AmneziaWG profile %i
After=network-online.target onyx-panel-firewall.service
Wants=network-online.target
Requires=onyx-panel-firewall.service

[Service]
Type=simple
User=root
Group=root
UMask=0077
Environment=WG_PROCESS_FOREGROUND=1
Environment=LOG_LEVEL=error
ExecStartPre=-/usr/local/sbin/onyx-panel-awg-down %i
ExecStart=/usr/local/sbin/onyx-panel-awg-run %i
ExecStartPost=/usr/local/sbin/onyx-panel-awg-up %i
ExecStopPost=-/usr/local/sbin/onyx-panel-awg-down %i
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
cat > /usr/local/sbin/onyx-panel-awg-down <<'AWGDOWN'
#!/usr/bin/env python3
import json,os,re,subprocess,sys
uid=sys.argv[1] if len(sys.argv)>1 else ""
if not re.fullmatch(r"[a-f0-9]{16}",uid): raise SystemExit(0)
try:
    with open("/etc/onyx-panel/awg/"+uid+".json",encoding="ascii") as handle: iface=str(json.load(handle).get("interface",""))
except Exception: iface="wa"+uid[:11]
if re.fullmatch(r"wa[a-f0-9]{11}",iface): subprocess.run(["/usr/sbin/ip","link","delete",iface],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
AWGDOWN
chmod 0755 /usr/local/sbin/onyx-panel-awg-down
# Retire the shared-interface AWG preview. Existing records are migrated by
# panelctl init to independent profiles with new ports and fingerprints.
for legacy in onyx-panel-awg20.service onyx-panel-awg31.service; do
    systemctl disable --now "$legacy" 2>/dev/null || true
    rm -f -- "/etc/systemd/system/$legacy"
done
cat > /etc/sysctl.d/90-onyx-panel-awg.conf <<'EOF'
net.ipv4.ip_forward=1
EOF
chmod 0644 /etc/sysctl.d/90-onyx-panel-awg.conf
/usr/sbin/sysctl -p /etc/sysctl.d/90-onyx-panel-awg.conf >/dev/null

if ! [[ "$ACME_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] && [[ -s /etc/caddy/Caddyfile ]]; then
    ACME_EMAIL="$(sed -n 's/^[[:space:]]*email[[:space:]][[:space:]]*\([^[:space:]]*\)[[:space:]]*$/\1/p' /etc/caddy/Caddyfile | head -n1 || true)"
fi
if ! [[ "$ACME_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
    echo "Caddy ACME email is missing or invalid."
    read -r -p "ACME email: " ACME_EMAIL
    [[ "$ACME_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] ||
        die "Invalid ACME email."
fi

# Keep one canonical source for the menu, future updates and Caddy itself.
install -d -m 0755 /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/tproxy.conf <<EOF
[Service]
Environment=TPROXY_HOSTNAME=$DOMAIN
Environment=TPROXY_SITE_ROOT=/srv/tproxy-site
Environment=ACME_EMAIL=$ACME_EMAIL
ReadWritePaths=/etc/caddy
EOF
chmod 0644 /etc/systemd/system/caddy.service.d/tproxy.conf

export DEBIAN_FRONTEND=noninteractive
if ! command -v qrencode >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1 || ! command -v xz >/dev/null 2>&1; then
    apt-get -o DPkg::Lock::Timeout=600 update
    apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends qrencode unzip xz-utils
fi

install -d -m 0755 "$APP_DIR" /etc/onyx-panel
install -d -m 0700 "$DATA_DIR"
install -o root -g root -m 0644 "$LOGO_SOURCE" "$LOGO_FILE"
install -o root -g root -m 0644 "$LOGO_SOURCE" "$APP_DIR/panel-logo.png"
chmod 0600 "$PRIMARY_SECRET"

echo "      Preparing Xray ${XRAY_VERSION}..."
if ! getent group xray >/dev/null 2>&1; then
    groupadd --system xray
    : > /etc/onyx-panel/xray-group-owned
    chmod 0600 /etc/onyx-panel/xray-group-owned
fi
if ! id xray >/dev/null 2>&1; then
    useradd --system --gid xray --home /var/lib/onyx-panel-xray --create-home --shell /usr/sbin/nologin xray
    : > /etc/onyx-panel/xray-user-owned
    chmod 0600 /etc/onyx-panel/xray-user-owned
else
    usermod -a -G xray xray
fi
install -d -o root -g root -m 0755 "$XRAY_ROOT"
install -d -o root -g xray -m 0750 "$XRAY_CONFIG_DIR"
install -d -o root -g xray -m 0750 "${XRAY_CONFIG_DIR}/tls"
install -d -o xray -g xray -m 0750 /var/lib/onyx-panel-xray
if [[ ! -x "$XRAY_BIN" ]] || ! "$XRAY_BIN" version 2>/dev/null | grep -q "${XRAY_VERSION}"; then
    XRAY_ARCHIVE="$(mktemp /tmp/onyx-panel-xray.XXXXXX.zip)"
    XRAY_UNPACK="$(mktemp -d /tmp/onyx-panel-xray.XXXXXX)"
    XRAY_BUNDLED="${BASE}/assets/Xray-linux-64.zip"
    if [[ -s "$XRAY_BUNDLED" ]]; then
        echo "      Using Xray included with this release."
        cp "$XRAY_BUNDLED" "$XRAY_ARCHIVE"
    else
        echo "      Xray archive not found in assets/; downloading it..."
        curl --fail --silent --show-error --location \
            --proto '=https' --proto-redir '=https' --tlsv1.2 \
            --retry 3 --retry-all-errors --connect-timeout 20 \
            --output "$XRAY_ARCHIVE" \
            "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip"
    fi
    echo "${XRAY_SHA256}  ${XRAY_ARCHIVE}" | sha256sum -c - >/dev/null || die "Xray checksum verification failed."
    unzip -q "$XRAY_ARCHIVE" xray -d "$XRAY_UNPACK"
    install -o root -g root -m 0755 "$XRAY_UNPACK/xray" "$XRAY_BIN"
    rm -f "$XRAY_ARCHIVE"
    rm -rf "$XRAY_UNPACK"
fi

echo "      Preparing OpenFlux ${OPENFLUX_VERSION}..."
if ! id onyx-openflux >/dev/null 2>&1; then
    if [[ -d /var/lib/onyx-openflux ]]; then
        useradd --system --home-dir /var/lib/onyx-openflux --no-create-home --shell /usr/sbin/nologin onyx-openflux
    else
        useradd --system --home-dir /var/lib/onyx-openflux --create-home --shell /usr/sbin/nologin onyx-openflux
    fi
fi
install -d -o root -g root -m 0755 "$OPENFLUX_ROOT"
if [[ ! -x "$OPENFLUX_BIN" ]] || ! sha256sum "$OPENFLUX_BIN" | grep -q "^${OPENFLUX_SHA256}  "; then
    if [[ -s "$OPENFLUX_BUNDLED" ]]; then
        OPENFLUX_DOWNLOAD="$OPENFLUX_BUNDLED"
        echo "      Using OpenFlux included with this release."
    else
        OPENFLUX_DOWNLOAD="$(mktemp /tmp/onyx-panel-openflux.XXXXXX)"
        curl --fail --silent --show-error --location \
            --proto '=https' --proto-redir '=https' --tlsv1.2 \
            --retry 3 --retry-all-errors --connect-timeout 20 \
            --output "$OPENFLUX_DOWNLOAD" \
            "https://github.com/damnurmum/OpenFlux-Android/releases/download/v${OPENFLUX_VERSION}/openflux-linux-amd64"
    fi
    echo "${OPENFLUX_SHA256}  ${OPENFLUX_DOWNLOAD}" | sha256sum -c - >/dev/null || die "OpenFlux checksum verification failed."
    install -o root -g root -m 0755 "$OPENFLUX_DOWNLOAD" "$OPENFLUX_BIN"
    [[ "$OPENFLUX_DOWNLOAD" == "$OPENFLUX_BUNDLED" ]] || rm -f "$OPENFLUX_DOWNLOAD"
fi

# Remove only blocks managed by the former experimental NaiveProxy integration.
# The distribution Caddy binary is retained and used again after this migration.
if [[ -s /etc/caddy/Caddyfile ]]; then
    python3 - /etc/caddy/Caddyfile "$DOMAIN" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); domain=sys.argv[2]; source=p.read_text(encoding="utf-8")
source=re.sub(r"\n?[ \t]*# ONYX NAIVE GLOBAL BEGIN\n.*?\n[ \t]*# ONYX NAIVE GLOBAL END\n?","\n",source,flags=re.S)
source=re.sub(r"\n?[ \t]*# ONYX NAIVE BEGIN\n.*?\n[ \t]*# ONYX NAIVE END\n?","\n",source,flags=re.S)
legacy_address = re.compile(
    r"(?m)^(?P<indent>\s*)(?:"
    r":443\s*,\s*" + re.escape(domain) +
    r"|" + re.escape(domain) + r"\s*,\s*:443"
    r"|https://" + re.escape(domain) + r"(?::443)?"
    r"|" + re.escape(domain) + r":443)\s*\{\s*$"
)
source=legacy_address.sub(lambda m:m.group("indent")+domain+" {",source,count=1)
tmp=p.with_suffix(".onyx-stable.tmp"); tmp.write_text(source,encoding="utf-8")
tmp.chmod(0o640); tmp.replace(p)
PY
    chown root:caddy /etc/caddy/Caddyfile
fi
command -v caddy >/dev/null 2>&1 || die "Caddy is missing. Run the full installer to restore it."
cat > /etc/systemd/system/caddy.service.d/tproxy.conf <<EOF
[Service]
Environment=TPROXY_HOSTNAME=$DOMAIN
Environment=TPROXY_SITE_ROOT=/srv/tproxy-site
Environment=ACME_EMAIL=$ACME_EMAIL
ReadWritePaths=/etc/caddy
EOF
chmod 0644 /etc/systemd/system/caddy.service.d/tproxy.conf
if [[ ! -s "$XRAY_PATH_FILE" ]]; then
    printf '/vless-%s\n' "$(openssl rand -hex 12)" > "$XRAY_PATH_FILE"
fi
chmod 0600 "$XRAY_PATH_FILE"
XRAY_PATH="$(cat "$XRAY_PATH_FILE")"
[[ "$XRAY_PATH" =~ ^/vless-[a-f0-9]{24}$ ]] || die "Stored VLESS path is invalid."

if [[ "$UPDATING" == "1" ]]; then
    echo "Updating Onyx Panel 1.2.5..."
else
    echo "Configuring Onyx Panel 1.2.5..."
fi
INSTALL_CREDENTIALS="/etc/onyx-panel/install-credentials"
if [[ "$UPDATING" == "1" ]]; then
    ADMIN="$(python3 - "$DATA_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d=json.load(f)
admin=d.get("admin",{})
if not isinstance(admin.get("user"),str) or not admin.get("user") or not isinstance(admin.get("hash"),str) or not admin.get("hash"):
    raise SystemExit(1)
print(admin["user"])
PY
)" || die "Existing administrator data is invalid. Run the full installer instead."
    PASS=""
elif [[ -s "$INSTALL_CREDENTIALS" ]]; then
    ADMIN="$(sed -n '1p' "$INSTALL_CREDENTIALS")"
    PASS="$(sed -n '2p' "$INSTALL_CREDENTIALS")"
    rm -f "$INSTALL_CREDENTIALS"
    [[ -n "$ADMIN" && -n "$PASS" ]] || die "Panel credentials are invalid."
else
    read -r -p "Логин администратора [admin]: " ADMIN
    ADMIN="${ADMIN:-admin}"
    while true; do
        read -r -s -p "Пароль администратора: " PASS
        echo
        [[ ${#PASS} -ge 3 ]] || { echo "Пароль должен содержать минимум 3 символа."; continue; }
        break
    done
fi

echo "[1/6] Writing manager..."

for module in onyx_subscriptions.py onyx_panel_extras.py onyx_ui.py onyx_metrics.py onyx_update.py onyx_nodes.py onyx_openflux.py onyx_awg.py onyx_firewall.py onyx_components.py; do
    [[ -s "$BASE/$module" ]] || die "Package is incomplete: $module is missing."
    install -o root -g root -m 0644 "$BASE/$module" "$APP_DIR/$module"
done
install -d -o root -g root -m 0755 "$APP_DIR/fonts"
for font in manrope-cyrillic-wght-normal.woff2 manrope-latin-wght-normal.woff2 jetbrains-mono-cyrillic-wght-normal.woff2 jetbrains-mono-latin-wght-normal.woff2; do
    [[ -s "$BASE/fonts/$font" ]] || die "Bundled font is missing: fonts/$font."
    install -o root -g root -m 0644 "$BASE/fonts/$font" "$APP_DIR/fonts/$font"
done
command -v tar >/dev/null 2>&1 || die "tar is required to install panel assets."
FLAG_ENTRIES="$(tar -tzf "$FLAG_ARCHIVE")" || die "Panel flag bundle cannot be read."
if grep -Eq '(^|/)\.\.(/|$)|^/' <<<"$FLAG_ENTRIES"; then
    die "Panel flag bundle contains an unsafe path."
fi
rm -rf -- "$APP_DIR/flags"
tar -xzf "$FLAG_ARCHIVE" -C "$APP_DIR" --no-same-owner
[[ -s "$APP_DIR/flags/fi.svg" && -s "$APP_DIR/flags/un.svg" ]] ||
    die "Panel flag bundle is incomplete."
chown -R root:root "$APP_DIR/flags"
find "$APP_DIR/flags" -type d -exec chmod 0755 {} +
find "$APP_DIR/flags" -type f -exec chmod 0644 {} +

# The service is enabled once and guarded by ConditionPathExists. Until the
# administrator saves a document URL it stays inactive and opens no ports.
python3 - "$APP_DIR" <<'PY'
import sys
sys.path.insert(0,sys.argv[1])
import onyx_openflux
onyx_openflux.install_service()
onyx_openflux.restore_if_configured()
PY
systemctl enable onyx-panel-openflux.service >/dev/null

# Detect the VPS country and city once for a new/default location. A failed
# HTTPS lookup is non-fatal and preserves the existing administrator value.
python3 - "$APP_DIR" "${DATA_DIR}/location.json" <<'PY'
import os,sys
sys.path.insert(0,sys.argv[1])
import onyx_nodes
path=sys.argv[2]
current=onyx_nodes.load_location(path)
placeholder=current.get("country_code")=="UN" or current.get("name") in ("Основная локация","Локация","Сервер")
if not os.path.exists(path) or placeholder:
    onyx_nodes.save_location(path,onyx_nodes.detect_location(current))
PY

cat > "$MANAGER" <<'PY'
#!/usr/bin/env python3
import copy, fcntl, grp, json, os, re, secrets, shutil, subprocess, sys, time, uuid
sys.path.insert(0,"/opt/onyx-panel")
from onyx_subscriptions import mutate as mutate_subscription, issue as issue_subscription, SubscriptionError
import onyx_awg
import onyx_firewall

USERS="/etc/onyx-panel/users.json"
PROFILES="/etc/tproxy-server/profiles.json"
PRIMARY_SECRET="/etc/onyx-panel/primary-secret"
MT_ENV="/etc/mtproxy/mtproxy.env"
UNIT_DIR="/etc/systemd/system"
FIREWALL_SCRIPT="/usr/local/sbin/onyx-panel-user-firewall"
MT_BIN="/opt/MTProxy/objs/bin/mtproto-proxy"
MT_AES="/etc/mtproxy/proxy-secret"
MT_CONF="/etc/mtproxy/proxy-multi.conf"
XRAY_BIN="/opt/onyx-panel/xray/xray"
XRAY_CONFIG="/etc/onyx-panel-xray/config.json"
XRAY_PATH_FILE="/etc/onyx-panel/xray-path"
XRAY_CERT="/etc/onyx-panel-xray/tls/domain.crt"
XRAY_KEY="/etc/onyx-panel-xray/tls/domain.key"
XRAY_SERVICE="onyx-panel-xray.service"
XRAY_TLS_SYNC="/usr/local/sbin/onyx-panel-sync-tls"
XRAY_VLESS_PORT=10000
XRAY_API="127.0.0.1:10085"
HYSTERIA_PORT=8443
CADDYFILE="/etc/caddy/Caddyfile"
TRAFFIC_FILE="/var/lib/onyx-panel/traffic.json"
TRAFFIC_LOCK="/var/lib/onyx-panel/traffic.lock"
UFW_HYSTERIA_MARKER="/etc/onyx-panel/hysteria-ufw-owned"
UFW_MTPROTO_MARKER="/etc/onyx-panel/mtproto-ufw-owned"
UFW_AWG_MARKER="/etc/onyx-panel/awg-ufw-owned"
UFW_AWG_ROUTE_MARKER="/etc/onyx-panel/awg-route-ufw-owned"
BASE_PORT=2399
BASE_STATS=8889
MAX_USERS=32

def run(*args, check=False, timeout=60):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip() or "command failed")
    return p

def load():
    try:
        with open(USERS,encoding="utf-8") as f:
            d=json.load(f)
            d.setdefault("users",[])
            d.setdefault("traffic",{})
            d.setdefault("subscriptions",[])
            # Remove the two withdrawn experimental protocols. Subscription
            # records keep working with their stable VLESS/Hysteria2 profiles.
            d["users"]=[u for u in d["users"] if u.get("protocol","web") not in ("mieru","naive")]
            for sub in d["subscriptions"]:
                supported=[p for p in sub.get("protocols",[]) if p in ("vless","hysteria")]
                sub["protocols"]=supported or ["vless","hysteria"]
            d["users"]=[u for u in d["users"] if not (u.get("subscription_id") and u.get("protocol")=="web")]
            for u in d["users"]:
                protocol=u.setdefault("protocol","web")
                # V2.2 briefly exposed experimental per-profile transports and
                # ports.  Stable V2.1 deliberately has one tested VLESS XHTTP
                # listener behind Caddy/443 and one Hysteria2 UDP/8443 listener.
                # Normalize those records while preserving IDs and secrets.
                if protocol=="vless":
                    u["backend_port"]=443
                    for key in ("transport","path","xray_port","xhttp_mode","fingerprint","legacy_shared"):
                        u.pop(key,None)
                elif protocol=="hysteria":
                    u["backend_port"]=HYSTERIA_PORT
                    for key in ("udp_idle_timeout","masquerade"):
                        u.pop(key,None)
            return d
    except FileNotFoundError:
        return {"users":[],"traffic":{},"subscriptions":[]}

def save(d):
    tmp=USERS+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(d,f,ensure_ascii=True,indent=2)
    os.chmod(tmp,0o600)
    os.replace(tmp,USERS)

def atomic_text(path,value,mode,group="root"):
    tmp=path+".tmp"
    try:
        with open(tmp,"w",encoding="utf-8") as f:
            f.write(value); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,0,grp.getgrnam(group).gr_gid if group!="root" else 0)
        os.chmod(tmp,mode)
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise

def normalize_proxy_secret(value):
    value=str(value or "").strip().lower()
    if not re.fullmatch(r"(?:dd)?[0-9a-f]{32}",value):
        raise ValueError("Секрет должен содержать 32 шестнадцатеричных символа; префикс dd допускается.")
    return value[2:] if value.startswith("dd") else value

def port_in_use(port):
    # Do not rely solely on users.json: a stopped/old installation can still
    # have an MTProxy process listening on a port that is absent from the file.
    sockets=run("ss","-lnt").stdout or ""
    return re.search(r"[:.]%d\b" % int(port),sockets) is not None

def alloc_ports(d,requested_port=None):
    used={int(u.get("backend_port",0)) for u in d["users"] if u.get("backend_port")}
    used_stats={int(u.get("stats_port",0)) for u in d["users"] if u.get("stats_port")}
    if requested_port not in (None,""):
        try: p=int(requested_port)
        except (TypeError,ValueError): raise ValueError("Порт MTProto должен быть числом от 1024 до 65535.")
        if p<1024 or p>65535:
            raise ValueError("Порт MTProto должен быть в диапазоне 1024–65535.")
        if p in {2398,443,8080,8081,8090} or p in used or p in used_stats or port_in_use(p):
            raise ValueError("Этот порт уже занят. Выберите другой порт MTProto.")
    else:
        p=BASE_PORT
        while p in used or p in used_stats or port_in_use(p): p+=1
        if p>=BASE_PORT+MAX_USERS:
            raise RuntimeError("Maximum panel users reached")
    s=BASE_STATS
    while s==p or s in used or s in used_stats or port_in_use(s): s+=1
    if s>65535: raise RuntimeError("Не удалось подобрать служебный порт MTProto.")
    return p,s

def mtproto_secrets(u):
    values=u.get("device_secrets")
    if not isinstance(values,list) or not values: values=[u.get("secret","")]
    result=[]
    for value in values:
        try: value=normalize_proxy_secret(value)
        except ValueError: continue
        if value not in result: result.append(value)
    if not result: result=[normalize_proxy_secret(u.get("secret",""))]
    return result

def write_unit(u):
    if u.get("protocol","web") not in ("web","mtproto"):
        return
    path=os.path.join(UNIT_DIR,f"onyx-user-{u['id']}.service")
    secret_args=" ".join("-S "+value for value in (mtproto_secrets(u) if u.get("protocol")=="mtproto" else [u["secret"]]))
    content=f"""[Unit]
Description=WEB Proxy User {u['id']}
After=network-online.target onyx-panel-firewall.service
Wants=network-online.target
Requires=onyx-panel-firewall.service

[Service]
Type=simple
User=root
Group=root
ExecStart={MT_BIN} -u nobody -p {int(u['stats_port'])} -H {int(u['backend_port'])} {secret_args} --aes-pwd {MT_AES} {MT_CONF} -M 1
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
    tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: f.write(content)
    os.chmod(tmp,0o644)
    os.replace(tmp,path)

def sync_firewall(d):
    # Preserve the last counters before recreating the nftables table.
    try: collect_traffic(d)
    except Exception: pass
    web_ports=[int(u["backend_port"]) for u in d["users"] if u.get("enabled",True) and u.get("protocol","web")=="web"]
    mtproto_ports=[int(u["backend_port"]) for u in d["users"] if u.get("enabled",True) and u.get("protocol","web")=="mtproto"]
    stats=[int(u["stats_port"]) for u in d["users"] if u.get("enabled",True) and u.get("protocol","web") in ("web","mtproto") and u.get("stats_port")]
    hysteria_enabled=any(u.get("enabled",True) and u.get("protocol")=="hysteria" for u in d["users"])
    awg_users=[u for u in d["users"] if u.get("enabled",True) and u.get("protocol") in onyx_awg.PROTOCOLS]
    lines=[
        "#!/usr/bin/env bash",
        "set -e",
        "nft list table inet onyx_panel >/dev/null 2>&1 && nft delete table inet onyx_panel || true",
        "nft add table inet onyx_panel",
        "nft 'add chain inet onyx_panel input { type filter hook input priority -20; policy accept; }'",
        "nft 'add chain inet onyx_panel output { type filter hook output priority -20; policy accept; }'",
        "nft 'add rule inet onyx_panel output oifname \"lo\" tcp dport 2398 counter comment \"onyx:primary:up\"'",
        "nft 'add rule inet onyx_panel input iifname \"lo\" tcp sport 2398 counter comment \"onyx:primary:down\"'"
    ]
    for u in d["users"]:
        if u.get("enabled",True) and u.get("protocol","web")=="web":
            uid=u["id"]
            port=int(u["backend_port"])
            lines.append("nft 'add rule inet onyx_panel output oifname \"lo\" tcp dport %d counter comment \"onyx:%s:up\"'"%(port,uid))
            lines.append("nft 'add rule inet onyx_panel input iifname \"lo\" tcp sport %d counter comment \"onyx:%s:down\"'"%(port,uid))
        elif u.get("enabled",True) and u.get("protocol")=="mtproto":
            uid=u["id"]
            port=int(u["backend_port"])
            # Keep MTProto rules compatible with both Ubuntu 22.04 and 24.04
            # nftables. Earlier packet-fingerprint expressions were rejected
            # by some nft versions and made client creation roll back.
            lines.append("nft 'add rule inet onyx_panel input iifname != \"lo\" tcp dport %d counter accept comment \"onyx:%s:up\"'"%(port,uid))
            lines.append("nft 'add rule inet onyx_panel output oifname != \"lo\" tcp sport %d counter accept comment \"onyx:%s:down\"'"%(port,uid))
    if web_ports:
        lines.append("nft 'add rule inet onyx_panel input iifname != \"lo\" tcp dport { %s } counter drop'" % ",".join(map(str,sorted(web_ports))))
    if stats:
        lines.append("nft 'add rule inet onyx_panel input iifname != \"lo\" tcp dport { %s } counter drop'" % ",".join(map(str,sorted(stats))))
    if hysteria_enabled:
        lines.append("nft 'add rule inet onyx_panel input udp dport %d counter accept'" % HYSTERIA_PORT)
    for u in awg_users:
        uid=u["id"]; port=int(u["backend_port"])
        lines.append("nft 'add rule inet onyx_panel input iifname != \"lo\" udp dport %d counter accept comment \"onyx:%s:up\"'"%(port,uid))
        lines.append("nft 'add rule inet onyx_panel output oifname != \"lo\" udp sport %d counter accept comment \"onyx:%s:down\"'"%(port,uid))
    lines.extend([
        "nft list table ip onyx_awg >/dev/null 2>&1 && nft delete table ip onyx_awg || true",
        "nft add table ip onyx_awg",
        "nft 'add chain ip onyx_awg forward { type filter hook forward priority -20; policy accept; }'",
        "nft 'add chain ip onyx_awg postrouting { type nat hook postrouting priority srcnat; policy accept; }'"
    ])
    for u in awg_users:
        iface=u["awg_interface"]; network=u["awg_network"]
        lines.append("nft 'add rule ip onyx_awg forward iifname \"%s\" counter accept'" % iface)
        lines.append("nft 'add rule ip onyx_awg forward oifname \"%s\" ct state related,established counter accept'" % iface)
        lines.append("nft 'add rule ip onyx_awg postrouting ip saddr %s oifname != \"%s\" counter masquerade'" % (network,iface))
    tmp=FIREWALL_SCRIPT+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: f.write("\n".join(lines)+"\n")
    os.chmod(tmp,0o750)
    os.replace(tmp,FIREWALL_SCRIPT)
    run(FIREWALL_SCRIPT,check=True)
    # UFW output is localized on many VPS images, so all UFW state management
    # lives in onyx_firewall and reads /etc/ufw/ufw.conf instead.  Fixed HTTPS
    # ports and every dynamic client port are reconciled in one transaction.
    route=run("ip","-4","route","show","default").stdout or ""
    match=re.search(r"\bdev\s+([A-Za-z0-9_.:-]+)",route)
    external_if=match.group(1) if match else ""
    onyx_firewall.reconcile(
        tcp={80,443,*mtproto_ports},
        udp=({HYSTERIA_PORT} if hysteria_enabled else set()) | {int(u["backend_port"]) for u in awg_users},
        routes={(u["awg_interface"],external_if) for u in awg_users if external_if},
    )

def sync_profiles(d):
    with open(PROFILES,encoding="utf-8") as f:
        old=json.load(f)
    keep=[p for p in old.get("profiles",[]) if not str(p.get("name","")).startswith("panel:")]
    for u in d["users"]:
        if u.get("enabled",True) and u.get("protocol","web")=="web":
            keep.append({
                "name":"panel:"+u["id"],
                "secret":u["secret"],
                "backend":"127.0.0.1:%d"%int(u["backend_port"]),
                "carrier_mode":"https"
            })
    tmp=PROFILES+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump({"profiles":keep},f,ensure_ascii=True,indent=2)
    os.chmod(tmp,0o400)
    c=run("/usr/local/bin/tproxy-server","-config","/etc/tproxy-server/config.json","-profiles-file",tmp,"-check")
    if c.returncode:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise RuntimeError("tproxy-server config check failed: "+(c.stderr or c.stdout)[-2000:])
    os.replace(tmp,PROFILES)

def sync_xray(d):
    with open(XRAY_PATH_FILE,encoding="utf-8") as f:
        xray_path=f.read().strip()
    if not re.fullmatch(r"/vless-[a-f0-9]{24}",xray_path):
        raise RuntimeError("Invalid stored VLESS path")
    vless=[]
    hysteria=[]
    for u in d["users"]:
        if not u.get("enabled",True):
            continue
        protocol=u.get("protocol","web")
        if protocol=="vless":
            vless.append({"id":u["secret"],"email":"panel:"+u["id"],"level":0})
        elif protocol=="hysteria":
            hysteria.append({"auth":u["secret"],"email":"panel:"+u["id"],"level":0})
    inbounds=[]
    if vless:
        inbounds.append({
            "tag":"vless-xhttp",
            "listen":"127.0.0.1",
            "port":XRAY_VLESS_PORT,
            "protocol":"vless",
            "settings":{"clients":vless,"decryption":"none"},
            "streamSettings":{
                # Xray's JSON stream selector is named "network".
                "network":"xhttp",
                "security":"none",
                "xhttpSettings":{"path":xray_path,"mode":"auto"}
            },
            "sniffing":{"enabled":True,"destOverride":["http","tls","quic"],"routeOnly":True}
        })
    if hysteria:
        if not (os.path.isfile(XRAY_CERT) and os.path.isfile(XRAY_KEY)):
            raise RuntimeError("TLS certificate for Hysteria 2 is not ready")
        inbounds.append({
            "tag":"hysteria2",
            "listen":"0.0.0.0",
            "port":HYSTERIA_PORT,
            "protocol":"hysteria",
            "settings":{"version":2,"clients":hysteria},
            "streamSettings":{
                "network":"hysteria",
                "security":"tls",
                "tlsSettings":{
                    "alpn":["h3"],
                    "minVersion":"1.3",
                    "certificates":[{"certificateFile":XRAY_CERT,"keyFile":XRAY_KEY}]
                },
                "hysteriaSettings":{"version":2,"udpIdleTimeout":60}
            },
            "sniffing":{"enabled":True,"destOverride":["http","tls","quic"],"routeOnly":True}
        })
    config={
        "log":{"loglevel":"warning"},
        "api":{"tag":"api","listen":XRAY_API,"services":["StatsService"]},
        "stats":{},
        "policy":{
            "levels":{"0":{"statsUserUplink":True,"statsUserDownlink":True}},
            "system":{"statsInboundUplink":True,"statsInboundDownlink":True}
        },
        "inbounds":inbounds,
        "outbounds":[{"tag":"direct","protocol":"freedom"}]
    }
    # Xray selects the configuration parser from the final extension.  A name
    # such as config.json.tmp is rejected before JSON parsing, so keep .json
    # as the temporary file's last suffix.
    tmp=os.path.splitext(XRAY_CONFIG)[0]+".tmp.json"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(config,f,ensure_ascii=True,indent=2)
    os.chown(tmp,0,grp.getgrnam("xray").gr_gid)
    os.chmod(tmp,0o640)
    check=run(XRAY_BIN,"run","-test","-config",tmp,timeout=60)
    if check.returncode:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise RuntimeError("Xray config check failed: "+(check.stderr or check.stdout)[-3000:])
    os.replace(tmp,XRAY_CONFIG)
    if inbounds:
        run("systemctl","enable",XRAY_SERVICE,check=True)
        run("systemctl","restart",XRAY_SERVICE,check=True)
        if run("systemctl","is-active","--quiet",XRAY_SERVICE).returncode:
            st=run("systemctl","status",XRAY_SERVICE,"--no-pager","--full")
            log=run("journalctl","-u",XRAY_SERVICE,"-n","50","--no-pager")
            raise RuntimeError("Xray failed: "+((st.stdout or st.stderr)+"\n"+(log.stdout or log.stderr))[-4000:])
    else:
        run("systemctl","disable","--now",XRAY_SERVICE,check=False)

def _load_traffic():
    try:
        with open(TRAFFIC_FILE,encoding="utf-8") as f:
            value=json.load(f)
            return value if isinstance(value,dict) else {}
    except Exception:
        return {}

def _save_traffic(value):
    os.makedirs(os.path.dirname(TRAFFIC_FILE),mode=0o700,exist_ok=True)
    tmp=TRAFFIC_FILE+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(value,f,ensure_ascii=True,indent=2)
    os.chmod(tmp,0o600)
    os.replace(tmp,TRAFFIC_FILE)

def _nft_traffic():
    result={}
    p=run("nft","-j","list","table","inet","onyx_panel",timeout=10)
    if p.returncode: return result
    try: doc=json.loads(p.stdout)
    except Exception: return result
    for item in doc.get("nftables",[]):
        rule=item.get("rule",{})
        comment=str(rule.get("comment", ""))
        m=re.fullmatch(r"onyx:([A-Za-z0-9_-]+):(up|down)",comment)
        if not m: continue
        count=0
        for expr in rule.get("expr",[]):
            if "counter" in expr:
                count=int(expr["counter"].get("bytes",0)); break
        result.setdefault(m.group(1),{"up":0,"down":0})[m.group(2)]=count
    return result

def _xray_traffic():
    result={}
    if run("systemctl","is-active","--quiet",XRAY_SERVICE).returncode:
        return result
    p=run(XRAY_BIN,"api","statsquery","--server="+XRAY_API,timeout=15)
    if p.returncode: return result
    try:
        start=p.stdout.find("{")
        doc=json.loads(p.stdout[start:])
    except Exception:
        return result
    for stat in doc.get("stat",[]):
        m=re.fullmatch(r"user>>>panel:([a-f0-9]+)>>>traffic>>>(uplink|downlink)",str(stat.get("name","")))
        if not m: continue
        key="up" if m.group(2)=="uplink" else "down"
        result.setdefault(m.group(1),{"up":0,"down":0})[key]=int(stat.get("value",0))
    return result

def _collect_traffic_unlocked(d=None):
    d=d or load()
    now=int(time.time())
    current=_nft_traffic()
    current.update(_xray_traffic())
    current.update(onyx_awg.traffic(d.get("users",[])))
    state=_load_traffic()
    targets={"primary":{"protocol":"web","enabled":True}}
    targets.update({u["id"]:u for u in d.get("users",[])})
    service_states={}
    for uid,u in targets.items():
        raw=current.get(uid)
        entry=state.setdefault(uid,{"up":0,"down":0,"raw_up":0,"raw_down":0,"last_change":0})
        changed=False
        for direction in ("up","down"):
            # A missing API/counter sample is not a reset to zero. Keeping the
            # baseline prevents counting all historical bytes again next time.
            if raw is None: continue
            value=max(0,int(raw.get(direction,0)))
            previous=max(0,int(entry.get("raw_"+direction,0)))
            delta=value-previous if value>=previous else value
            if delta>0:
                entry[direction]=max(0,int(entry.get(direction,0)))+delta
                changed=True
            entry["raw_"+direction]=value
        if changed: entry["last_change"]=now
        protocol=u.get("protocol","web")
        if uid=="primary":
            unit="mtproxy.service"
        elif protocol=="web":
            unit="onyx-user-"+uid+".service"
        elif protocol in ("vless","hysteria"):
            unit=XRAY_SERVICE
        elif protocol=="mtproto":
            unit="onyx-user-"+uid+".service"
        elif protocol in onyx_awg.PROTOCOLS:
            unit=onyx_awg.service_for(u)
        else:
            unit=""
        if unit not in service_states:
            service_states[unit]=(run("systemctl","is-active","--quiet",unit).returncode==0)
        entry["service_active"]=service_states[unit] and u.get("enabled",True)
        if raw is not None: entry["updated_at"]=now
        entry["protocol"]=protocol
    _save_traffic(state)
    return state

def collect_traffic(d=None):
    os.makedirs(os.path.dirname(TRAFFIC_LOCK),mode=0o700,exist_ok=True)
    with open(TRAFFIC_LOCK,"a+",encoding="ascii") as lock:
        os.chmod(TRAFFIC_LOCK,0o600)
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        return _collect_traffic_unlocked(d)

def remove_old_units(d):
    keep={"onyx-user-"+u["id"]+".service" for u in d["users"] if u.get("enabled",True) and u.get("protocol","web") in ("web","mtproto")}
    for name in os.listdir(UNIT_DIR):
        if name.startswith("onyx-user-") and name.endswith(".service") and name not in keep:
            run("systemctl","disable","--now",name,check=False)
            try: os.remove(os.path.join(UNIT_DIR,name))
            except FileNotFoundError: pass

def apply(d,restart=True,previous=None):
    with open(PROFILES,encoding="utf-8") as f:
        old_profiles=f.read()
    if os.path.exists(XRAY_CONFIG):
        with open(XRAY_CONFIG,encoding="utf-8") as f:
            old_xray=f.read()
    else:
        old_xray=None
    with open(CADDYFILE,encoding="utf-8") as f:
        old_caddy=f.read()
    old_users=copy.deepcopy(previous) if previous is not None else load()
    force=previous is None
    old_by_id={u.get("id"):u for u in old_users.get("users",[])}
    new_by_id={u.get("id"):u for u in d.get("users",[])}
    changed_ids={uid for uid in set(old_by_id)|set(new_by_id) if old_by_id.get(uid)!=new_by_id.get(uid)}
    def protocol_changed(*protocols):
        return force or any((old_by_id.get(uid) or new_by_id.get(uid) or {}).get("protocol","web") in protocols for uid in changed_ids)
    direct_changed=protocol_changed("web","mtproto")
    web_changed=protocol_changed("web")
    xray_changed=protocol_changed("vless","hysteria")
    awg_changed=protocol_changed(*onyx_awg.PROTOCOLS)
    try:
        for u in d["users"]:
            if u.get("enabled",True): write_unit(u)
        remove_old_units(d)
        if web_changed: sync_profiles(d)
        sync_firewall(d)
        if direct_changed: run("systemctl","daemon-reload",check=True)
        if xray_changed: sync_xray(d)
        if awg_changed: onyx_awg.sync(d["users"])
        if restart:
            for u in d["users"]:
                if (u.get("id") in changed_ids or force) and u.get("enabled",True) and u.get("protocol","web") in ("web","mtproto"):
                    unit="onyx-user-"+u["id"]+".service"
                    run("systemctl","enable",unit,check=True)
                    run("systemctl","restart",unit,check=True)
                    if run("systemctl","is-active","--quiet",unit).returncode:
                        st=run("systemctl","status",unit,"--no-pager","--full")
                        log=run("journalctl","-u",unit,"-n","30","--no-pager")
                        detail=((st.stdout or st.stderr)+"\n"+(log.stdout or log.stderr))[-3500:]
                        raise RuntimeError("User MTProxy failed: "+detail)
                    # Verify the actual WEB backend listener on its loopback port.
                    chk=run("bash","-lc",f"ss -lnt | grep -Eq ':{int(u['backend_port'])}\\b'")
                    if chk.returncode:
                        st=run("systemctl","status",unit,"--no-pager","--full")
                        raise RuntimeError("User MTProxy is active but backend port is not listening: "+(st.stdout or st.stderr)[-2000:])
            if web_changed: run("systemctl","restart","tproxy-server.service",check=True)
    except Exception:
        with open(PROFILES,"w",encoding="utf-8") as f: f.write(old_profiles)
        os.chmod(PROFILES,0o400)
        save(old_users)
        if old_xray is None:
            try: os.unlink(XRAY_CONFIG)
            except FileNotFoundError: pass
        else:
            with open(XRAY_CONFIG,"w",encoding="utf-8") as f: f.write(old_xray)
            os.chmod(XRAY_CONFIG,0o640)
        if old_xray is None:
            run("systemctl","disable","--now",XRAY_SERVICE,check=False)
        else:
            run("systemctl","restart",XRAY_SERVICE,check=False)
        with open(CADDYFILE,"w",encoding="utf-8") as f: f.write(old_caddy)
        try: shutil.chown(CADDYFILE,user="root",group="caddy")
        except Exception: pass
        os.chmod(CADDYFILE,0o640)
        run("systemctl","reload","caddy.service",check=False)
        try:
            sync_firewall(old_users)
            if awg_changed: onyx_awg.sync(old_users.get("users",[]))
        except Exception:
            pass
        raise

def add(protocol,name,requested_port=None,device_count=1):
    d=load()
    before=copy.deepcopy(d)
    # A failed request from an older manager can leave a systemd unit in an
    # auto-restart loop even though it is absent from users.json. Remove such
    # orphan units before choosing ports for the next user.
    remove_old_units(d)
    run("systemctl","daemon-reload",check=True)
    if protocol not in ("web","mtproto","vless","hysteria","awg20","awg31"):
        raise RuntimeError("Unknown proxy protocol")
    if sum(not u.get("subscription_id") for u in d["users"])>=MAX_USERS:
        raise RuntimeError("Maximum panel users reached")
    u={"id":secrets.token_hex(8),"name":name.strip(),"protocol":protocol,"enabled":True,"created_at":int(time.time())}
    if protocol in ("web","mtproto"):
        if protocol=="mtproto":
            try: device_count=int(device_count)
            except (TypeError,ValueError): raise ValueError("Количество устройств MTProto должно быть числом.")
            if device_count<1 or device_count>20:
                raise ValueError("Для MTProto можно создать от 1 до 20 отдельных ключей устройств.")
        else:
            device_count=1
        port,stats=alloc_ports(d,requested_port if protocol=="mtproto" else None)
        device_secrets=[secrets.token_hex(16) for _ in range(device_count)]
        u.update({"secret":device_secrets[0],"backend_port":port,"stats_port":stats})
        if protocol=="mtproto":
            u.update({"max_devices":device_count,"device_secrets":device_secrets})
    elif protocol=="vless":
        u.update({"secret":str(uuid.uuid4()),"backend_port":443})
    elif protocol=="hysteria":
        u.update({"secret":str(uuid.uuid4()),"backend_port":HYSTERIA_PORT})
        tls=run(XRAY_TLS_SYNC)
        if tls.returncode:
            raise RuntimeError("Hysteria 2 TLS certificate is not ready: "+(tls.stderr or tls.stdout)[-1500:])
    elif protocol in onyx_awg.PROTOCOLS:
        u.update(onyx_awg.new_user(protocol,d["users"],u["id"]))
    d["users"].append(u)
    save(d)
    try:
        apply(d,True,before)
    except Exception:
        # Re-apply the saved state so that a failed new unit is stopped and
        # deleted. Without this rollback a restart loop holds the same port
        # and every following attempt to create a user fails as well.
        save(before)
        try: apply(before,True,d)
        except Exception: pass
        raise
    print(json.dumps(u,ensure_ascii=True))

def add_json(request):
    if not isinstance(request,dict): raise ValueError("Некорректный запрос.")
    protocol=str(request.get("protocol",""))
    name=str(request.get("name","")).strip()
    if not name or len(name)>80 or any(ord(c)<32 for c in name):
        raise ValueError("Укажите имя длиной от 1 до 80 символов.")
    add(protocol,name,request.get("port"),request.get("devices",1))

def federation_sync(request):
    external_id=str(request.get("external_id", ""))
    name=str(request.get("name", "")).strip()
    protocols=request.get("protocols", [])
    if not re.fullmatch(r"[a-f0-9]{32,64}",external_id):
        raise ValueError("Invalid federation id")
    if not name or len(name)>80 or any(ord(c)<32 for c in name):
        raise ValueError("Invalid federation profile name")
    if not isinstance(protocols,list) or not protocols or any(p not in ("vless","hysteria") for p in protocols):
        raise ValueError("Federation supports VLESS and Hysteria2")
    protocols=list(dict.fromkeys(protocols))
    before=load(); d=copy.deepcopy(before)
    d["users"]=[u for u in d["users"] if u.get("federation_id")!=external_id or u.get("protocol") in protocols]
    for user in d["users"]:
        if user.get("federation_id")==external_id:
            user["name"]=name+" · "+("VLESS" if user["protocol"]=="vless" else "Hysteria2")
            user["enabled"]=True
    for protocol in protocols:
        if any(u.get("federation_id")==external_id and u.get("protocol")==protocol for u in d["users"]):
            continue
        if protocol=="hysteria":
            tls=run(XRAY_TLS_SYNC)
            if tls.returncode: raise RuntimeError("Hysteria2 TLS certificate is not ready")
        d["users"].append({"id":secrets.token_hex(8),"name":name+" · "+("VLESS" if protocol=="vless" else "Hysteria2"),
            "protocol":protocol,"enabled":True,"secret":str(uuid.uuid4()),
            "backend_port":443 if protocol=="vless" else HYSTERIA_PORT,
            "federation_id":external_id,"created_at":int(time.time())})
    save(d)
    try: apply(d,True,before)
    except Exception:
        save(before)
        try: apply(before,True,d)
        except Exception: pass
        raise
    print(json.dumps({"ok":True,"profiles":[u for u in d["users"] if u.get("federation_id")==external_id]},ensure_ascii=True))

def federation_delete(external_id):
    if not re.fullmatch(r"[a-f0-9]{32,64}",external_id): raise ValueError("Invalid federation id")
    before=load(); d=copy.deepcopy(before)
    d["users"]=[u for u in d["users"] if u.get("federation_id")!=external_id]
    if d==before:
        print(json.dumps({"ok":True,"deleted":False})); return
    save(d)
    try: apply(d,True,before)
    except Exception:
        save(before)
        try: apply(before,True,d)
        except Exception: pass
        raise
    print(json.dumps({"ok":True,"deleted":True}))

def federation_purge():
    before=load(); d=copy.deepcopy(before)
    removed=sum(1 for u in d["users"] if u.get("federation_id"))
    d["users"]=[u for u in d["users"] if not u.get("federation_id")]
    if not removed:
        print(json.dumps({"ok":True,"deleted":0})); return
    save(d)
    try: apply(d,True,before)
    except Exception:
        save(before)
        try: apply(before,True,d)
        except Exception: pass
        raise
    print(json.dumps({"ok":True,"deleted":removed}))

def delete(uid):
    before=load()
    if any(u.get("id")==uid and u.get("subscription_id") for u in before["users"]):
        raise RuntimeError("Управляйте этим профилем через вкладку Подписки.")
    try: collect_traffic(before)
    except Exception: pass
    d=copy.deepcopy(before)
    if not any(u.get("id")==uid for u in d["users"]):
        # Deletion may be repeated after a browser refresh or after a prior
        # successful request.  Treat that situation as an already-completed
        # deletion instead of returning a traceback to the panel.
        return False
    d["users"]=[u for u in d["users"] if u.get("id")!=uid]
    save(d)
    try:
        apply(d,True,before)
    except Exception:
        save(before)
        try: apply(before,True,d)
        except Exception: pass
        raise
    return True

def edit_user(uid,enabled=None,name=None):
    before=load()
    target=next((u for u in before['users'] if u['id']==uid),None)
    if uid=='primary' or target is None or target.get('subscription_id'):
        raise ValueError('Отдельный пользователь не найден или недоступен для изменения.')
    if enabled is not None and not isinstance(enabled,bool): raise ValueError('Некорректное состояние доступа.')
    if name is not None and (not name.strip() or len(name.strip())>80 or any(ord(c)<32 for c in name)):
        raise ValueError('Имя должно содержать от 1 до 80 символов.')
    after=copy.deepcopy(before)
    user=next(u for u in after['users'] if u['id']==uid)
    if enabled is not None: user['enabled']=enabled
    if name is not None: user['name']=name.strip()
    if after==before: return
    runtime_changed=user.get('enabled',True)!=target.get('enabled',True)
    if runtime_changed: collect_traffic(before)
    save(after)
    if runtime_changed:
        try: apply(after,True,before)
        except Exception:
            save(before)
            try: apply(before,True,after)
            except Exception: raise RuntimeError('Не удалось восстановить службы. Проверьте VPS через SSH.')
            raise

def edit_primary_secret(secret):
    secret=normalize_proxy_secret(secret)
    with open(PRIMARY_SECRET,encoding="ascii") as f: old_secret=f.read().strip()
    if secret==old_secret: return
    d=load()
    if any(secret in (mtproto_secrets(u) if u.get("protocol")=="mtproto" else [normalize_proxy_secret(u.get("secret",""))])
           for u in d["users"] if u.get("protocol","web") in ("web","mtproto")):
        raise ValueError("Этот секрет уже используется другим подключением.")
    with open(PROFILES,encoding="utf-8") as f: old_profiles=f.read()
    with open(MT_ENV,encoding="utf-8") as f: old_env=f.read()
    profiles=json.loads(old_profiles)
    candidates=[p for p in profiles.get("profiles",[]) if not str(p.get("name","")).startswith("panel:")]
    target=next((p for p in candidates if p.get("name")=="default"),None)
    if target is None:
        target=next((p for p in candidates if str(p.get("backend",""))=="127.0.0.1:2398"),None)
    if target is None:
        raise RuntimeError("Основной профиль WEB Proxy не найден.")
    target["secret"]=secret
    new_profiles=json.dumps(profiles,ensure_ascii=True,indent=2)+"\n"
    if re.search(r"(?m)^MTPROXY_SECRET=.*$",old_env):
        new_env=re.sub(r"(?m)^MTPROXY_SECRET=.*$","MTPROXY_SECRET="+secret,old_env)
    else:
        new_env="MTPROXY_SECRET="+secret+"\n"+old_env
    check_path=PROFILES+".check"
    try:
        atomic_text(check_path,new_profiles,0o400,"tproxy")
        checked=run("/usr/local/bin/tproxy-server","-config","/etc/tproxy-server/config.json",
                    "-profiles-file",check_path,"-check")
        if checked.returncode:
            raise RuntimeError("Новый секрет отклонён relay: "+(checked.stderr or checked.stdout)[-1200:])
        os.unlink(check_path)
        atomic_text(PRIMARY_SECRET,secret+"\n",0o600)
        atomic_text(PROFILES,new_profiles,0o400,"tproxy")
        atomic_text(MT_ENV,new_env,0o640,"mtproxy")
        run("systemctl","restart","mtproxy.service",check=True)
        run("systemctl","restart","tproxy-server.service",check=True)
        for service in ("mtproxy.service","tproxy-server.service"):
            if run("systemctl","is-active","--quiet",service).returncode:
                raise RuntimeError(service+" не запустилась после смены секрета.")
    except Exception:
        try: os.unlink(check_path)
        except FileNotFoundError: pass
        atomic_text(PRIMARY_SECRET,old_secret+"\n",0o600)
        atomic_text(PROFILES,old_profiles,0o400,"tproxy")
        atomic_text(MT_ENV,old_env,0o640,"mtproxy")
        run("systemctl","restart","mtproxy.service",check=False)
        run("systemctl","restart","tproxy-server.service",check=False)
        raise

def edit_direct_secret(uid,secret):
    before=load()
    target=next((u for u in before["users"] if u.get("id")==uid),None)
    if target is None or target.get("subscription_id") or target.get("protocol","web") not in ("web","mtproto"):
        raise ValueError("Секрет можно изменить только у отдельного WEB Proxy или MTProto.")
    secret=normalize_proxy_secret(secret)
    with open(PRIMARY_SECRET,encoding="ascii") as f: primary=normalize_proxy_secret(f.read())
    occupied=set()
    for other in before["users"]:
        if other.get("id")==uid or other.get("protocol","web") not in ("web","mtproto"): continue
        occupied.update(mtproto_secrets(other) if other.get("protocol")=="mtproto" else [normalize_proxy_secret(other.get("secret",""))])
    if secret==primary or secret in occupied:
        raise ValueError("Этот секрет уже используется другим подключением.")
    if secret==normalize_proxy_secret(target.get("secret","")): return
    after=copy.deepcopy(before)
    edited=next(u for u in after["users"] if u.get("id")==uid)
    edited["secret"]=secret
    if edited.get("protocol")=="mtproto":
        current=mtproto_secrets(edited)
        current[0]=secret
        edited["device_secrets"]=current
        edited["max_devices"]=len(current)
    collect_traffic(before)
    save(after)
    try:
        apply(after,True,before)
    except Exception:
        save(before)
        try: apply(before,True,after)
        except Exception: raise RuntimeError("Не удалось восстановить службы. Проверьте VPS через SSH.")
        raise

def set_secret(request):
    if not isinstance(request,dict): raise ValueError("Некорректный запрос.")
    uid=str(request.get("id",""))
    if uid=="primary": edit_primary_secret(request.get("secret",""))
    elif re.fullmatch(r"[a-f0-9]{16}",uid): edit_direct_secret(uid,request.get("secret",""))
    else: raise ValueError("Подключение не найдено.")
    print(json.dumps({"ok":True}))

def init():
    d=load()
    onyx_awg.upgrade_users(d["users"])
    # Persist stable normalization when upgrading. Profiles from the withdrawn
    # shared-interface preview receive independent keys, ports and fingerprints.
    save(d)
    for u in d["users"]:
        if u.get("enabled",True): write_unit(u)
    remove_old_units(d)
    sync_profiles(d)
    sync_firewall(d)
    run("systemctl","daemon-reload",check=True)
    sync_xray(d)
    onyx_awg.sync(d["users"])
    collect_traffic(d)

def subscription_command():
    try:
        raw=sys.stdin.read(8193)
        if len(raw)>8192: raise SubscriptionError("Request too large")
        request=json.loads(raw)
        if not isinstance(request,dict): raise SubscriptionError("Invalid request")
        before=load()
        after,result=(issue_subscription if request.get("operation")=="fetch" else mutate_subscription)(before,request)
        changed=before["users"]!=after["users"]
        if changed:
            if any(u.get("enabled",True) and u.get("protocol")=="hysteria" for u in after["users"]):
                run(XRAY_TLS_SYNC,check=True)
            collect_traffic(before)
            try:
                sync_firewall(after)
                sync_xray(after)
                save(after)
            except Exception:
                # Database remains unchanged until both runtime components pass.
                # Restore only managed Xray/firewall; never restart WEB backends.
                try:
                    sync_firewall(before)
                    sync_xray(before)
                except Exception:
                    raise RuntimeError("Не удалось восстановить службы после ошибки; требуется диагностика VPS.")
                raise
        elif after!=before:
            save(after)
        print(json.dumps(result,ensure_ascii=True))
    except SubscriptionError as exc:
        print(json.dumps({"ok":False,"status":exc.status,"code":exc.code,"message":str(exc)},ensure_ascii=True))
    except Exception:
        print(json.dumps({"ok":False,"status":503,"code":"backend","message":"Не удалось применить подписку. Проверьте Xray и TLS на сервере."}))

cmd=sys.argv[1] if len(sys.argv)>1 else "init"
# Serialize state changes, including slot allocation, with CLI and the panel.
# Traffic has its own lock and only reads users.json via atomic replacement.
if cmd not in ("users","traffic"):
    manager_lock=open("/etc/onyx-panel/manager.lock","a+")
    os.chmod(manager_lock.name,0o600)
    deadline=time.monotonic()+15
    while True:
        try:
            fcntl.flock(manager_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic()>deadline: raise SystemExit("Менеджер занят. Повторите запрос позже.")
            time.sleep(0.1)
if cmd=="init": init()
elif cmd=="subscription": subscription_command()
elif cmd=="add": add(sys.argv[2]," ".join(sys.argv[3:]))
elif cmd=="add-json": add_json(json.load(sys.stdin))
elif cmd=="federation-sync": federation_sync(json.load(sys.stdin))
elif cmd=="federation-delete": federation_delete(json.load(sys.stdin).get("external_id",""))
elif cmd=="federation-purge": federation_purge()
elif cmd=="delete": print(json.dumps({"deleted":delete(sys.argv[2])}))
elif cmd=="set-user":
    if sys.argv[3] not in ('0','1'): raise SystemExit('Invalid enabled state')
    edit_user(sys.argv[2],enabled=sys.argv[3]=='1')
    print(json.dumps({'ok':True}))
elif cmd=="rename-user":
    edit_user(sys.argv[2],name=sys.argv[3])
    print(json.dumps({'ok':True}))
elif cmd=="set-secret": set_secret(json.load(sys.stdin))
elif cmd=="sync": apply(load(),True)
elif cmd=="firewall": sync_firewall(load())
elif cmd=="traffic":
    traffic_state=collect_traffic()
    print(json.dumps(traffic_state,ensure_ascii=True))
elif cmd=="users": print(json.dumps(load(),ensure_ascii=True))
else: raise SystemExit("usage: init|add|delete|set-user|rename-user|set-secret|sync|firewall|traffic|users")

PY

chmod 0755 "$MANAGER"

cat > "$FIREWALL_SERVICE_FILE" <<'EOF'
[Unit]
Description=Onyx Panel persistent user-port firewall
After=nftables.service
PartOf=nftables.service
Before=network-online.target onyx-panel.service

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/usr/local/sbin/onyx-panelctl firewall
ExecReload=/usr/local/sbin/onyx-panelctl firewall
ExecStop=/bin/sh -c '/usr/sbin/nft delete table inet onyx_panel 2>/dev/null || true; /usr/sbin/nft delete table ip onyx_awg 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$FIREWALL_SERVICE_FILE"

cat > /etc/systemd/system/onyx-panel-traffic.service <<'EOF'
[Unit]
Description=Onyx Panel traffic collector
After=network-online.target onyx-panel-firewall.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/onyx-panelctl traffic
TimeoutStartSec=60
Nice=10
EOF

cat > /etc/systemd/system/onyx-panel-traffic.timer <<'EOF'
[Unit]
Description=Collect Onyx Panel traffic every 10 seconds

[Timer]
OnActiveSec=5s
OnUnitInactiveSec=10s
AccuracySec=1s
Unit=onyx-panel-traffic.service

[Install]
WantedBy=timers.target
EOF
chmod 0644 /etc/systemd/system/onyx-panel-traffic.service /etc/systemd/system/onyx-panel-traffic.timer

# Resource metrics must not depend on the success of the proxy Stats API.
cat > /etc/systemd/system/onyx-panel-metrics.service <<'EOF'
[Unit]
Description=Onyx Panel VPS metrics

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/onyx-panel/onyx_metrics.py collect
TimeoutStartSec=20
Nice=10
EOF
cat > /etc/systemd/system/onyx-panel-metrics.timer <<'EOF'
[Unit]
Description=Collect Onyx Panel VPS metrics every 10 seconds

[Timer]
OnActiveSec=5s
OnUnitInactiveSec=10s
AccuracySec=1s
Unit=onyx-panel-metrics.service

[Install]
WantedBy=timers.target
EOF
chmod 0644 /etc/systemd/system/onyx-panel-metrics.service /etc/systemd/system/onyx-panel-metrics.timer

cat > /usr/local/sbin/onyx-panel-sync-tls <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
MODE="${1:-sync}"
[[ "$MODE" == "sync" || "$MODE" == "--maintain" || "$MODE" == "--force" ]] || {
    echo "Usage: onyx-panel-sync-tls [--maintain|--force]" >&2
    exit 2
}
exec 8>/run/lock/onyx-panel-tls.lock
flock -w 15 8 || { echo "Another TLS check is still running" >&2; exit 1; }
DOMAIN="$(sed -n 's/^Environment=TPROXY_HOSTNAME=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)"
[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || { echo "Invalid WEB Proxy domain" >&2; exit 1; }
DEST_DIR="/etc/onyx-panel-xray/tls"
DEST_CERT="$DEST_DIR/domain.crt"
DEST_KEY="$DEST_DIR/domain.key"
LIVE_CERT="$(mktemp /tmp/onyx-live-certificate.XXXXXX)"
trap 'rm -f "$LIVE_CERT"' EXIT

read_live_certificate() {
    : > "$LIVE_CERT"
    timeout 12 openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" </dev/null 2>/dev/null |
        openssl x509 -outform PEM -out "$LIVE_CERT" 2>/dev/null
}

if [[ "$MODE" != "sync" ]]; then
    needs_attention=0
    if ! read_live_certificate || ! openssl x509 -in "$LIVE_CERT" -noout -checkend 1209600 >/dev/null 2>&1; then
        needs_attention=1
    fi
    if [[ "$MODE" == "--force" || "$needs_attention" == 1 ]]; then
        caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
        # The canonical Caddyfile intentionally has `admin off`; SIGUSR1 is
        # Caddy's supported config reload signal for `caddy run` in this mode.
        if ! systemctl kill --signal=SIGUSR1 --kill-who=main caddy.service >/dev/null 2>&1; then
            systemctl restart caddy.service
        fi
        renewed=0
        for _ in $(seq 1 24); do
            if read_live_certificate && openssl x509 -in "$LIVE_CERT" -noout -checkend 0 >/dev/null 2>&1; then
                renewed=1
                break
            fi
            sleep 5
        done
        [[ "$renewed" == 1 ]] || { echo "Caddy did not provide a valid TLS certificate for $DOMAIN" >&2; exit 1; }
    fi
    read_live_certificate || { echo "Could not read the active TLS certificate for $DOMAIN" >&2; exit 1; }
    echo "TLS certificate: $(openssl x509 -in "$LIVE_CERT" -noout -enddate | cut -d= -f2-)"
fi

CADDY_USER="$(systemctl show -p User --value caddy.service 2>/dev/null || true)"
CADDY_USER="${CADDY_USER:-caddy}"
CADDY_HOME="$(getent passwd "$CADDY_USER" | cut -d: -f6 || true)"
SEARCH_ROOTS=(
    "${CADDY_HOME:-/var/lib/caddy}/.local/share/caddy/certificates"
    "/etc/caddy/caddy/.local/share/caddy/certificates"
    "/var/lib/caddy/.local/share/caddy/certificates"
    "/root/.local/share/caddy/certificates"
)
SOURCE_CERT=""
SOURCE_KEY=""
[[ "$MODE" == "sync" ]] || echo "Searching the Caddy certificate store..."
for root in "${SEARCH_ROOTS[@]}"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r candidate; do
        key="${candidate%.crt}.key"
        [[ -s "$key" ]] || continue
        if openssl x509 -in "$candidate" -noout -checkend 86400 >/dev/null 2>&1; then
            SOURCE_CERT="$candidate"
            SOURCE_KEY="$key"
            break 2
        fi
    done < <(timeout 12 find "$root" -xdev -type f -path "*/${DOMAIN}/${DOMAIN}.crt" -print 2>/dev/null || true)
done
# Caddy can be started with a custom HOME/XDG_DATA_HOME by a pre-existing
# service.  Search only the known Caddy state directories as a bounded
# fallback; never scan the whole VPS.
if [[ -z "$SOURCE_CERT" ]]; then
    for root in /etc/caddy /var/lib/caddy /root/.local/share/caddy; do
        [[ -d "$root" ]] || continue
        while IFS= read -r candidate; do
            key="${candidate%.crt}.key"
            [[ -s "$key" ]] || continue
            if openssl x509 -in "$candidate" -noout -checkend 86400 >/dev/null 2>&1; then
                SOURCE_CERT="$candidate"
                SOURCE_KEY="$key"
                break 2
            fi
        done < <(timeout 12 find "$root" -xdev -type f -path "*/${DOMAIN}/${DOMAIN}.crt" -print 2>/dev/null || true)
    done
fi
[[ -n "$SOURCE_CERT" && -n "$SOURCE_KEY" ]] || { echo "Caddy TLS certificate for $DOMAIN was not found" >&2; exit 1; }
CERT_PUB="$(timeout 10 openssl x509 -in "$SOURCE_CERT" -pubkey -noout | openssl sha256)"
KEY_PUB="$(timeout 10 openssl pkey -in "$SOURCE_KEY" -pubout 2>/dev/null | openssl sha256)"
[[ -n "$CERT_PUB" && "$CERT_PUB" == "$KEY_PUB" ]] || { echo "Caddy certificate/private key mismatch" >&2; exit 1; }
install -d -o root -g xray -m 0750 "$DEST_DIR"
changed=0
if ! cmp -s "$SOURCE_CERT" "$DEST_CERT" 2>/dev/null; then
    install -o root -g xray -m 0640 "$SOURCE_CERT" "$DEST_CERT"
    changed=1
fi
if ! cmp -s "$SOURCE_KEY" "$DEST_KEY" 2>/dev/null; then
    install -o root -g xray -m 0640 "$SOURCE_KEY" "$DEST_KEY"
    changed=1
fi
if [[ "$changed" == 1 ]] && systemctl is-active --quiet onyx-panel-xray.service; then
    [[ "$MODE" == "sync" ]] || echo "Applying the renewed certificate to Hysteria2..."
    timeout 45 systemctl try-restart onyx-panel-xray.service || {
        echo "Xray did not restart within 45 seconds" >&2
        exit 1
    }
fi
[[ "$MODE" == "sync" ]] || echo "TLS maintenance completed."
SH
chmod 0750 /usr/local/sbin/onyx-panel-sync-tls

cat > /etc/systemd/system/onyx-panel-sync-tls.service <<'EOF'
[Unit]
Description=Synchronize Caddy certificate for Onyx Panel Xray
After=caddy.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/onyx-panel-sync-tls --maintain
TimeoutStartSec=180
EOF

cat > /etc/systemd/system/onyx-panel-sync-tls.timer <<'EOF'
[Unit]
Description=Refresh Onyx Panel Xray TLS certificate

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/onyx-panel-xray.service <<EOF
[Unit]
Description=Onyx Panel Xray (VLESS and Hysteria 2)
After=network-online.target caddy.service
Wants=network-online.target

[Service]
Type=simple
User=xray
Group=xray
ExecStart=$XRAY_BIN run -config $XRAY_CONFIG
Restart=on-failure
RestartSec=2
LimitNOFILE=1048576
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/onyx-panel-xray

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 /etc/systemd/system/onyx-panel-sync-tls.service /etc/systemd/system/onyx-panel-sync-tls.timer /etc/systemd/system/onyx-panel-xray.service

systemctl daemon-reload
systemctl enable --now onyx-panel-sync-tls.timer
if ! /usr/local/sbin/onyx-panel-sync-tls; then
    echo "      NOTE: Caddy certificate is not available to Xray yet; VLESS remains available, while Hysteria 2 can be created after certificate issuance."
fi

echo "[2/6] Writing panel..."

cat > "$APP_FILE" <<'PY'
#!/usr/bin/env python3
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import grp
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse
from collections import defaultdict, deque
from onyx_subscriptions import PREFIX as SUB_PREFIX
from onyx_panel_extras import preview_document
from onyx_ui import page_layout, login_ui, dashboard_body, dashboard_page, users_ui, editor_ui, openflux_ui, client_records, nodes_ui, updates_ui
import onyx_metrics as server_metrics
import onyx_update as web_updates
import onyx_components as components
import onyx_nodes as node_api
import onyx_openflux as openflux
import onyx_awg as awg

HOST="127.0.0.1"
PORT=8090
DATA="/var/lib/onyx-panel/data.json"
KEY="/var/lib/onyx-panel/session.key"
DOMAIN=os.environ.get("ONYX_DOMAIN","")
MTPROTO_HOST=os.environ.get("ONYX_MTPROTO_HOST",DOMAIN)
PANEL_PATH=os.environ.get("ONYX_PANEL_PATH","")
PRIMARY="/etc/onyx-panel/primary-secret"
PROFILES="/etc/tproxy-server/profiles.json"
USERS="/etc/onyx-panel/users.json"
TRAFFIC="/var/lib/onyx-panel/traffic.json"
XRAY_PATH_FILE="/etc/onyx-panel/xray-path"
HYSTERIA_PORT=8443
MANAGER="/usr/local/sbin/onyx-panelctl"
QR="/usr/bin/qrencode"
LOGO="/opt/onyx-panel/onyx-logo.png"
FLAGS="/opt/onyx-panel/flags"
SITE_INDEX="/srv/tproxy-site/index.html"
SITE_BACKUP="/var/lib/onyx-panel/index.html.bak"
SITE_SOURCE="/var/lib/onyx-panel/site-source.html"
SITE_SOURCE_BACKUP="/var/lib/onyx-panel/site-source.html.bak"
SITE_CSS="/srv/tproxy-site/panel-site.css"
SITE_CSS_BACKUP="/var/lib/onyx-panel/panel-site.css.bak"
SITE_JS="/srv/tproxy-site/panel-site.js"
SITE_JS_BACKUP="/var/lib/onyx-panel/panel-site.js.bak"
MAX_HTML_BYTES=1024*1024
SITE_DRAFT="/var/lib/onyx-panel/site-draft.html"
CUSTOM_PRESETS_FILE="/var/lib/onyx-panel/custom-presets.json"
API_KEY_FILE="/var/lib/onyx-panel/api.key"
NODES_FILE="/var/lib/onyx-panel/nodes.json"
LOCATION_FILE="/var/lib/onyx-panel/location.json"
API_KEY=node_api.ensure_api_key(API_KEY_FILE)
SUB_FETCH_SLOTS=threading.BoundedSemaphore(4)
SUB_RATE_LOCK=threading.Lock()
SUB_REQUESTS={}

# Presets are deliberately standalone at authoring time: no CDN and no icon
# font. On publication the panel moves executable CSS/JS into immutable local
# files because the public relay uses a strict Content-Security-Policy.
PRESETS=[]
os.makedirs(os.path.dirname(DATA),exist_ok=True)
if not os.path.exists(KEY):
    with open(KEY,"wb") as f: f.write(secrets.token_bytes(32))
with open(KEY,"rb") as f: SESSION_KEY=f.read()
os.chmod(KEY,0o600)
STATE_LOCK=threading.RLock()
LOGIN_LOCK=threading.RLock()
LOGIN_FAILURES=defaultdict(deque)
LOGIN_FAILURES_GLOBAL=deque()
LOGIN_WINDOW=10*60
LOGIN_LIMIT=8
LOGIN_GLOBAL_LIMIT=200

def esc(x): return html.escape(str(x),quote=True)
def hash_password(p):
    salt=secrets.token_bytes(16)
    d=hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return base64.b64encode(salt+d).decode()
def check_password(p,h):
    try:
        raw=base64.b64decode(h); salt,exp=raw[:16],raw[16:]
        got=hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
        return secrets.compare_digest(exp,got)
    except Exception:
        return False
def sign(x): return x+"."+hmac.new(SESSION_KEY,x.encode(),hashlib.sha256).hexdigest()
def rotate_session_key():
    global SESSION_KEY
    fresh=secrets.token_bytes(32)
    tmp=KEY+".tmp"
    with open(tmp,"wb") as f:
        f.write(fresh); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o600)
    os.replace(tmp,KEY)
    SESSION_KEY=fresh
def client_id(handler):
    forwarded=handler.headers.get("X-Forwarded-For","")
    candidate=forwarded.split(",")[-1].strip() if forwarded else handler.client_address[0]
    try: return str(ipaddress.ip_address(candidate))
    except ValueError: return "unknown"
def login_blocked(client):
    now=time.monotonic(); cutoff=now-LOGIN_WINDOW
    with LOGIN_LOCK:
        bucket=LOGIN_FAILURES[client]
        while bucket and bucket[0]<cutoff: bucket.popleft()
        while LOGIN_FAILURES_GLOBAL and LOGIN_FAILURES_GLOBAL[0]<cutoff: LOGIN_FAILURES_GLOBAL.popleft()
        if not LOGIN_FAILURES_GLOBAL:
            LOGIN_FAILURES.clear()
            bucket=LOGIN_FAILURES[client]
        return len(bucket)>=LOGIN_LIMIT or len(LOGIN_FAILURES_GLOBAL)>=LOGIN_GLOBAL_LIMIT
def login_failed(client):
    now=time.monotonic()
    with LOGIN_LOCK:
        LOGIN_FAILURES[client].append(now)
        LOGIN_FAILURES_GLOBAL.append(now)
def login_succeeded(client):
    with LOGIN_LOCK: LOGIN_FAILURES.pop(client,None)
def load():
    try:
        with open(DATA,encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {"admin":{"user":"admin","hash":""}}
def save(d):
    t=DATA+".tmp"
    with open(t,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=True,indent=2)
    os.chmod(t,0o600); os.replace(t,DATA)
def primary():
    try:
        with open(PRIMARY,encoding="utf-8") as f: return f.read().strip()
    except Exception: return ""
def users():
    try:
        with open(USERS,encoding="utf-8") as f: return json.load(f).get("users",[])
    except Exception: return []
def traffic():
    try:
        with open(TRAFFIC,encoding="utf-8") as f:
            value=json.load(f)
            return value if isinstance(value,dict) else {}
    except Exception: return {}
def human_bytes(value):
    value=max(0,int(value or 0))
    units=("Б","КБ","МБ","ГБ","ТБ")
    size=float(value)
    for unit in units:
        if size<1024 or unit==units[-1]:
            return ("%.0f"%size if unit=="Б" else "%.1f"%size)+" "+unit
        size/=1024
def traffic_info(uid,state=None):
    state=state or traffic()
    item=state.get(uid,{})
    up=max(0,int(item.get("up",0)))
    down=max(0,int(item.get("down",0)))
    last=max(0,int(item.get("last_change",0)))
    active=bool(item.get("service_active")) and last>0 and time.time()-last<=90
    return {"up":up,"down":down,"total":up+down,"last":last,"active":active,"service":bool(item.get("service_active"))}
def read_site_html():
    try:
        # Keep the author source separate from the generated public files.
        # Reading index.html here used to make the next edit depend on the
        # previous preset's CSS/JS files.
        if os.path.exists(SITE_SOURCE):
            with open(SITE_SOURCE,encoding="utf-8") as f: return f.read()
        with open(SITE_INDEX,encoding="utf-8") as f: return hydrate_legacy_assets(f.read())
    except Exception as e:
        raise RuntimeError("Не удалось прочитать index.html: "+str(e))
def install_public_file(path,raw):
    tmp=path+".tmp"
    try:
        with open(tmp,"wb") as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,0,grp.getgrnam("tproxy").gr_gid)
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
def install_private_file(path,raw):
    tmp=path+".tmp"
    try:
        with open(tmp,"wb") as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,0,0)
        os.chmod(tmp,0o600)
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
def restart_public_site():
    r=subprocess.run(["systemctl","restart","tproxy-server.service"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    if r.returncode or subprocess.run(["systemctl","is-active","--quiet","tproxy-server.service"],timeout=10).returncode:
        raise RuntimeError((r.stderr or r.stdout or "tproxy-server failed to restart").strip())
    # systemd considers the process active before both HTTP listeners have
    # completed their startup. Wait for the local health endpoint instead of
    # racing the first landing-page request.
    for _ in range(30):
        health=subprocess.run(["curl","-fsS","--noproxy","*","--max-time","2",
                               "http://127.0.0.1:8081/healthz"],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=4)
        if health.returncode==0: break
        time.sleep(0.5)
    else:
        raise RuntimeError("Relay health endpoint did not become ready after restart")
def fetch_published(path):
    # Resolve the real HTTPS hostname to loopback. This validates Caddy and the
    # relay without depending on public DNS, IPv6 routing or hairpin NAT.
    commands=(
        ["curl","-kfsS","--noproxy","*","--resolve",DOMAIN+":443:127.0.0.1",
         "--connect-timeout","2","--max-time","5","https://"+DOMAIN+path],
        ["curl","-fsS","--noproxy","*","-H","Host: "+DOMAIN,
         "--connect-timeout","2","--max-time","5","http://127.0.0.1:8080"+path],
    )
    last=""
    for attempt in range(12):
        for command in commands:
            result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=8)
            if result.returncode==0: return result.stdout
            last=(result.stderr or result.stdout or "relay request failed").strip()
        time.sleep(min(0.5+attempt*0.15,1.5))
    raise RuntimeError("Relay did not publish the landing page after restart: "+last[-300:])
def verify_public_asset(path, marker):
    body=fetch_published(path)
    if marker not in body:
        raise RuntimeError("Relay did not publish "+path+" after restart")
def verify_public_page(css_name,js_name):
    # A query forces the relay's no-store path, avoiding a false success from
    # the five-minute public index cache while a new design is being published.
    stamp=hashlib.sha256(((css_name or "")+(js_name or "")).encode()).hexdigest()[:12]
    body=fetch_published("/?onyx-site-check="+stamp)
    if css_name and ('/'+css_name) not in body:
        raise RuntimeError("Published landing page does not reference its stylesheet")
    if js_name and ('/'+js_name) not in body:
        raise RuntimeError("Published landing page does not reference its script")
def insert_into_head(document,tag):
    """Insert an asset without placing anything before <!doctype html>."""
    closing=re.search(r"</head\s*>",document,flags=re.I)
    if closing:
        return document[:closing.start()]+tag+document[closing.start():]
    opening=re.search(r"<html\b[^>]*>",document,flags=re.I)
    if opening:
        return document[:opening.end()]+"<head>"+tag+"</head>"+document[opening.end():]
    doctype=re.match(r"\s*<!doctype\b[^>]*>",document,flags=re.I)
    position=doctype.end() if doctype else 0
    return document[:position]+"<head>"+tag+"</head>"+document[position:]
def externalize_inline_assets(source):
    # Static public pages intentionally block inline CSS/JS. Keep generated
    # assets at local paths that tproxy-server can serve from public_dir. Data
    # scripts (JSON-LD, import maps and other non-executable payloads) must stay
    # in the HTML exactly where the author put them.
    styles=[]
    def replace_style(match):
        css=match.group(1).strip()
        if not css: return ""
        styles.append(css)
        return '<link rel="stylesheet" href="/panel-site.css">' if len(styles)==1 else ""
    rendered=re.sub(r"<style\b[^>]*>(.*?)</style\s*>",replace_style,source,flags=re.I|re.S)
    scripts=[]
    def replace_script(match):
        attributes=match.group(1) or ""
        type_match=re.search(r'\btype\s*=\s*(["\'])(.*?)\1',attributes,flags=re.I|re.S)
        script_type=(type_match.group(2).strip().lower() if type_match else "")
        executable_types={"","module","text/javascript","application/javascript","text/ecmascript","application/ecmascript"}
        if script_type not in executable_types:
            return match.group(0)
        code=match.group(2).strip()
        if not code: return ""
        scripts.append(code)
        return '<script src="/panel-site.js" defer></script>' if len(scripts)==1 else ""
    rendered=re.sub(r"<script\b(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script\s*>",replace_script,rendered,flags=re.I|re.S)
    # The relay CSP intentionally rejects style="..." attributes. Convert
    # them to same-origin stylesheet rules so standalone HTML pasted into the
    # editor keeps its layout without enabling unsafe-inline globally.
    inline_styles=[]
    def replace_inline_style(match):
        value=match.group(2).strip()
        if not value: return ""
        index=len(inline_styles)
        marker="onyx-%d"%index
        inline_styles.append('[data-onyx-style="%s"]{%s}'%(marker,value))
        return ' data-onyx-style="'+marker+'"'
    rendered=re.sub(r'\sstyle\s*=\s*(["\'])(.*?)\1',replace_inline_style,rendered,flags=re.I|re.S)
    if inline_styles:
        styles.append("\n".join(inline_styles))
    css="/* Onyx Panel public CSS */\n"+"\n\n".join(styles) if styles else ""
    javascript="/* Onyx Panel public JS */\n"+"\n\n".join(scripts) if scripts else ""
    css_name="panel-site-"+hashlib.sha256(css.encode()).hexdigest()[:12]+".css" if css else ""
    js_name="panel-site-"+hashlib.sha256(javascript.encode()).hexdigest()[:12]+".js" if javascript else ""
    if css_name:
        rendered=rendered.replace('/panel-site.css','/'+css_name)
        if '/'+css_name not in rendered:
            rendered=insert_into_head(rendered,'<link rel="stylesheet" href="/'+css_name+'">')
    if js_name:
        rendered=rendered.replace('/panel-site.js','/'+js_name)
    # Never keep a reference to a generated asset unless we generated it in
    # this exact save. It prevents a stale link from a damaged old page.
    if not styles:
        rendered=re.sub(r'<link\b[^>]*\bhref\s*=\s*(["\'])/panel-site(?:-[a-f0-9]{12})?\.css\1[^>]*>\s*',"",rendered,flags=re.I)
    if not scripts:
        rendered=re.sub(r'<script\b[^>]*\bsrc\s*=\s*(["\'])/panel-site(?:-[a-f0-9]{12})?\.js\1[^>]*>\s*</script\s*>\s*',"",rendered,flags=re.I|re.S)
    return rendered,css,javascript,css_name,js_name
def hydrate_legacy_assets(source):
    """Convert pages saved by older panel versions back to one HTML file."""
    css_ref=re.search(r'/((?:panel-site)(?:-[a-f0-9]{12})?\.css)',source,flags=re.I)
    js_ref=re.search(r'/((?:panel-site)(?:-[a-f0-9]{12})?\.js)',source,flags=re.I)
    try:
        css_path=os.path.join(os.path.dirname(SITE_INDEX),css_ref.group(1)) if css_ref else SITE_CSS
        with open(css_path,encoding="utf-8") as f: css=f.read()
    except Exception: css=""
    try:
        js_path=os.path.join(os.path.dirname(SITE_INDEX),js_ref.group(1)) if js_ref else SITE_JS
        with open(js_path,encoding="utf-8") as f: javascript=f.read()
    except Exception: javascript=""
    if css:
        source=re.sub(
            r'<link\b[^>]*\bhref\s*=\s*(["\'])/panel-site(?:-[a-f0-9]{12})?\.css\1[^>]*>',
            '<style>\n'+css+'\n</style>', source, flags=re.I)
    if javascript:
        source=re.sub(
            r'<script\b[^>]*\bsrc\s*=\s*(["\'])/panel-site(?:-[a-f0-9]{12})?\.js\1[^>]*>\s*</script\s*>',
            '<script>\n'+javascript+'\n</script>', source, flags=re.I|re.S)
    return source
def write_site_html(source):
    # Preserve the author's original document in SITE_SOURCE. The public copy
    # references same-origin immutable assets so the relay's strict CSP does
    # not strip the design. JSON-LD, SEO and verification markup stay inline.
    rendered,css,javascript,css_name,js_name=externalize_inline_assets(source)
    raw=rendered.encode("utf-8")
    if not source.strip(): raise ValueError("HTML не может быть пустым")
    if len(source.encode("utf-8"))>MAX_HTML_BYTES: raise ValueError("HTML превышает лимит 1 МБ")
    with STATE_LOCK:
        had_index_backup=os.path.exists(SITE_INDEX)
        had_source_backup=os.path.exists(SITE_SOURCE)
        had_css_backup=os.path.exists(SITE_CSS)
        had_js_backup=os.path.exists(SITE_JS)
        if had_index_backup:
            shutil.copy2(SITE_INDEX,SITE_BACKUP)
            os.chmod(SITE_BACKUP,0o600)
        if had_source_backup:
            shutil.copy2(SITE_SOURCE,SITE_SOURCE_BACKUP)
            os.chmod(SITE_SOURCE_BACKUP,0o600)
        if had_css_backup:
            shutil.copy2(SITE_CSS,SITE_CSS_BACKUP)
            os.chmod(SITE_CSS_BACKUP,0o600)
        if had_js_backup:
            shutil.copy2(SITE_JS,SITE_JS_BACKUP)
            os.chmod(SITE_JS_BACKUP,0o600)
        try:
            css_path=os.path.join(os.path.dirname(SITE_INDEX),css_name) if css_name else ""
            js_path=os.path.join(os.path.dirname(SITE_INDEX),js_name) if js_name else ""
            if css:
                install_public_file(css_path,css.encode("utf-8"))
            if javascript:
                install_public_file(js_path,javascript.encode("utf-8"))
            install_public_file(SITE_INDEX,raw)
            # tproxy-server serves public_dir from memory; a successful
            # restart makes the edited landing page visible immediately.
            restart_public_site()
            if css: verify_public_asset("/"+css_name,"Onyx Panel public CSS")
            if javascript: verify_public_asset("/"+js_name,"Onyx Panel public JS")
            verify_public_page(css_name,js_name)
            install_private_file(SITE_SOURCE,source.encode("utf-8"))
            # Keep a few prior immutable assets for rollback/open browser tabs.
            generated=[]
            for name in os.listdir(os.path.dirname(SITE_INDEX)):
                if re.fullmatch(r"panel-site-[a-f0-9]{12}\.(?:css|js)",name):
                    path=os.path.join(os.path.dirname(SITE_INDEX),name)
                    generated.append((os.path.getmtime(path),path))
            for _,path in sorted(generated,reverse=True)[12:]:
                try: os.unlink(path)
                except FileNotFoundError: pass
        except Exception:
            if had_index_backup and os.path.exists(SITE_BACKUP):
                try:
                    install_public_file(SITE_INDEX,open(SITE_BACKUP,"rb").read())
                    if had_css_backup and os.path.exists(SITE_CSS_BACKUP):
                        install_public_file(SITE_CSS,open(SITE_CSS_BACKUP,"rb").read())
                    elif os.path.exists(SITE_CSS):
                        os.unlink(SITE_CSS)
                    if had_js_backup and os.path.exists(SITE_JS_BACKUP):
                        install_public_file(SITE_JS,open(SITE_JS_BACKUP,"rb").read())
                    elif os.path.exists(SITE_JS):
                        os.unlink(SITE_JS)
                    if had_source_backup and os.path.exists(SITE_SOURCE_BACKUP):
                        install_private_file(SITE_SOURCE,open(SITE_SOURCE_BACKUP,"rb").read())
                    elif os.path.exists(SITE_SOURCE):
                        os.unlink(SITE_SOURCE)
                    restart_public_site()
                except Exception: pass
            raise
def custom_presets():
    try:
        with open(CUSTOM_PRESETS_FILE,encoding="utf-8") as stream: value=json.load(stream)
        if not isinstance(value,list): return []
        return [item for item in value if isinstance(item,dict) and
                isinstance(item.get("id"),str) and item["id"].startswith("custom-") and
                isinstance(item.get("name"),str) and isinstance(item.get("description"),str) and
                isinstance(item.get("html"),str)]
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return []
def save_custom_presets(items):
    install_private_file(CUSTOM_PRESETS_FILE,json.dumps(items,ensure_ascii=False,indent=2).encode("utf-8"))
def all_presets():
    return PRESETS+custom_presets()
def get_preset(preset_id):
    for preset in all_presets():
        if preset.get("id")==preset_id: return preset
    raise ValueError("Пресет не найден")

def ctl(*args):
    r=subprocess.run([MANAGER,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
    if r.returncode: raise RuntimeError(r.stderr.strip() or "manager failed")
    return json.loads(r.stdout) if r.stdout.strip() else None
def subscription_registry():
    try:
        with open(USERS,encoding="utf-8") as f:
            return json.load(f).get("subscriptions",[])
    except FileNotFoundError:
        return []
def ctl_subscription(request):
    # Tokens and hardware identifiers never appear in process arguments.
    try:
        r=subprocess.run([MANAGER,"subscription"],input=json.dumps(request),stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,text=True,timeout=180)
        if not r.returncode:
            value=json.loads(r.stdout)
            if isinstance(value,dict): return value
    except (OSError,subprocess.TimeoutExpired,ValueError):
        pass
    return {"ok":False,"status":503,"message":"Менеджер занят или недоступен. Повторите позже."}
def ctl_manager_json(command,request):
    r=subprocess.run([MANAGER,command],input=json.dumps(request),stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,text=True,timeout=180)
    if r.returncode:
        message=r.stderr.strip() or "manager failed"
        marker="ValueError: "
        if marker in message: raise ValueError(message.rsplit(marker,1)[-1].strip())
        raise RuntimeError(message)
    value=json.loads(r.stdout)
    if not isinstance(value,dict): raise RuntimeError("manager returned invalid JSON")
    return value
def federation_id(subscription_id,device_id):
    return hashlib.sha256((DOMAIN+":"+subscription_id+":"+device_id).encode()).hexdigest()
def purge_remote_profiles(subscription,device_id=None):
    if not subscription: return
    devices=[d for d in subscription.get("devices",[]) if device_id is None or d.get("id")==device_id]
    for node in node_api.load_nodes(NODES_FILE):
        if not node.get("enabled",True): continue
        for device in devices:
            try: node_api.delete_profile(node,federation_id(subscription.get("id",""),device.get("id","")))
            except node_api.NodeError as exc:
                print("node profile cleanup failed:",node.get("url"),str(exc),file=sys.stderr,flush=True)
def purge_remote_profiles_async(subscription,device_id=None):
    if not subscription: return
    threading.Thread(target=purge_remote_profiles,args=(subscription,device_id),
                     name="onyx-node-cleanup",daemon=True).start()
def allow_subscription_request(client):
    now=time.monotonic()
    with SUB_RATE_LOCK:
        for key in list(SUB_REQUESTS):
            if SUB_REQUESTS[key][0]<now-60: del SUB_REQUESTS[key]
        if client not in SUB_REQUESTS:
            if len(SUB_REQUESTS)>=2048: return False
            SUB_REQUESTS[client]=[now,0]
        SUB_REQUESTS[client][1]+=1
        return SUB_REQUESTS[client][1]<=30
def validate_html(source):
    if not source.strip(): raise ValueError("HTML не может быть пустым")
    if len(source.encode("utf-8"))>MAX_HTML_BYTES: raise ValueError("HTML превышает лимит 1 МБ")
    return source
def web_link(secret):
    return "https://t.me/webproxy?server="+DOMAIN+"&secret="+secret
def mtproto_link(secret,port):
    # Keep the 32-hex server secret unchanged, but request Telegram's random
    # packet-padding mode on the client. This makes MTProxy substantially less
    # likely to be rejected by networks that identify its packet sizes.
    client_secret=secret if secret.startswith("dd") else "dd"+secret
    return "https://t.me/proxy?server="+MTPROTO_HOST+"&port="+str(int(port))+"&secret="+client_secret
def xray_path():
    with open(XRAY_PATH_FILE,encoding="utf-8") as f: value=f.read().strip()
    if not re.fullmatch(r"/vless-[a-f0-9]{24}",value): raise RuntimeError("Некорректный путь VLESS")
    return value
def proxy_link(protocol,secret,port=443,name="Proxy",username=""):
    if protocol=="mtproto": return mtproto_link(secret,port)
    if protocol=="web": return web_link(secret)
    protocol_label={"vless":"VLESS","hysteria":"Hysteria2","awg20":"AWG 2.0","awg31":"AWG 3.1"}.get(protocol,protocol)
    if not (name.startswith("🌐") or (name and 0x1F1E6 <= ord(name[0]) <= 0x1F1FF)):
        name=node_api.location_prefix(node_api.load_location(LOCATION_FILE))+" · "+protocol_label
    label=quote(name or "Proxy",safe="")
    if protocol=="vless":
        query=urlencode({"encryption":"none","security":"tls","sni":DOMAIN,"fp":"chrome","type":"xhttp","host":DOMAIN,"path":xray_path(),"mode":"auto","alpn":"h2"})
        return "vless://"+quote(secret,safe="-")+"@"+DOMAIN+":443?"+query+"#"+label
    if protocol=="hysteria":
        query=urlencode({"sni":DOMAIN,"alpn":"h3"})
        return "hysteria2://"+quote(secret,safe="-")+"@"+DOMAIN+":"+str(HYSTERIA_PORT)+"/?"+query+"#"+label
    if protocol in awg.PROTOCOLS:
        user=next((u for u in users() if u.get("protocol")==protocol and secrets.compare_digest(str(u.get("secret","")),str(secret))),None)
        if user is None: raise RuntimeError("Профиль AWG не найден")
        return awg.client_config(user,DOMAIN,name)
    raise RuntimeError("Неизвестный протокол")
def qr_png_bytes(link):
    return subprocess.run([QR,"-o","-","-t","PNG","-s","6","-m","2",link],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=10).stdout
def layout(title,body,active=""):
    return page_layout(title,body,PANEL_PATH,active,DOMAIN)

class Handler(BaseHTTPRequestHandler):
    timeout=20
    def log_message(self,*a): pass
    def send_html(self,s,code=200):
        b=s.encode(); self.send_response(code); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-store"); self.send_header("X-Frame-Options","DENY"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Referrer-Policy","no-referrer")
        # srcdoc is inline content. Deny network frame navigations as well as
        # requests from within the sandbox, including location/meta refresh.
        self.send_header("Content-Security-Policy","default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(b)
    def send_data(self,body,code=200,mime="text/plain; charset=utf-8",headers=None):
        raw=body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store, private")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        for key,value in (headers or {}).items(): self.send_header(key,str(value))
        self.end_headers()
        self.wfile.write(raw)
    def send_json(self,value,code=200):
        self.send_data(json.dumps(value,ensure_ascii=True),code,"application/json")
    def send_png(self,b):
        self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_logo(self,b):
        self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Cache-Control","public, max-age=86400"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_svg(self,b):
        self.send_response(200); self.send_header("Content-Type","image/svg+xml"); self.send_header("Cache-Control","public, max-age=604800, immutable"); self.send_header("Content-Length",str(len(b))); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(b)
    def redirect(self,p):
        self.send_response(303); self.send_header("Location",PANEL_PATH+p if p.startswith("/") else p); self.end_headers()
    def form(self,max_bytes=MAX_HTML_BYTES*3+8192):
        try: n=int(self.headers.get("Content-Length","0"))
        except ValueError: n=0
        if n < 0 or n > max_bytes: raise ValueError("Invalid form size")
        return {k:v[-1] for k,v in parse_qs(self.rfile.read(n).decode("utf-8"),max_num_fields=32).items()}
    def auth(self):
        c=cookies.SimpleCookie(self.headers.get("Cookie","")); v=c.get("sid")
        if not v:return False
        try:
            x,_=v.value.rsplit(".",1)
            issued=int(x.split("-",1)[0])
            return secrets.compare_digest(sign(x),v.value) and 0 <= time.time()-issued < 86400
        except Exception:
            return False
    def session_cookie(self,value,max_age):
        # Caddy supplies this header for public requests.  Keeping Secure for
        # HTTPS prevents accidental exposure, while loopback diagnostics still
        # receive a usable cookie.
        secure="; Secure" if self.headers.get("X-Forwarded-Proto","").lower()=="https" else ""
        return f"sid={value}; Path={PANEL_PATH}; Max-Age={max_age}; HttpOnly{secure}; SameSite=Lax"
    def csrf(self):
        c=cookies.SimpleCookie(self.headers.get("Cookie","")); v=c.get("sid")
        if not v: return ""
        return hmac.new(SESSION_KEY,b"csrf:"+v.value.encode(),hashlib.sha256).hexdigest()
    def valid_csrf(self,form):
        return secrets.compare_digest(form.get("csrf",""),self.csrf())
    def api_auth(self):
        if node_api.bearer_valid(self.headers.get("Authorization",""),API_KEY): return True
        self.send_response(401); self.send_header("WWW-Authenticate",'Bearer realm="Onyx Panel API"')
        self.send_header("Content-Type","application/json"); body=b'{"ok":false,"message":"Unauthorized"}'
        self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(body)
        return False
    def json_request(self,maximum=65536):
        try: length=int(self.headers.get("Content-Length","0"))
        except ValueError: raise ValueError("Invalid content length")
        if length<2 or length>maximum: raise ValueError("Invalid JSON size")
        value=json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value,dict): raise ValueError("JSON object required")
        return value
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith(node_api.API_PREFIX+"/"):
            if not self.api_auth(): return
            if path==node_api.API_PREFIX+"/status":
                loc=node_api.load_location(LOCATION_FILE)
                self.send_json({"ok":True,"api_version":1,"version":"1.2.5","domain":DOMAIN,
                    "location":loc,"capabilities":["vless","hysteria","awg20","awg31","federation"]}); return
            if path==node_api.API_PREFIX+"/profiles":
                result=[]
                for user in users():
                    if user.get("subscription_id"): continue
                    result.append({"id":user["id"],"name":user["name"],"protocol":user["protocol"],
                        "enabled":user.get("enabled",True),"link":proxy_link(user["protocol"],user["secret"],user.get("backend_port",443),user["name"],user.get("username",""))})
                self.send_json({"ok":True,"profiles":result}); return
            self.send_json({"ok":False,"message":"Not found"},404); return
        if path.startswith(SUB_PREFIX):
            self.serve_subscription(path[len(SUB_PREFIX):]); return
        d=load()
        if path==PANEL_PATH+"/__health":
            self.send_response(200)
            self.send_header("Content-Type","text/plain; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            body=b"OK"
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path==PANEL_PATH+"/__logo":
            logo=None
            for cand in (LOGO,"/opt/onyx-panel/panel-logo.png"):
                try:
                    with open(cand,"rb") as f: logo=f.read(); break
                except OSError: pass
            if not logo and globals().get("LOGO_EMBEDDED"):
                try: logo=base64.b64decode(LOGO_EMBEDDED)
                except Exception: logo=None
            if logo: self.send_logo(logo)
            else: self.send_html("Logo not found",404)
            return
        if path=="/favicon.ico":
            logo=None
            for cand in (LOGO,"/opt/onyx-panel/panel-logo.png"):
                try:
                    with open(cand,"rb") as f: logo=f.read(); break
                except OSError: pass
            if not logo and globals().get("LOGO_EMBEDDED"):
                try: logo=base64.b64decode(LOGO_EMBEDDED)
                except Exception: logo=None
            if logo:
                self.send_response(200)
                self.send_header("Content-Type","image/png")
                self.send_header("Content-Length",str(len(logo)))
                self.send_header("Cache-Control","public, max-age=86400")
                self.end_headers()
                self.wfile.write(logo)
            else:
                self.send_response(404); self.end_headers()
            return
        if path.startswith(PANEL_PATH+"/__font/"):
            fname=path[len(PANEL_PATH+"/__font/"):]
            if not re.fullmatch(r"[a-z0-9-]+\.woff2",fname):
                self.send_response(404); self.end_headers(); return
            try:
                with open("/opt/onyx-panel/fonts/"+fname,"rb") as f: fontdata=f.read()
                self.send_response(200)
                self.send_header("Content-Type","font/woff2")
                self.send_header("Content-Length",str(len(fontdata)))
                self.send_header("Cache-Control","public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(fontdata)
            except OSError:
                self.send_response(404); self.end_headers()
            return

        flag_match=re.fullmatch(re.escape(PANEL_PATH)+r"/__flag/([a-z]{2})\.svg",path)
        if flag_match:
            flag_path=os.path.join(FLAGS,flag_match.group(1)+".svg")
            if not os.path.isfile(flag_path): flag_path=os.path.join(FLAGS,"un.svg")
            try:
                with open(flag_path,"rb") as stream: flag_data=stream.read(131073)
                if len(flag_data)>131072: raise OSError("flag is too large")
                self.send_svg(flag_data)
            except OSError:
                self.send_html("Flag not found",404)
            return

        if path==PANEL_PATH+"/login":
            self.send_html(login_ui(PANEL_PATH)); return
        if path==PANEL_PATH+"/logout":
            self.send_response(303); self.send_header("Set-Cookie",self.session_cookie("",0)); self.send_header("Location",PANEL_PATH+"/login"); self.end_headers(); return
        if not self.auth():
            self.redirect("/login"); return

        if path==PANEL_PATH+"/export":
            try: blob=build_backup_tar()
            except ValueError as exc: self.send_html(esc(str(exc)),500); return
            except Exception:
                print("export failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_html("Не удалось собрать резервную копию.",500); return
            self.send_response(200)
            self.send_header("Content-Type","application/gzip")
            self.send_header("Content-Disposition",'attachment; filename="onyx-panel-backup-%s.tar.gz"'%time.strftime("%Y%m%d-%H%M%S"))
            self.send_header("Content-Length",str(len(blob)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(blob)
            return

        if path==PANEL_PATH or path==PANEL_PATH+"/":
            self.redirect("/dashboard"); return

        if path in (PANEL_PATH+"/dashboard",PANEL_PATH+"/dashboard-data"):
            try: hours=int(parse_qs(urlparse(self.path).query).get("hours",["1"])[0])
            except ValueError: hours=1
            if hours not in (1,6,24): hours=1
            profiles=[{"id":"primary","name":"Основной WEB Proxy","secret":primary(),"protocol":"web","enabled":True,"backend_port":443}]+users()
            body=dashboard_body(server_metrics.dashboard_data(hours),subscription_registry(),profiles,traffic(),
                                PANEL_PATH,DOMAIN,self.csrf(),proxy_link,web_updates.current_version(),hours)
            if path.endswith("/dashboard-data"):
                self.send_json({"html":body,"update":web_updates.get_status()})
            else:
                self.send_html(layout("Дашборд",dashboard_page(body,PANEL_PATH,self.csrf()),"dashboard"))
            return

        if path==PANEL_PATH+'/clients-state':
            profiles=[{'id':'primary','name':'Основной WEB Proxy','secret':primary(),'protocol':'web','enabled':True,'backend_port':443}]+users()
            records=client_records(subscription_registry(),profiles,traffic(),DOMAIN,proxy_link)
            clients=[{'id':r['id'],'name':r['name'],'kind':r['kind'],'enabled':r['enabled'],
                'protocols':r['protocols'],'devices':r['devices'],'limit':r['limit'],**r['totals']} for r in records]
            clients.extend({'id':'openflux-'+p['id'],'name':p.get('name','OpenFlux'),'kind':'openflux',
                'enabled':bool(p.get('enabled',True)),'protocols':['openflux'],'devices':0,'limit':0,
                'up':0,'down':0,'active':bool(p.get('active',False))} for p in openflux.profile_states())
            self.send_json({'clients':clients})
            return

        if path==PANEL_PATH+"/users":
            profiles=[{"id":"primary","name":"Основной WEB Proxy","secret":primary(),"protocol":"web","enabled":True,"backend_port":443}]+users()
            body=users_ui(subscription_registry(),profiles,traffic(),PANEL_PATH,DOMAIN,self.csrf(),proxy_link,openflux.profile_states(),load().get("expires",{}))
            self.send_html(layout("Клиенты",body,"users")); return
        if path==PANEL_PATH+"/nodes":
            body=nodes_ui([node_api.public_node(n) for n in node_api.load_nodes(NODES_FILE)],
                          node_api.load_location(LOCATION_FILE),node_api.make_connection_token(DOMAIN,API_KEY),PANEL_PATH,self.csrf())
            self.send_html(layout("Ноды",body,"nodes")); return
        if path==PANEL_PATH+"/updates":
            self.send_html(layout("Обновления",updates_ui(PANEL_PATH,self.csrf(),web_updates.current_version()),"updates")); return
        if path==PANEL_PATH+"/subscriptions":
            self.redirect("/users"); return
        if path==PANEL_PATH+"/update-status":
            self.send_json(web_updates.get_status()); return
        if path==PANEL_PATH+"/component-status":
            self.send_json(components.status()); return
        if path==PANEL_PATH+"/openflux-qr":
            profile_id=parse_qs(urlparse(self.path).query).get("id",[""])[0]
            profile=next((item for item in openflux.profile_states() if item.get("id")==profile_id),None)
            if profile is None: self.send_html("Not found",404); return
            try: self.send_png(qr_png_bytes(str(profile.get("url") or "")))
            except (OSError,subprocess.SubprocessError):
                self.send_json({'message':'Не удалось сформировать QR OpenFlux. Проверьте qrencode на сервере.'},503)
            return
        if path==PANEL_PATH+"/subscription-qr":
            sid=parse_qs(urlparse(self.path).query).get("id",[""])[0]
            sub=next((s for s in subscription_registry() if s["id"]==sid),None)
            if sub is None: self.send_html("Not found",404); return
            try: self.send_png(qr_png_bytes("https://"+DOMAIN+SUB_PREFIX+sub["token"]))
            except (OSError,subprocess.SubprocessError): self.send_json({'message':'Не удалось сформировать QR. Проверьте qrencode на сервере.'},503)
            return

        if path==PANEL_PATH+"/__qr":
            query=parse_qs(urlparse(self.path).query)
            q=query.get("secret",[""])[0]; protocol=query.get("protocol",["web"])[0]
            port=query.get("port",["443"])[0]
            uid=query.get("id",[""])[0]
            current_users=users()
            matching=(next((x for x in current_users if x.get("id")==uid and x.get("protocol") in awg.PROTOCOLS),None)
                      if uid else next((x for x in current_users if x.get("secret")==q or
                          (x.get("protocol")=="mtproto" and q in x.get("device_secrets",[]))),None))
            if uid and matching:
                q=matching.get("secret",""); protocol=matching.get("protocol",""); port=str(matching.get("backend_port",0))
            if q==primary(): matching={"protocol":"web","backend_port":443,"name":"Основной WEB Proxy"}
            if not matching or protocol!=matching.get("protocol","web"):
                self.send_html("Not found",404); return
            try:
                expected=str(int(matching.get("backend_port",443)))
                if protocol in ("mtproto","hysteria","awg20","awg31") and port!=expected:
                    self.send_html("Not found",404); return
                if protocol in ("web","vless") and port!="443":
                    self.send_html("Not found",404); return
                self.send_png(qr_png_bytes(proxy_link(protocol,q,expected,matching.get("name","Proxy"),matching.get("username",""))))
            except Exception:self.send_json({'message':'Не удалось сформировать QR. Проверьте qrencode на сервере.'},503)
            return

        if path==PANEL_PATH+"/awg-config":
            uid=parse_qs(urlparse(self.path).query).get("id",[""])[0]
            user=next((u for u in users() if u.get("id")==uid and u.get("protocol") in awg.PROTOCOLS),None)
            if user is None: self.send_html("Not found",404); return
            try:
                config=awg.client_config(user,DOMAIN,user.get("name","AWG"))
                self.send_data(config,mime="text/plain; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=\"onyx-%s.conf\""%uid})
            except Exception:
                self.send_html("Не удалось сформировать конфигурацию AWG.",503)
            return


        if path==PANEL_PATH+"/settings":
            token=esc(self.csrf())
            has_draft=os.path.exists(SITE_DRAFT)
            try:
                if has_draft:
                    with open(SITE_DRAFT,encoding="utf-8") as f: site_html=f.read()
                else: site_html=read_site_html()
            except Exception: site_html="<!-- Не удалось прочитать исходник -->"
            editor=editor_ui(site_html,PANEL_PATH,self.csrf(),all_presets(),has_draft)
            d=load()
            admin_login=esc(d.get("admin",{}).get("user","admin"))
            panel_url=("https://"+DOMAIN if DOMAIN else "")+PANEL_PATH
            panel_js='''<script>
(()=>{async function submit(form,status,done){
  const btn=form.querySelector("button[type=submit]");const label=btn.textContent;btn.disabled=true;
  status.className="panel-setting-status";status.textContent="Применяю…";
  try{
    const r=await fetch(form.getAttribute("action"),{method:"POST",headers:{"X-Onyx-Async":"1"},body:new URLSearchParams(new FormData(form))});
    let res;try{res=await r.json()}catch(e){throw new Error("Панель недоступна. Обновите страницу и попробуйте снова.")}
    if(!r.ok||!res.ok)throw new Error(res.message||"Операция не выполнена.");
    status.className="panel-setting-status ok";status.textContent=res.message||"Готово.";
    if(done)done(res);
  }catch(err){status.className="panel-setting-status err";status.textContent=err.message}
  finally{btn.disabled=false;btn.textContent=label}
}
const pathForm=document.getElementById("panelPathForm");
if(pathForm){const status=document.getElementById("panelPathStatus");
pathForm.addEventListener("submit",e=>{e.preventDefault();submit(pathForm,status,res=>{status.textContent="";showMove(res)})})}
const moveOverlay=document.getElementById("moveOverlay");
function showMove(res){
  const url=res.newUrl||location.origin+res.newPath+"/login";
  document.getElementById("moveUrl").textContent=url;
  document.getElementById("moveLink").href=url;
  moveOverlay.hidden=false;
  requestAnimationFrame(()=>moveOverlay.classList.add("show"));
  const ring=document.getElementById("moveRing"),secs=document.getElementById("moveSecs"),C=276.5;
  let left=8;const total=8;
  const setRing=()=>{ring.style.strokeDashoffset=(C*(1-Math.max(left,0)/total)).toFixed(1)};
  secs.textContent=left;setRing();
  const iv=setInterval(()=>{
    left-=1;
    if(left>0){secs.textContent=left;setRing();return}
    clearInterval(iv);secs.textContent="…";ring.style.strokeDashoffset=C;
  },1000);
  const started=Date.now();
  const probe=()=>{
    fetch(res.newPath+"/__health",{cache:"no-store"}).then(r=>{
      if(r.ok)location.href=url;
      else if(Date.now()-started<30000)setTimeout(probe,1200);
      else location.href=url;
    }).catch(()=>{if(Date.now()-started<30000)setTimeout(probe,1200);else location.href=url});
  };
  setTimeout(probe,8600);
}
const loginForm=document.getElementById("panelLoginForm");
if(loginForm){const status=document.getElementById("panelLoginStatus");const input=loginForm.querySelector("input[name=user]");
loginForm.addEventListener("submit",e=>{e.preventDefault();submit(loginForm,status,res=>{input.value="";input.placeholder=res.login||input.placeholder})})}
const importForm=document.getElementById("importForm");
if(importForm){const status=document.getElementById("importStatus"),file=document.getElementById("importFile"),data=document.getElementById("importData");
file.addEventListener("change",()=>{const f=file.files&&file.files[0];if(!f)return;if(f.size>9*1024*1024){status.className="panel-setting-status err";status.textContent="Файл больше 9 МБ.";file.value="";return}const reader=new FileReader();reader.onload=()=>{data.value=String(reader.result).split(",").pop()||"";status.className="panel-setting-status ok";status.textContent="Файл загружен: "+f.name+". Нажмите «Восстановить из копии»."};reader.onerror=()=>{status.className="panel-setting-status err";status.textContent="Не удалось прочитать файл."};reader.readAsDataURL(f)});
importForm.addEventListener("submit",async e=>{e.preventDefault();if(!data.value.trim()){status.className="panel-setting-status err";status.textContent="Выберите файл копии или вставьте его содержимое.";return}if(!(await onyxConfirm("Заменить текущих пользователей, настройки и заглушки содержимым копии?",{title:"Восстановление из копии",ok:"Восстановить",danger:true})))return;submit(importForm,status)})};
const passForm=document.getElementById("panelPasswordForm");
if(passForm){const status=document.getElementById("panelPasswordStatus");
passForm.addEventListener("submit",e=>{e.preventDefault();submit(passForm,status,res=>{const target=passForm.getAttribute("data-goto");setTimeout(()=>{location.href=target},2200)})})}
const compGrid=document.getElementById("componentGrid");
if(compGrid){
  const compCsrf=compGrid.dataset.csrf,checkUrl=compGrid.dataset.check,installUrl=compGrid.dataset.install,statusUrl=compGrid.dataset.status;
  const compRows={};
  compGrid.querySelectorAll("[data-component]").forEach(row=>{compRows[row.dataset.component]={row,ver:row.querySelector("[data-ver]"),sel:row.querySelector("select"),btn:row.querySelector("button"),status:row.querySelector(".component-item-status")}});
  async function compApi(url,body){const r=await fetch(url,{method:"POST",headers:{"X-Onyx-Async":"1"},body:new URLSearchParams(body)});let j;try{j=await r.json()}catch(e){throw new Error("Панель недоступна.")}if(!r.ok)throw new Error(j.message||"Не выполнено.");return j}
  async function compRefresh(){const d=await compApi(checkUrl,{csrf:compCsrf});Object.keys(compRows).forEach(n=>{const item=compRows[n];item.ver.textContent=(d.current&&d.current[n])||"—";if(item.sel){const tags=(d.catalog&&d.catalog[n])||[];const cur=(d.current&&d.current[n])||"";item.sel.innerHTML="";tags.slice(0,6).forEach(t=>{const o=document.createElement("option");o.value=t;o.textContent=t==="v"+cur?t+" — установлена":t;item.sel.appendChild(o)})}});return d}
  compRefresh().catch(()=>{Object.values(compRows).forEach(item=>{item.ver.textContent="—"})});
  Object.keys(compRows).forEach(n=>{const item=compRows[n];
    item.btn.addEventListener("click",async()=>{
      const target=n==="mtproto"?"refresh":(item.sel?item.sel.value:"");
      if(!target){item.status.className="component-item-status err";item.status.textContent="Нет доступной версии.";return}
      if(!(await onyxConfirm("Обновить "+item.row.dataset.label+" до "+target+"? Служба кратковременно перезапустится.",{title:"Обновление компонента",ok:"Обновить"})))return;
      item.btn.disabled=true;item.status.className="component-item-status";item.status.textContent="Запускаю обновление…";
      try{
        await compApi(installUrl,{csrf:compCsrf,component:n,target});
        for(let i=0;i<200;i++){
          await new Promise(r=>setTimeout(r,3000));
          const st=await compApi(statusUrl,{csrf:compCsrf});
          if(st.phase==="done"){item.status.className="component-item-status ok";item.status.textContent=st.message||"Готово.";compRefresh().catch(()=>{});return}
          if(st.phase==="failed"){item.status.className="component-item-status err";item.status.textContent=st.message||"Не удалось.";return}
          item.status.textContent="Устанавливаю… "+(i*3)+" c";
        }
        throw new Error("Обновление слишком долго не отвечает. Проверьте статус позже.");
      }catch(e){item.status.className="component-item-status err";item.status.textContent=e.message}
      finally{item.btn.disabled=false}
    })
  })
}
})();
</script>'''
            body=f'''<div class="page-head"><div><span class="eyebrow">ONYX PANEL / STUDIO</span><h1>Настройки</h1><p>Оформление сайта и доступ к панели</p></div></div>
<div class="settings-grid"><div class="card settings-card"><div class="card-title"><div><h2>Панель</h2><p>Адрес входа и учётные данные администратора</p></div></div>
<section class="panel-setting"><div class="panel-setting-info"><b>Адрес панели</b><small>Секретный путь входа — любой, от 4 символов: /xray, /my-vpn, /ab12. Меняйте его, если ссылка стала известна посторонним. После смены панель перезапустится — входите заново по новому адресу.</small></div><form id="panelPathForm" action="{PANEL_PATH}/panel-path"><p class="panel-current"><span>Текущий адрес</span><code>{panel_url}</code></p><input type=hidden name=csrf value="{token}"><label for="panelPathInput">Новый путь</label><input id="panelPathInput" name="path" value="{esc(PANEL_PATH)}" spellcheck="false" autocomplete="off" required><div class="actions"><button type="submit" class="btn primary">Сменить адрес</button></div><p class="panel-setting-status" id="panelPathStatus" role="status"></p></form></section>
<section class="panel-setting"><div class="panel-setting-info"><b>Логин администратора</b><small>От 1 до 64 символов. Используется вместе с паролем на странице входа.</small></div><form id="panelLoginForm" action="{PANEL_PATH}/panel-login"><input type=hidden name=csrf value="{token}"><label for="panelLoginInput">Новый логин</label><input id="panelLoginInput" name="user" placeholder="{admin_login}" maxlength="64" autocomplete="username" required><div class="actions"><button type="submit" class="btn primary">Сменить логин</button></div><p class="panel-setting-status" id="panelLoginStatus" role="status"></p></form></section>
<section class="panel-setting"><div class="panel-setting-info"><b>Пароль</b><small>Минимум 3 символа. Смена пароля завершает все сессии панели.</small></div><form id="panelPasswordForm" action="{PANEL_PATH}/panel-password" data-goto="{PANEL_PATH}/login"><input type=hidden name=csrf value="{token}"><label for="panelPasswordInput">Новый пароль</label><input id="panelPasswordInput" type=password name="a" minlength="3" required autocomplete="new-password"><div class="actions"><button type="submit" class="btn primary">Сменить пароль</button></div><p class="panel-setting-status" id="panelPasswordStatus" role="status"></p></form></section>
<div class="move-overlay" id="moveOverlay" hidden><div class="move-card"><div class="move-ring"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="move-ring-bg" cx="50" cy="50" r="44"/><circle class="move-ring-fg" id="moveRing" cx="50" cy="50" r="44"/></svg><b id="moveSecs">8</b></div><h3>Панель переезжает</h3><p id="moveText">Адрес изменён. Caddy и панель перезапускаются — сейчас откроется новый адрес входа. Войдите на нём заново.</p><code id="moveUrl"></code><a class="btn primary" id="moveLink" href="#">Перейти сейчас</a></div></div>
{panel_js}</div>
<div class="settings-col"><div class="card"><div class="card-title"><div><h2>Компоненты</h2><p>Обновление Xray, OpenFlux, AmneziaWG и MTProto с их репозиториев</p></div></div>
<div class="component-stack" id="componentGrid" data-csrf="{token}" data-check="{PANEL_PATH}/component-check" data-install="{PANEL_PATH}/component-install" data-status="{PANEL_PATH}/component-status">
<div class="component-item" data-component="xray" data-label="Xray"><div class="component-item-head"><strong>Xray</strong><small data-ver>…</small></div><div class="update-control"><select data-sel aria-label="Версия Xray"></select><button class="primary">Обновить</button></div><p class="component-item-status" role="status"></p></div>
<div class="component-item" data-component="openflux" data-label="OpenFlux"><div class="component-item-head"><strong>OpenFlux</strong><small data-ver>…</small></div><div class="update-control"><select data-sel aria-label="Версия OpenFlux"></select><button class="primary">Обновить</button></div><p class="component-item-status" role="status"></p></div>
<div class="component-item" data-component="awg" data-label="AmneziaWG"><div class="component-item-head"><strong>AmneziaWG</strong><small data-ver>…</small></div><div class="update-control"><select data-sel aria-label="Версия AmneziaWG"></select><button class="primary">Обновить</button></div><p class="component-item-status" role="status"></p></div>
<div class="component-item" data-component="mtproto" data-label="MTProto"><div class="component-item-head"><strong>MTProto</strong><small data-ver>…</small></div><div class="update-control"><button class="primary">Пересобрать из исходников</button></div><p class="component-item-status" role="status"></p></div>
</div>
<p class="muted" style="font-size:11px;margin:10px 0 0">Перед заменой бинарника создаётся его копия; если новая версия не запустится, предыдущая вернётся автоматически. MTProto собирается из исходников, закреплённых за версией панели.</p></div>
<div class="card"><div class="card-title"><div><h2>Резервная копия</h2><p>Настройки, пользователи, заглушки и конфигурации — одним архивом</p></div></div>
<div class="actions" style="margin:2px 0 8px"><a class="btn primary" href="{PANEL_PATH}/export" download>Скачать резервную копию</a><small>Архив содержит ключи доступа — храните его как пароль.</small></div>
<form id="importForm" action="{PANEL_PATH}/import"><input type=hidden name=csrf value="{token}"><label for="importFile">Файл копии (.tar.gz)</label><input id="importFile" type="file" accept=".tar.gz,.tgz,application/gzip"><label for="importData">…или вставьте его содержимое (base64)</label><textarea id="importData" name="backup" rows="4" spellcheck="false" placeholder="Выберите файл выше — он подставится сюда автоматически"></textarea><div class="actions" style="margin-top:10px"><button type="submit" class="btn primary">Восстановить из копии</button><small>Импорт заменяет пользователей и настройки; текущее состояние сохраняется в архив-откат.</small></div><p class="panel-setting-status" id="importStatus" role="status"></p></form></div></div></div>
{editor}'''
            self.send_html(layout("Настройки",body,"settings")); return

        self.redirect("/")

    def do_POST(self):
        path=urlparse(self.path).path

        if path.startswith(node_api.API_PREFIX+"/"):
            if not self.api_auth(): return
            try:
                request=self.json_request()
                if path==node_api.API_PREFIX+"/federation/sync":
                    result=ctl_manager_json("federation-sync",request)
                    profiles=[{"id":u["id"],"protocol":u["protocol"],
                        "link":proxy_link(u["protocol"],u["secret"],u.get("backend_port",443),u.get("name",request.get("name","")),u.get("username",""))}
                        for u in result.get("profiles",[])]
                    self.send_json({"ok":True,"profiles":profiles}); return
                if path==node_api.API_PREFIX+"/federation/delete":
                    result=ctl_manager_json("federation-delete",request)
                    self.send_json({"ok":True,"deleted":bool(result.get("deleted"))}); return
                if path==node_api.API_PREFIX+"/federation/purge":
                    result=ctl_manager_json("federation-purge",{})
                    self.send_json({"ok":True,"deleted":int(result.get("deleted",0))}); return
                if path==node_api.API_PREFIX+"/profiles/create":
                    protocol=str(request.get("protocol","")); name=str(request.get("name","")).strip()
                    if protocol not in ("web","mtproto","vless","hysteria","awg20","awg31") or not name or len(name)>80:
                        self.send_json({"ok":False,"message":"Invalid profile"},400); return
                    user=(ctl_manager_json("add-json",{"protocol":protocol,"name":name,
                        "port":request.get("port"),"devices":request.get("devices",1)})
                        if protocol=="mtproto" else ctl("add",protocol,name))
                    self.send_json({"ok":True,"profile":{"id":user["id"],"name":user["name"],"protocol":protocol,
                        "link":proxy_link(protocol,user["secret"],user.get("backend_port",443),name,user.get("username",""))}},201); return
                if path==node_api.API_PREFIX+"/profiles/delete":
                    uid=str(request.get("id",""))
                    if not re.fullmatch(r"[a-f0-9]{16}",uid): self.send_json({"ok":False,"message":"Invalid profile id"},400); return
                    ctl("delete",uid); self.send_json({"ok":True}); return
                self.send_json({"ok":False,"message":"Not found"},404)
            except (ValueError,json.JSONDecodeError) as exc: self.send_json({"ok":False,"message":str(exc)},400)
            except Exception as exc:
                print("API request failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_json({"ok":False,"message":"Node operation failed"},503)
            return

        # Login does not require an authenticated session.
        if path==PANEL_PATH+"/login":
            client=client_id(self)
            if login_blocked(client):
                body="Слишком много попыток входа. Повторите позже.".encode("utf-8")
                self.send_response(429)
                self.send_header("Retry-After",str(LOGIN_WINDOW))
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            try: form=self.form(8192)
            except (ValueError,UnicodeDecodeError):
                self.send_html("Некорректный запрос.",400); return
            d=load()
            username=form.get("user","")
            password=form.get("password","")
            if username==d.get("admin",{}).get("user","admin") and check_password(password,d.get("admin",{}).get("hash","")):
                # A cookie-safe token: the old ':' separator was accepted by
                # most browsers but is rejected/rewritten by some proxies.
                token=str(int(time.time()))+"-"+secrets.token_hex(16)
                sid=sign(token)
                login_succeeded(client)
                self.send_response(303)
                self.send_header("Set-Cookie",self.session_cookie(sid,86400))
                self.send_header("Location",PANEL_PATH+"/dashboard")
                self.end_headers()
            else:
                login_failed(client)
                self.send_html("""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#060910;color:#fff;font:15px system-ui}.b{width:min(420px,90vw);padding:28px;border:1px solid #223148;border-radius:22px;background:#0d1520}a{color:#8edcff}</style>
<div class=b><h2>Неверный логин или пароль</h2><p>Попробуйте войти ещё раз.</p><a href="%s/login">Вернуться</a></div>""" % esc(PANEL_PATH),401)
            return

        # Everything below requires an authenticated session.
        if not self.auth():
            self.redirect("/login")
            return

        try: form=self.form()
        except (ValueError,UnicodeDecodeError) as e:
            self.send_html(esc(e),400); return
        d=load()

        if not self.valid_csrf(form):
            self.send_html("Недействительный запрос. Обновите страницу и попробуйте снова.",403)
            return

        if path in (PANEL_PATH+"/update-check",PANEL_PATH+"/update-start"):
            try:
                result=web_updates.start_update(form.get("target","")) if path.endswith("/update-start") else web_updates.check_release()
                self.send_json(result)
            except ValueError as exc: self.send_json({"message":str(exc)},400)
            except (OSError,subprocess.TimeoutExpired): self.send_json({"message":"Служба обновления недоступна. Проверьте VPS через SSH."},503)
            return

        if path in (PANEL_PATH+"/component-check",PANEL_PATH+"/component-install"):
            try:
                result=(components.start(form.get("component",""),form.get("target",""))
                        if path.endswith("/component-install") else components.catalog(force=True))
                self.send_json(result)
            except ValueError as exc:
                self.send_json({"message":str(exc)},400)
            except (OSError,subprocess.TimeoutExpired):
                self.send_json({"message":"Не удалось связаться с репозиторием или службой обновления."},503)
            return

        if path==PANEL_PATH+"/node-action":
            try:
                operation=form.get("operation","")
                if operation=="add":
                    bundled=node_api.parse_connection_token(form.get("connection_token",""))
                    candidate=bundled["url"]
                    if urlparse(candidate).hostname==DOMAIN:
                        raise node_api.NodeError("Нельзя добавить эту же панель как удалённую ноду.")
                    node_api.add_node(NODES_FILE,form)
                elif operation=="delete":
                    nodes=node_api.load_nodes(NODES_FILE); uid=form.get("id","")
                    selected=next((n for n in nodes if n.get("id")==uid),None)
                    if selected is None: raise node_api.NodeError("Нода не найдена.")
                    # Revoke remotely before forgetting the only credential that
                    # can remove controller-created profiles from this node.
                    node_api.purge_profiles(selected)
                    node_api.save_nodes(NODES_FILE,[n for n in nodes if n.get("id")!=uid])
                elif operation=="location":
                    node_api.save_location(LOCATION_FILE,form)
                else: raise node_api.NodeError("Неизвестная операция с нодой.")
                self.redirect("/nodes")
            except node_api.NodeError as exc:
                self.send_html(esc(str(exc)),400)
            return

        if path==PANEL_PATH+"/create-account":
            async_create=self.headers.get("X-Onyx-Async","")=="1"
            def create_error(message,status=400):
                if async_create: self.send_json({"ok":False,"message":str(message)},status)
                else: self.send_html(esc(str(message)),status)
            name=form.get("name","").strip()
            kind=form.get("kind","")
            if not name or len(name)>80 or any(ord(c)<32 for c in name):
                create_error("Укажите имя длиной от 1 до 80 символов."); return
            new_id=None
            if kind=="subscription":
                result=ctl_subscription({"operation":"create","name":name,"max_devices":form.get("max_devices","2"),
                                         "protocols":[p for p in ("vless","hysteria") if form.get(p)=="1"]})
                if not result.get("ok"):
                    create_error(result.get("message","Ошибка создания подписки"),int(result.get("status",400))); return
                new_id=result.get("id")
            elif kind in ("web","mtproto","vless","hysteria","awg20","awg31"):
                try:
                    if kind=="mtproto":
                        created=ctl_manager_json("add-json",{"protocol":kind,"name":name,
                            "port":form.get("mtproto_port",""),"devices":form.get("mtproto_devices","1")})
                        new_id=created.get("id")
                    else:
                        created=ctl("add",kind,name); new_id=created.get("id")
                except ValueError as exc:
                    create_error(str(exc)); return
                except Exception as exc:
                    print("create connection failed:",type(exc).__name__,file=sys.stderr,flush=True)
                    create_error("Не удалось создать подключение. Проверьте службы через SSH и повторите попытку.",503); return
            else:
                create_error("Неизвестный тип доступа"); return
            expires_raw=form.get("expires","").strip()
            if new_id and expires_raw:
                try:
                    ts=int(time.mktime(time.strptime(expires_raw,"%Y-%m-%d")))+86399
                    if ts>time.time():
                        with STATE_LOCK:
                            d=load(); d.setdefault("expires",{})[new_id]=ts; save(d)
                except ValueError:
                    pass
            if async_create: self.send_json({"ok":True})
            else: self.redirect("/users")
            return

        if path==PANEL_PATH+"/openflux":
            operation=form.get("operation","")
            try:
                if operation=="save":
                    openflux.configure(form.get("url",""),form.get("ios_compatible","")=="1")
                elif operation=="enable": openflux.set_enabled(True)
                elif operation=="disable": openflux.set_enabled(False)
                elif operation=="rotate": openflux.rotate_key()
                else: raise openflux.OpenFluxError("Неизвестная операция OpenFlux.")
                self.redirect("/settings")
            except openflux.OpenFluxError as exc:
                self.send_html("Ошибка OpenFlux: "+esc(str(exc)),400)
            return

        if path==PANEL_PATH+"/openflux-profile":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            operation=form.get("operation","")
            try:
                if operation=="create":
                    openflux.create_profile(form.get("name",""),form.get("url",""),form.get("platform",""),form.get("transport","yandex"))
                elif operation=="enable": openflux.profile_set_enabled(form.get("id",""),True)
                elif operation=="disable": openflux.profile_set_enabled(form.get("id",""),False)
                elif operation=="rotate": openflux.profile_rotate(form.get("id",""))
                elif operation=="delete": openflux.delete_profile(form.get("id",""))
                else: raise openflux.OpenFluxError("Неизвестная операция OpenFlux.")
                if async_action: self.send_json({"ok":True})
                else: self.redirect("/users")
            except openflux.OpenFluxError as exc:
                if async_action: self.send_json({"ok":False,"message":str(exc)},400)
                else: self.send_html("Ошибка OpenFlux: "+esc(str(exc)),400)
            return

        if path==PANEL_PATH+"/client-action":
            uid=form.get('id',''); kind=form.get('kind',''); operation=form.get('operation','')
            if uid!='primary' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',uid):
                self.send_json({'message':'Подключение не найдено.'},400); return
            if uid=='primary' and operation!='secret':
                self.send_json({'message':'У основного подключения можно изменить только секрет.'},400); return
            if operation=='state' and form.get('enabled') not in ('0','1'):
                self.send_json({'message':'Некорректное состояние доступа.'},400); return
            if kind not in ('subscription','direct') or operation not in ('state','rename','secret','expiry'):
                self.send_json({'message':'Недопустимая операция.'},400); return
            if operation=='secret' and (kind!='direct' or not re.fullmatch(r'(?:dd)?[0-9A-Fa-f]{32}',form.get('secret','').strip())):
                self.send_json({'message':'Секрет должен содержать 32 символа 0–9, a–f; префикс dd допускается.'},400); return
            if operation=='rename' and (not form.get('name','').strip() or len(form['name'].strip())>80 or any(ord(c)<32 for c in form['name'])):
                self.send_json({'message':'Имя должно содержать от 1 до 80 символов без управляющих знаков.'},400); return
            try:
                if operation=='expiry':
                    raw=form.get('expires','').strip()
                    if raw and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",raw):
                        self.send_json({'message':'Некорректная дата. Формат ГГГГ-ММ-ДД.'},400); return
                    with STATE_LOCK:
                        d=load(); exp=d.setdefault('expires',{})
                        if raw: exp[uid]=int(time.mktime(time.strptime(raw,"%Y-%m-%d")))+86399
                        else: exp.pop(uid,None)
                        save(d)
                    self.send_json({'ok':True}); return
                if kind=='subscription':
                    previous=next((s for s in subscription_registry() if s.get('id')==uid),None)
                    request={'id':uid,'operation':'set-enabled' if operation=='state' else 'update'}
                    if operation=='state': request['enabled']=form['enabled']=='1'
                    else: request['name']=form.get('name','')
                    result=ctl_subscription(request)
                    if not result.get('ok'):
                        self.send_json({'message':result.get('message','Изменение не применено.')},int(result.get('status',400))); return
                    if operation=='rename' or (operation=='state' and form['enabled']=='0'):
                        purge_remote_profiles_async(previous)
                    if operation=='state' and form['enabled']=='1':
                        with STATE_LOCK:
                            d=load()
                            if uid in d.get('expires',{}):
                                d['expires'].pop(uid,None); save(d)
                else:
                    if operation=='state':
                        ctl('set-user',uid,form['enabled'])
                        if form['enabled']=='1':
                            with STATE_LOCK:
                                d=load()
                                if uid in d.get('expires',{}):
                                    d['expires'].pop(uid,None); save(d)
                    elif operation=='rename': ctl('rename-user',uid,form.get('name',''))
                    else: ctl_manager_json('set-secret',{'id':uid,'secret':form.get('secret','')})
                self.send_json({'ok':True})
            except Exception:
                self.send_json({'message':'Изменение не применено. Проверьте службы через SSH и обновите список.'},503)
            return

        if path==PANEL_PATH+"/subscription-action":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            request={k:form[k] for k in ("operation","id","device_id","name","max_devices") if k in form}
            if request.get("operation") not in ("create","update","toggle","rotate","delete","revoke","allow"):
                self.send_html("Недопустимая операция",400); return
            if request["operation"] in ("create","update"):
                request["protocols"]=[p for p in ("vless","hysteria") if form.get(p)=="1"]
            previous=next((s for s in subscription_registry() if s.get("id")==request.get("id")),None)
            result=ctl_subscription(request)
            if result.get("ok"):
                if request["operation"] in ("update","delete","rotate","toggle"):
                    purge_remote_profiles_async(previous)
                elif request["operation"]=="revoke":
                    purge_remote_profiles_async(previous,request.get("device_id"))
                if async_action: self.send_json({"ok":True})
                else: self.redirect("/users")
            elif async_action: self.send_json({"ok":False,"message":result.get("message","Ошибка подписки")},int(result.get("status",400)))
            else: self.send_html(esc(result.get("message","Ошибка подписки")),int(result.get("status",400)))
            return

        if path==PANEL_PATH+"/custom-preset":
            try:
                operation=form.get("operation","")
                items=custom_presets()
                if operation=="create":
                    name=form.get("name","").strip()
                    description=form.get("description","").strip() or "Пользовательская заглушка"
                    if not 1<=len(name)<=80: raise ValueError("Название должно содержать от 1 до 80 символов.")
                    if len(description)>180: raise ValueError("Описание не должно превышать 180 символов.")
                    if len(items)>=20: raise ValueError("Можно сохранить не более 20 своих заглушек.")
                    source=validate_html(form.get("html",""))
                    items.append({"id":"custom-"+secrets.token_hex(8),"name":name,
                                  "description":description,"html":source,"custom":True})
                    save_custom_presets(items)
                elif operation=="delete":
                    preset_id=form.get("preset","")
                    if not preset_id.startswith("custom-"): raise ValueError("Встроенный пресет удалить нельзя.")
                    retained=[item for item in items if item.get("id")!=preset_id]
                    if len(retained)==len(items): raise ValueError("Заглушка не найдена.")
                    save_custom_presets(retained)
                else:
                    raise ValueError("Неизвестная операция.")
                self.redirect("/settings")
            except ValueError as exc:
                self.send_html("Ошибка сохранения заглушки: "+esc(exc),400)
            except OSError as exc:
                print("custom preset failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_html("Не удалось сохранить заглушку на сервере.",503)
            return

        if path in (PANEL_PATH+"/preview-html",PANEL_PATH+"/save-draft",PANEL_PATH+"/draft-preset",PANEL_PATH+"/discard-draft"):
            try:
                if path.endswith("/discard-draft"):
                    with STATE_LOCK:
                        if os.path.exists(SITE_DRAFT): os.unlink(SITE_DRAFT)
                else:
                    source=validate_html(get_preset(form.get("preset",""))["html"] if path.endswith("/draft-preset") else form.get("html",""))
                    if path.endswith("/preview-html"):
                        self.send_json({"document":preview_document(source,externalize_inline_assets)}); return
                    with STATE_LOCK: install_private_file(SITE_DRAFT,source.encode("utf-8"))
                self.redirect("/settings")
            except ValueError as exc:
                self.send_json({"message":str(exc)},400)
            except (RuntimeError,OSError) as exc:
                print("landing draft failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_json({"message":"Не удалось обработать черновик. Проверьте службы через SSH."},503)
            return

        if path==PANEL_PATH+"/add-user":
            name=form.get("name","").strip()
            protocol=form.get("protocol","web").strip().lower()
            if not name or len(name)>80:
                self.send_html("Имя пользователя обязательно.",400); return
            if protocol not in ("web","mtproto","vless","hysteria","awg20","awg31"):
                self.send_html("Неизвестный протокол подключения.",400); return
            try:
                result=ctl("add",protocol,name)
                self.redirect("/users")
            except Exception as exc:
                print("create user failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_html("Не удалось создать пользователя. Проверьте службы через SSH и повторите попытку.",503)
            return

        if path==PANEL_PATH+"/delete-user":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            uid=form.get("id","")
            if not uid or uid=="primary":
                if async_action: self.send_json({"ok":False,"message":"Нельзя удалить основной профиль."},400)
                else: self.send_html("Нельзя удалить основной профиль.",400)
                return
            try:
                ctl("delete",uid)
                if async_action: self.send_json({"ok":True})
                else: self.redirect("/users")
            except Exception as exc:
                print("delete user failed:",type(exc).__name__,file=sys.stderr,flush=True)
                if async_action: self.send_json({"ok":False,"message":"Не удалось удалить пользователя. Обновите список и повторите попытку."},503)
                else: self.send_html("Не удалось удалить пользователя. Обновите список и повторите попытку.",503)
            return

        if path==PANEL_PATH+"/site-html":
            try:
                with STATE_LOCK:
                    source=validate_html(form.get("html",""))
                    install_private_file(SITE_DRAFT,source.encode("utf-8"))
                    write_site_html(source)
                    if os.path.exists(SITE_DRAFT): os.unlink(SITE_DRAFT)
                self.redirect("/settings")
            except ValueError as exc:
                self.send_html("Ошибка сохранения HTML: "+esc(exc),400)
            except (RuntimeError,OSError) as exc:
                print("landing publish failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_html("Не удалось опубликовать HTML. Предыдущая страница сохранена; проверьте службы через SSH.",503)
            return

        if path==PANEL_PATH+"/apply-preset":
            try:
                preset=get_preset(form.get("preset",""))
                # Applying a bundled preset is an explicit publish operation.
                # Remove a stale custom draft so it cannot overwrite the
                # selected preset on the next save.
                with STATE_LOCK:
                    write_site_html(preset["html"])
                    if os.path.exists(SITE_DRAFT): os.unlink(SITE_DRAFT)
                self.redirect("/settings")
            except ValueError as exc:
                self.send_html("Ошибка применения пресета: "+esc(exc),400)
            except (RuntimeError,OSError) as exc:
                print("landing preset failed:",type(exc).__name__,file=sys.stderr,flush=True)
                self.send_html("Не удалось применить пресет. Предыдущая страница сохранена; проверьте службы через SSH.",503)
            return

        if path==PANEL_PATH+"/import":
            import io, tarfile
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            def imp_fail(msg):
                if async_action: self.send_json({"ok":False,"message":msg},400)
                else: self.send_html(esc(msg),400)
            raw=form.get("backup","").strip()
            if not raw:
                imp_fail("Выберите файл резервной копии или вставьте его содержимое."); return
            try: blob=base64.b64decode(raw,validate=True)
            except Exception:
                imp_fail("Не удалось прочитать данные: нужен файл резервной копии (.tar.gz)."); return
            if len(blob)>12*1024*1024:
                imp_fail("Архив слишком большой (лимит 12 МБ)."); return
            try:
                tar=tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz")
                members=tar.getmembers()
            except Exception:
                imp_fail("Архив повреждён или это не tar.gz."); return
            if len(members)>200:
                imp_fail("В архиве слишком много файлов."); return
            allow={"panel","onyx-panel","onyx-panel-xray"}
            restore={}; total=0; meta_ok=False
            try:
                for m in members:
                    if not m.isfile(): raise ValueError("Архив содержит нестандартные элементы.")
                    if m.size>4*1024*1024: raise ValueError("Файл в архиве слишком большой: "+m.name)
                    total+=m.size
                    if total>12*1024*1024: raise ValueError("Архив слишком большой.")
                    name=m.name
                    if name.startswith("./"): name=name[2:]
                    parts=name.split("/")
                    if parts==["manifest.json"]:
                        try: meta=json.loads(tar.extractfile(m).read().decode("utf-8"))
                        except Exception: raise ValueError("manifest.json повреждён.")
                        if not isinstance(meta,dict) or meta.get("app")!="onyx-panel":
                            raise ValueError("Это резервная копия другого приложения.")
                        meta_ok=True; continue
                    if len(parts)==2 and parts[0] in allow and re.fullmatch(r"[A-Za-z0-9._-]{1,80}",parts[1]):
                        restore[name]=tar.extractfile(m).read(); continue
                    if len(parts)==3 and parts[0]=="onyx-panel" and parts[1]=="awg" and re.fullmatch(r"[a-f0-9]{16}\.json",parts[2]):
                        restore[name]=tar.extractfile(m).read(); continue
                    raise ValueError("Архив содержит неожиданный файл: "+name)
            except ValueError as exc:
                imp_fail(str(exc)); return
            except Exception:
                imp_fail("Не удалось прочитать архив."); return
            if not meta_ok or "panel/data.json" not in restore:
                imp_fail("В архиве нет настроек панели (panel/data.json) — это не полная копия."); return
            try: json.loads(restore["panel/data.json"].decode("utf-8"))
            except Exception:
                imp_fail("panel/data.json в архиве повреждён."); return
            if "onyx-panel/users.json" in restore:
                try:
                    parsed=json.loads(restore["onyx-panel/users.json"].decode("utf-8"))
                    if not isinstance(parsed,dict) or not isinstance(parsed.get("users"),list) or not isinstance(parsed.get("subscriptions"),list):
                        raise ValueError
                except Exception:
                    imp_fail("onyx-panel/users.json в архиве повреждён."); return
            try:
                stamp=time.strftime("%Y%m%d-%H%M%S")
                backup_path="/var/lib/onyx-panel/import-backup-%s.tar.gz"%stamp
                with open(backup_path,"wb") as f: f.write(build_backup_tar())
                os.chmod(backup_path,0o600)
                dest_map={
                    "panel/data.json":("/var/lib/onyx-panel/data.json",0o600),
                    "panel/site-draft.html":("/var/lib/onyx-panel/site-draft.html",0o600),
                    "panel/custom-presets.json":("/var/lib/onyx-panel/custom-presets.json",0o600),
                    "panel/location.json":("/var/lib/onyx-panel/location.json",0o600),
                    "panel/api.key":("/var/lib/onyx-panel/api.key",0o600),
                    "onyx-panel/users.json":("/etc/onyx-panel/users.json",0o600),
                    "onyx-panel/mtproxy-secrets":("/etc/onyx-panel/mtproxy-secrets",0o600),
                    "onyx-panel/mtproto-host":("/etc/onyx-panel/mtproto-host",0o600),
                    "onyx-panel/manifest":("/etc/onyx-panel/manifest",0o600),
                    "onyx-panel/xray-path":("/etc/onyx-panel/xray-path",0o600),
                    "onyx-xray/config.json":("/etc/onyx-panel-xray/config.json",0o640)}
                for arc,data in restore.items():
                    if arc.startswith("onyx-panel/awg/"):
                        os.makedirs("/etc/onyx-panel/awg",exist_ok=True)
                        phys,mode=("/etc/onyx-panel/awg/"+arc.split("/")[2],0o600)
                    else: phys,mode=dest_map[arc]
                    os.makedirs(os.path.dirname(phys),exist_ok=True)
                    with open(phys,"wb") as f: f.write(data)
                    os.chmod(phys,mode)
                    if arc=="onyx-xray/config.json":
                        try: os.chown(phys,os.getuid(),grp.getgrnam("xray").gr_gid)
                        except Exception: pass
            except OSError as exc:
                print("import apply failed:",type(exc).__name__,file=sys.stderr,flush=True)
                imp_fail("Не удалось записать файлы. Проверьте диск и повторите."); return
            xray="onyx-xray/config.json" in restore
            if xray:
                def _restart_xray():
                    try: subprocess.run(["systemctl","restart","onyx-panel-xray.service"],capture_output=True,timeout=60)
                    except Exception: pass
                timer=threading.Timer(1.0,_restart_xray); timer.daemon=True; timer.start()
            msg="Импортировано файлов: %d. Предыдущее состояние сохранено: %s."%(len(restore),backup_path)+(" Xray перезапускается." if xray else "")
            if async_action: self.send_json({"ok":True,"message":msg})
            else: self.redirect("/settings")
            return

        if path==PANEL_PATH+"/panel-password":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            a=form.get("a","")
            if len(a)<3:
                msg="Пароль должен содержать минимум 3 символа."
                if async_action: self.send_json({"ok":False,"message":msg},400)
                else: self.send_html(msg,400)
                return
            d["admin"]["hash"]=hash_password(a)
            save(d)
            rotate_session_key()
            if async_action:
                self.send_json({"ok":True,"message":"Пароль изменён. Все сессии завершены — открываем страницу входа."})
            else:
                self.send_response(303)
                self.send_header("Set-Cookie",self.session_cookie("",0))
                self.send_header("Location",PANEL_PATH+"/login")
                self.end_headers()
            return

        if path==PANEL_PATH+"/panel-login":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            new_user=form.get("user","").strip()
            if not 1<=len(new_user)<=64:
                msg="Логин должен содержать от 1 до 64 символов."
                if async_action: self.send_json({"ok":False,"message":msg},400)
                else: self.send_html(esc(msg),400)
                return
            d["admin"]["user"]=new_user
            save(d)
            if async_action:
                self.send_json({"ok":True,"message":"Логин изменён. Используйте его при следующем входе.","login":new_user})
            else:
                self.redirect("/settings")
            return

        if path==PANEL_PATH+"/panel-path":
            async_action=self.headers.get("X-Onyx-Async","")=="1"
            def path_fail(msg):
                if async_action: self.send_json({"ok":False,"message":msg},400)
                else: self.send_html(esc(msg),400)
            new_path=form.get("path","").strip().rstrip("/").lower()
            old_path=PANEL_PATH
            if not re.fullmatch(r"/[a-z0-9][a-z0-9-]{2,58}[a-z0-9]",new_path):
                path_fail("Путь — от 4 до 60 символов после /: латиница, цифры и дефис, без дефиса по краям. Например /xray или /my-vpn.")
                return
            if new_path.strip("/") in ("onyx-sub","wpp-sub"):
                path_fail("Этот путь занят маршрутами подписок. Выберите другой.")
                return
            if new_path==old_path:
                path_fail("Этот путь уже используется.")
                return
            import fcntl
            lock=open("/run/lock/onyx-panel.lock","a")
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                path_fail("Выполняется другая операция с панелью. Повторите позже.")
                return
            caddy_path="/etc/caddy/Caddyfile"
            service_path="/etc/systemd/system/onyx-panel.service"
            tmp_caddy=caddy_path+".newpath"
            try:
                s=open(caddy_path,encoding="utf-8").read()
                pattern=r'\n\s*handle(?:_path)?\s+'+re.escape(old_path)+r'/\*\s*\{\s*reverse_proxy\s+127\.0\.0\.1:8090\s*\}\s*'
                s,n=re.subn(pattern,'\n',s,count=1,flags=re.S)
                if n!=1: raise ValueError("Не найден текущий маршрут панели в Caddy. Смените путь через консольную команду ONYX.")
                m=re.search(r'(?m)^\s*reverse_proxy 127\.0\.0\.1:8080\s*\{',s)
                if not m: raise ValueError("Не найден маршрут WEB Proxy в конфигурации Caddy.")
                route="    handle "+new_path+"/* {\n        reverse_proxy 127.0.0.1:8090\n    }\n\n"
                s=s[:m.start()]+route+s[m.start():]
                with open(tmp_caddy,"w",encoding="utf-8") as f: f.write(s)
                u=open(service_path,encoding="utf-8").read()
                u,n2=re.subn(r'(?m)^Environment=ONYX_PANEL_PATH=.*$',"Environment=ONYX_PANEL_PATH="+new_path,u,count=1)
                if n2!=1: raise ValueError("Не найден путь панели в systemd-службе. Смените путь через консольную команду ONYX.")
                subprocess.run(["caddy","fmt","--overwrite",tmp_caddy],capture_output=True,timeout=20)
                check=subprocess.run(["caddy","validate","--config",tmp_caddy,"--adapter","caddyfile"],capture_output=True,timeout=30)
                if check.returncode!=0: raise ValueError("Новая конфигурация Caddy не прошла проверку.")
                # Write in place so the root:caddy owner group of the Caddyfile survives.
                with open(caddy_path,"w",encoding="utf-8") as f: f.write(s)
                with open(service_path,"w",encoding="utf-8") as f: f.write(u)
            except ValueError as exc:
                try: os.unlink(tmp_caddy)
                except OSError: pass
                path_fail(str(exc))
                return
            except (OSError,subprocess.TimeoutExpired):
                try: os.unlink(tmp_caddy)
                except OSError: pass
                path_fail("Не удалось изменить конфигурацию. Используйте консольную команду ONYX.")
                return
            new_url=("https://"+DOMAIN if DOMAIN else "")+new_path+"/login"
            def _apply_restart():
                try:
                    subprocess.run(["systemctl","daemon-reload"],capture_output=True,timeout=30)
                    # Caddy first: the new routing must be live even if this
                    # process is killed by the panel restart that follows.
                    subprocess.run(["systemctl","restart","caddy.service"],capture_output=True,timeout=60,start_new_session=True)
                    subprocess.run(["systemctl","restart","onyx-panel.service"],capture_output=True,timeout=60,start_new_session=True)
                except Exception:
                    pass
            restart=threading.Timer(1.2,_apply_restart)
            restart.daemon=True
            restart.start()
            if async_action:
                self.send_json({"ok":True,"message":"Адрес панели изменён. Службы перезапускаются.","newPath":new_path,"newUrl":new_url})
            else:
                self.redirect(new_url)
            return

        self.send_html("Not found",404)

    def serve_subscription(self,token):
        if not re.fullmatch(r"[a-f0-9]{64}",token):
            self.send_data("Not found",404); return
        if not allow_subscription_request(client_id(self)):
            self.send_data("Слишком много запросов. Повторите через минуту.",429,headers={"Retry-After":"60"}); return
        if not SUB_FETCH_SLOTS.acquire(blocking=False):
            self.send_data("Сервис занят. Повторите позже.",503,headers={"Retry-After":"15"}); return
        try:
            # Reject unknown URLs before spawning any privileged helper.
            if not any(s.get("enabled") and secrets.compare_digest(s["token"],token) for s in subscription_registry()):
                self.send_data("Not found",404); return
            if "text/html" in self.headers.get("Accept",""):
                self.send_data("Добавьте эту ссылку как подписку в клиент. Для ограниченной подписки нужен X-HWID (Happ).",200); return
            result=ctl_subscription({"operation":"fetch","token":token,"hwid":self.headers.get("X-HWID","")})
            if not result.get("ok"):
                headers={"X-Hwid-Active":"true","subscription-always-hwid-enable":"true"}
                if result.get("code")=="hwid_required": headers["X-Hwid-Not-Supported"]="true"
                if result.get("code")=="device_limit": headers.update({"X-Hwid-Limit":"true","X-Hwid-Max-Devices-Reached":"true"})
                self.send_data(result.get("message","Подписка недоступна"),int(result.get("status",503)),headers=headers); return
            labels={"vless":"VLESS","hysteria":"Hysteria2"}
            local_name=node_api.location_prefix(node_api.load_location(LOCATION_FILE))
            lines=[proxy_link(u["protocol"],u["secret"],u["backend_port"],local_name+" · "+labels[u["protocol"]],u.get("username","")) for u in result["users"]]
            if result["users"]:
                first=result["users"][0]
                remote_id=federation_id(first.get("subscription_id",""),first.get("device_id",""))
                wanted=[u["protocol"] for u in result["users"] if u["protocol"] in ("vless","hysteria")]
                for node in node_api.load_nodes(NODES_FILE):
                    if not node.get("enabled",True): continue
                    try:
                        remote=node_api.sync_profile(node,remote_id,node_api.location_prefix(node),wanted)
                        lines.extend(p["link"] for p in remote.get("profiles",[]) if isinstance(p,dict) and isinstance(p.get("link"),str))
                    except node_api.NodeError as exc:
                        print("node subscription sync failed:",node.get("url"),str(exc),file=sys.stderr,flush=True)
            state=traffic()
            up=sum(int(state.get(u["id"],{}).get("up",0)) for u in result["users"])
            down=sum(int(state.get(u["id"],{}).get("down",0)) for u in result["users"])
            headers={"profile-title":"base64:"+base64.b64encode(result["name"].encode()).decode(),"profile-update-interval":"6",
                     "subscription-userinfo":f"upload={up}; download={down}; total=0; expire=0"}
            if result["limited"]: headers.update({"X-Hwid-Active":"true","subscription-always-hwid-enable":"true"})
            self.send_data(base64.b64encode(("\n".join(lines)+"\n").encode()).decode(),headers=headers)
        except Exception:
            self.send_data("Подписка временно недоступна.",503)
        finally:
            SUB_FETCH_SLOTS.release()

def backup_manifest():
    try: ver=open("/etc/onyx-panel/version",encoding="ascii").read().strip()
    except OSError: ver="unknown"
    return {"app":"onyx-panel","version":ver,"domain":DOMAIN,"exported":int(time.time())}

BACKUP_FILES=(
    ("panel/data.json","/var/lib/onyx-panel/data.json",True),
    ("panel/site-draft.html","/var/lib/onyx-panel/site-draft.html",False),
    ("panel/custom-presets.json","/var/lib/onyx-panel/custom-presets.json",False),
    ("panel/location.json","/var/lib/onyx-panel/location.json",False),
    ("panel/api.key","/var/lib/onyx-panel/api.key",False),
    ("onyx-panel/users.json","/etc/onyx-panel/users.json",True),
    ("onyx-panel/mtproxy-secrets","/etc/onyx-panel/mtproxy-secrets",False),
    ("onyx-panel/mtproto-host","/etc/onyx-panel/mtproto-host",False),
    ("onyx-panel/manifest","/etc/onyx-panel/manifest",False),
    ("onyx-panel/xray-path","/etc/onyx-panel/xray-path",False),
    ("onyx-xray/config.json","/etc/onyx-panel-xray/config.json",False),
)

def build_backup_tar():
    import io, tarfile
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode="w:gz") as tar:
        payload=json.dumps(backup_manifest(),ensure_ascii=False).encode("utf-8")
        info=tarfile.TarInfo("manifest.json"); info.size=len(payload)
        info.mtime=int(time.time()); tar.addfile(info,io.BytesIO(payload))
        for arc,phys,required in BACKUP_FILES:
            if not os.path.exists(phys):
                if required: raise ValueError("Файл не найден: "+arc)
                continue
            with open(phys,"rb") as f: data=f.read()
            info=tarfile.TarInfo(arc); info.size=len(data)
            info.mtime=int(time.time()); info.mode=0o600
            tar.addfile(info,io.BytesIO(data))
        awg_dir="/etc/onyx-panel/awg"
        if os.path.isdir(awg_dir):
            for name in sorted(os.listdir(awg_dir)):
                if not re.fullmatch(r"[a-f0-9]{16}\.json",name): continue
                with open(os.path.join(awg_dir,name),"rb") as f: data=f.read()
                info=tarfile.TarInfo("onyx-panel/awg/"+name); info.size=len(data)
                info.mtime=int(time.time()); info.mode=0o600
                tar.addfile(info,io.BytesIO(data))
    return buf.getvalue()

def expiry_sweep():
    # Auto-disable clients whose access date has passed; runs every minute.
    while True:
        time.sleep(60)
        try:
            now=int(time.time())
            with STATE_LOCK:
                pending={k:v for k,v in load().get("expires",{}).items() if v<=now}
            if not pending: continue
            subs={s.get("id"):s for s in subscription_registry()}
            profiles={u.get("id"):u for u in users()}
            for uid,ts in pending.items():
                s=subs.get(uid)
                if s is not None:
                    if s.get("enabled",True):
                        try:
                            if ctl_subscription({"id":uid,"operation":"set-enabled","enabled":False}).get("ok"):
                                purge_remote_profiles_async(s)
                                print("access expired, disabled:",uid,file=sys.stderr,flush=True)
                        except Exception:
                            print("expiry disable failed:",uid,file=sys.stderr,flush=True)
                else:
                    u=profiles.get(uid)
                    if u is not None and u.get("enabled",True):
                        try: ctl("set-user",uid,"0")
                        except Exception:
                            print("expiry disable failed:",uid,file=sys.stderr,flush=True)
                if s is None and uid not in profiles:
                    with STATE_LOCK:
                        d=load()
                        if uid in d.get("expires",{}):
                            d["expires"].pop(uid,None); save(d)
        except Exception as exc:
            print("expiry sweep failed:",type(exc).__name__,file=sys.stderr,flush=True)

def heal_caddy_route():
    # If a path change was interrupted before caddy restarted, the Caddyfile
    # already names the new path while the running caddy still routes the old
    # one and the panel ends up stranded behind the landing page. Reconcile on
    # every start: remove stale panel routes, add the current one if missing.
    caddy_path="/etc/caddy/Caddyfile"
    try: s=open(caddy_path,encoding="utf-8").read()
    except OSError: return
    known={"/onyx-sub/*","/wpp-sub/*","/wpp-api/*",PANEL_PATH+"/*"}
    route="    handle "+PANEL_PATH+"/* {\n        reverse_proxy 127.0.0.1:8090\n    }\n"
    blocks=[(m.start(),m.end(),m.group(1)) for m in re.finditer(
        r"(?m)^[ \t]*handle\s+(/\S+/\*)\s*\{\s*\n[ \t]*reverse_proxy 127\.0\.0\.1:8090[ \t]*\n[ \t]*\}[ \t]*\n?",s)]
    stale=[b for b in blocks if b[2] not in known]
    has_current=any(b[2]==PANEL_PATH+"/*" for b in blocks)
    if not stale and has_current: return
    for start,end,_ in sorted(stale,key=lambda b:-b[0]):
        s=s[:start]+s[end:]
    if not has_current:
        m=re.search(r'(?m)^[ \t]*reverse_proxy 127\.0\.0\.1:8080[ \t]*\{',s)
        if not m: return
        s=s[:m.start()]+route+"\n"+s[m.start():]
    open(caddy_path,"w",encoding="utf-8").write(s)
    subprocess.run(["caddy","fmt","--overwrite",caddy_path],capture_output=True,timeout=20)
    check=subprocess.run(["caddy","validate","--config",caddy_path,"--adapter","caddyfile"],capture_output=True,timeout=30)
    if check.returncode!=0:
        print("caddy route heal skipped: config invalid",file=sys.stderr,flush=True); return
    r=subprocess.run(["systemctl","reload","caddy.service"],capture_output=True,timeout=30)
    if r.returncode: subprocess.run(["systemctl","restart","caddy.service"],capture_output=True,timeout=60)
    print("caddy route healed for",PANEL_PATH,file=sys.stderr,flush=True)

def main():
    heal_caddy_route()
    threading.Thread(target=expiry_sweep,daemon=True).start()
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="--repair-site":
        write_site_html(read_site_html())
        print("Public landing page assets repaired.")
    else:
        main()



PY

# Embed the panel logo so /__logo always serves even if the file is missing
# (an in-place update from an installation that shipped panel-logo.png).
{ printf 'LOGO_EMBEDDED="%s"\n' "$(base64 -w 0 "$LOGO_SOURCE" 2>/dev/null || openssl base64 -A -in "$LOGO_SOURCE")"; cat "$APP_FILE"; } > "$APP_FILE.newpath" && mv "$APP_FILE.newpath" "$APP_FILE"

if [[ "$UPDATING" != "1" ]]; then
python3 - "${DATA_FILE}" "${ADMIN}" "${PASS}" <<'PY'
import base64,hashlib,json,os,secrets,sys

data_file,admin,password=sys.argv[1],sys.argv[2],sys.argv[3]
salt=secrets.token_bytes(16)
digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
data={
    "admin":{"user":admin,"hash":base64.b64encode(salt+digest).decode()},
    "site":{"html":"<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Система подключения</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#05070b;color:#fff;font:16px system-ui}.card{width:min(700px,88vw);padding:48px;text-align:center;border:1px solid #ffffff14;border-radius:28px;background:#101722e8;box-shadow:0 30px 100px #0009}.ok{color:#65efad}h1{font-size:clamp(34px,6vw,58px)}</style></head><body><div class=\"card\"><div class=\"ok\">● ONLINE</div><h1>Система подключения</h1><p>Безопасное соединение активно.</p></div></body></html>"}
}
tmp=data_file+".tmp"
with open(tmp,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=True,indent=2)
os.chmod(tmp,0o600)
os.replace(tmp,data_file)
PY
fi

python3 -m py_compile "$APP_FILE"
python3 -m py_compile "$APP_DIR/onyx_subscriptions.py" "$APP_DIR/onyx_panel_extras.py" "$APP_DIR/onyx_ui.py" "$APP_DIR/onyx_metrics.py" "$APP_DIR/onyx_update.py" "$APP_DIR/onyx_nodes.py" "$APP_DIR/onyx_openflux.py" "$APP_DIR/onyx_awg.py" "$APP_DIR/onyx_firewall.py" "$APP_DIR/onyx_components.py"


# ---- Finish installation: service, Caddy route, permissions, start ----
echo "[3/6] Creating data..."
python3 - <<PY
import json
with open("${DATA_FILE}", encoding="utf-8") as f:
    json.load(f)
PY
chown root:root "$DATA_FILE"
chmod 0600 "$DATA_FILE"

echo "[3.5/6] Verifying administrator credentials..."
if [[ "$UPDATING" == "1" ]]; then
python3 - "$DATA_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d=json.load(f)
assert d["admin"]["user"] and d["admin"]["hash"]
print("      Existing administrator credentials retained.")
PY
else
python3 - "$DATA_FILE" "$ADMIN" "$PASS" <<'PY'
import base64, hashlib, json, secrets, sys
p, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
with open(p, encoding="utf-8") as f:
    d=json.load(f)
assert d["admin"]["user"] == user
raw=base64.b64decode(d["admin"]["hash"])
salt, expected = raw[:16], raw[16:]
actual=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
assert secrets.compare_digest(expected, actual)
print("      Administrator credentials verified.")
PY
fi

echo "[4/6] Creating systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Onyx Panel 1.2.5
After=network-online.target caddy.service tproxy-server.service mtproxy.service onyx-panel-firewall.service
Wants=network-online.target
Requires=onyx-panel-firewall.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_FILE
Environment=ONYX_DOMAIN=$DOMAIN
Environment=ONYX_MTPROTO_HOST=$MTPROTO_HOST
Environment=ONYX_PANEL_PATH=$PANEL_PATH
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR /etc/onyx-panel /srv/tproxy-site
[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$SERVICE_FILE"

echo "[4.2/6] Installing Onyx console menu..."
# Replace the updater atomically: the running outer update.sh may still be
# executing from this exact path, so never truncate its inode in place.
install -o root -g root -m 0755 "$BASE/update.sh" /usr/local/sbin/.onyx-panel-update.new
mv -f /usr/local/sbin/.onyx-panel-update.new /usr/local/sbin/onyx-panel-update
cat > /etc/systemd/system/onyx-panel-web-update.service <<'UNIT'
[Unit]
Description=Onyx Panel administrator-requested update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/onyx-panel/onyx_update.py run
TimeoutStartSec=infinity
# Separate cgroup: stopping onyx-panel during an update must not kill this job.
# No Install section: this unit runs only after an authenticated admin request.
UNIT
chmod 0644 /etc/systemd/system/onyx-panel-web-update.service
cat > /etc/systemd/system/onyx-panel-component-update.service <<'UNIT'
[Unit]
Description=Onyx Panel component version manager
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/onyx-panel/onyx_components.py run
TimeoutStartSec=infinity
UNIT
chmod 0644 /etc/systemd/system/onyx-panel-component-update.service
cat > /usr/local/sbin/ONYX <<'ONYX'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SERVICE="/etc/systemd/system/onyx-panel.service"
DATA="/var/lib/onyx-panel/data.json"
CADDYFILE="/etc/caddy/Caddyfile"
DROPIN="/etc/systemd/system/caddy.service.d/tproxy.conf"
LOCK="/run/lock/onyx-panel.lock"

die(){ echo "ОШИБКА: $*" >&2; exit 1; }
[[ ${EUID:-1} -eq 0 ]] || die "Запустите меню от root: sudo ONYX"
[[ -s "$SERVICE" && -s "$DATA" ]] || die "Onyx Panel не установлен полностью."

domain(){ sed -n 's/^Environment=TPROXY_HOSTNAME=//p' "$DROPIN" 2>/dev/null | head -n1; }
panel_path(){ sed -n 's/^Environment=ONYX_PANEL_PATH=//p' "$SERVICE" 2>/dev/null | head -n1; }
admin_name(){ python3 - "$DATA" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8")).get("admin",{}).get("user","не задан"))
PY
}
service_state(){ systemctl is-active "$1" 2>/dev/null || echo "не найден"; }
ssl_expiry(){
    local d
    d="$(domain)"
    timeout 10 openssl s_client -connect 127.0.0.1:443 -servername "$d" </dev/null 2>/dev/null |
        openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2- || echo "не удалось прочитать"
}
port_80_state(){
    if ss -lntp 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:80[[:space:]]'; then
        if ss -lntp 2>/dev/null | grep -E ':80[[:space:]]' | grep -q 'caddy'; then
            echo "занят Caddy (нормально)"
        else
            echo "занят другой программой — конфликт"
        fi
    else
        echo "свободен"
    fi
}
pause(){ echo; read -r -p "Нажмите Enter, чтобы вернуться в меню..." _; }
lock_changes(){ exec 9>"$LOCK"; flock -n 9 || die "Установка, обновление или удаление уже выполняется."; }
unlock_changes(){ flock -u 9 2>/dev/null || true; exec 9>&-; }

show_info(){
    local d p version
    d="$(domain)"; p="$(panel_path)"; version="$(cat /etc/onyx-panel/version 2>/dev/null || echo '1.0.0')"
    echo
    echo "============================================================"
    echo "                 Onyx Panel"
    echo "============================================================"
    printf 'Версия:          %s\n' "$version"
    printf 'Домен:           %s\n' "$d"
    printf 'URL панели:      https://%s%s/login\n' "$d" "$p"
    printf 'Логин:           %s\n' "$(admin_name)"
    echo  "Пароль:          не хранится в открытом виде; его можно сменить"
    echo
    printf 'Панель:          %s\n' "$(service_state onyx-panel.service)"
    printf 'Caddy:           %s\n' "$(service_state caddy.service)"
    printf 'WEB Proxy:       %s\n' "$(service_state tproxy-server.service)"
    printf 'MTProxy:         %s\n' "$(service_state mtproxy.service)"
    printf 'Xray:            %s\n' "$(service_state onyx-panel-xray.service)"
    printf 'OpenFlux:        %s\n' "$(service_state onyx-panel-openflux.service)"
    printf 'SSL действует до:%s\n' " $(ssl_expiry)"
    printf 'TCP/80:          %s\n' "$(port_80_state)"
    echo "============================================================"
}

change_credentials(){
    local current new_user new_pass
    current="$(admin_name)"
    echo
    read -r -p "Новый логин [$current]: " new_user
    new_user="${new_user:-$current}"
    [[ ${#new_user} -ge 1 && ${#new_user} -le 64 ]] || { echo "Логин должен содержать от 1 до 64 символов."; return 1; }
    read -r -s -p "Новый пароль (минимум 3 символа): " new_pass
    echo
    [[ ${#new_pass} -ge 3 ]] || { echo "Пароль должен содержать минимум 3 символа."; return 1; }
    lock_changes
    if ! ONYX_NEW_USER="$new_user" ONYX_NEW_PASS="$new_pass" python3 - "$DATA" <<'PY'
import base64,hashlib,json,os,secrets,sys,tempfile
p=sys.argv[1]
user=os.environ.pop("ONYX_NEW_USER","")
password=os.environ.pop("ONYX_NEW_PASS","")
if not user or len(user)>64 or len(password)<3:
    raise SystemExit("Некорректные учётные данные")
with open(p,encoding="utf-8") as f: d=json.load(f)
salt=secrets.token_bytes(16)
digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
d["admin"]={"user":user,"hash":base64.b64encode(salt+digest).decode()}
fd,tmp=tempfile.mkstemp(prefix="data.json.",dir=os.path.dirname(p))
try:
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(d,f,ensure_ascii=True,indent=2); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o600); os.replace(tmp,p)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY
    then
        unlock_changes
        echo "Не удалось сохранить учётные данные."
        return 1
    fi
    systemctl restart onyx-panel.service
    unlock_changes
    echo "Логин и пароль изменены. Все старые сессии завершены."
}

change_path(){
    local old suffix new backup service_backup d
    old="$(panel_path)"; d="$(domain)"
    echo
    echo "Текущий путь: $old"
    read -r -p "Новый суффикс после panel- (пусто = создать случайный): " suffix
    if [[ -z "$suffix" ]]; then suffix="$(openssl rand -hex 16)"; fi
    suffix="${suffix,,}"
    [[ "$suffix" =~ ^[a-z0-9][a-z0-9-]{2,58}[a-z0-9]$ ]] || {
        echo "Используйте 4–60 символов: латинские буквы, цифры и дефис; без дефиса по краям."
        return 1
    }
    new="/panel-$suffix"
    [[ "$new" != "$old" ]] || { echo "Этот путь уже используется."; return 1; }
    lock_changes
    backup="$(mktemp /tmp/onyx-Caddyfile.XXXXXX)"
    service_backup="$(mktemp /tmp/onyx-panel-service.XXXXXX)"
    cp -a "$CADDYFILE" "$backup"; cp -a "$SERVICE" "$service_backup"
    rollback_path(){
        cp -a "$backup" "$CADDYFILE"; cp -a "$service_backup" "$SERVICE"
        systemctl daemon-reload
        systemctl restart onyx-panel.service caddy.service 2>/dev/null || true
        rm -f "$backup" "$service_backup"
        unlock_changes
    }
    if ! python3 - "$CADDYFILE" "$SERVICE" "$old" "$new" <<'PY'
import re,sys
caddy,service,old,new=sys.argv[1:]
s=open(caddy,encoding="utf-8").read()
pattern=r'\n\s*handle(?:_path)?\s+'+re.escape(old)+r'/\*\s*\{\s*reverse_proxy\s+127\.0\.0\.1:8090\s*\}\s*'
s,n=re.subn(pattern,'\n',s,count=1,flags=re.S)
if n!=1: raise SystemExit("Не найден текущий маршрут панели в Caddy")
m=re.search(r'(?m)^\s*reverse_proxy 127\.0\.0\.1:8080\s*\{',s)
if not m: raise SystemExit("Не найден маршрут WEB Proxy в Caddy")
route="    handle "+new+"/* {\n        reverse_proxy 127.0.0.1:8090\n    }\n\n"
s=s[:m.start()]+route+s[m.start():]
open(caddy,"w",encoding="utf-8").write(s)
u=open(service,encoding="utf-8").read()
u,n=re.subn(r'(?m)^Environment=ONYX_PANEL_PATH=.*$',"Environment=ONYX_PANEL_PATH="+new,u,count=1)
if n!=1: raise SystemExit("Не найден путь панели в systemd-службе")
open(service,"w",encoding="utf-8").write(u)
PY
    then
        rollback_path; echo "Смена пути отменена."; return 1
    fi
    caddy fmt --overwrite "$CADDYFILE" >/dev/null 2>&1 || true
    if ! caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
        rollback_path; echo "Новая конфигурация Caddy не прошла проверку. Старый путь восстановлен."; return 1
    fi
    systemctl daemon-reload
    if ! systemctl restart onyx-panel.service caddy.service ||
       ! curl -fsS --max-time 5 "http://127.0.0.1:8090${new}/__health" >/dev/null ||
       ! curl -kfsS --max-time 10 "https://${d}${new}/__health" >/dev/null; then
        rollback_path; echo "Проверка нового URL не прошла. Старый путь восстановлен."; return 1
    fi
    rm -f "$backup" "$service_backup"
    unlock_changes
    echo "Новый URL панели: https://${d}${new}/login"
}

run_update(){
    echo
    echo "Запускается безопасное обновление до последней опубликованной версии..."
    exec /usr/local/sbin/onyx-panel-update
}

maintain_ssl(){
    echo
    echo "Проверяю HTTPS-сертификат и запускаю обслуживание Caddy..."
    lock_changes
    if /usr/local/sbin/onyx-panel-sync-tls --force; then
        unlock_changes
        echo "SSL-сертификат действителен; копия для Hysteria2 синхронизирована."
        echo "TCP/80 используется для HTTP→HTTPS и обновления сертификата: $(port_80_state)"
    else
        unlock_changes
        echo "Не удалось подтвердить обновление SSL. Проверьте DNS, TCP/80, TCP/443 и журнал Caddy."
        return 1
    fi
}

run_remove(){
    echo
    echo "Запускается полное удаление Onyx Panel..."
    exec /usr/local/sbin/onyx-panel-uninstall
}

while true; do
    clear 2>/dev/null || true
    echo "============================================================"
    echo "              Onyx Panel — WPP MENU"
    echo "============================================================"
    echo "  1) Информация"
    echo "  2) Обновить"
    echo "  3) Сменить логин и пароль"
    echo "  4) Сменить URL-путь панели"
    echo "  5) Проверить SSL-сертификат"
    echo "  6) Удалить"
    echo "  0) Выход"
    echo "============================================================"
    read -r -p "Выберите пункт: " choice
    case "$choice" in
        1) show_info; pause ;;
        2) run_update ;;
        3) change_credentials || true; pause ;;
        4) change_path || true; pause ;;
        5) maintain_ssl || true; pause ;;
        6) run_remove ;;
        0) exit 0 ;;
        *) echo "Неизвестный пункт."; sleep 1 ;;
    esac
done
ONYX
chmod 0755 /usr/local/sbin/ONYX
ln -sfn /usr/local/sbin/ONYX /usr/local/sbin/onyx

echo "[4.5/6] Configuring Caddy panel route..."
CADDYFILE="/etc/caddy/Caddyfile"
test -s "$CADDYFILE" || die "Caddyfile is missing."

python3 - "$CADDYFILE" "$PANEL_PATH" "$DOMAIN" "$ACME_EMAIL" "$XRAY_PATH" <<'PY'
import re, sys
from pathlib import Path
p, path, domain, email, xray_path = sys.argv[1:]
s = Path(p).read_text(encoding="utf-8")
legacy_address = re.compile(
    r"(?m)^(?P<indent>\s*)(?:"
    r":443\s*,\s*" + re.escape(domain) +
    r"|" + re.escape(domain) + r"\s*,\s*:443"
    r"|https://" + re.escape(domain) + r"(?::443)?"
    r"|" + re.escape(domain) + r":443)\s*\{\s*$"
)
s = legacy_address.sub(lambda m:m.group("indent")+domain+" {",s,count=1)

# Materialize the core Caddyfile placeholders before validation.
s = s.replace("{$TPROXY_HOSTNAME}", domain)
s = s.replace("{$ACME_EMAIL}", email)
s = re.sub(
    r'\n\s*handle /onyx-sub/\*\s*\{\s*reverse_proxy 127\.0\.0\.1:8090\s*\}\s*',
    '\n', s, flags=re.S,
)
s = re.sub(
    r'\n\s*handle /onyx-api/\*\s*\{\s*reverse_proxy 127\.0\.0\.1:8090\s*\}\s*',
    '\n', s, flags=re.S,
)
s = re.sub(
    r'\n\s*handle(?:_path)? /panel-[a-z0-9-]{3,64}/\*\s*\{\s*reverse_proxy 127\.0\.0\.1:8090\s*\}\s*',
    '\n',
    s,
    flags=re.S,
)
# Remove the complete managed block written by the experimental V2.2 router
# before installing the single stable VLESS XHTTP route.
s = re.sub(
    r'\n?\s*# ONYX XRAY ROUTES BEGIN\n.*?\n\s*# ONYX XRAY ROUTES END\n?',
    '\n',
    s,
    flags=re.S,
)
s = re.sub(
    r'\n\s*@web_panel_vless\s+path\s+/vless-[a-f0-9]{24}(?:\s+/vless-[a-f0-9]{24}/\*)?\s*\n\s*reverse_proxy\s+@web_panel_vless\s+h2c://127\.0\.0\.1:10000\s*\{\s*flush_interval\s+-1\s*\}\s*',
    '\n',
    s,
    flags=re.S,
)
s = re.sub(
    r'\n\s*@web_panel_vless\s+path\s+/vless-[a-f0-9]{24}(?:\s+/vless-[a-f0-9]{24}/\*)?\s*\n\s*handle\s+@web_panel_vless\s*\{\s*reverse_proxy\s+127\.0\.0\.1:10000\s*\{\s*transport\s+http\s*\{\s*versions\s+h2c\s*\}\s*flush_interval\s+-1\s*\}\s*\}\s*',
    '\n',
    s,
    flags=re.S,
)
m = re.search(r'(?m)^\s*reverse_proxy 127\.0\.0\.1:8080\s*\{', s)
if not m:
    raise SystemExit("Could not locate tproxy relay reverse_proxy in Caddyfile")
route = (
    "    handle /onyx-api/* {\n"
    "        reverse_proxy 127.0.0.1:8090\n"
    "    }\n\n"
    "    handle /onyx-sub/* {\n"
    "        reverse_proxy 127.0.0.1:8090\n"
    "    }\n\n"
    "    @web_panel_vless path " + xray_path + " " + xray_path + "/*\n"
    "    handle @web_panel_vless {\n"
    "        reverse_proxy 127.0.0.1:10000 {\n"
    "            transport http {\n"
    "                versions h2c\n"
    "            }\n"
    "            flush_interval -1\n"
    "        }\n"
    "    }\n\n"
    "    handle " + path + "/* {\n"
    "        reverse_proxy 127.0.0.1:8090\n"
    "    }\n\n"
)
s = s[:m.start()] + route + s[m.start():]

# Restore standard Caddy automatic HTTPS. TCP/80 remains open for redirects
# and HTTP-01 validation; TCP/443 serves the panel and proxy traffic.
s = re.sub(
    r'\n?\s*# ONYX TLS WITHOUT PORT 80 BEGIN\n.*?\n\s*# ONYX TLS WITHOUT PORT 80 END\n?',
    '\n', s, flags=re.S,
)
s = re.sub(r'(?m)^\s*auto_https\s+disable_redirects\s*\n?', '', s)
s = re.sub(r'\A\s*\{\s*\}\s*', '', s, count=1)
s = re.sub(
    r'\n?\s*# ONYX HTTP REDIRECT BEGIN\n.*?\n\s*# ONYX HTTP REDIRECT END\n?',
    '\n', s, flags=re.S,
)
def enable_http_challenge(text, hostname):
    match = re.search(r'(?m)^\s*' + re.escape(hostname) + r'\s*\{\s*$', text)
    if not match:
        raise SystemExit("Onyx Panel Caddy site block was not found")
    opening = text.find('{', match.start(), match.end())
    depth = 0
    closing = None
    for index in range(opening, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                closing = index + 1
                break
    if closing is None:
        raise SystemExit("Onyx Panel Caddy site block is incomplete")
    block = text[match.start():closing]
    block = re.sub(r'(?m)^\s*disable_http_challenge\s*\n?', '', block)
    return text[:match.start()] + block + text[closing:]
s = enable_http_challenge(s, domain)
redirect = (
    "# ONYX HTTP REDIRECT BEGIN\n"
    "http://" + domain + " {\n"
    "    redir https://" + domain + "{uri} permanent\n"
    "}\n"
    "# ONYX HTTP REDIRECT END\n"
)
s = s.rstrip() + "\n\n" + redirect
Path(p).write_text(s, encoding="utf-8")
PY

if grep -Eq '\{\$(TPROXY_HOSTNAME|ACME_EMAIL)\}' "$CADDYFILE"; then
    echo "ERROR: unresolved Caddy environment placeholders remain."
    sed -n '1,100p' "$CADDYFILE" || true
    exit 1
fi

caddy fmt --overwrite "$CADDYFILE" >/dev/null 2>&1 || true

if ! caddy validate --config "$CADDYFILE" --adapter caddyfile; then
    echo
    echo "ERROR: Caddy validation failed."
    sed -n '1,100p' "$CADDYFILE" || true
    exit 1
fi

systemctl daemon-reload
echo "      Activating Caddy..."
if ! systemctl restart caddy.service; then
    systemctl --no-pager --full status caddy.service >&2 || true
    journalctl -u caddy.service -n 60 --no-pager >&2 || true
    die "Caddy failed to start."
fi
systemctl enable onyx-panel-firewall.service
systemctl restart onyx-panel-firewall.service
systemctl enable onyx-panel-traffic.timer onyx-panel-metrics.timer
systemctl stop onyx-panel-traffic.timer onyx-panel-metrics.timer
systemctl reset-failed onyx-panel-traffic.service onyx-panel-metrics.service 2>/dev/null || true
systemctl enable onyx-panel.service
systemctl restart onyx-panel.service

echo "      Initializing user/secret manager..."
"$MANAGER" init

echo "      Checking initial traffic collection..."
systemctl restart onyx-panel-traffic.service || {
    journalctl -u onyx-panel-traffic.service -n 30 --no-pager >&2 || true
    die "Traffic collection failed; update cannot be considered successful."
}
echo "      Checking initial VPS metrics..."
systemctl restart onyx-panel-metrics.service || {
    journalctl -u onyx-panel-metrics.service -n 30 --no-pager >&2 || true
    die "VPS metrics failed; update cannot be considered successful."
}
systemctl restart onyx-panel-traffic.timer onyx-panel-metrics.timer
for timer in onyx-panel-traffic.timer onyx-panel-metrics.timer; do
    systemctl is-active --quiet "$timer" || die "Collector timer did not start: $timer"
    timer_state="$(systemctl show --property=SubState --value "$timer")"
    case "$timer_state" in
        waiting|running) ;;
        *) die "Collector timer has no future trigger: $timer ($timer_state)" ;;
    esac
done

chown -R root:tproxy /srv/tproxy-site
find /srv/tproxy-site -type d -exec chmod 0750 {} +
find /srv/tproxy-site -type f -exec chmod 0640 {} +

echo "[5/6] Starting service..."
systemctl restart caddy.service
systemctl restart tproxy-server.service
systemctl restart mtproxy.service

# Re-publish the retained author source through the current CSP-safe renderer.
# This automatically repairs pages saved by the affected release where the
# HTML loaded but its inline styles and scripts were blocked by the browser.
ONYX_DOMAIN="$DOMAIN" \
ONYX_MTPROTO_HOST="$MTPROTO_HOST" \
ONYX_PANEL_PATH="$PANEL_PATH" \
    python3 "$APP_FILE" --repair-site

# Ensure no stale copy of this exact panel occupies 127.0.0.1:8090.
systemctl stop onyx-panel.service 2>/dev/null || true
pkill -f '[/]opt/onyx-panel/panel\.py' 2>/dev/null || true
sleep 0.3

if ss -lntp 2>/dev/null | grep -Eq ':8090\\b'; then
    echo "ERROR: 127.0.0.1:8090 is still occupied before starting the panel."
    ss -lntp 2>/dev/null | grep -E ':8090\\b' || true
    exit 1
fi

systemctl start onyx-panel.service
sleep 1

for unit in caddy.service tproxy-server.service mtproxy.service onyx-panel.service; do
    systemctl is-active --quiet "$unit" || {
        echo "ERROR: $unit failed to become active."
        systemctl --no-pager --full status "$unit" || true
        if [[ "$unit" == "onyx-panel.service" ]]; then
            echo "--- Current panel journal ---"
            journalctl -u onyx-panel.service --since "2 minutes ago" -n 120 --no-pager || true
        fi
        exit 1
    }
done

echo "[6/6] Checking panel service and route..."
if ! systemctl is-active --quiet onyx-panel.service; then
    echo "ERROR: onyx-panel.service is not active."
    systemctl --no-pager --full status onyx-panel.service || true
    journalctl -u onyx-panel.service --since "10 minutes ago" -n 80 --no-pager || true
    exit 1
fi

if ! curl -fsS --max-time 5 "http://127.0.0.1:8090${PANEL_PATH}/__health" >/dev/null; then
    echo "ERROR: panel is not answering on 127.0.0.1:8090."
    ss -lntp 2>/dev/null | grep -E ':8090\b' || true
    journalctl -u onyx-panel.service --since "10 minutes ago" -n 80 --no-pager || true
    exit 1
fi

if ! curl -k -fsS --max-time 10 "https://${DOMAIN}${PANEL_PATH}/__health" >/dev/null; then
    echo "ERROR: Caddy panel route returned an error."
    echo "--- Caddy route ---"
    grep -n -A4 -B2 "${PANEL_PATH}" "$CADDYFILE" || true
    echo "--- panel service ---"
    systemctl --no-pager --full status onyx-panel.service || true
    journalctl -u onyx-panel.service --since "10 minutes ago" -n 50 --no-pager || true
    exit 1
fi

# Retire components owned by the withdrawn experimental integrations only
# after the stable panel, Caddy and proxy services have passed health checks.
if [[ -e /etc/onyx-panel/mieru-ufw-owned ]]; then
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
        while read -r old_port; do
            [[ "$old_port" =~ ^[0-9]+$ ]] || continue
            (( old_port >= 1 && old_port <= 65535 )) || continue
            ufw --force delete allow "${old_port}/tcp" >/dev/null 2>&1 || true
        done < /etc/onyx-panel/mieru-ufw-owned
    fi
    rm -f /etc/onyx-panel/mieru-ufw-owned
fi
if [[ -e /etc/onyx-panel/mita-package-owned ]]; then
    command -v mita >/dev/null 2>&1 && mita stop >/dev/null 2>&1 || true
    apt-get -o DPkg::Lock::Timeout=600 remove -y mita >/dev/null || die "Could not remove the Onyx-owned Mieru package."
    rm -f /etc/onyx-panel/mita-package-owned
fi
rm -f /etc/onyx-panel/mieru-server.json /etc/onyx-panel/mieru-port
if [[ -e /etc/onyx-panel/naive-caddy-owned ]]; then
    rm -rf -- /opt/onyx-panel/caddy-naive
    rm -f /etc/onyx-panel/naive-caddy-owned
fi

echo
echo "============================================================"
if [[ "$UPDATING" == "1" ]]; then
echo "          Onyx Panel 1.2.5 UPDATED"
else
echo "         Onyx Panel 1.2.5 IS READY"
fi
echo "============================================================"
echo
echo "Panel URL:"
echo "  https://${DOMAIN}${PANEL_PATH}/login"
echo
NODE_API_TOKEN="$(python3 - "$DOMAIN" <<'PY'
import sys
sys.path.insert(0,"/opt/onyx-panel")
import onyx_nodes
try:
    key=open("/var/lib/onyx-panel/api.key",encoding="ascii").read().strip()
    print(onyx_nodes.make_connection_token(sys.argv[1],key))
except (OSError,ValueError):
    pass
PY
)"
if [[ "$UPDATING" != "1" && "$NODE_API_TOKEN" == onyxnode1_* ]]; then
echo "Node API token:"
echo "  ${NODE_API_TOKEN}"
echo
fi
echo "Administrator login:"
echo "  ${ADMIN}"
echo
if [[ "$UPDATING" == "1" ]]; then
echo "Administrator password: retained (unchanged)"
echo
else
echo "Administrator password:"
echo "  ${PASS}"
echo
fi
echo "============================================================"
