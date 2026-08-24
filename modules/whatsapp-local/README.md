# whatsapp-local — local WhatsApp ingest (macOS, read-only)

**Experimental.** Reads the WhatsApp Desktop database on macOS into the spine. It never sends:
an outbound WhatsApp message is a gated action under SPINE.md, taken by the agent only on a
recorded, single-use authorisation.

```bash
python3 ingest.py sync        # snapshot (all 3 files) + extract (union) in one go
cp routes.example.json routes.json   # optional: chat name -> case routing
```

## The two laws (both paid for in production)

1. **Copy all three files.** WhatsApp runs SQLite in WAL mode; the newest messages live in
   `ChatStorage.sqlite-wal` until checkpointed. Copy the `.sqlite` alone and you get a file that
   opens cleanly, carries a fresh mtime, and is missing exactly the messages you came for. A stale
   snapshot is worse than a missing one: a missing file errors, a stale one answers.
2. **Union, never replace.** Extraction only ever ADDS messages (keyed ts + direction + text).
   A shallow pass can never delete what a deeper pass captured.

Caveat: some chats use linked-identity JIDs (`...@lid`) containing no phone number — this module
keys chats on partner NAME and stores the JID alongside. Never probe by phone number.
