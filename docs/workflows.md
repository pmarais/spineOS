# Example workflows — what a day on the spine looks like

Five worked patterns. In each, "you" is the human operator and the agent does the typing. Everything the agent runs is shown so you (or another LLM reading this) can reproduce it exactly.

---

## 1. The daily sit-down

You: **"seed, then what should I work on?"**

```bash
python3 spine.py seed          # rules + index + ranked worklist
```

The worklist is the scheduler: P1 = deadline pressure or blocked on us, P2 = money due, P3 = the rest. You pick a case (or accept the top one); the agent loads it (`show`), works it, appends, and reports in SITREP. Nobody opens a raw inbox; nobody asks "where were we?".

---

## 2. New engagement (lead → promise → work)

You: **"New lead: Dr Naidoo, thesis support, referred by Acme. She's emailed her draft."**

```bash
python3 spine.py new "Naidoo thesis support" --note "Inbound referral from Acme. Draft received by email."
```

Discovery happens in conversation. When the deal is accepted:

You: **"She accepted option B: 45,000 ZAR, deposit 15k, delivery 20k, final 10k, deadline end of October."**

```bash
python3 spine.py promise naidoo --client "Dr A Naidoo" --type thesis --total 45000 --currency ZAR \
  --deadline 2026-10-31 --scope "Thesis support per option B" \
  --milestone "deposit:15000" --milestone "delivery:20000" --milestone "final:10000"
python3 spine.py append naidoo --stage agreed --owner you \
  --asks-them "deposit payment" --next "Start on deposit confirmation" \
  --action STATUS --note "Option B accepted by email 09:40. Awaiting deposit before work starts (house rule)."
```

The promise is now the standing answer to "what did we sell?" — every later update reasons against it.

---

## 3. The gate (sending anything to an outside party)

The agent drafts a delivery email. It does NOT send. It shows you the draft and waits.

You: **"Send it."**

```bash
python3 spine.py append naidoo --action AUTH_GRANT \
  --note "Operator authorised: send delivery email v1 to client (draft as shown 14:02)"
# agent sends via whatever channel tool exists
python3 spine.py append naidoo --action AUTH_CONSUME --asks-them "review feedback" \
  --next "Await her review; nudge Friday if silent" \
  --note "Delivery email sent 14:04, confirmed in Sent folder. Authorisation consumed."
```

Five minutes later the agent wants to send a follow-up. **It must ask again.** One authorisation, one action. This single habit prevents the double-send class of incident entirely.

---

## 4. Handover between operators

You: **"Hand Naidoo over to Sam."**

```bash
python3 spine.py show naidoo            # the agent reads the full position first
python3 spine.py append naidoo --owner sam --action HANDOVER \
  --note "Handover to Sam. Position: delivery draft v2 with client for review since 14 Oct; deposit and delivery milestones paid (35,000/45,000); final 10,000 gates the editable files. Watch: she asked twice about referencing style — answered 12 Oct, style file in case folder. Next: her review feedback, then final invoice."
```

The note IS the handover brief. Sam's next session seeds, sees `owner sam` on the worklist, and reads a complete position without a meeting.

---

## 5. Incident → invariant (how the spine learns)

Something goes wrong: a message was sent twice because a hung script looked failed.

1. Record the incident on the case (`append --note` with the full story).
2. **Add the rule to SPINE.md §8, with the origin:**

> **N. A hanging send has usually already sent.** Verify against the channel record before concluding failure; never re-fire on the old authorisation. *(Origin: case 0007, 2026-11-03 — a hung script delivered successfully; the retry double-sent the client.)*

3. Commit. Every future session, forever, boots with that rule loaded.

This is the compounding loop: the organisation's judgement accumulates in a file that every agent reads before touching anything.

---

## Multi-operator note

Run the spine as a shared git repo (each operator clones; pull before sessions, push after — or use any shared filesystem). Append-only files merge trivially: order is irrelevant because reads fold by timestamp. Set `merge=union` for `*.jsonl` and `*.csv` in `.gitattributes` (already configured in this repo) and two operators can append concurrently without conflicts.
