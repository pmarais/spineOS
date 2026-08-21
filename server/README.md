# server/ — the SpineOS server kit

Self-host a governed, append-only spine server on **any box with git, python3 and ssh** — a small
VPS or an on-prem machine. No database, no web app, no daemon beyond sshd and one backup cron.

## Install (once, ~2 minutes)

```bash
scp -r server/ you@yourbox:
ssh you@yourbox 'cd server && sudo ./init.sh spine'
```

What that sets up, idempotently:

| Piece | What it does |
|---|---|
| `spine` user (git-shell) | serves git and nothing else; no interactive login |
| bare repo `~spine/spine.git` | `receive.denyNonFastForwards` + `denyDeletes`: **history can only grow, no client can rewrite it** |
| `hooks/update` (python3) | branch ownership + path RBAC per push (below) |
| `bin/spine-shell` | forced command that stamps each SSH key with its member identity |
| daily `spine-bundle` cron | full-repo bundle at 03:10, last 14 kept — recovery exists even if the repo is damaged. **Backups are the only automation; reconcile stays manual** |

## Members and roles

```bash
sudo ./add-member.sh alice ~/alice.pub      # installs the key, bound to identity 'alice'
```

Permissions come from **`ROLES.json` at the spine root** (start from `ROLES.json.example`), and the
hook reads it **from the accepted `main` branch only** — an incoming push can never grant itself
permissions. Roles: `admin` (everything, and the only role that may push `main` — the manual
reconcile), `it-admin` (modules, server config, environments; **no cases, no client-facing gates**),
`business-manager` (cases, routers, policies), `member` (cases only). Agents get their own identities
(`agent-carol`) with member paths and, per SPINE.md, never any gate authorisation.

**Enforced per push by the update hook:** members push only `refs/heads/member/<their-name>`;
`main` is admin-only; `snap/*` tags are open, other tags admin-only; deletions and history rewrites
are refused for everyone; and a push touching paths outside the member's role is refused with the
violating paths named.

## Bootstrap (do this immediately after init)

The **first** push to `main` is accepted openly and must carry `ROLES.json` — from then on it
governs. From the admin's clone:

```bash
cp server/ROLES.json.example ROLES.json   # edit members
git remote add origin spine@yourbox:spine.git
python3 spine.py sync                     # first push → main, carrying ROLES.json
```

Members then: `git clone spine@yourbox:spine.git`, set `branch_mode: "member"` in `.spineos.json`
(or keep `shared` for a small trusted team on one branch). In member mode everyone pushes their own
branch and pulls `main`; **an admin advances `main` manually with `python3 spine.py reconcile`**.

## Recovery

Bundles restore everything: `git clone ~spine/backups/spine-YYYYMMDD.bundle restored`. Client-side,
every write also exists in each machine's local journal (`spine.py recover`). Between the two, loss
requires losing the server, every clone, and every journal in the same incident.
