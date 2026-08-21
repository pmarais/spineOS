# Copilot instructions — this repository is a SpineOS spine

Read `AGENTS.md` and follow it exactly. Boot every session with `python3 spine.py seed` and obey the
printed rules (SPINE.md). Core contract: load one case before acting (`show`), append after every
substantive step (`append`), never edit ledger/log history, irreversible actions require a recorded
single-use authorisation (AUTH_GRANT → act → AUTH_CONSUME), report only in SITREP format, and share
work with `python3 spine.py sync` (commits only the files this session touched).
