#!/usr/bin/env bash
# Safe in-place updater for Onyx Panel.
# The panel modules (AmneziaWG binaries, OpenFlux) ship with the package; Xray,
# Caddy, Go, AmneziaWG tools and the relay source are downloaded from their
# official repositories during the update. Set ONYX_UPDATE_REPOSITORY to pull
# the package from your own Git repository instead of using the local copy.
set -Eeuo pipefail
umask 077

export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null

REPOSITORY="${ONYX_UPDATE_REPOSITORY:-https://github.com/flareon2008/Onyx-Panel.git}"
REQUESTED_REF="${ONYX_PANEL_REF:-}"
RELEASE_REF="$REQUESTED_REF"
LOCAL_SOURCE=""
LOCAL_VERSION="1.2.0"
# `--local` is accepted for compatibility and behaves the same as the default.
LOCAL_SOURCE="$(cd "$(dirname "$0")" && pwd)"
# Invoked as the installed /usr/local/sbin/onyx-panel-update, the script's own
# directory is not a package — fall back to the copy the installer saved.
if [[ ! -s "$LOCAL_SOURCE/install-final.sh" && -d /opt/onyx-panel-package ]]; then
    LOCAL_SOURCE="/opt/onyx-panel-package"
fi
for file in install-final.sh install-panel.sh install-core.sh uninstall-onyx-panel.sh repair-landing-pages.sh onyx-logo.png onyx_subscriptions.py onyx_panel_extras.py onyx_ui.py onyx_metrics.py onyx_update.py onyx_nodes.py onyx_openflux.py onyx_awg.py onyx_firewall.py onyx_components.py; do
    [[ -s "$LOCAL_SOURCE/$file" ]] || { echo "Incomplete local archive: $file is missing." >&2; exit 1; }
done
[[ -s "$LOCAL_SOURCE/assets/OpenFlux-linux-amd64" || -s "$LOCAL_SOURCE/OpenFlux-linux-amd64" ]] || {
    echo "Incomplete local archive: OpenFlux-linux-amd64 is missing." >&2; exit 1;
}
for asset in amneziawg-go-linux-amd64 awg-linux-amd64 awg-quick-linux-amd64; do
    [[ -s "$LOCAL_SOURCE/assets/$asset" ]] || { echo "Incomplete local archive: assets/$asset is missing." >&2; exit 1; }
done
for font in manrope-cyrillic-wght-normal.woff2 manrope-latin-wght-normal.woff2 jetbrains-mono-cyrillic-wght-normal.woff2 jetbrains-mono-latin-wght-normal.woff2; do
    [[ -s "$LOCAL_SOURCE/fonts/$font" ]] || { echo "Incomplete local archive: fonts/$font is missing." >&2; exit 1; }
done
[[ -s "$LOCAL_SOURCE/onyx-panel/flags.tar.gz" ]] || {
    echo "Incomplete local archive: onyx-panel/flags.tar.gz is missing." >&2; exit 1;
}
SERVICE="/etc/systemd/system/onyx-panel.service"
LEGACY_SERVICE="/etc/systemd/system/onyx-panel.service"
DATA_FILE="/var/lib/onyx-panel/data.json"
PRIMARY_SECRET="/etc/onyx-panel/primary-secret"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ ${EUID} -eq 0 ]] || die "Run as root: sudo -i"
command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
exec 9>/run/lock/onyx-panel.lock
flock -n 9 || die "Another Onyx Panel install, update or removal is already running."

echo "============================================================"
echo "     Onyx Panel 1.2.0 — SAFE UPDATE"
echo "============================================================"
echo "Users, administrator password, panel URL and site HTML will be retained."

MIGRATING_LEGACY=0
PANEL_PATH=""
LEGACY_SECRET=""

if [[ -s "$DATA_FILE" ]] &&
   { [[ -f "$SERVICE" ]] || [[ -f "$LEGACY_SERVICE" ]]; }; then
    echo "Current control panel detected; account and data will be preserved."
else
    for legacy_item in /etc/tproxy-server/config.json /etc/tproxy-server/profiles.json /etc/mtproxy /opt/MTProxy /etc/systemd/system/mtproxy.service /etc/systemd/system/tproxy-server.service; do
        if [[ -e "$legacy_item" ]]; then
            MIGRATING_LEGACY=1
            break
        fi
    done
    [[ "$MIGRATING_LEGACY" == 1 ]] || die "No supported WEB Proxy installation was found."
    echo "First-generation WEB Proxy detected (without a control panel)."
    echo "The updater will add the panel and ask for a new administrator login and password."
fi

# Some early builds used this service name. Copying it only supplies the
# existing secret panel address; install-panel.sh replaces the definition.
if [[ "$MIGRATING_LEGACY" != 1 && ! -f "$SERVICE" && -f "$LEGACY_SERVICE" ]]; then
    cp -a "$LEGACY_SERVICE" "$SERVICE"
fi
if [[ "$MIGRATING_LEGACY" != 1 ]]; then
    [[ -f "$SERVICE" ]] || die "Panel service file was not found."
    PANEL_PATH="$(sed -n 's/^Environment=ONYX_PANEL_PATH=//p' "$SERVICE" | head -n1 || true)"
    [[ "$PANEL_PATH" =~ ^/[a-z0-9][a-z0-9-]{2,58}[a-z0-9]$ ]] || die "Could not read the existing panel address."
fi

if [[ "$MIGRATING_LEGACY" == 1 ]]; then
    LEGACY_SECRET="$(cat "$PRIMARY_SECRET" 2>/dev/null || true)"
    if ! [[ "$LEGACY_SECRET" =~ ^([0-9a-f]{32}|dd[0-9a-f]{32})$ ]] && [[ -s /etc/tproxy-server/profiles.json ]]; then
        LEGACY_SECRET="$(sed -n 's/.*"secret"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' /etc/tproxy-server/profiles.json | head -n1)"
    fi
    if ! [[ "$LEGACY_SECRET" =~ ^([0-9a-f]{32}|dd[0-9a-f]{32})$ ]] && [[ -s /etc/mtproxy/mtproxy.env ]]; then
        LEGACY_SECRET="$(sed -n 's/^MTPROXY_SECRET=//p' /etc/mtproxy/mtproxy.env | head -n1)"
    fi
    if ! [[ "$LEGACY_SECRET" =~ ^([0-9a-f]{32}|dd[0-9a-f]{32})$ ]]; then
        # The first public installer stored the Secret only in ExecStart=-S.
        LEGACY_SECRET="$(systemctl cat mtproxy.service 2>/dev/null |
            sed -n 's/.*[[:space:]]-S[[:space:]]\([0-9a-f]*\).*/\1/p' | head -n1 || true)"
    fi
    [[ "$LEGACY_SECRET" =~ ^([0-9a-f]{32}|dd[0-9a-f]{32})$ ]] ||
        die "Could not recover the primary Secret from the first-generation installation."
else
    [[ -s "$PRIMARY_SECRET" ]] || die "Primary Secret is missing from the existing panel installation."
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
# Pause the HTTP writer before taking a snapshot of subscription slots/keys.
# Proxy services keep running. Recover the panel if snapshot/download fails.
PANEL_WAS_RUNNING=0
if systemctl is-active --quiet onyx-panel.service; then
    PANEL_WAS_RUNNING=1
    systemctl stop onyx-panel.service
fi
trap 'if [[ "$PANEL_WAS_RUNNING" == 1 ]]; then systemctl start onyx-panel.service || true; fi' EXIT
BACKUP="/root/onyx-panel-update-backup-${STAMP}"
install -d -m 0700 "$BACKUP"
BACKUP_ITEMS=()
for item in /opt/onyx-panel /opt/onyx-panel /opt/MTProxy /usr/local/bin/caddy /usr/local/bin/tproxy-server /usr/local/bin/amneziawg-go /usr/local/bin/awg /usr/local/bin/awg-quick /usr/local/sbin/onyx-panelctl /usr/local/sbin/onyx-panel-user-firewall /usr/local/sbin/onyx-panel-sync-tls /usr/local/sbin/onyx-panel-awg-run /usr/local/sbin/onyx-panel-awg-up /usr/local/sbin/onyx-panel-awg-down /usr/local/sbin/onyx-panel-update /usr/local/sbin/onyx-panel-uninstall /usr/local/sbin/ONYX /usr/local/sbin/onyx /etc/systemd/system/onyx-panel.service /etc/systemd/system/onyx-panel-firewall.service /etc/systemd/system/onyx-panel-traffic.service /etc/systemd/system/onyx-panel-traffic.timer /etc/systemd/system/onyx-panel-xray.service /etc/systemd/system/onyx-panel-openflux.service /etc/systemd/system/onyx-panel-awg@.service /etc/systemd/system/onyx-panel-sync-tls.service /etc/systemd/system/onyx-panel-sync-tls.timer /etc/systemd/system/onyx-panel-component-update.service /etc/systemd/system/tproxy-server.service /etc/systemd/system/mtproxy.service /etc/systemd/system/caddy.service.d/tproxy.conf /etc/caddy/Caddyfile /etc/tproxy-server /etc/mtproxy /etc/mita /etc/onyx-panel-xray /etc/sysctl.d/90-onyx-panel-awg.conf /var/lib/onyx-panel-xray /var/lib/onyx-panel-components /var/lib/onyx-panel /etc/onyx-panel /srv/tproxy-site; do
    [[ -e "$item" ]] && BACKUP_ITEMS+=("$item")
    [[ -e "$item" ]] && cp -a --parents "$item" "$BACKUP"
done
shopt -s nullglob
for item in /etc/systemd/system/onyx-user-*.service /etc/systemd/system/onyx-panel-web-update.service /etc/systemd/system/onyx-panel-metrics.service /etc/systemd/system/onyx-panel-metrics.timer; do
    [[ -e "$item" ]] || continue
    BACKUP_ITEMS+=("$item")
    cp -a --parents "$item" "$BACKUP"
done
shopt -u nullglob
tar --numeric-owner -cpf "$BACKUP/state.tar" "${BACKUP_ITEMS[@]}"
echo "Backup created: $BACKUP"

HAD_FIREWALL_SERVICE=0
[[ -e /etc/systemd/system/onyx-panel-firewall.service ]] && HAD_FIREWALL_SERVICE=1
HAD_TRAFFIC_TIMER=0
[[ -e /etc/systemd/system/onyx-panel-traffic.timer ]] && HAD_TRAFFIC_TIMER=1
HAD_METRICS_TIMER=0
[[ -e /etc/systemd/system/onyx-panel-metrics.timer ]] && HAD_METRICS_TIMER=1
HAD_PANEL_DATA=0
HAD_PANEL_SERVICE=0
HAD_PRIMARY_SECRET=0
HAD_CADDY_DROPIN=0
HAD_PANEL_STATE_DIR=0
HAD_XRAY_STATE=0
HAD_XRAY_USER=0
HAD_XRAY_GROUP=0
HAD_OPENFLUX_UNIT=0
HAD_OPENFLUX_USER=0
HAD_AWG=0
HAD_ONYX_MENU=0
HAD_WEB_UPDATE_UNIT=0
[[ -e /etc/systemd/system/onyx-panel-web-update.service ]] && HAD_WEB_UPDATE_UNIT=1
HAD_COMPONENT_UPDATE_UNIT=0
[[ -e /etc/systemd/system/onyx-panel-component-update.service ]] && HAD_COMPONENT_UPDATE_UNIT=1
[[ -e "$DATA_FILE" ]] && HAD_PANEL_DATA=1
[[ -e "$SERVICE" ]] && HAD_PANEL_SERVICE=1
[[ -e "$PRIMARY_SECRET" ]] && HAD_PRIMARY_SECRET=1
[[ -e /etc/systemd/system/caddy.service.d/tproxy.conf ]] && HAD_CADDY_DROPIN=1
[[ -d /etc/onyx-panel ]] && HAD_PANEL_STATE_DIR=1
{ [[ -e /opt/onyx-panel ]] || [[ -e /etc/onyx-panel-xray ]] || [[ -e /etc/systemd/system/onyx-panel-xray.service ]]; } && HAD_XRAY_STATE=1
id xray >/dev/null 2>&1 && HAD_XRAY_USER=1
getent group xray >/dev/null 2>&1 && HAD_XRAY_GROUP=1
[[ -e /etc/systemd/system/onyx-panel-openflux.service ]] && HAD_OPENFLUX_UNIT=1
id onyx-openflux >/dev/null 2>&1 && HAD_OPENFLUX_USER=1
[[ -e /etc/systemd/system/onyx-panel-awg@.service || -x /usr/local/bin/amneziawg-go ]] && HAD_AWG=1
[[ -e /usr/local/sbin/ONYX ]] && HAD_ONYX_MENU=1
UPDATE_COMMITTED=0
rollback_update() {
    local code="$1"
    [[ "$UPDATE_COMMITTED" == 1 || "$code" == 0 ]] && return 0
    echo "Update failed; restoring the previous working state..." >&2
    systemctl stop onyx-panel.service onyx-panel-firewall.service onyx-panel-traffic.timer onyx-panel-traffic.service onyx-panel-metrics.timer onyx-panel-metrics.service onyx-panel-xray.service onyx-panel-openflux.service onyx-panel-sync-tls.timer 2>/dev/null || true
    for unit in $(systemctl list-units --all 'onyx-panel-awg@*.service' --no-legend 2>/dev/null | awk '{print $1}'); do systemctl stop "$unit" 2>/dev/null || true; done
    tar --numeric-owner -xpf "$BACKUP/state.tar" -C / 2>/dev/null || true
    if [[ "$HAD_FIREWALL_SERVICE" == 0 ]]; then
        rm -f /etc/systemd/system/onyx-panel-firewall.service
        rm -f /usr/local/sbin/onyx-panel-user-firewall
    fi
    if [[ "$HAD_TRAFFIC_TIMER" == 0 ]]; then
        rm -f /etc/systemd/system/onyx-panel-traffic.service /etc/systemd/system/onyx-panel-traffic.timer
    fi
    if [[ "$HAD_METRICS_TIMER" == 0 ]]; then
        systemctl disable onyx-panel-metrics.timer 2>/dev/null || true
        rm -f /etc/systemd/system/onyx-panel-metrics.service /etc/systemd/system/onyx-panel-metrics.timer
    fi
    if [[ "$HAD_ONYX_MENU" == 0 ]]; then
        rm -f /usr/local/sbin/ONYX /usr/local/sbin/onyx /usr/local/sbin/onyx-panel-update
    fi
    if [[ "$HAD_WEB_UPDATE_UNIT" == 0 ]]; then
        rm -f /etc/systemd/system/onyx-panel-web-update.service
    fi
    if [[ "$HAD_COMPONENT_UPDATE_UNIT" == 0 ]]; then
        rm -f /etc/systemd/system/onyx-panel-component-update.service
        rm -rf /var/lib/onyx-panel-components
    fi
    if [[ "$HAD_PANEL_SERVICE" == 0 ]]; then
        rm -f "$SERVICE"
        rm -rf /opt/onyx-panel
    fi
    if [[ "$HAD_PANEL_DATA" == 0 ]]; then
        rm -rf /var/lib/onyx-panel
    fi
    if [[ "$HAD_PRIMARY_SECRET" == 0 ]]; then
        rm -f "$PRIMARY_SECRET"
    fi
    if [[ "$HAD_PANEL_STATE_DIR" == 0 ]]; then
        rm -rf /etc/onyx-panel
    fi
    if [[ "$HAD_CADDY_DROPIN" == 0 ]]; then
        rm -f /etc/systemd/system/caddy.service.d/tproxy.conf
    fi
    if [[ "$HAD_XRAY_STATE" == 0 ]]; then
        rm -rf /opt/onyx-panel /etc/onyx-panel-xray /var/lib/onyx-panel-xray
        rm -f /etc/onyx-panel/xray-path /etc/onyx-panel/xray-user-owned /etc/onyx-panel/xray-group-owned \
            /etc/onyx-panel/hysteria-ufw-owned
        rm -f /usr/local/sbin/onyx-panel-sync-tls \
            /etc/systemd/system/onyx-panel-xray.service \
            /etc/systemd/system/onyx-panel-sync-tls.service \
            /etc/systemd/system/onyx-panel-sync-tls.timer
    fi
    if [[ "$HAD_XRAY_USER" == 0 ]]; then
        userdel xray 2>/dev/null || true
    fi
    if [[ "$HAD_XRAY_GROUP" == 0 ]]; then
        groupdel xray 2>/dev/null || true
    fi
    if [[ "$HAD_OPENFLUX_UNIT" == 0 ]]; then
        systemctl disable --now onyx-panel-openflux.service 2>/dev/null || true
        rm -f /etc/systemd/system/onyx-panel-openflux.service
        rm -rf /opt/onyx-panel/openflux
    fi
    if [[ "$HAD_OPENFLUX_USER" == 0 ]]; then
        userdel onyx-openflux 2>/dev/null || true
    fi
    if [[ "$HAD_AWG" == 0 ]]; then
        rm -f /usr/local/bin/amneziawg-go /usr/local/bin/awg /usr/local/bin/awg-quick \
            /usr/local/sbin/onyx-panel-awg-run /usr/local/sbin/onyx-panel-awg-up /usr/local/sbin/onyx-panel-awg-down \
            /etc/systemd/system/onyx-panel-awg@.service /etc/sysctl.d/90-onyx-panel-awg.conf
        rm -f /etc/systemd/system/multi-user.target.wants/onyx-panel-awg@*.service
        nft delete table ip onyx_awg 2>/dev/null || true
    fi
    systemctl daemon-reload
    systemctl restart mtproxy.service tproxy-server.service caddy.service onyx-panel.service 2>/dev/null || true
    [[ -e /etc/onyx-panel/openflux/enabled ]] && systemctl restart onyx-panel-openflux.service 2>/dev/null || true
    [[ "$HAD_FIREWALL_SERVICE" == 1 ]] && systemctl restart onyx-panel-firewall.service 2>/dev/null || true
    [[ "$HAD_XRAY_STATE" == 1 ]] && systemctl restart onyx-panel-xray.service 2>/dev/null || true
    if [[ "$HAD_AWG" == 1 ]]; then
        for unit in $(systemctl list-unit-files 'onyx-panel-awg@*.service' --no-legend 2>/dev/null | awk '$2=="enabled" {print $1}'); do
            systemctl restart "$unit" 2>/dev/null || true
        done
    fi
    [[ "$HAD_TRAFFIC_TIMER" == 1 ]] && systemctl restart onyx-panel-traffic.timer 2>/dev/null || true
    [[ "$HAD_METRICS_TIMER" == 1 ]] && systemctl restart onyx-panel-metrics.timer 2>/dev/null || true
    echo "Previous files restored from: $BACKUP" >&2
}

REMOTE_OK=0
if [[ -n "$REPOSITORY" ]]; then
    echo "Checking the published Onyx Panel versions at the configured repository..."
    if ! command -v git >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get -o DPkg::Lock::Timeout=600 update
        apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends git
    fi
    if git ls-remote --heads "$REPOSITORY" >/dev/null 2>&1; then
        REMOTE_OK=1
    else
        echo "Repository unreachable — updating from the local package instead."
        REPOSITORY=""
    fi
fi
if [[ -n "$REPOSITORY" && "$REMOTE_OK" == 1 ]]; then
    if [[ -z "$RELEASE_REF" ]]; then
        RELEASE_REF="$(git ls-remote --tags --refs "$REPOSITORY" 'v[0-9]*' |
            awk -F/ '{print $3}' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n1)"
    fi
    [[ "$RELEASE_REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]] ||
        die "Could not determine a valid published release tag."
    echo "Selected release: $RELEASE_REF"
    CURRENT_VERSION="$(cat /etc/onyx-panel/version 2>/dev/null || true)"
    if [[ -z "$REQUESTED_REF" && "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+~-][A-Za-z0-9.+~-]+)?$ ]] &&
       dpkg --compare-versions "$CURRENT_VERSION" ge "${RELEASE_REF#v}"; then
        echo "Onyx Panel ${CURRENT_VERSION} is already the latest published stable version."
        exit 0
    fi
fi

TEMP_DIR="$(mktemp -d /tmp/onyx-panel-update.XXXXXX)"
finish() {
    local code=$?
    trap - EXIT
    rollback_update "$code"
    rm -rf "$TEMP_DIR"
    exit "$code"
}
trap finish EXIT

echo "Preparing Onyx Panel update files..."
if [[ -n "$REPOSITORY" && "$REMOTE_OK" == 1 ]]; then
    if ! git clone --depth 1 --branch "$RELEASE_REF" "$REPOSITORY" "$TEMP_DIR/source" 2>/dev/null; then
        echo "Clone failed — falling back to the local package."
        cp -a "$LOCAL_SOURCE/." "$TEMP_DIR/source/"
    fi
else
    cp -a "$LOCAL_SOURCE/." "$TEMP_DIR/source/"
fi
[[ -f "$TEMP_DIR/source/install-panel.sh" ]] || die "Update package is incomplete."
chmod 0700 "$TEMP_DIR/source/install-panel.sh" "$TEMP_DIR/source/install-final.sh" "$TEMP_DIR/source/install-core.sh"

if [[ "$MIGRATING_LEGACY" == 1 ]]; then
    DOMAIN="$(sed -n 's/^Environment=TPROXY_HOSTNAME=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)"
    if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] && [[ -s /etc/tproxy-server/config.json ]]; then
        DOMAIN="$(sed -n 's/.*"public_hostname"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /etc/tproxy-server/config.json | head -n1)"
    fi
    if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] && [[ -s /etc/caddy/Caddyfile ]]; then
        DOMAIN="$(sed -n 's/^[[:space:]]*\([a-z0-9][a-z0-9.-]*\)[[:space:]]*{[[:space:]]*$/\1/p' /etc/caddy/Caddyfile |
            grep -vE '^(http|https|localhost)$' | head -n1 || true)"
    fi
    [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]] ||
        die "Could not recover the domain from the first-generation installation."

    ACME_EMAIL="$(sed -n 's/^Environment=ACME_EMAIL=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)"
    if ! [[ "$ACME_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        while true; do
            read -r -p "ACME email for the existing domain: " ACME_EMAIL
            [[ "$ACME_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] && break
            echo "Invalid email."
        done
    fi

    install -d -m 0700 /etc/onyx-panel
    printf '%s\n' "$LEGACY_SECRET" > "$PRIMARY_SECRET"
    chmod 0600 "$PRIMARY_SECRET"
    if [[ ! -s /etc/onyx-panel/mtproto-host ]]; then
        MTPROTO_HOST="$(curl -4fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)"
        printf '%s\n' "${MTPROTO_HOST:-$DOMAIN}" > /etc/onyx-panel/mtproto-host
        chmod 0600 /etc/onyx-panel/mtproto-host
    fi
    if [[ ! -s /etc/onyx-panel/caddy-owned ]]; then
        printf '%s\n' 'ONYX_PANEL_V2_CADDY_SHARED' > /etc/onyx-panel/caddy-owned
        chmod 0600 /etc/onyx-panel/caddy-owned
    fi
    install -d -m 0755 /etc/systemd/system/caddy.service.d
    cat > /etc/systemd/system/caddy.service.d/tproxy.conf <<EOF
[Service]
Environment=TPROXY_HOSTNAME=$DOMAIN
Environment=TPROXY_SITE_ROOT=/srv/tproxy-site
Environment=ACME_EMAIL=$ACME_EMAIL
ReadWritePaths=/etc/caddy
EOF
    chmod 0644 /etc/systemd/system/caddy.service.d/tproxy.conf
    systemctl daemon-reload
fi

# Keep the relay binary current as part of the same public update command.
# Configuration, users, secrets and public-site files are not replaced.
if [[ -f "$TEMP_DIR/source/repair-landing-pages.sh" ]]; then
    chmod 0700 "$TEMP_DIR/source/repair-landing-pages.sh"
    bash "$TEMP_DIR/source/repair-landing-pages.sh"
fi

if [[ "$MIGRATING_LEGACY" == 1 ]]; then
    # New panel bootstrap: install-panel asks for a login and one password,
    # creates the private URL and leaves the old core proxy data in place.
    bash "$TEMP_DIR/source/install-panel.sh"
else
    ONYX_PANEL_UPDATE=1 bash "$TEMP_DIR/source/install-panel.sh"
fi
install -o root -g root -m 0755 \
    "$TEMP_DIR/source/uninstall-onyx-panel.sh" \
    /usr/local/sbin/onyx-panel-uninstall

if [[ -f "$LEGACY_SERVICE" ]]; then
    systemctl disable --now onyx-panel.service 2>/dev/null || true
    rm -f "$LEGACY_SERVICE"
    systemctl daemon-reload
fi

DOMAIN="$(sed -n 's/^Environment=TPROXY_HOSTNAME=//p' /etc/systemd/system/caddy.service.d/tproxy.conf | head -n1)"
PANEL_PATH="$(sed -n 's/^Environment=ONYX_PANEL_PATH=//p' "$SERVICE" | head -n1 || true)"
[[ "$PANEL_PATH" =~ ^/[a-z0-9][a-z0-9-]{2,58}[a-z0-9]$ ]] || die "The updated panel address could not be read."
systemctl is-active --quiet onyx-panel-firewall.service ||
    die "Persistent user firewall did not start after the update."
nft list table inet onyx_panel >/dev/null 2>&1 ||
    die "Persistent user firewall table is missing after the update."
[[ -x /opt/onyx-panel/xray/xray ]] || die "Xray binary is missing after the update."
[[ -s /etc/onyx-panel-xray/config.json ]] || die "Xray configuration is missing after the update."
command -v caddy >/dev/null 2>&1 || die "Caddy is missing after the update."
[[ -x /opt/MTProxy/objs/bin/mtproto-proxy ]] || die "MTProxy is missing after the update."
systemctl is-active --quiet caddy.service || die "Caddy did not start after the update."
systemctl is-active --quiet onyx-panel-sync-tls.timer ||
    die "The Xray TLS synchronization timer did not start after the update."
if [[ ! -s /etc/onyx-panel/caddy-owned ]]; then
    printf '%s\n' 'ONYX_PANEL_V2_CADDY_SHARED' > /etc/onyx-panel/caddy-owned
fi
UPDATE_VERSION="${RELEASE_REF#v}"
[[ -n "$REPOSITORY" || -n "$RELEASE_REF" ]] || UPDATE_VERSION="$LOCAL_VERSION"
printf '%s\n' "$UPDATE_VERSION" > /etc/onyx-panel/version
chmod 0600 /etc/onyx-panel/caddy-owned /etc/onyx-panel/version
UPDATE_COMMITTED=1
echo
echo "Update completed. Open the panel at: https://${DOMAIN}${PANEL_PATH}/login"
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
if [[ "$NODE_API_TOKEN" == onyxnode1_* ]]; then
    echo "Node API token: ${NODE_API_TOKEN}"
fi
