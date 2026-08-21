#!/usr/bin/env bash
# SpineOS server kit — idempotent setup of a spine git server on any Linux box.
#   sudo ./init.sh [repo-name]          (default: spine)
# Installs: the 'spine' user (git-shell), a bare append-only repo, the RBAC
# update hook, spine-shell, and the daily bundle backup cron.
# Requirements: git, python3, a POSIX system. Nothing else.
set -euo pipefail

REPO="${1:-spine}"
HOME_DIR="/home/spine"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo ./init.sh"; exit 1; }
command -v git >/dev/null || { echo "git is required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required (the update hook)"; exit 1; }

# 1. the spine user, serving git and nothing else
if ! id spine >/dev/null 2>&1; then
  useradd --create-home --home-dir "$HOME_DIR" --shell "$(command -v git-shell)" spine
  echo "✓ user 'spine' created (shell: git-shell)"
fi
mkdir -p "$HOME_DIR/.ssh" "$HOME_DIR/bin" "$HOME_DIR/backups"
touch "$HOME_DIR/.ssh/authorized_keys"
chmod 700 "$HOME_DIR/.ssh"; chmod 600 "$HOME_DIR/.ssh/authorized_keys"

# 2. spine-shell (member identity via forced command)
install -m 755 "$KIT_DIR/bin/spine-shell" "$HOME_DIR/bin/spine-shell"

# 3. the bare repo, append-only
BARE="$HOME_DIR/$REPO.git"
if [ ! -d "$BARE" ]; then
  sudo -u spine git init --bare -b main "$BARE" >/dev/null
  echo "✓ bare repo $BARE (default branch: main)"
fi
sudo -u spine git -C "$BARE" config receive.denyNonFastForwards true
sudo -u spine git -C "$BARE" config receive.denyDeletes true

# 4. the RBAC update hook
install -m 755 "$KIT_DIR/hooks/update" "$BARE/hooks/update"
echo "✓ update hook installed (branch ownership + path RBAC; roles read from main:ROLES.json)"

# 5. daily bundle backups (03:10, keep 14) — backups are automated; RECONCILE IS NOT
install -m 755 "$KIT_DIR/bundle.sh" "$HOME_DIR/bin/spine-bundle"
CRON_LINE="10 3 * * * $HOME_DIR/bin/spine-bundle $BARE $HOME_DIR/backups"
( crontab -u spine -l 2>/dev/null | grep -vF "spine-bundle" ; echo "$CRON_LINE" ) | crontab -u spine -
echo "✓ daily bundle cron installed"

chown -R spine:spine "$HOME_DIR"

cat <<EOF

Done. Next steps:
  1. Add members:      sudo ./add-member.sh <name> <pubkey-file>
  2. First push (BOOTSTRAP — do this immediately): from the admin's clone,
     make sure ROLES.json exists at the spine root, then:
       git remote add origin spine@<this-host>:$REPO.git
       python3 spine.py sync        # or: git push origin main
     The FIRST push to main is accepted openly and must carry ROLES.json;
     every push after that is governed by it.
  3. Members clone:    git clone spine@<this-host>:$REPO.git
     (member branch mode: python3 spine.py init --branch-mode member, or set
      branch_mode in .spineos.json; members push member/<name>, pull main)
  4. Reconcile is MANUAL: an admin runs 'python3 spine.py reconcile' when they
     choose. Nothing on this server advances main on its own.
EOF
