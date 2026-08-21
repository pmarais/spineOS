#!/usr/bin/env bash
# Add a member's SSH key, bound to their identity via spine-shell.
#   sudo ./add-member.sh <name> <pubkey-file>
# Then an ADMIN adds them to ROLES.json in the spine and pushes (that push is
# what grants permissions — this script only installs the key).
set -euo pipefail
NAME="${1:?usage: add-member.sh <name> <pubkey-file>}"
KEYFILE="${2:?usage: add-member.sh <name> <pubkey-file>}"
[[ "$NAME" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "name must be [A-Za-z0-9_.-]+"; exit 1; }
KEY="$(grep -m1 -E '^(ssh|ecdsa)-' "$KEYFILE")" || { echo "no SSH public key in $KEYFILE"; exit 1; }
AK="/home/spine/.ssh/authorized_keys"
if grep -qF "$KEY" "$AK" 2>/dev/null; then echo "key already installed"; exit 0; fi
OPTS='command="/home/spine/bin/spine-shell '"$NAME"'",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty'
echo "$OPTS $KEY" >> "$AK"
chown spine:spine "$AK"; chmod 600 "$AK"
echo "✓ key installed for member '$NAME'"
echo "  remaining step (an ADMIN, in the spine): add \"$NAME\" to ROLES.json members and sync/reconcile."
