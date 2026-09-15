format_version: 1
work_method: native
active_work_ref: T028
current_role: checker
next_action: Executar revisão independente r03 via OpenAI Codex (gpt-5.6-terra/high) em fresh session report-only.
coordinator:
  harness: claude
  session: claude-code-b5b7f943
  started_at: 20260911T121833Z
  last_write_at: 20260911T161300Z
  released: true
active_batch: none
batch_status: none
review_followups: []
next_task_id: 31
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
next_batch_id: 1
open_discussions: []

## Tasks
| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| T001 | fix | none | draft | [] | [] | 0 | - |
| T002 | analysis | none | done | [] | [] | 2 | evidence/T002-r04.md |
| T003 | analysis | none | draft | [] | [] | 0 | - |
| T004 | fix | none | done | [] | [] | 3 | evidence/T004-r02.md |
| T005 | feat | none | done | [T004] | [] | 4 | evidence/T005-r02.md |
| T006 | fix | none | draft | [] | [] | 0 | - |
| T007 | analysis | none | draft | [] | [] | 0 | - |
| T008 | analysis | none | draft | [] | [] | 0 | - |
| T009 | analysis | none | done | [] | [] | 9 | evidence/T009-r07.md |
| T010 | fix | none | done | [T009] | [] | 11 | evidence/T010-r07.md |
| T011 | analysis | none | done | [T010] | [] | 2 | evidence/T011-r02.md |
| T012 | feature | package | done | [] | [] | 565 | evidence/T012-verification.md |
| T013 | feat | package | done | [] | [] | 1 | - |
| T014 | feat | package | done | [T013] | [] | 1 | - |
| T015 | feat | package | done | [T014] | [] | 1 | evidence/T015-verification.md |
| T016 | gov | none | done | [T022] | [] | 2 | evidence/T016-r01.md |
| T017 | gov | none | done | [T016] | [] | 2 | evidence/T017-r02.md |
| T018 | feat | none | done | [T017] | [] | 2 | evidence/T018-r05.md |
| T019 | feat | none | done | [T018, T024] | [] | 1 | evidence/T019-r05.md |
| T020 | fix | none | done | [T011] | [] | 2 | evidence/T013-r01.md |
| T021 | feat | none | done | [T020] | [] | 2 | evidence/T014-r01.md |
| T022 | feat | none | done | [] | [] | 2 | evidence/T015-r03b.md |
| T023 | analysis | none | ready | [T010, T021] | [] | 1 | evidence/T012-r01.md |
| T024 | gov | none | done | [T015, T018] | [] | 1 | evidence/T024-r02.md |
| T025 | feat | none | done | [] | [] | 2 | evidence/T025-r11.md |
| T026 | feat | none | done | [T025] | [] | 6 | evidence/T026-r03.md |
| T027 | feat | package | done | [T018, T026] | [] | 2 | evidence/T027-r01.md |
| T028 | gov | none | in_progress | [T027] | [] | 3 | evidence/T028-r01.md |
| T029 | feat | none | done | [T026] | [] | 12 | evidence/T029-r11.md |
| T030 | gov | none | done | [T029] | [] | 2 | evidence/T030-r01.md |
