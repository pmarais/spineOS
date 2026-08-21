# Architecture v0.3 — modules, research dogma, roles, and the self-hosted server

*Status: §6–§7 BUILT 2026-08-17 (see [server/](../server/README.md); reconcile manual by decision). §1 partially built (doctor --env). §2 ingest, §4 research dogma, §5 policies scaffold: designed, not yet built.*

The target deployment stays deliberately small: **one box with git and ssh is the entire server requirement.** Everything below runs on a bare git instance plus hooks and cron. No database server, no queue, no web app on the critical path. Any subscription agent CLI (Claude Code, Grok CLI, Copilot CLI, Codex) is a full client, because the interfaces are files, a CLI and AGENTS.md.

---

## 1. Pinned environments (the boring foundation everything sits on)

One environment, pinned, everywhere — per repo, enforced, never advisory:

- `.python-version` (3.13) + `requirements.txt` frozen against it; local `venv/` built from exactly that pair.
- `.nvmrc` (Node 22 LTS) + `package.json` with pinned versions + lockfile, for the document skills.
- **`spine doctor --env`**: checks interpreter versions, venv integrity, requirements satisfaction, node_modules presence, and treats a version mismatch as **BLOCKING**, not a warning. Production origin: a 3.9 venv under a 3.13 shell silently broke four cron steps; a second machine had the whole render stack missing. The doctor is the only thing that catches drift on a machine you have not used today.

## 2. Ingest modules (`modules/`) — channels become facts on the spine

Every module follows the same contract, learned the hard way:

> **Sync first, full fidelity, union always, route to cases, never act from a stale snapshot.** A sync window controls what we LOOK at, never what we KEEP. Feeds are facts; messages are claims.

```
modules/
├── email-imap/      # any IMAP host (privateemail.com, Gmail, self-hosted)
├── whatsapp-local/  # macOS WhatsApp ChatStorage (snapshot + WAL discipline)
├── api/             # generic pull adapters: banking, market data, webhooks-by-poll
└── docs-node/       # document skills (§3) — an output module, same registry
```

**email-imap.** Config: host, mailboxes, credentials via env/keychain (never in the repo). Behaviour baked in from scars: store **full bodies** (a request hidden past a preview cut went unanswered 27 days), sync a window but **merge as a union** into `channels/email/threads.jsonl`, route to cases via an address map that supports **multiple addresses per case** (the second-address routing gap), and land unroutable mail in an `unrouted` log that `doctor` surfaces — silence is never "no mail".

**whatsapp-local.** Reads the local WhatsApp database on macOS. Hard rules from production: copy **all three files** (`.sqlite`, `-wal`, `-shm`) — the WAL holds precisely the newest messages; compare snapshot mtime against the live DB before any read; unions into per-case `messages.jsonl`. Sending stays out of the module entirely: sends are gated actions under SPINE.md, one authorisation each.

**api.** A generic adapter: a fetcher script per source (bank feed, Bloomberg-class market data, an internal system), a schedule, and a **recon rule** declaring what the feed is authoritative FOR (payments, prices, filings). Fetched records land append-only under `channels/api/<source>/`; recon reconciles claims on the spine against them and appends findings. This is the institution-specific recon process from the enterprise story, as a plain module.

All ingest is **cron-driven and report-only**: modules collect and route; they never send, never commit-and-push on their own (the sync pipeline owns transport), and a broken ingest is a P1 doctor flag because everything downstream silently degrades while it is broken.

## 3. Document skills (`modules/docs-node/`) — the translate layer

Node 22, three libraries, one rule:

| Skill | Library | Reads | Writes |
|---|---|---|---|
| DOCX | `docx` (docx-js) | via unpack/inspect | build from markdown; tracked-changes redlines computed from source diffs |
| PPTX | `pptxgenjs` | — | decks as projections of approved markdown |
| XLSX | `exceljs` | full read: sheets, formulas, formats | governed writes with provenance sheet |

The rule is the Central Dogma's: **rendered files are build artifacts.** You never hand-edit an output; you edit the source and re-render. "Accept All Changes" on a redline must equal the clean render of the new source. Team spreadsheets that join the workspace are read and interpreted through the XLSX skill and sense-checked against the spine before any number from them is trusted.

## 4. The research dogma (generic Central Dogma for numbers, stats, analysis)

Generalised from a medical-research pipeline that survived real supervisors, statisticians and disputes:

```
DATA (immutable)  →  ANALYSIS (pinned Python)  →  NUMBERS LEDGER  →  PROSE  →  RENDERS
data/ inputs,        scripts in analysis/,        numbers.jsonl:     cites     DOCX/PPTX/
verbatim, never      pandas/scipy/matplotlib,     key · value ·      numbers   HTML via §3,
edited               deterministic, re-runnable   script · inputs-   by KEY    never typed
                                                  hash · ts
```

The load-bearing invention is the **numbers ledger**: every analysis run appends its computed quantities (`{"key":"mortality_over40","value":0.82,"script":"analysis/03_outcomes.py","inputs":"sha256:…"}`). Prose references `{{num:mortality_over40}}`; the renderer substitutes; a lint **fails the build on any number in prose that is not in the ledger**. Consequences: no transcribed figures, no orphaned numbers, every published quantity re-derivable to a script and an input hash. Third-party analyses are *reproduced against our data and concordance-counted*, never transcribed — reproduction is evidence; what will not reconcile is a finding.

Supporting rules: sample sizes shown as calculations; effect size with every p-value; honest non-significant results stay in; verification cascade on references (nothing cited from model memory).

## 5. Policies and procedures — the platform IS the spine

No separate policy product. Policies live where the agents already boot:

```
SPINE.md        the constitution: invariants with origins (admin-owned)
routers/        procedures: one process per task type (business-manager-owned)
policies/       formal policy documents (leave, POPIA/GDPR, security, comms) — markdown sources
```

What makes it a "platform" rather than a folder: policies are **versioned** (git history is the policy register), **delivered at boot** (every seed carries current rules — update once, every next session inherits), **enforced at write time** (§6 makes policy paths writable only by the roles that own them), **auditable** (who changed which policy when, structurally), and **renderable** (the staff handbook is a projection built by §3, never hand-maintained). The deploy runbook itself is a router — which is how "do a deploy using Claude, Grok or Copilot" works: the agent reads `routers/deploy.md` and executes it under the gates; the runbook, not the vendor, carries the knowledge.

## 6. Branches and roles — the reversal, argued honestly

**Production history first:** the firm this system comes from considered per-person branches and REJECTED them — work on other branches was invisible until someone merged, nobody merges reliably mid-day, the worklist fragmented per-person, and two operators each believing they held current state could double-act toward a client. That rejection was correct **for ordinary git semantics**.

**The v0.2 data model changes the calculus.** Once ledgers are union-merged CRDTs (sync-design §3), merging member branches is *mechanical* — no conflicts, no judgement, no human in the loop. So the old costs collapse, and branches start buying something new: **git-level permission enforcement**, which a shared branch can never give you. The design:

```
refs/heads/main                ← protected: no client pushes directly; the reconciler writes it
refs/heads/member/<name>       ← each member (human or agent identity) pushes ONLY here
```

- **Push rights enforced server-side** (git `update` hook): a key may push only to its own `member/<name>` ref. Main is untouchable by clients; force-push and deletion refused repo-wide (append-only remote, sync-design §7).
- **The reconciler** (DECIDED 2026-08-17: **MANUAL** — an admin runs `spine reconcile`; cron/hook automation is a later opt-in): octopus-merges all member branches into `main` — unions cannot conflict; a prose conflict parks THAT file's integration and flags doctor, touching nothing else. Members' `spine sync` pulls `main`, so everyone reads the reconciled whole after each admin reconcile. **Functionally this is the shared branch — same one-truth, same worklist — with attribution, isolation of the unreviewed instant, and enforceable permissions added.** The double-act risk returns only in the sub-minute window, which the same-case awareness note (sync-design §10.2) covers.
- **Path-level RBAC in the same update hook**: a push is rejected if the diff touches paths the member's role does not own. This is real enforcement on a bare git box — no platform, no web app.

**The roles** (stored in `ROLES.json`, admin-owned, itself path-protected):

| Role | Owns (writable paths) | Gates they may authorise |
|---|---|---|
| **admin** (principal) | everything, incl. `SPINE.md`, `ROLES.json`, `policies/` | all, incl. money and early release |
| **it-admin** | server config, `modules/` code, envs, keys, backups | deploys, infra changes; **no client-facing or money gates** |
| **business-manager** | `routers/`, `policies/` drafts, all `cases/` | case-level gates (sends, deliveries) per SPINE.md; money gates only if admin delegates |
| **member / operator** | `cases/` they own or act on | none by default; owner-granted per case |
| **agent:<member>** | as its member, minus ALL gate authorisation | none, ever — agents request, humans grant |

The CLI reads ROLES.json for advisory refusal (fail fast, good message); the server hook is the enforcement; `doctor` audits divergence between the two. Separation of duties falls out naturally: it-admin can rebuild the server but cannot authorise a client send; a business manager can run every engagement but cannot rewrite the constitution.

## 7. The server kit (`spine server init`) — self-hosting in one command

Target: any Linux box (a R100/month VPS) or an on-prem machine. The kit installs, idempotently:

1. A `git` user with `git-shell` (serves git, nothing else), per-member authorized keys with forced command.
2. The bare spine repo with `receive.denyNonFastForwards` + `denyDeletes`.
3. The `update` hook: branch ownership + path RBAC (§6).
4. The daily `git bundle` snapshot rotation (sync-design §7). Reconciliation stays a manual admin verb (§6).
5. Optional ingest crons (§2) if the box also runs collectors.

This is the same pattern our production firm runs today (own git server, JNB, data-resident) — proven, boring, and sovereign: the enterprise data-residency story is "your spine on your box in your jurisdiction", and this kit is that story as a script.

## 8. What deliberately stays OUT (critical scope control)

- **No web platform for policies or admin.** The spine + projections + RBAC already are the platform; a web UI is Spine Cloud's job later, not the open core's.
- **No webhook/push ingestion.** Poll-based collectors keep the "one box, git + ssh" promise; webhooks need a public endpoint and re-open the infra question.
- **No per-file encryption/secrets in the repo.** Credentials stay in env/keychain; the repo carries config, never secrets.
- **No LLM API dependencies anywhere.** Modules and skills are deterministic code; the intelligence remains the operator's subscription CLI.

## 9. Order of construction

| Phase | Contents | Depends on |
|---|---|---|
| 1 | sync v0.2 (the [sync-design](sync-design.md) plan, incl. line ids + manifests) | — |
| 2 | env pinning + `doctor --env`; `modules/docs-node` (docx/pptx/xlsx) | 1 |
| 3 | server kit: member branches, update hook RBAC, reconciler, bundles | 1 |
| 4 | ingest modules: email-imap → api → whatsapp-local (hardest last) | 1–3 |
| 5 | research dogma: numbers ledger + prose lint + analysis scaffold | 2 |
| 6 | policies scaffold + handbook projection; deploy router exemplar | 2–3 |

Rationale for the order: transport correctness first (everything writes through it), then the cheap high-leverage layers (envs, documents), then the server that makes roles real, then collectors that feed it, then the research and policy layers that ride on all of it.
