# router: delivery — what leaves the building, and through which gate

**Scope:** any work product going to the client, on any channel.

1. **The review surface is read-only.** Clients review a read-only proof (hosted HTML, view-only link). The editable files (DOCX, XLSX, source) are the product; they are released only on bank-confirmed full settlement.
2. **Never offer the editable files early, in any wording.** If a sentence would let a reasonable client reply "yes please", it is an offer, and an offer is a commitment.
3. **A client asking for the editable files is the FINAL-MILESTONE TRIGGER**, not a delivery request. Same-day response: stage the final invoice, point at the read-only proof for any further review, answer plainly that the files release on settlement.
4. **Every outbound delivery passes the gate:** stage → owner authorises (`AUTH_GRANT` appended) → send → verify against the channel record → `AUTH_CONSUME` appended with the verification noted.
5. **Archive what was actually sent.** The as-sent copy goes into the case folder at send time; regenerating a file later never counts as the record of what the client received.

*Exceptions (early release, partial release) are recorded in the case's PROMISE.json `exceptions[]` BEFORE anything is sent — an exception that is not recorded does not exist.*
