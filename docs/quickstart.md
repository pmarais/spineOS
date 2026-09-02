# Quickstart — zero to a working spine in five minutes

SpineOS runs inside the agent CLI you already subscribe to: **Claude Code, Grok CLI, Codex CLI, Cursor** — no API keys, no server, no dependencies beyond Python 3.9+. The agent is the processor; the spine is the disk and operating system.

## 1. Get the repo

```bash
git clone <this-repo> myspine && cd myspine
```

Your clone IS your spine. Your cases will live in `cases/`, your rules in `SPINE.md`. The clone's `origin` is the public product repo: you pull updates from it, but your state can never be pushed there. The moment you have a private remote (your server, a private GitHub/GitLab repo), run `python3 spine.py remote <git-url>`; the product repo stays attached as `upstream`. Until then the spine works local-only and `sync` commits locally.

## 2. Set your operator identity (once per person per machine)

```bash
echo 'export SPINE_OPERATOR=yourname' >> ~/.zshenv   # or ~/.bashrc
export SPINE_OPERATOR=yourname
```

Every write to the spine is attributed. `unattributed` writes work, but you lose the blame trail that makes collaboration safe.

## 3. Open your agent CLI and boot

Start Claude Code (or your agent CLI) in the repo and say:

> seed

(or run `/seed` in Claude Code — the skill is installed). The agent runs `python3 spine.py seed`, reads the rules, the case index and the worklist, and reports readiness. From a cold start to full working context in under a minute — every session, forever.

## 4. First case, end to end

Tell the agent, in plain language:

> New case: Acme Ltd, market-entry study. They accepted this morning: 120,000 ZAR total, deposit 40,000 already paid, delivery milestone 60,000, final 20,000. Deadline 15 September. Scope: market-entry study for their SA expansion.

The agent will run, roughly:

```bash
python3 spine.py new "Acme Ltd market entry" --note "Accepted engagement, inbound referral"
python3 spine.py promise 1 --client "Acme Ltd" --type consulting --total 120000 --currency ZAR \
    --scope "Market-entry study for SA expansion" --deadline 2026-09-15 \
    --milestone "deposit:40000:paid" --milestone "delivery:60000" --milestone "final:20000"
python3 spine.py append 1 --stage in_progress --owner yourname --paid 40000 \
    --next "Draft sections 1-2" --action WORK --note "Engagement started. Deposit bank-confirmed."
```

Close your laptop. Tomorrow, in a fresh session, say "seed" and then "what's going on with Acme?" — the new session knows everything the old one recorded, because the spine remembers for you.

## 5. Learn from the worked example

```bash
cd examples/demo_spine
python3 ../../spine.py seed
python3 ../../spine.py show 1
python3 ../../spine.py worklist
```

The demo spine holds three cases in different states — an engagement in progress, a message staged at a gate awaiting authorisation, and a raw lead — with realistic ledgers and logs to read.

## The three habits that make it work

1. **Boot every session** (`seed`). You have no memory; the spine does.
2. **Append after every substantive step.** If it only exists in the conversation, it does not exist.
3. **Gates are sacred.** Nothing irreversible executes without a recorded, single-use authorisation.
