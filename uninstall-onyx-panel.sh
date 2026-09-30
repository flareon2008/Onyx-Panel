#!/usr/bin/env bash
# Onyx Panel 1.3.2 complete removal utility.
set -Eeuo pipefail

[[ ${EUID:-1} -eq 0 ]] || { echo "Run this script as root." >&2; exit 1; }
command -v flock >/dev/null 2>&1 || { echo "flock is required (package: util-linux)." >&2; exit 1; }
exec 9>/run/lock/onyx-panel.lock
flock -n 9 || { echo "Another Onyx Panel install, update or removal is already running." >&2; exit 1; }

echo "Onyx Panel 1.3.2 — complete removal"
echo "Removing all Onyx Panel 1.3.2 components..."

DOMAIN="$(sed -n 's/^Environment=TPROXY_HOSTNAME=//p' /etc/systemd/system/caddy.service.d/tproxy.conf 2>/dev/null | head -n1 || true)"
CADDY_MARKER="$(cat /etc/onyx-panel/caddy-owned 2>/dev/null || true)"
CADDY_OWNED=0
CADDY_SHARED=0
XRAY_USER_OWNED=0
XRAY_GROUP_OWNED=0
HYSTERIA_UFW_OWNED=0
HYSTERIA_UFW_PORTS=""
MTPROTO_UFW_PORTS=""
AWG_UFW_PORTS=""
AWG_UFW_ROUTES=""
AWG_OWNED=0
MIERU_UFW_OWNED=0
MIERU_PACKAGE_OWNED=0
NAIVE_CADDY_OWNED=0
[[ "$CADDY_MARKER" == "ONYX_PANEL_V2_CADDY_OWNER" ]] && CADDY_OWNED=1
[[ "$CADDY_MARKER" == "ONYX_PANEL_V2_CADDY_SHARED" ]] && CADDY_SHARED=1
[[ -e /etc/onyx-panel/xray-user-owned ]] && XRAY_USER_OWNED=1
[[ -e /etc/onyx-panel/xray-group-owned ]] && XRAY_GROUP_OWNED=1
[[ -e /etc/onyx-panel/mieru-ufw-owned ]] && MIERU_UFW_OWNED=1
[[ -e /etc/onyx-panel/mita-package-owned ]] && MIERU_PACKAGE_OWNED=1
[[ -e /etc/onyx-panel/naive-caddy-owned ]] && NAIVE_CADDY_OWNED=1
[[ -e /etc/onyx-panel/awg-owned ]] && AWG_OWNED=1
if [[ -e /etc/onyx-panel/hysteria-ufw-owned ]]; then
  HYSTERIA_UFW_OWNED=1
  HYSTERIA_UFW_PORTS="$(grep -Eo '[0-9]{1,5}' /etc/onyx-panel/hysteria-ufw-owned 2>/dev/null | sort -nu | tr '\n' ' ' || true)"
  [[ -n "$HYSTERIA_UFW_PORTS" ]] || HYSTERIA_UFW_PORTS="8443"
fi
if [[ -e /etc/onyx-panel/mtproto-ufw-owned ]]; then
  MTPROTO_UFW_PORTS="$(grep -Eo '[0-9]{1,5}' /etc/onyx-panel/mtproto-ufw-owned 2>/dev/null | sort -nu | tr '\n' ' ' || true)"
fi
if [[ -e /etc/onyx-panel/awg-ufw-owned ]]; then
  AWG_UFW_PORTS="$(grep -Eo '[0-9]{1,5}' /etc/onyx-panel/awg-ufw-owned 2>/dev/null | sort -nu | tr '\n' ' ' || true)"
fi
[[ -e /etc/onyx-panel/awg-route-ufw-owned ]] && AWG_UFW_ROUTES="$(cat /etc/onyx-panel/awg-route-ufw-owned 2>/dev/null || true)"

echo "Stopping services..."
for unit in \
  onyx-panel-web-update.service \
  onyx-panel-component-update.service \
  onyx-panel-metrics.timer onyx-panel-metrics.service \
  onyx-panel.service onyx-panel.service onyx-panel-mtproxy.service \
  onyx-panel-firewall.service onyx-panel-traffic.timer onyx-panel-traffic.service onyx-panel-xray.service \
  onyx-panel-sync-tls.timer onyx-panel-sync-tls.service \
  tproxy-firewall.service refresh-mtproxy-config.timer refresh-mtproxy-config.service \
  tproxy-server.service mtproxy.service
do
  systemctl disable --now "$unit" 2>/dev/null || true
done
for unit in $(systemctl list-units --all 'onyx-panel-awg@*.service' --no-legend 2>/dev/null | awk '{print $1}'); do
  systemctl disable --now "$unit" 2>/dev/null || true
done
mita stop >/dev/null 2>&1 || true

shopt -s nullglob
USER_UNITS=(/etc/systemd/system/onyx-user-*.service)
for unit_path in "${USER_UNITS[@]}"; do
  unit="$(basename "$unit_path")"
  systemctl disable --now "$unit" 2>/dev/null || true
  rm -f -- "$unit_path"
done

# Remove the firewall tables created by the panel and the proxy firewall.
nft delete table inet onyx_panel 2>/dev/null || true
nft delete table ip onyx_awg 2>/dev/null || true
nft delete table inet tproxy_backend 2>/dev/null || true
if [[ "$HYSTERIA_UFW_OWNED" == 1 ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  for port in $HYSTERIA_UFW_PORTS; do
    [[ "$port" =~ ^[0-9]+$ ]] || continue
    (( port >= 1 && port <= 65535 )) || continue
    ufw --force delete allow "$port/udp" >/dev/null 2>&1 || true
    ufw --force delete allow "$port/udp" >/dev/null 2>&1 || true
  done
fi
if [[ -n "$AWG_UFW_PORTS" ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  for port in $AWG_UFW_PORTS; do ufw --force delete allow "$port/udp" >/dev/null 2>&1 || true; done
fi
if [[ -n "$AWG_UFW_ROUTES" ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  while read -r awg_if awg_out; do
    [[ "$awg_if" =~ ^[A-Za-z0-9_.:-]+$ && "$awg_out" =~ ^[A-Za-z0-9_.:-]+$ ]] || continue
    ufw --force route delete allow in on "$awg_if" out on "$awg_out" >/dev/null 2>&1 || true
  done <<< "$AWG_UFW_ROUTES"
fi
if [[ -n "$MTPROTO_UFW_PORTS" ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  for port in $MTPROTO_UFW_PORTS; do
    [[ "$port" =~ ^[0-9]+$ ]] || continue
    (( port >= 1 && port <= 65535 )) || continue
    ufw --force delete allow "$port/tcp" >/dev/null 2>&1 || true
  done
fi
if [[ "$MIERU_UFW_OWNED" == 1 ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw --force delete allow 8965/tcp >/dev/null 2>&1 || true
fi

# Remove Caddy only when this release installed it and its configuration still
# contains only the project site. If another site was added later, remove just
# the project's top-level site block and preserve the shared Caddy deployment.
REMOVE_CADDY=0
PRESERVE_CADDY=0
if [[ "$((CADDY_OWNED + CADDY_SHARED))" -gt 0 && -n "$DOMAIN" && -f /etc/caddy/Caddyfile ]]; then
  CADDY_TMP="$(mktemp /tmp/onyx-panel-Caddyfile.XXXXXX)"
  set +e
  python3 - /etc/caddy/Caddyfile "$CADDY_TMP" "$DOMAIN" <<'PY'
import re,sys
source,target,domain=sys.argv[1:]
text=open(source,encoding="utf-8").read()
text=re.sub(r"\n?[ \t]*# ONYX NAIVE GLOBAL BEGIN\n.*?\n[ \t]*# ONYX NAIVE GLOBAL END\n?","\n",text,flags=re.S)
text=re.sub(r"\n?[ \t]*# ONYX NAIVE BEGIN\n.*?\n[ \t]*# ONYX NAIVE END\n?","\n",text,flags=re.S)
text=re.sub(r"(?m)^\s*:443,\s*"+re.escape(domain)+r"\s*\{\s*$",domain+" {",text,count=1)
lines=text.splitlines(keepends=True)
start=None
pattern=re.compile(r"^\s*"+re.escape(domain)+r"\s*\{\s*$")
for i,line in enumerate(lines):
    if pattern.match(line):
        start=i
        break
if start is None:
    raise SystemExit(2)
depth=0
end=None
for i in range(start,len(lines)):
    depth+=lines[i].count("{")-lines[i].count("}")
    if depth==0:
        end=i
        break
if end is None:
    raise SystemExit(3)
remaining=lines[:start]+lines[end+1:]
while remaining and not remaining[0].strip(): remaining.pop(0)
while remaining and not remaining[-1].strip(): remaining.pop()
meaningful=[x for x in remaining if x.strip() and not x.lstrip().startswith("#")]
if not meaningful:
    open(target,"w",encoding="utf-8").write("")
    raise SystemExit(10)
open(target,"w",encoding="utf-8").writelines(remaining)

# A project-owned canonical Caddyfile also contains one global options block
# (`{ ... }`). It is not another website. Report status 10 when that block and
# comments/blank lines are all that remain. Shared Caddy is still preserved by
# the shell branch below, together with this global block.
depth=0
outside=[]
for line in remaining:
    stripped=line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if depth == 0 and stripped == "{":
        depth=1
        continue
    if depth > 0:
        depth+=line.count("{")-line.count("}")
        continue
    outside.append(stripped)
if depth != 0:
    raise SystemExit(3)
if not outside:
    raise SystemExit(10)
PY
  PARSE_STATUS=$?
  set -e
  if [[ "$PARSE_STATUS" == 10 ]]; then
    if [[ "$CADDY_OWNED" == 1 ]]; then
      REMOVE_CADDY=1
      systemctl disable --now caddy.service 2>/dev/null || true
    else
      install -o root -g caddy -m 0640 "$CADDY_TMP" /etc/caddy/Caddyfile
      PRESERVE_CADDY=1
    fi
  elif [[ "$PARSE_STATUS" == 0 ]]; then
    if caddy validate --config "$CADDY_TMP" --adapter caddyfile >/dev/null 2>&1; then
      install -o root -g caddy -m 0640 "$CADDY_TMP" /etc/caddy/Caddyfile
      PRESERVE_CADDY=1
    else
      PRESERVE_CADDY=1
      echo "WARNING: the remaining Caddy configuration did not validate; the original file was preserved."
    fi
  else
    PRESERVE_CADDY=1
    echo "WARNING: the project Caddy block could not be removed automatically; Caddy was preserved."
  fi
  rm -f -- "$CADDY_TMP"
  [[ "$PRESERVE_CADDY" == 1 ]] && rm -f -- /etc/caddy/Caddyfile.before-onyx-panel
fi

echo "Removing Onyx Panel 1.3.2 files..."
if [[ -s /opt/onyx-panel/onyx_firewall.py ]]; then
  PYTHONPATH=/opt/onyx-panel python3 -c 'import onyx_firewall; onyx_firewall.purge()' 2>/dev/null || true
fi
systemctl disable --now onyx-panel-openflux.service 2>/dev/null || true
for unit in /etc/systemd/system/onyx-panel-openflux-*.service; do
  [[ -e "$unit" ]] || continue
  systemctl disable --now "$(basename "$unit")" 2>/dev/null || true
  rm -f -- "$unit"
done
rm -f -- \
  /etc/systemd/system/onyx-panel-web-update.service \
  /etc/systemd/system/onyx-panel-component-update.service \
  /etc/systemd/system/onyx-panel-metrics.service \
  /etc/systemd/system/onyx-panel-metrics.timer \
  /etc/systemd/system/onyx-panel.service \
  /etc/systemd/system/onyx-panel.service \
  /etc/systemd/system/onyx-panel-mtproxy.service \
  /etc/systemd/system/onyx-panel-firewall.service \
  /etc/systemd/system/onyx-panel-traffic.service \
  /etc/systemd/system/onyx-panel-traffic.timer \
  /etc/systemd/system/onyx-panel-xray.service \
  /etc/systemd/system/onyx-panel-openflux.service \
  /etc/systemd/system/onyx-panel-awg@.service \
  /etc/systemd/system/onyx-panel-sync-tls.service \
  /etc/systemd/system/onyx-panel-sync-tls.timer \
  /etc/systemd/system/tproxy-firewall.service \
  /etc/systemd/system/tproxy-server.service \
  /etc/systemd/system/mtproxy.service \
  /etc/systemd/system/refresh-mtproxy-config.timer \
  /etc/systemd/system/refresh-mtproxy-config.service \
  /usr/local/bin/tproxy-server \
  /usr/local/bin/tproxy-server.previous \
  /usr/local/bin/tproxy-server.next \
  /usr/local/sbin/onyx-panelctl \
  /usr/local/sbin/onyx-panel-user-firewall \
  /usr/local/sbin/onyx-panel-sync-tls \
  /usr/local/sbin/onyx-panel-awg-run \
  /usr/local/sbin/onyx-panel-awg-up \
  /usr/local/sbin/onyx-panel-awg-down \
  /usr/local/sbin/onyx-panel-update \
  /usr/local/sbin/ONYX \
  /usr/local/sbin/onyx \
  /usr/local/sbin/web-proxy-public-mtproxy \
  /usr/local/sbin/onyx-panel-mtproxy \
  /usr/local/sbin/onyx-panel-uninstall \
  /usr/local/sbin/refresh-mtproxy-config \
  /usr/local/libexec/onyx-user-backend.py

rm -rf -- \
  /var/lib/onyx-panel-update \
  /var/lib/onyx-panel-components \
  /etc/systemd/system/mtproxy.service.d \
  /etc/tproxy-server \
  /etc/mtproxy \
  /etc/onyx-panel \
  /etc/onyx-panel-xray \
  /etc/onyx-panel \
  /opt/MTProxy \
  /opt/go1.26.5 \
  /opt/onyx-panel \
  /opt/onyx-panel \
  /opt/tproxy-site \
  /srv/tproxy-site \
  /var/lib/onyx-panel \
  /var/lib/onyx-panel-xray \
  /root/tproxy-server

rm -f -- /etc/sysctl.d/90-onyx-panel-awg.conf
if [[ "$AWG_OWNED" == 1 ]]; then
  rm -f -- /usr/local/bin/amneziawg-go /usr/local/bin/awg /usr/local/bin/awg-quick
fi

# qrencode is the only Debian package installed exclusively for the panel.
if command -v apt-get >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 purge -y qrencode 2>/dev/null || true
  if [[ "$MIERU_PACKAGE_OWNED" == 1 ]]; then
    DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 purge -y mita 2>/dev/null || true
  fi
fi

if [[ "$REMOVE_CADDY" == 1 ]]; then
  rm -f -- /usr/local/bin/caddy /etc/caddy/Caddyfile /etc/systemd/system/caddy.service.d/tproxy.conf
  rmdir /etc/systemd/system/caddy.service.d 2>/dev/null || true
  rm -f -- /etc/systemd/system/caddy.service
  rm -rf -- /etc/caddy /var/lib/caddy
  id caddy >/dev/null 2>&1 && userdel caddy 2>/dev/null || true
  echo "WEB PROXY Caddy configuration removed."
elif [[ "$PRESERVE_CADDY" == 1 ]]; then
  rm -f -- /etc/systemd/system/caddy.service.d/tproxy.conf
  rmdir /etc/systemd/system/caddy.service.d 2>/dev/null || true
  systemctl daemon-reload
  if command -v caddy >/dev/null 2>&1 && caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    systemctl restart caddy.service 2>/dev/null || true
    echo "Other Caddy sites were preserved; only the Onyx Panel site block was removed."
  else
    echo "WARNING: preserved Caddy configuration requires manual validation."
  fi
else
  rm -f -- /etc/systemd/system/caddy.service.d/tproxy.conf
  rmdir /etc/systemd/system/caddy.service.d 2>/dev/null || true
  echo "Caddy was preserved because it was not marked as installed by Onyx Panel 1.3.2."
fi

id mtproxy >/dev/null 2>&1 && userdel mtproxy 2>/dev/null || true
id tproxy >/dev/null 2>&1 && userdel tproxy 2>/dev/null || true
id onyx-openflux >/dev/null 2>&1 && userdel onyx-openflux 2>/dev/null || true
[[ "$XRAY_USER_OWNED" == 1 ]] && id xray >/dev/null 2>&1 && userdel xray 2>/dev/null || true
[[ "$XRAY_GROUP_OWNED" == 1 ]] && getent group xray >/dev/null 2>&1 && groupdel xray 2>/dev/null || true

systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true
echo "Onyx Panel 1.3.2 has been removed."
