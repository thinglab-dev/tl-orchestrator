---
id: connector:2-10
title: Connector retry and backoff contract
type: feat
status: ready
content_paths: [src/connector.py, tests/test_connector.py]
do_not_touch: [secrets/]
---

## Spec

### Acceptance criteria
- AC01: `src/connector.py` retries a transient transport failure with bounded exponential backoff.
- AC02: The backoff never exceeds the configured ceiling and never sleeps on the final attempt.
- AC03: A non-transient failure is surfaced immediately, without consuming a retry.
- AC04: `tests/test_connector.py` covers the straight-line path, the retry path and the ceiling.

### Verification
- `python3 -m unittest tests.test_connector`
