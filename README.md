# SpineOS

**LLMs are the processor. Chat is RAM. SpineOS is the disk, and the operating system.**

Durable, append-only operational state for humans and AI working together: what you promised, where every case stands, who did what, and the rules of execution. It survives every session, every operator, and every model swap.

**Status: pre-release.** This repository is the future open-source home of the SpineOS spec and CLI. Nothing here is published yet.

## The five primitives

| Primitive | What it holds |
|---|---|
| `PROMISE` | The commitment, snapshotted at acceptance. Immutable until the deal itself changes |
| `LEDGER` | Append-only position record. Current state is folded: latest value per field wins, by timestamp |
| `LOG` | Append-only action record: what was done, by whom, when |
| `RULES` | The OS as a document the model reads at boot. Invariants carry the incident that created them |
| `PROJECTIONS` | Worklists, banners, briefs. Always computed, never authored |

Plus **GATES**: irreversible actions default to stage-for-review; an authorisation is consumed by the action it authorises.

## Planned layout and CLI

See [BLUEPRINT.md](BLUEPRINT.md) for the full repo blueprint: package layout, the verbs (`seed · new · promise · append · show · fold · worklist · doctor · sitrep · export · import`), backends (plain files, then SQLite), the SITREP operator-report protocol, adapters (Claude Code, Cursor, MCP), and conformance levels.

## Provenance

Extracted from a production operations spine that has run a real professional-services firm since July 2026: two operators, concurrent AI agents on multiple machines, real client commitments executed under gates, attribution and audit.

## Licence

Apache-2.0 (intended; to be confirmed at first public release).

---

Website: [spineos.dev](https://spineos.dev) · Internal concept package: `39_mmedghostlab/products/spine/`
