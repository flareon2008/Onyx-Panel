#!/usr/bin/env bash
# Publish an Onyx Panel release.
#
# The panel updates itself from the latest v[0-9]* tag of this repository, so a
# release is: an annotated tag + a GitHub Release describing the changes.
#
# Usage:
#   ./release.sh v1.2.0 -m "первая строка описания
# вторая строка"
#   ./release.sh v1.2.0 -f NOTES.md
#   ./release.sh v1.2.0                 # description built from commits only
#   ./release.sh v1.2.0 --dry-run       # everything except push and API call
#
# GITHUB_TOKEN (or GH_TOKEN, or `gh auth token`) is needed to create the
# GitHub Release. Without a token the tag is still pushed and the script
# prints the manual release URL. Pushing uses your existing git credentials.
set -Eeuo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }
usage() { sed -n '2,17p' "$0"; exit 0; }

TAG=""
NOTES=""
NOTES_FILE=""
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--message) NOTES="${2:-}"; shift 2 ;;
        -f|--file)    NOTES_FILE="${2:-}"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        -h|--help)    usage ;;
        -*)           die "Unknown option: $1 (see --help)" ;;
        *)            TAG="$1"; shift ;;
    esac
done
[[ -n "$TAG" ]] || { usage; }

[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]] ||
    die "Tag must look like v1.2.0 (optional -beta.1 suffix), got: $TAG"

command -v git >/dev/null 2>&1 || die "git is required."
BASE="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Run this script from inside the Onyx Panel repository."
cd "$BASE"

BRANCH="$(git symbolic-ref --short -q HEAD)" || die "Detach from HEAD checkout: switch to a branch first (git switch main)."
ORIGIN_URL="$(git remote get-url origin 2>/dev/null)" || die "No 'origin' remote configured."

if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    die "Working tree is not clean. Commit the changes first, then release."
fi

# Latest tag known on the remote; keep working when offline.
if git fetch --tags origin >/dev/null 2>&1; then
    echo "Fetched tags from origin."
else
    echo "WARNING: could not fetch tags from origin; using local tags only." >&2
fi

TAG_ON_REMOTE=0
if [[ -n "$(git ls-remote --tags --refs origin "$TAG" 2>/dev/null)" ]]; then
    TAG_ON_REMOTE=1
    echo "Tag $TAG is already on the remote; the release will be (re)published for it."
fi
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    [[ "$TAG_ON_REMOTE" == 1 ]] || die "Tag $TAG already exists locally but is not pushed. Remove it (git tag -d $TAG) or push it first."
fi

PREV="$(git tag -l 'v[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$' | grep -vx "$TAG" | sort -V | tail -n1 || true)"
RANGE=""
if [[ -n "$PREV" ]]; then
    RANGE="${PREV}..HEAD"
else
    RANGE="HEAD"
fi
COMMITS="$(git log --no-decorate --format='- %s (%h)' $RANGE 2>/dev/null || true)"

NOTES_TMP=$(mktemp "${TMPDIR:-/tmp}/onyx-release-notes.XXXXXX.md")
trap 'rm -f "$NOTES_TMP"' EXIT
if [[ -n "$NOTES_FILE" ]]; then
    [[ -s "$NOTES_FILE" ]] || die "Notes file is empty or missing: $NOTES_FILE"
    cat "$NOTES_FILE" > "$NOTES_TMP"
elif [[ -n "$NOTES" ]]; then
    printf '%s\n' "$NOTES" > "$NOTES_TMP"
elif [[ -t 0 && -n "${EDITOR:-}" ]]; then
    {
        echo "# Опишите изменения релиза $TAG. Строки с # удаляются автоматически."
        echo
        [[ -n "$COMMITS" ]] && { echo "$COMMITS"; echo; }
    } > "$NOTES_TMP"
    "$EDITOR" "$NOTES_TMP"
fi
# Drop comment lines and trailing blank lines.
grep -v '^[[:space:]]*#' "$NOTES_TMP" > "$NOTES_TMP.clean" || true
mv "$NOTES_TMP.clean" "$NOTES_TMP"
NOTES_FINAL="$(cat "$NOTES_TMP")"
if [[ -n "$COMMITS" ]]; then
    [[ -n "$(tr -d '[:space:]' < "$NOTES_TMP")" ]] && printf '\n## Изменения\n\n' >> "$NOTES_TMP"
    printf '%s\n' "$COMMITS" >> "$NOTES_TMP"
    NOTES_FINAL="$(cat "$NOTES_TMP")"
fi
[[ -n "$(tr -d '[:space:]' <<< "$NOTES_FINAL")" ]] ||
    die "Release notes are empty. Pass -m \"...\", -f file, or run from a terminal with \$EDITOR set."

echo "----- release notes -----"
cat "$NOTES_TMP"
echo "-------------------------"

if [[ "$TAG_ON_REMOTE" != 1 ]]; then
    git tag -a "$TAG" -m "Release Onyx Panel ${TAG#v}"
    echo "Tag $TAG created."
fi

if [[ "$DRY_RUN" == 1 ]]; then
    echo "DRY RUN: skipped git push and the GitHub Release API call."
    exit 0
fi

echo "Pushing $BRANCH and $TAG to origin..."
git push origin "$BRANCH"
[[ "$TAG_ON_REMOTE" == 1 ]] || git push origin "refs/tags/$TAG"

SLUG="$(printf '%s' "$ORIGIN_URL" | sed -n -E 's#.*github\.com[:/]+([^/]+/[^/.]+)(\.git)?#\1#p')"
if [[ -z "$SLUG" ]]; then
    echo "Origin is not GitHub ($ORIGIN_URL); the tag is pushed — create the release in your Git host UI."
    exit 0
fi

TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [[ -z "$TOKEN" ]] && command -v gh >/dev/null 2>&1; then
    TOKEN="$(gh auth token 2>/dev/null || true)"
fi

API="https://api.github.com"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json")
if [[ -z "$TOKEN" ]]; then
    echo "No GITHUB_TOKEN found. The tag is pushed; publish the release manually:"
    echo "  https://github.com/$SLUG/releases/new?tag=$TAG"
    exit 0
fi

json_escape() {
    local s="$1"
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\r'/'\r'}
    s=${s//$'\n'/'\n'}
    s=${s//$'\t'/'\t'}
    printf '%s' "$s"
}
NAME="Onyx Panel ${TAG#v}"
PRERELEASE="false"
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || PRERELEASE="true"
BODY_JSON=$(printf '{"tag_name":"%s","name":"%s","body":"%s","prerelease":%s}' \
    "$(json_escape "$TAG")" "$(json_escape "$NAME")" "$(json_escape "$NOTES_FINAL")" "$PRERELEASE")

RELEASE_ID="$(curl -fsS --proto '=https' "${AUTH[@]}" "$API/repos/$SLUG/releases/tags/$TAG" 2>/dev/null |
    sed -n 's/.*"id":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1 || true)"
if [[ -n "$RELEASE_ID" ]]; then
    HTTP=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' "${AUTH[@]}" -X PATCH \
        -H "Content-Type: application/json" -d "$BODY_JSON" "$API/repos/$SLUG/releases/$RELEASE_ID")
    [[ "$HTTP" == 200 ]] || die "GitHub API returned $HTTP while updating the release."
    echo "Existing release for $TAG updated."
else
    HTTP=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' "${AUTH[@]}" -X POST \
        -H "Content-Type: application/json" -d "$BODY_JSON" "$API/repos/$SLUG/releases")
    [[ "$HTTP" == 201 || "$HTTP" == 200 ]] || die "GitHub API returned $HTTP while creating the release. Check the token scopes (repo / Contents: read & write)."
fi

echo
echo "Release published: https://github.com/$SLUG/releases/tag/$TAG"
echo "Servers pick it up with: onyx-panel-update"
