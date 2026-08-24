# router: deploy — how ANY agent ships this organisation's software

**Scope:** every deployment, executed by whichever agent CLI the operator runs (Claude, Grok,
Copilot, Codex). The runbook carries the knowledge; the vendor does not matter.

1. **Read this file fully before starting.** If the target or steps here disagree with your
   instinct, this file wins (Prime Rule).
2. **Build first, locally.** Run the project's build and its tests. A red test stops the deploy;
   report and await instruction. Never deploy around a failure.
3. **Deployment is a GATED action** (it changes what the outside world sees). Stage: state exactly
   what will ship, where, and how it rolls back. Execute only on a recorded, single-use
   authorisation (`AUTH_GRANT`), consumed by this one deploy.
4. **Execute the project's deploy script** — never an improvised command sequence. If no script
   exists, that is a finding: write one, get it reviewed, then deploy with it.
5. **Verify against the live surface** (the deployed URL, the running service), not the script's
   exit code. Record what you checked.
6. **Append the outcome** to the relevant case: what shipped, verification, rollback point
   (`--action DEPLOY`). If it went wrong: what, why, and the invariant to add to SPINE.md.

*Adapt the specifics per project (targets, scripts, checks) by editing THIS file — the next agent
inherits your corrections at boot.*
