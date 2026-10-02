#!/usr/bin/env bash
set -Eeuo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
umask 077

die() { echo "ERROR: $*" >&2; exit 1; }
for file in install-panel.sh install-core.sh uninstall-onyx-panel.sh update.sh onyx-logo.png onyx_subscriptions.py onyx_panel_extras.py onyx_ui.py onyx_metrics.py onyx_update.py onyx_nodes.py onyx_openflux.py onyx_awg.py onyx_firewall.py onyx_components.py; do
    [[ -s "$BASE/$file" ]] || die "Package is incomplete: missing $file. Extract the complete archive."
done
[[ -s "$BASE/assets/OpenFlux-linux-amd64" || -s "$BASE/OpenFlux-linux-amd64" ]] ||
    die "Package is incomplete: missing OpenFlux-linux-amd64. Extract the complete archive."
for asset in amneziawg-go-linux-amd64 awg-linux-amd64 awg-quick-linux-amd64; do
    [[ -s "$BASE/assets/$asset" ]] || die "Package is incomplete: missing assets/$asset. Extract the complete archive."
done
[[ -s "$BASE/onyx-panel/flags.tar.gz" ]] ||
    die "Package is incomplete: onyx-panel/flags.tar.gz is missing. Extract the complete archive."
for font in manrope-cyrillic-wght-normal.woff2 manrope-latin-wght-normal.woff2 jetbrains-mono-cyrillic-wght-normal.woff2 jetbrains-mono-latin-wght-normal.woff2; do
    [[ -s "$BASE/fonts/$font" ]] || die "Package is incomplete: missing fonts/$font. Extract the complete archive."
done
command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
exec 9>/run/lock/onyx-panel.lock
flock -n 9 || die "Another Onyx Panel install, update or removal is already running."
cleanup_credentials() {
    if [[ -f /etc/onyx-panel/install-credentials ]]; then
        command -v shred >/dev/null 2>&1 && shred -u /etc/onyx-panel/install-credentials 2>/dev/null || \
            rm -f /etc/onyx-panel/install-credentials
    fi
}
trap cleanup_credentials EXIT

echo "Onyx Panel 1.8.0: preparing server..."

PANEL_UPDATE=0
if [[ -s /var/lib/onyx-panel/data.json ]] &&
   [[ -f /etc/systemd/system/onyx-panel.service ]] &&
   sed -n 's/^Environment=ONYX_PANEL_PATH=//p' /etc/systemd/system/onyx-panel.service |
       head -n1 | grep -Eq '^/[a-z0-9][a-z0-9-]{2,58}[a-z0-9]$'; then
    PANEL_UPDATE=1
    echo "Existing control panel detected; its users, password, address and site HTML will be preserved."
else
    echo "Installation/resume mode enabled. Existing compatible services will be reused and missing components installed."
fi

# Install the recovery command before making system changes so even an
# interrupted first installation can be cleaned up deterministically.
install -d -m 0700 /etc/onyx-panel
install -o root -g root -m 0755 \
    "$BASE/uninstall-onyx-panel.sh" \
    /usr/local/sbin/onyx-panel-uninstall

echo "Installing proxy services..."
bash "$BASE/install-core.sh"

echo "Installing control panel..."
if [[ "$PANEL_UPDATE" == 1 ]]; then
    ONYX_PANEL_UPDATE=1 bash "$BASE/install-panel.sh"
else
    bash "$BASE/install-panel.sh"
fi

for unit in caddy.service mtproxy.service tproxy-server.service onyx-panel.service onyx-panel-firewall.service; do
    systemctl is-active --quiet "$unit" || { echo "Installation failed: $unit did not start."; exit 1; }
done
systemctl is-enabled --quiet onyx-panel-firewall.service ||
    die "Persistent user firewall is not enabled."
nft list table inet onyx_panel >/dev/null 2>&1 ||
    die "Persistent user firewall table is missing."
nft list table ip onyx_awg >/dev/null 2>&1 ||
    die "AWG routing firewall table is missing."
[[ -x /opt/onyx-panel/xray/xray ]] || die "Xray binary was not installed."
[[ -x /usr/local/bin/amneziawg-go && -x /usr/local/bin/awg ]] || die "AmneziaWG was not installed."
/usr/local/bin/awg --version >/dev/null || die "AmneziaWG tools check failed."
[[ -s /etc/onyx-panel-xray/config.json ]] || die "Xray configuration was not created."
[[ -x /usr/local/sbin/ONYX ]] || die "Onyx console menu was not installed."
systemctl is-active --quiet onyx-panel-sync-tls.timer ||
    die "The Xray TLS synchronization timer did not start."
echo "Installation complete."
printf '%s\n' '1.8.0' > /etc/onyx-panel/version
chmod 0600 /etc/onyx-panel/version

# Keep a private copy of the complete package on the server so the panel can
# reinstall or roll back later without any external downloads.
if [[ "$BASE" != "/opt/onyx-panel-package" ]]; then
    rm -rf /opt/onyx-panel-package.tmp
    install -d -o root -g root -m 0700 /opt/onyx-panel-package.tmp
    cp -a "$BASE/." /opt/onyx-panel-package.tmp/
    rm -rf /opt/onyx-panel-package
    mv /opt/onyx-panel-package.tmp /opt/onyx-panel-package
    printf '%s\n' '1.8.0' > /opt/onyx-panel-package/version
    chmod 0600 /opt/onyx-panel-package/version
fi
