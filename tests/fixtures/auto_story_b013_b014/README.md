# Canonical AUTO_STORY replay fixture: B013 → B014

Deterministic reconstruction of the Lynvia production canary cycle that motivated T032.

In the real cycle the child batch B013 ran Classifier, Maker, Checker R01, Classifier rework,
Maker rework and Checker R02 under a single authorization, reached `rework_limit_exhausted`
with 98% of the implementation approved, and left exactly two surgical Checker findings (R5 and
R6). Because authority was per-proposal, the system had to stop and ask a human for a second
cryptographic authorization to open B014 — which then inherited the preserved functional commit,
fixed R5/R6, was approved and closed the Story.

The fixture replays that cycle under one Story Authority (`A001`, budget 14 model calls,
`max_child_batches: 2`) and proves the properties T032 adds:

| file | role in the replay |
| :--- | :--- |
| `spec.md` | the authorized specification; its SHA-256 is frozen in the authority payload and must not change across children |
| `docs-arch.md` | content of a protected path held under `exact_file_hash` for the whole authority |
| `authority-payload.json` | the twelve immutable fields submitted to the human decision; `root_authority_digest` is computed from this and never stored inside it |
| `b013-review-result.json` | Checker R02 of B013: `changes_requested`, two patch-only action items (R5, R6) |
| `b014-review-result.json` | Checker of B014 over the cumulative candidate: `approved`, zero action items |
| `execution-plan.json` | the execution plan validated by T033: closed assertion registry, lifecycle phases, protected paths, budget satisfiability |

`authorized_spec_sha256` and the `exact_file_hash` of `docs/ARCH.md` are the real SHA-256 of
`spec.md` and `docs-arch.md` in this directory. The replay asserts that identity, so a fixture
edited without recomputing the digests fails instead of silently replaying a different Story.
