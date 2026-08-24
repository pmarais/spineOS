# api — external feeds as append-only facts

Generic pull adapter for anything with an HTTP endpoint: a bank feed, Bloomberg-class market data,
an internal system, a public dataset. Stdlib only.

```bash
cp sources.example.json sources.json     # edit; tokens via env (auth_env), never in the repo
python3 fetch.py                         # or --source bank-feed
```

Each fetch lands in `channels/api/<source>/records.jsonl` with a timestamp and a content hash —
**append-only, deduplicated by hash**, so identical re-fetches add nothing and history is never
rewritten. Schedule it with cron if you want it regular; it is report-only either way (`spine.py
sync` owns transport, and this module never acts on what it fetches).

## The recon pattern

Every source declares `authoritative_for` — the class of claim it settles. The rule it serves is
SPINE.md §5: **feeds are facts; messages are claims.** A client says they paid → the bank-feed
records decide. A spreadsheet asserts a price → the market-feed records decide. When the agent
reconciles a claim, it reads the records, appends the finding to the case ledger, and names which
source settled it. Discrepancies are appended as findings, never silently adopted or dropped.
