#!/usr/bin/env bash
# One-command entry point for Onyx Panel 1.0.0.
# The complete installation package ships with every module, source archive and
# binary it needs, so no repository download is performed here.
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
          -s "$LOCAL_BASE/assets/Xray-linux-64.zip" ]]; then
        exec bash "$LOCAL_BASE/install-final.sh"
    fi
fi

die "This is not the complete Onyx Panel package. Unpack the full release archive and run ./install.sh from it."
