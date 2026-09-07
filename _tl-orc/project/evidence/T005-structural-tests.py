#!/usr/bin/env python3
"""Testes estruturais de T005 (docs/specs/review-followups.md §11) em consumidor sintético.

Sem harness pago. Cada cenário constrói documentos sintéticos (evidência de rodada com bloco
RF-<unit_id>-rNN, STATUS global com review_followups, Task ou story), aplica as regras do
contrato como funções deterministas e verifica invariantes: âncora produzida pelo título e
resolvida pela mesma regra do validador do repositório, alvo idêntico para fechar, famílias
disjuntas, cadeia de substituição com procedência e motivo, estados válidos.

Uso: python3 _tl-orc/project/evidence/T005-structural-tests.py <dir_saida>
Saída: árvores sintéticas por cenário em <dir_saida>/<cenário>/ e um relatório em stdout.
As regras codificadas aqui transcrevem o texto aprovado (WORK_MODEL.md "Registro de revisão",
playbook "Fechamento ou interrupção", perfis "Independência do Checker"); o script não é
parte do método distribuído e não substitui a leitura do contrato.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_repository import github_slug, heading_anchors  # noqa: E402  (mesma regra do validador)

STATES = {"pending", "superseded", "closed"}


class ContractViolation(Exception):
    pass


@dataclass
class Target:
    unit: str
    spec_revision: str
    content_id: str
    content_paths: list[str]
    locator: str  # commit | artefato preservado | not_recoverable


@dataclass
class FollowUp:
    unit_id: str
    round: str
    target: Target
    origin_run_id: str
    families_used: list[str]
    origin_round: str = ""
    status: str = "pending"
    review_ref: str = "none"
    attempts: list[str] = field(default_factory=list)
    superseded_by: str = "none"
    supersedes: str = "none"
    reason: str = "none"
    log: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"RF-{self.unit_id}-{self.round}"

    @property
    def anchor(self) -> str:
        return github_slug(self.id)

    def render(self) -> str:
        t = self.target
        lines = [
            f"## {self.id}",
            "kind: review follow-up",
            "target:",
            f"  unit: {t.unit}",
            f"  spec_revision: {t.spec_revision}",
            f"  content_id: {t.content_id}",
            f"  content_paths: [{', '.join(t.content_paths)}]",
            f"  locator: {t.locator}",
            f"origin_review: {self.origin_round or self.round} run_id: {self.origin_run_id}",
            "limitation: same_family_fresh_session",
            f"families_used: [{', '.join(self.families_used)}]",
            f"status: {self.status}",
            f"review_ref: {self.review_ref}",
            f"attempts: [{', '.join(self.attempts)}]",
            f"superseded_by: {self.superseded_by}",
            f"supersedes: {self.supersedes}",
            f"reason: {self.reason}",
            "log:",
        ] + [f"  - {e}" for e in self.log]
        return "\n".join(lines) + "\n"


@dataclass
class Review:
    """Parecer de uma rodada posterior, já registrado pelo Orquestrador (dados fabricados)."""
    unit: str
    spec_revision: str
    content_id: str
    family: str
    fresh_session: bool
    verdict: str  # approved | changes_requested
    run_id: str
    evidence_ref: str


# ---------------------------------------------------------------- regras do contrato

def open_followup(policy: str, distinct_unavailable_proven: bool, **kw) -> FollowUp | None:
    """perfis#independência-do-checker: sob preferred, mesma família em sessão nova só com
    indisponibilidade comprovada; abre pendência. Sob required, bloqueia sem abrir bloco."""
    if policy == "required":
        raise ContractViolation("required: ausência de família distinta bloqueia a revisão com ponto de retomada; sem bloco")
    if policy != "preferred":
        raise ContractViolation(f"política desconhecida: {policy}")
    if not distinct_unavailable_proven:
        raise ContractViolation("preferred: mesma família só após indisponibilidade comprovada das famílias distintas")
    rf = FollowUp(**kw)
    rf.log.append("T0 pendência criada por revisão de mesma família sob preferred")
    return rf


def task_done_allowed(policy: str, verdict: str, rf: FollowUp | None) -> bool:
    """WORK_MODEL#conclusão: done exige approved; sob preferred é permitido com pendência aberta."""
    if verdict != "approved":
        return False
    if rf is not None and rf.status == "pending" and policy == "required":
        return False
    return True


def close_followup(rf: FollowUp, review: Review) -> None:
    """WORK_MODEL#registro-de-revisão: closed somente com approved, sessão nova, família distinta
    de todas as families_used, cobrindo exatamente o alvo (unidade, spec_revision, content_id).
    changes_requested mantém pending e registra em attempts."""
    if rf.status != "pending":
        raise ContractViolation(f"{rf.id} não está pending ({rf.status})")
    if not review.fresh_session:
        raise ContractViolation("revisão posterior exige sessão nova")
    if review.family in rf.families_used:
        raise ContractViolation(f"família {review.family} consta em families_used {rf.families_used}")
    same_target = (review.unit == rf.target.unit and review.spec_revision == rf.target.spec_revision
                   and review.content_id == rf.target.content_id)
    if not same_target:
        rf.attempts.append(f"{review.run_id} verdict={review.verdict} alvo_divergente")
        raise ContractViolation("aprovação em outra unidade ou com outro content_id não transporta e não fecha a pendência")
    if review.verdict == "changes_requested":
        rf.attempts.append(f"{review.run_id} verdict=changes_requested")
        rf.log.append(f"T1 changes_requested por {review.run_id}; pendência mantida")
        return
    if review.verdict != "approved":
        raise ContractViolation(f"veredito inválido: {review.verdict}")
    rf.status = "closed"
    rf.review_ref = f"{review.evidence_ref} run_id={review.run_id}"
    rf.log.append(f"T1 closed por {review.run_id}")


def supersede(rf: FollowUp, new_target: Target, new_round: str, reason: str,
              distinct_approval: Review | None = None) -> FollowUp:
    """WORK_MODEL#registro-de-revisão: superseded exige substituta vinculada e reason com
    mapeamento de garantias; a substituta herda origin_review e nasce pending ou closed."""
    if rf.status != "pending":
        raise ContractViolation(f"{rf.id} não está pending")
    if not reason or reason == "none" or "garantia" not in reason.lower():
        raise ContractViolation("substituição exige reason com mapeamento de garantias; dois content_id não bastam")
    if new_target.content_id == rf.target.content_id:
        raise ContractViolation("substituta exige conteúdo novo")
    sub = FollowUp(unit_id=rf.unit_id, round=new_round, target=new_target, origin_run_id=rf.origin_run_id,
                   families_used=list(rf.families_used), supersedes=rf.id, origin_round=rf.origin_round or rf.round)
    sub.log.append(f"T2 substituta de {rf.id} (origin_review herdado: {rf.origin_run_id})")
    if distinct_approval is not None:
        close_followup(sub, distinct_approval)  # nasce closed só se cobrir exatamente o novo alvo
    rf.status = "superseded"
    rf.superseded_by = sub.id
    rf.reason = reason
    rf.log.append(f"T2 superseded por {sub.id}")
    return sub


def checker_families_allowed(catalog: dict[str, str], families_used: list[str]) -> list[str]:
    """perfis: candidatos de família distinta de todas as famílias efetivas."""
    return [m for m, fam in catalog.items() if fam not in families_used]


# ---------------------------------------------------------------- utilidades de documento

def write_evidence(dir_: Path, name: str, unit: str, rnd: str, runs: list[str], review_record: str,
                   rf: FollowUp | None) -> Path:
    body = [f"unit: {unit}", f"round: {rnd}", "", "## Agent runs",
            "| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"] + runs + \
           ["", "## Commands and exits", "sintético", "", "## Own proof", "sintético", "", "## Review record",
            review_record, "### Verdict (JSON, íntegro)", '{"schema_version":1,"verdict":"approved","action_items":[],"deferred":[],"rejected":[]}', ""]
    if rf is not None:
        body += [rf.render()]
    p = dir_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(body))
    return p


def write_status(dir_: Path, method: str, followups: list[str], extra: str = "") -> Path:
    p = dir_ / "_tl-orc/project/STATUS.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""format_version: 1
work_method: {method}
active_work_ref: none
current_role: none
next_action: sintético
coordinator:
  harness: codex
  session: synthetic
  started_at: 20260907T000000Z
  last_write_at: 20260907T000000Z
  released: true
review_followups: [{', '.join(followups)}]
next_task_id: 2
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
open_discussions: []
{extra}""")
    return p


def resolve_reference(consumer: Path, ref: str) -> bool:
    """<unit>@<evidence_ref>#anchor → o arquivo existe e o título produz a âncora (regra do validador)."""
    path_part, _, anchor = ref.rpartition("#")
    evidence_ref = path_part.rsplit("@", 1)[-1]
    f = consumer / evidence_ref
    return f.is_file() and anchor in heading_anchors(f)


# ---------------------------------------------------------------- cenários

def run(out: Path) -> list[tuple[str, str, bool, str]]:
    results: list[tuple[str, str, bool, str]] = []

    def rec(n: str, what: str, ok: bool, detail: str) -> None:
        results.append((n, what, ok, detail))

    catalog = {"codex/gpt-5.6-terra/high": "OpenAI", "claude/sonnet/high": "Anthropic", "agy/gemini-3.1-pro-high/high": "Google"}
    base_target = Target("native/task/T001@_tl-orc/project/tasks/T001-slug.md", "s1a2b3c4d5e6f708",
                         "1111111111111111111111111111111111111111:aaaaaaaaaaaaaaaa", ["src/a.go"], "commit 11111111")
    runs_fallback = [
        "| T001-r01-checker-1 | checker | agy | gemini-3.1-pro-high | high | Google | not_observable | review | r01 | unavailable: 429 insufficient_quota | quota esgotada comprovada |",
        "| T001-r01-checker-2 | checker | claude | sonnet | high | Anthropic | not_observable | review | r01 | unavailable: 401 authentication_error | autenticação recusada |",
        "| T001-r01-checker-3 | checker | codex | gpt-5.6-terra | high | OpenAI | synthetic-3 | review | r01 | approved | same_family_fresh_session |",
    ]
    rr = "run_id: T001-r01-checker-3 | harness: codex | model: gpt-5.6-terra | effort: high | family: OpenAI | independence: mesma família do Maker em sessão nova após indisponibilidade comprovada | limitation: same_family_fresh_session"

    # 1 — preferred: bloco criado, referência resolve, done permitido
    c1 = out / "s01-preferred"
    rf1 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    ev1 = write_evidence(c1, "_tl-orc/project/evidence/T001-r01.md", base_target.unit, "r01", runs_fallback, rr, rf1)
    ref1 = f"{base_target.unit}@_tl-orc/project/evidence/T001-r01.md#{rf1.anchor}"
    write_status(c1, "native", [ref1], "\n## Tasks\n| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| T001 | fix | none | done | [] | [] | 4 | evidence/T001-r01.md |\n")
    rec("1", "bloco RF criado com status pending e limitação", rf1.status == "pending" and "same_family_fresh_session" in ev1.read_text(), rf1.id)
    rec("1", "STATUS referencia por caminho e âncora produzida pelo título", resolve_reference(c1, ref1), ref1)
    rec("1", "done permitido sob preferred com pendência aberta", task_done_allowed("preferred", "approved", rf1), "")
    rec("1", "mesma família recusada sem prova de indisponibilidade", _raises(lambda: open_followup("preferred", False, unit_id="T001", round="r01", target=base_target, origin_run_id="x", families_used=["OpenAI"])), "")

    # 2 — required: bloqueio, sem bloco
    c2 = out / "s02-required"
    err2 = _raises(lambda: open_followup("required", True, unit_id="T001", round="r01", target=base_target, origin_run_id="x", families_used=["OpenAI"]), want="required")
    write_evidence(c2, "_tl-orc/project/evidence/T001-r01.md", base_target.unit, "r01", runs_fallback[:2], "revisão bloqueada: nenhuma família distinta disponível; ponto de retomada registrado", None)
    write_status(c2, "native", [], "\n## Tasks\n| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| T001 | fix | none | in_review | [] | [checker: nenhuma família distinta disponível (required)] | 3 | evidence/T001-r01.md |\n")
    rec("2", "required bloqueia sem abrir bloco", err2 and "## RF-" not in (c2 / "_tl-orc/project/evidence/T001-r01.md").read_text(), "")
    rec("2", "done não permitido sem parecer approved", not task_done_allowed("required", "blocked", None), "")
    rec("2", "review_followups vazio no STATUS", "review_followups: []" in (c2 / "_tl-orc/project/STATUS.md").read_text(), "")

    # 4 — closed pelo alvo correto
    rf4 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    rev4 = Review(base_target.unit, base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", "T001-r02-checker-1", "evidence/T001-r02.md#r02")
    close_followup(rf4, rev4)
    c4 = out / "s04-closed"
    write_evidence(c4, "_tl-orc/project/evidence/T001-r01.md", base_target.unit, "r01", runs_fallback, rr, rf4)
    write_evidence(c4, "_tl-orc/project/evidence/T001-r02.md", base_target.unit, "r02", ["| T001-r02-checker-1 | checker | claude | sonnet | high | Anthropic | synthetic-4 | review | r02 | approved | none |"], "run_id: T001-r02-checker-1 | family: Anthropic | independence: distinta de families_used [OpenAI]", None)
    write_status(c4, "native", [])
    rec("4", "closed com review_ref contendo evidência, rodada e run_id", rf4.status == "closed" and "run_id=T001-r02-checker-1" in rf4.review_ref, rf4.review_ref)
    rec("4", "registro de controle acrescenta log sem alterar alvo", rf4.target == base_target and len(rf4.log) == 2, "")
    rec("4", "mesma família de families_used é recusada para fechar", _raises(lambda: close_followup(open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="x", families_used=["OpenAI"]), Review(base_target.unit, base_target.spec_revision, base_target.content_id, "OpenAI", True, "approved", "x", "y"))), "")

    # 5 — changes_requested sem autorização
    rf5 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    close_followup(rf5, Review(base_target.unit, base_target.spec_revision, base_target.content_id, "Google", True, "changes_requested", "T001-r02-checker-1", "evidence/T001-r02.md#r02"))
    c5 = out / "s05-changes-requested-sem-autorizacao"
    write_evidence(c5, "_tl-orc/project/evidence/T001-r01.md", base_target.unit, "r01", runs_fallback, rr, rf5)
    (c5 / "_tl-orc/project/tasks").mkdir(parents=True, exist_ok=True)
    (c5 / "_tl-orc/project/tasks/T002-achado-da-revisao-posterior.md").write_text("id: T002\ntype: fix\nstatus: draft\norigin: revisão posterior T001-r02-checker-1 (changes_requested), sem autorização vigente\n")
    write_status(c5, "native", [f"{base_target.unit}@_tl-orc/project/evidence/T001-r01.md#{rf5.anchor}"])
    rec("5", "pendência permanece pending com attempts registrado", rf5.status == "pending" and rf5.attempts == ["T001-r02-checker-1 verdict=changes_requested"], "")
    rec("5", "achados entram na fila como Task fix draft; nenhum run de maker após o parecer", (c5 / "_tl-orc/project/tasks/T002-achado-da-revisao-posterior.md").exists() and "maker" not in "".join(runs_fallback), "")

    # 6 / 6b — substituição com autorização
    new_target = Target(base_target.unit, base_target.spec_revision, "2222222222222222222222222222222222222222:bbbbbbbbbbbbbbbb", ["src/a.go"], "commit 22222222")
    reason = "garantias G1 (idempotência) e G2 (timeout) do alvo r01 continuam cobertas pelo alvo r03; G3 (retry) retirada por DEC002; decisão registrada em decisions/DEC002.md"
    rf6 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    close_followup(rf6, Review(base_target.unit, base_target.spec_revision, base_target.content_id, "Google", True, "changes_requested", "T001-r02-checker-1", "e"))
    sub6 = supersede(rf6, new_target, "r03", reason)
    rec("6", "original superseded com superseded_by e reason com garantias", rf6.status == "superseded" and rf6.superseded_by == sub6.id and "garantia" in rf6.reason, rf6.superseded_by)
    rec("6", "substituta pending herda origin_review (rodada e run da original) e registra supersedes", sub6.status == "pending" and sub6.origin_run_id == rf6.origin_run_id and sub6.origin_round == "r01" and "origin_review: r01 run_id: T001-r01-checker-3" in sub6.render() and sub6.supersedes == rf6.id, sub6.id)
    rf6b = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    appr = Review(new_target.unit, new_target.spec_revision, new_target.content_id, "Anthropic", True, "approved", "T001-r03-checker-1", "evidence/T001-r03.md#r03")
    sub6b = supersede(rf6b, new_target, "r03", reason, distinct_approval=appr)
    rec("6b", "substituta nasce closed com review_ref; original superseded; nenhuma pendência aberta", sub6b.status == "closed" and rf6b.status == "superseded" and "T001-r03-checker-1" in sub6b.review_ref, "")
    rec("6b", "aprovação do conteúdo novo não fecha a original (fica superseded, não closed)", rf6b.status != "closed", "")
    c6 = out / "s06-substituicao"
    write_evidence(c6, "_tl-orc/project/evidence/T001-r01.md", base_target.unit, "r01", runs_fallback, rr, rf6b)
    write_evidence(c6, "_tl-orc/project/evidence/T001-r03.md", base_target.unit, "r03", ["| T001-r03-checker-1 | checker | claude | sonnet | high | Anthropic | synthetic-6 | review | r03 | approved | none |"], "run_id: T001-r03-checker-1", sub6b)
    ref6 = f"{base_target.unit}@_tl-orc/project/evidence/T001-r03.md#{sub6b.anchor}"
    write_status(c6, "native", [])
    rec("6b", "cadeia navegável: superseded_by aponta para bloco existente com âncora própria", resolve_reference(c6, ref6) and rf6b.superseded_by == sub6b.id, ref6)

    # 7 — conteúdo alterado sem revisão; substituta sem reason é rejeitada
    rf7 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    rec("7", "alteração do conteúdo sem revisão não fecha nem apaga a pendência", rf7.status == "pending", "")
    rec("7", "substituição sem reason é rejeitada", _raises(lambda: supersede(rf7, new_target, "r02", "none")), "")
    rec("7", "substituição com dois content_id e sem mapeamento de garantias é rejeitada", _raises(lambda: supersede(rf7, new_target, "r02", "content_id 1111→2222")), "")
    rec("7", "nova revisão de mesma família no conteúdo novo cria substituta vinculada", supersede(rf7, new_target, "r02", reason).supersedes == rf7.id and rf7.status == "superseded", "")

    # 8 — approved de outra família com content_id diferente não fecha
    rf8 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    rec("8", "approved distinto com outro content_id não fecha e fica em attempts", _raises(lambda: close_followup(rf8, Review(base_target.unit, base_target.spec_revision, new_target.content_id, "Anthropic", True, "approved", "T001-r02-checker-1", "e"))) and rf8.status == "pending" and rf8.attempts == ["T001-r02-checker-1 verdict=approved alvo_divergente"], "")

    # 9 — mesmo content_id em outra unidade não transporta
    rf9 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    rec("9", "mesmo content_id em outra unidade não transporta", _raises(lambda: close_followup(rf9, Review("native/task/T002@_tl-orc/project/tasks/T002-slug.md", base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", "T002-r01-checker-1", "e"))) and rf9.status == "pending", "")

    # 10 — duas stories BMAD 1.1 em áreas distintas
    c10 = out / "s10-bmad-multiarea"
    refs10 = []
    for area in ("billing", "identity"):
        t = Target(f"bmad/story/{area}:1.1@modules/{area}/_bmad-output/implementation-artifacts/sprint-status.yaml", "s1", f"{area[0]*40}:{area[0]*16}", ["x.go"], "commit x")
        rf = open_followup("preferred", True, unit_id=f"{area}:1.1", round="r01", target=t, origin_run_id=f"{area}:1.1-r01-checker-3", families_used=["OpenAI"])
        evp = f"modules/{area}/_bmad-output/implementation-artifacts/evidence-1.1-r01.md"
        write_evidence(c10, evp, t.unit, "r01", runs_fallback, rr, rf)
        refs10.append(f"{t.unit}@{evp}#{rf.anchor}")
    write_status(c10, "bmad", refs10)
    rec("10", "duas pendências distintas, blocos nos artefatos de cada área", len(set(refs10)) == 2 and all(resolve_reference(c10, r) for r in refs10), "; ".join(refs10))
    rec("10", "nenhuma Task Native criada", not (c10 / "_tl-orc/project/tasks").exists(), "")
    rec("10", "STATUS global lista as duas identidades completas", all(r in (c10 / "_tl-orc/project/STATUS.md").read_text() for r in refs10), "")

    # 12 — alvo não recuperável
    rf12 = open_followup("preferred", True, unit_id="T001", round="r01", target=Target(base_target.unit, "s1", base_target.content_id, ["src/a.go"], "not_recoverable"), origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    rf12.reason = "alvo não recuperável: commit 11111111 ausente após reescrita de histórico; revisão posterior examinou apenas o conteúdo atual (commit 22222222)"
    rf12.log.append("T1 revisão posterior T001-r02-checker-1 declarou o que examinou; pendência mantida")
    rec("12", "pendência permanece pending com limitação e reason", rf12.status == "pending" and rf12.target.locator == "not_recoverable" and "não recuperável" in rf12.reason, "")
    rec("12", "fechamento pelo conteúdo atual (outro content_id) é recusado", _raises(lambda: close_followup(rf12, Review(base_target.unit, "s1", new_target.content_id, "Anthropic", True, "approved", "T001-r02-checker-1", "e"))) and rf12.status == "pending", "")

    # 15 — correção própria do Orquestrador
    families15 = ["Google", "Anthropic"]  # Maker Google + correção própria do Orquestrador Anthropic
    allowed15 = checker_families_allowed(catalog, families15)
    rec("15", "families_used inclui a família do Orquestrador; só OpenAI elegível", allowed15 == ["codex/gpt-5.6-terra/high"], str(allowed15))
    rf15 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=families15 + ["OpenAI"])
    rec("15", "revisão posterior por família já usada (Anthropic) é recusada", _raises(lambda: close_followup(rf15, Review(base_target.unit, base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", "x", "e"))), "")

    # invariantes gerais dos documentos gerados
    bad_states = [p for p in out.rglob("*.md") for m in re.findall(r"^status: (\S+)$", p.read_text(), re.M) if m not in STATES and "kind: review follow-up" in p.read_text()]
    rec("*", "todos os blocos RF gerados têm status em {pending, superseded, closed}", not bad_states, str(bad_states))
    return results


def _raises(fn, want: str | None = None) -> bool:
    try:
        fn()
    except ContractViolation as e:
        return want is None or want in str(e)
    return False


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/t005-structural").resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = run(out)
    ok_all = True
    print("| cenário | verificação | resultado | detalhe |")
    print("| :--- | :--- | :--- | :--- |")
    for n, what, ok, detail in results:
        ok_all &= ok
        print(f"| {n} | {what} | {'OK' if ok else 'FALHA'} | {detail} |")
    print(f"\n{sum(1 for r in results if r[2])}/{len(results)} verificações OK; árvores em {out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
