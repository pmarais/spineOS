# policies/ — formal policies, governed like everything else

The policy "platform" is the spine itself (docs/architecture-v03.md §5). What makes these files a
register rather than a folder:

- **Versioned**: git history is the policy register — who changed what, when, structurally.
- **Delivered at boot**: SPINE.md §9 points every session here; an agent acting in a policy's area
  reads the policy first (Prime Rule: use the registered process, never invent one).
- **Enforced at write time**: with the server kit, policy paths are writable only by the roles that
  own them (`business-manager` drafts, `admin` lands) — a member cannot quietly edit the leave policy.
- **Rendered, never hand-maintained**: the staff handbook is a projection — concatenate + render via
  `modules/docs-node/examples/md-to-docx.mjs`; regenerate on change, never patch the DOCX.

Start from the examples: copy `*.example.md` → the real name, edit, sync. One policy per file,
short, in controlled language: one idea per sentence; the reader may be skimming.
