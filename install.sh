#!/usr/bin/env bash
# One-command entry point for Onyx Panel.
# The panel modules (AmneziaWG binaries, OpenFlux) ship with the package; Xray,
# Caddy, Go, AmneziaWG tools and the relay source are downloaded from their
# official repositories during installation.
set -Eeuo pipefail
umask 077

die() { echo "ERROR: $*" >&2; exit 1; }
[[ ${EUID:-1} -eq 0 ]] || die "Run this command with sudo or as root."

# When launched from the complete package directory, run the real installer.
# With `bash -c "$(curl ...)"` there is no script file; never trust unrelated
# files from the caller's current directory in that mode.
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_SOURCE" && -f "$SCRIPT_SOURCE" ]]; then
    LOCAL_BASE="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    if [[ -s "$LOCAL_BASE/install-final.sh" && -s "$LOCAL_BASE/onyx_subscriptions.py" &&
          -s "$LOCAL_BASE/assets/OpenFlux-linux-amd64" &&
          -s "$LOCAL_BASE/assets/amneziawg-go-linux-amd64" &&
          -s "$LOCAL_BASE/assets/awg-linux-amd64" &&
          -s "$LOCAL_BASE/assets/awg-quick-linux-amd64" ]]; then
        exec bash "$LOCAL_BASE/install-final.sh"
    fi
fi

die "This is not the complete Onyx Panel package. Unpack the full release archive (or clone the release tag) and run ./install.sh from it."
