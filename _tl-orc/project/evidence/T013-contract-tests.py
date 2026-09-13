#!/usr/bin/env python3
"""
T013 Contract Tests
Automated deterministic verification of the 9 contractual rules ratified in T011 r02:
1. liveness_probe_after configurable parameter;
2. Mechanical inspection required before inferring latency;
3. OS-agnostic process/I/O inspection (process state, CPU, stdout/stderr, stdin with EOF / < /dev/null);
4. question_emitted_at as technically observable start for human timeout;
5. transport_ack_at permitted only if provided by channel;
6. Strict prohibition of presuming human reading or cognitive awareness;
7. Default behavior on batch block: stop at the blocked unit without skipping (trava anti-salto);
8. Independent branch continuation allowed only when continue_independent_on_block: true is explicitly authorized;
9. Subordinate agents in Debater mode can instruct, but NEVER grant authorization.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PERFIS = ROOT / "prompts" / "orchestrator-perfis.md"
PLAYBOOK = ROOT / "prompts" / "orchestrator-playbook.md"
WORK_MODEL = ROOT / "docs" / "WORK_MODEL.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def assert_in_file(path: Path, pattern: str, desc: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        fail(f"[{path.name}] Missing {desc} (pattern: {pattern})")
    print(f"  OK: [{path.name}] {desc}")


def test_textual_invariants() -> None:
    print("Running Textual Invariant Checks...")

    # 1 & 2 & 3: liveness_probe_after, mechanical inspection, OS-agnostic, adapters
    assert_in_file(
        PERFIS,
        r"liveness_probe_after",
        "liveness_probe_after configurable parameter in Fallback e interrupção",
    )
    assert_in_file(
        PERFIS,
        r"investigação\s+mecânica\s+proporcional\s+do\s+subprocesso",
        "proportional mechanical investigation before inferring latency",
    )
    assert_in_file(
        PERFIS,
        r"agnóstica\s+ao\s+sistema\s+operacional",
        "OS-agnostic process and stream inspection",
    )
    assert_in_file(
        PERFIS,
        r"stdin.*?EOF.*?<\s*/dev/null",
        "stdin EOF and /dev/null verification",
    )
    assert_in_file(
        PERFIS,
        r"adaptadores\s+de\s+sistema\s+operacional",
        "ps/lsof treated as platform adapters",
    )
    assert_in_file(
        PERFIS,
        r"contabilidade\s+de\s+esforço\s+da\s+amostra",
        "local mechanical fixes recorded in effort accounting",
    )

    # 4 & 5 & 6: question_emitted_at, transport_ack_at, prohibition of cognitive presumption
    assert_in_file(
        PERFIS,
        r"question_emitted_at",
        "question_emitted_at in Acompanhar e retomar",
    )
    assert_in_file(
        PERFIS,
        r"transport_ack_at",
        "transport_ack_at admitted only if provided by channel",
    )
    assert_in_file(
        PERFIS,
        r"proibido\s+presumir\s+leitura\s+ou\s+cognição\s+humana",
        "strict prohibition of presuming human reading or cognition",
    )

    # 9: Debater agents instruct, never authorize
    assert_in_file(
        PERFIS,
        r"Debater.*?nunca\s+possuem\s+autoridade\s+para\s+conceder\s+autorizações",
        "Debater agents instruct but never grant authorization",
    )

    # 7 & 8: Anti-skip lock and continue_independent_on_block: true in Playbook & WORK_MODEL
    assert_in_file(
        PLAYBOOK,
        r"parada\s+imediata\s+da\s+execução\s+naquela\s+unidade,\s+sendo\s+estritamente\s+proibido\s+saltá-la",
        "Playbook anti-skip default lock on batch block",
    )
    assert_in_file(
        PLAYBOOK,
        r"continue_independent_on_block:\s*true",
        "Playbook continue_independent_on_block: true clause",
    )
    assert_in_file(
        WORK_MODEL,
        r"parada\s+imediata.*?vedado\s+saltá-la",
        "WORK_MODEL anti-skip default lock on batch block",
    )
    assert_in_file(
        WORK_MODEL,
        r"continue_independent_on_block:\s*true",
        "WORK_MODEL continue_independent_on_block: true clause",
    )
    assert_in_file(
        WORK_MODEL,
        r"question_emitted_at",
        "WORK_MODEL question_emitted_at observable human event",
    )

    # CHANGELOG entries
    assert_in_file(
        CHANGELOG,
        r"liveness_probe_after",
        "CHANGELOG mention of liveness_probe_after",
    )
    assert_in_file(
        CHANGELOG,
        r"continue_independent_on_block:\s*true",
        "CHANGELOG mention of continue_independent_on_block: true",
    )
    assert_in_file(
        CHANGELOG,
        r"question_emitted_at",
        "CHANGELOG mention of question_emitted_at",
    )


# --- Contrafactual Behavioral Simulators ---


class BatchQueueSimulator:
    """Simulates queue execution over an authorized batch."""

    def __init__(self, tasks: dict[str, list[str]], continue_independent: bool = False) -> None:
        self.tasks = tasks
        self.continue_independent = continue_independent
        self.executed: list[str] = []
        self.blocked: list[str] = []

    def run(self, failing_task: str) -> None:
        for tid in self.tasks:
            deps = self.tasks[tid]
            if any(d in self.blocked for d in deps):
                self.blocked.append(tid)
                continue

            if tid == failing_task:
                self.blocked.append(tid)
                if not self.continue_independent:
                    break
                else:
                    continue

            self.executed.append(tid)


def test_contrafactual_queue_behavior() -> None:
    print("\nRunning Contrafactual 1: Queue Anti-Skip Lock...")
    graph = {
        "T1": [],
        "T2": ["T1"],
        "T3": [],
    }

    # Case A: Default (continue_independent = False) -> MUST stop at T1, T3 NOT executed
    sim_default = BatchQueueSimulator(graph, continue_independent=False)
    sim_default.run(failing_task="T1")
    if "T3" in sim_default.executed:
        fail("Violation: Queue skipped blocked T1 and executed independent T3 without authorization!")
    if sim_default.blocked != ["T1"]:
        fail(f"Expected blocked to be ['T1'], got {sim_default.blocked}")
    print("  OK: Default batch halted at blocked T1; anti-skip lock enforced.")

    # Case B: Explicit continue_independent_on_block = True -> allows independent T3, blocks T2
    sim_opt_in = BatchQueueSimulator(graph, continue_independent=True)
    sim_opt_in.run(failing_task="T1")
    if "T3" not in sim_opt_in.executed:
        fail("Expected T3 to be executed under continue_independent_on_block: true")
    if "T2" in sim_opt_in.executed:
        fail("Violation: Dependent T2 executed despite dependency T1 being blocked!")
    print("  OK: With continue_independent_on_block: true, independent T3 ran while T2 was blocked.")


class LivenessInvestigatorSimulator:
    """Simulates decision engine upon process silence."""

    def evaluate(self, elapsed_s: int, liveness_probe_after_s: int, mechanical_check_done: bool, is_infra_failure: bool) -> str:
        if elapsed_s < liveness_probe_after_s:
            return "WAITING_NORMAL"
        if not mechanical_check_done:
            return "TRIGGER_MECHANICAL_INVESTIGATION"
        if is_infra_failure:
            return "ELIGIBLE_FOR_FALLBACK"
        return "LOCAL_MECHANICAL_REPAIR"


def test_contrafactual_liveness_investigation() -> None:
    print("\nRunning Contrafactual 2: Liveness & Fallback Guard...")
    engine = LivenessInvestigatorSimulator()
    probe_threshold = 45

    # Case A: Silence exceeds probe_after, but no mechanical check done -> fallback forbidden
    decision1 = engine.evaluate(elapsed_s=50, liveness_probe_after_s=probe_threshold, mechanical_check_done=False, is_infra_failure=False)
    if decision1 != "TRIGGER_MECHANICAL_INVESTIGATION":
        fail(f"Expected TRIGGER_MECHANICAL_INVESTIGATION, got {decision1}")
    print("  OK: Silence triggered mechanical investigation before any fallback consideration.")

    # Case B: Mechanical check done, confirmed simple stdin block -> local repair, NOT fallback
    decision2 = engine.evaluate(elapsed_s=50, liveness_probe_after_s=probe_threshold, mechanical_check_done=True, is_infra_failure=False)
    if decision2 != "LOCAL_MECHANICAL_REPAIR":
        fail(f"Expected LOCAL_MECHANICAL_REPAIR, got {decision2}")
    print("  OK: Simple mechanical problem routed to local repair; fallback prevented.")


class HumanTimeoutSimulator:
    """Simulates start of human wait interval."""

    def start_timer(self, runtime_emission_ok: bool, assumed_human_reading: bool) -> tuple[bool, str]:
        if not runtime_emission_ok:
            return False, "REJECTED_EMISSION_NOT_OBSERVED"
        if assumed_human_reading:
            return False, "REJECTED_COGNITIVE_PRESUMPTION_FORBIDDEN"
        return True, "TIMER_STARTED_AT_QUESTION_EMITTED_AT"


def test_contrafactual_human_timeout() -> None:
    print("\nRunning Contrafactual 3: Human Timeout & Emission...")
    timer = HumanTimeoutSimulator()

    # Case A: Trying to start timer before runtime emission confirms delivery
    ok1, reason1 = timer.start_timer(runtime_emission_ok=False, assumed_human_reading=False)
    if ok1 or reason1 != "REJECTED_EMISSION_NOT_OBSERVED":
        fail("Violation: Timer started without question_emitted_at confirmation!")
    print("  OK: Timer cannot start without observable question_emitted_at.")

    # Case B: Trying to assume cognitive reading
    ok2, reason2 = timer.start_timer(runtime_emission_ok=True, assumed_human_reading=True)
    if ok2 or reason2 != "REJECTED_COGNITIVE_PRESUMPTION_FORBIDDEN":
        fail("Violation: Presumption of human reading accepted!")
    print("  OK: Cognitive presumption strictly rejected.")

    # Case C: Valid emission
    ok3, reason3 = timer.start_timer(runtime_emission_ok=True, assumed_human_reading=False)
    if not ok3 or reason3 != "TIMER_STARTED_AT_QUESTION_EMITTED_AT":
        fail("Valid timer initialization failed!")
    print("  OK: Timer correctly started at question_emitted_at.")


class AgentAuthorityValidator:
    """Validates whether agent actions can grant user authority."""

    def validate_action(self, role: str, action: str) -> bool:
        if action in {"grant_scope", "authorize_budget", "approve_external_action"}:
            if role != "user":
                return False
        return True


def test_contrafactual_agent_authority() -> None:
    print("\nRunning Contrafactual 4: Agent Authority Restriction...")
    validator = AgentAuthorityValidator()

    # Case A: Agent in debater role attempts to authorize budget
    if validator.validate_action(role="debater", action="authorize_budget"):
        fail("Violation: Debater agent authorized budget!")
    print("  OK: Agent in Debater role denied authority to authorize budget.")

    # Case B: User authorizes budget
    if not validator.validate_action(role="user", action="authorize_budget"):
        fail("User authority mistakenly denied!")
    print("  OK: User authority recognized exclusively.")


def main() -> None:
    print("=== T013 Contract Tests ===")
    test_textual_invariants()
    test_contrafactual_queue_behavior()
    test_contrafactual_liveness_investigation()
    test_contrafactual_human_timeout()
    test_contrafactual_agent_authority()
    print("\nALL 9 CONTRACTUAL INVARIANTS AND 4 CONTRAFACTUAL PROBES PASSED (exit 0).")


if __name__ == "__main__":
    main()
