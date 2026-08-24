# email-imap — IMAP ingest for a spine

Stdlib only. Works with any IMAP host: privateemail.com, Gmail (app password), self-hosted.

```bash
cp config.example.json config.json          # edit accounts; password via env, NEVER in the repo
cp routes.example.json routes.json          # address -> case map
export SPINE_IMAP_MAIN='...'                # the password env named in config
python3 ingest.py --days 7
```

## The laws this module enforces (each from a production incident)

1. **Full bodies, always.** A second request hidden past a preview cut once went unanswered for 27 days. `body` is complete; any preview is display-only.
2. **Union, never replace.** `--days` controls what we LOOK at, never what we KEEP. Messages are keyed `account/mailbox/uid` and only ever added to `channels/email/threads.jsonl`.
3. **Many addresses per case.** A client's work address once routed nowhere for 30 of her 33 sends. Add every address; routing matches from/to/cc.
4. **Unrouted mail is loud.** Anything unmatched lands in `channels/email/unrouted.jsonl`. An unrouted message is a waiting client, not noise.
5. **Partial failure is visible.** A failed account does not stamp freshness for a window it did not cover, and the run exits non-zero.
6. **Report-only.** Never sends, never commits. Share with `python3 spine.py sync`. Replies are drafted by the agent and pass the SPINE.md gate like every outbound action.

Routed mail lands per case in `cases/<case>/EMAIL.jsonl` — read it before writing any wait (`blocked_on: them`): the request that flips the wait is usually sitting there.
