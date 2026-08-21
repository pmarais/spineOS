#!/usr/bin/env bash
# Daily snapshot bundle of the spine repo. Keep the last 14.
#   spine-bundle <bare-repo> <backup-dir>
set -euo pipefail
BARE="${1:?bare repo path}"
DEST="${2:?backup dir}"
mkdir -p "$DEST"
NAME="$(basename "$BARE" .git)-$(date +%Y%m%d).bundle"
git -C "$BARE" bundle create "$DEST/$NAME" --all 2>/dev/null
ls -1t "$DEST"/*.bundle 2>/dev/null | tail -n +15 | xargs -r rm --
