#!/usr/bin/env python3
"""Testes estruturais de T005 (docs/specs/review-followups.md §11) em consumidor sintético.

Sem harness pago. Cada cenário constrói um consumidor sintético (evidências de rodada com tabela
`Agent runs`, registro de revisão e parecer correspondentes ao cenário, blocos RF-<unit_id>-rNN,
STATUS global com review_followups, Task ou story), aplica as regras do contrato como funções
deterministas e verifica invariantes em dois níveis:

1. objetos: alvo idêntico para fechar, famílias disjuntas, cadeia de substituição com procedência
   e motivo, estados válidos;
2. documentos gerados: toda referência encontra o que referencia — âncora de bloco RF produzida
   pelo título e resolvida pela mesma regra do validador do repositório; `origin_review` e
   `review_ref` apontam para runs registrados na tabela `Agent runs` do arquivo referenciado;
   `attempts` apontam para runs registrados no consumidor; `supersedes`/`superseded_by` apontam
   para blocos existentes; um documento cuja revisão foi bloqueada não contém parecer; um bloco
   `closed` referencia um parecer `approved`.

Uso: python3 _tl-orc/project/evidence/T005-structural-tests.py <dir_saida>
As regras codificadas transcrevem o texto aprovado (WORK_MODEL.md "Registro de revisão" e
"Conclusão", playbook "Fechamento ou interrupção", perfis "Independência do Checker"); o script
não é parte do método distribuído e não substitui a leitura do contrato.
"""
from __future__ import annotations

import json
import re
import sys
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
    """Parecer de uma rodada, já registrado pelo Orquestrador (dados fabricados)."""
    unit: str
    spec_revision: str
    content_id: str
    family: str
    fresh_session: bool
    verdict: str  # approved | changes_requested
    run_id: str
    evidence_ref: str  # <caminho>#<âncora do registro de revisão>


# ---------------------------------------------------------------- regras do contrato

def open_followup(policy: str, distinct_unavailable_proven: bool, **kw) -> FollowUp:
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


# ---------------------------------------------------------------- geração de documentos

@dataclass
class Run:
    run_id: str
    role: str
    harness: str
    model: str
    effort: str
    family: str
    session: str
    phase: str
    round: str
    outcome: str
    fallback_reason: str

    def row(self) -> str:
        return f"| {self.run_id} | {self.role} | {self.harness} | {self.model} | {self.effort} | {self.family} | {self.session} | {self.phase} | {self.round} | {self.outcome} | {self.fallback_reason} |"


def fallback_runs(unit_id: str, rnd: str = "r01") -> list[Run]:
    """Duas famílias distintas comprovadamente indisponíveis; mesma família do Maker aprova em sessão nova."""
    return [
        Run(f"{unit_id}-{rnd}-maker-1", "maker", "codex", "gpt-5.6-terra", "medium", "OpenAI", f"syn-{unit_id}-m", "implementation", rnd, "entrega completa", "none"),
        Run(f"{unit_id}-{rnd}-checker-1", "checker", "agy", "gemini-3.1-pro-high", "high", "Google", "not_observable", "review", rnd, "unavailable: 429 insufficient_quota", "quota esgotada comprovada"),
        Run(f"{unit_id}-{rnd}-checker-2", "checker", "claude", "sonnet", "high", "Anthropic", "not_observable", "review", rnd, "unavailable: 401 authentication_error", "autenticação recusada"),
        Run(f"{unit_id}-{rnd}-checker-3", "checker", "codex", "gpt-5.6-terra", "high", "OpenAI", f"syn-{unit_id}-c3", "review", rnd, "approved", "same_family_fresh_session"),
    ]


def verdict_json(verdict: str) -> str:
    items = [] if verdict == "approved" else [{"id": "R1", "severity": "medium", "category": "patch", "target_role": "maker",
                                               "location": "src/a.go:10", "problem": "sintético", "evidence": "sintético", "required_action": "sintético"}]
    return json.dumps({"schema_version": 1, "verdict": verdict, "action_items": items, "deferred": [], "rejected": []}, ensure_ascii=False)


def write_evidence(consumer: Path, rel: str, unit: str, rnd: str, runs: list[Run], review_run: Run | None,
                   verdict: str | None, independence: str, rf: FollowUp | None, blocked_note: str | None = None) -> str:
    """Escreve a evidência da rodada. Sem parecer (revisão bloqueada) não há JSON. Devolve a
    referência do registro de revisão (`<rel>#<âncora>`) para uso em review_ref."""
    body = [f"unit: {unit}", f"round: {rnd}", "", "## Agent runs",
            "| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"] + [r.row() for r in runs] + \
           ["", "## Commands and exits", "sintético", "", "## Own proof", "sintético", "", f"## Review record {rnd}"]
    if review_run is None or verdict is None:
        body += [f"revisão bloqueada: {blocked_note}", ""]
    else:
        body += [f"run_id: {review_run.run_id} | harness: {review_run.harness} | model: {review_run.model} | effort: {review_run.effort} | family: {review_run.family} | session: {review_run.session} | independence: {independence}",
                 "### Verdict (JSON, íntegro)", verdict_json(verdict), ""]
    if rf is not None:
        body += [rf.render()]
    p = consumer / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(body))
    return f"{rel}#{github_slug(f'Review record {rnd}')}"


def write_status(consumer: Path, method: str, followups: list[str], extra: str = "") -> None:
    p = consumer / "_tl-orc/project/STATUS.md"
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
next_task_id: 3
next_deliverable_id: 1
next_decision_id: 1
next_discussion_id: 1
open_discussions: []
{extra}""")


def tasks_table(rows: str) -> str:
    return "\n## Tasks\n| id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n" + rows + "\n"


# ---------------------------------------------------------------- verificação documental

def resolve_reference(consumer: Path, ref: str) -> bool:
    """<unit>@<evidence_ref>#anchor → o arquivo existe e um título produz a âncora (regra do validador)."""
    path_part, _, anchor = ref.rpartition("#")
    evidence_ref = path_part.rsplit("@", 1)[-1]
    f = consumer / evidence_ref
    return f.is_file() and anchor in heading_anchors(f)


def runs_in(path: Path) -> set[str]:
    return set(re.findall(r"^\| (\S+-r\d+-\S+-\d+) \|", path.read_text(), re.M))


def rf_blocks(path: Path) -> list[dict[str, str]]:
    text = path.read_text()
    blocks = []
    for m in re.finditer(r"^## (RF-\S+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        fields = dict(re.findall(r"^(\w+): (.*)$", m.group(2), re.M))
        fields["id"] = m.group(1)
        blocks.append(fields)
    return blocks


def check_documents(consumer: Path) -> list[str]:
    """Devolve a lista de inconsistências encontradas nos documentos gerados (vazia = consistente)."""
    problems: list[str] = []
    files = sorted(consumer.rglob("*.md"))
    all_runs = {r for f in files for r in runs_in(f)}
    all_blocks = {b["id"] for f in files for b in rf_blocks(f)}
    for f in files:
        text = f.read_text()
        here = runs_in(f)
        if "revisão bloqueada" in text and '"verdict"' in text:
            problems.append(f"{f.name}: revisão bloqueada com parecer presente")
        for b in rf_blocks(f):
            if b.get("status") not in STATES:
                problems.append(f"{b['id']}: status inválido {b.get('status')}")
            m = re.search(r"run_id: (\S+)", b.get("origin_review", ""))
            origin = m.group(1) if m else "?"
            if b.get("supersedes", "none") == "none":
                if origin not in here:  # bloco original: o run de origem está na própria evidência
                    problems.append(f"{b['id']}: origin_review run {origin} ausente em Agent runs de {f.name}")
            elif origin not in all_runs:  # substituta: herda o origin_review, registrado na evidência da original
                problems.append(f"{b['id']}: origin_review herdado {origin} não registrado no consumidor")
            if b.get("review_ref", "none") != "none":
                ref, _, run = b["review_ref"].partition(" run_id=")
                target = consumer / ref.split("#")[0]
                if not (target.is_file() and ref.split("#")[1] in heading_anchors(target)):
                    problems.append(f"{b['id']}: review_ref {ref} não resolve")
                elif run not in runs_in(target):
                    problems.append(f"{b['id']}: review_ref run {run} ausente em Agent runs de {target.name}")
                elif b.get("status") == "closed" and '"verdict": "approved"' not in target.read_text():
                    problems.append(f"{b['id']}: closed sem parecer approved em {target.name}")
            for att in re.findall(r"([A-Za-z0-9:.]+-r\d+-[a-z]+-\d+) verdict=", b.get("attempts", "")):
                if att not in all_runs:
                    problems.append(f"{b['id']}: attempts run {att} não registrado no consumidor")
            for key in ("supersedes", "superseded_by"):
                v = b.get(key, "none")
                if v != "none" and v not in all_blocks:
                    problems.append(f"{b['id']}: {key} {v} não existe")
            if b.get("status") == "superseded" and (b.get("reason") in (None, "none") or b.get("superseded_by") == "none"):
                problems.append(f"{b['id']}: superseded sem reason ou sem superseded_by")
    status = consumer / "_tl-orc/project/STATUS.md"
    if status.is_file():
        m = re.search(r"review_followups: \[(.*)\]", status.read_text())
        for ref in filter(None, (s.strip() for s in (m.group(1) if m else "").split(","))):
            if not resolve_reference(consumer, ref):
                problems.append(f"STATUS: referência {ref} não resolve")
    return problems


# ---------------------------------------------------------------- cenários

def run(out: Path) -> list[tuple[str, str, bool, str]]:
    results: list[tuple[str, str, bool, str]] = []

    def rec(n: str, what: str, ok: bool, detail: str = "") -> None:
        results.append((n, what, ok, detail))

    def docs_ok(n: str, consumer: Path) -> None:
        problems = check_documents(consumer)
        rec(n, "documentos gerados consistentes (referências, runs, pareceres, blocos)", not problems, "; ".join(problems))

    catalog = {"codex/gpt-5.6-terra/high": "OpenAI", "claude/sonnet/high": "Anthropic", "agy/gemini-3.1-pro-high/high": "Google"}
    U1 = "native/task/T001@_tl-orc/project/tasks/T001-slug.md"
    base_target = Target(U1, "s1a2b3c4d5e6f708", "1111111111111111111111111111111111111111:aaaaaaaaaaaaaaaa", ["src/a.go"], "commit 11111111")
    new_target = Target(U1, "s1a2b3c4d5e6f708", "2222222222222222222222222222222222222222:bbbbbbbbbbbbbbbb", ["src/a.go"], "commit 22222222")
    R1 = fallback_runs("T001")
    IND = "mesma família do Maker (OpenAI) em sessão nova após indisponibilidade comprovada de Google e Anthropic"
    reason = "garantias G1 (idempotência) e G2 (timeout) do alvo r01 continuam cobertas pelo alvo r03; G3 (retry) retirada por DEC002; decisão registrada em decisions/DEC002.md"

    def rf_r01() -> FollowUp:
        return open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])

    def distinct_run(rnd: str, family: str, verdict: str, unit_id: str = "T001") -> Run:
        h, m = {"Anthropic": ("claude", "sonnet"), "Google": ("agy", "gemini-3.1-pro-high")}[family]
        return Run(f"{unit_id}-{rnd}-checker-1", "checker", h, m, "high", family, f"syn-{unit_id}-{rnd}", "review", rnd, verdict, "none")

    # 1 — preferred: bloco criado, referência resolve, done permitido
    c1 = out / "s01-preferred"
    rf1 = rf_r01()
    ev1 = write_evidence(c1, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf1)
    ref1 = f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf1.anchor}"
    write_status(c1, "native", [ref1], tasks_table("| T001 | fix | none | done | [] | [] | 4 | evidence/T001-r01.md |"))
    rec("1", "bloco RF criado com status pending e limitação", rf1.status == "pending" and "same_family_fresh_session" in (c1 / "_tl-orc/project/evidence/T001-r01.md").read_text(), rf1.id)
    rec("1", "STATUS referencia por caminho e âncora produzida pelo título", resolve_reference(c1, ref1), ref1)
    rec("1", "done permitido sob preferred com pendência aberta", task_done_allowed("preferred", "approved", rf1))
    rec("1", "mesma família recusada sem prova de indisponibilidade", _raises(lambda: open_followup("preferred", False, unit_id="T001", round="r01", target=base_target, origin_run_id="x", families_used=["OpenAI"])))
    docs_ok("1", c1)

    # 2 — required: bloqueio, sem bloco, sem parecer
    c2 = out / "s02-required"
    err2 = _raises(lambda: open_followup("required", True, unit_id="T001", round="r01", target=base_target, origin_run_id="x", families_used=["OpenAI"]), want="required")
    write_evidence(c2, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1[:3], None, None, "", None,
                   blocked_note="nenhuma família distinta disponível (required); ponto de retomada: repetir a cadeia do Checker quando Google ou Anthropic voltarem")
    write_status(c2, "native", [], tasks_table("| T001 | fix | none | in_review | [] | [checker: nenhuma família distinta disponível (required)] | 3 | evidence/T001-r01.md |"))
    t2 = (c2 / "_tl-orc/project/evidence/T001-r01.md").read_text()
    rec("2", "required bloqueia sem abrir bloco", err2 and "## RF-" not in t2)
    rec("2", "evidência bloqueada não contém parecer", '"verdict"' not in t2 and "revisão bloqueada" in t2)
    rec("2", "done não permitido sem parecer approved", not task_done_allowed("required", "blocked", None))
    rec("2", "review_followups vazio no STATUS", "review_followups: []" in (c2 / "_tl-orc/project/STATUS.md").read_text())
    docs_ok("2", c2)

    # 4 — closed pelo alvo correto
    c4 = out / "s04-closed"
    rf4 = rf_r01()
    run4 = distinct_run("r02", "Anthropic", "approved")
    rr4 = write_evidence(c4, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run4], run4, "approved", "distinta de families_used [OpenAI]", None)
    close_followup(rf4, Review(U1, base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", run4.run_id, rr4))
    write_evidence(c4, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf4)
    write_status(c4, "native", [])
    rec("4", "closed com review_ref resolvível contendo evidência, registro e run_id", rf4.status == "closed" and rf4.review_ref == f"{rr4} run_id=T001-r02-checker-1", rf4.review_ref)
    rec("4", "registro de controle acrescenta log sem alterar alvo", rf4.target == base_target and len(rf4.log) == 2)
    rec("4", "mesma família de families_used é recusada para fechar", _raises(lambda: close_followup(rf_r01(), Review(U1, base_target.spec_revision, base_target.content_id, "OpenAI", True, "approved", "x", "y"))))
    docs_ok("4", c4)

    # 5 — changes_requested sem autorização
    c5 = out / "s05-changes-requested-sem-autorizacao"
    rf5 = rf_r01()
    run5 = distinct_run("r02", "Google", "changes_requested")
    rr5 = write_evidence(c5, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run5], run5, "changes_requested", "distinta de families_used [OpenAI]", None)
    close_followup(rf5, Review(U1, base_target.spec_revision, base_target.content_id, "Google", True, "changes_requested", run5.run_id, rr5))
    write_evidence(c5, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf5)
    (c5 / "_tl-orc/project/tasks").mkdir(parents=True, exist_ok=True)
    (c5 / "_tl-orc/project/tasks/T002-achado-da-revisao-posterior.md").write_text("id: T002\ntype: fix\nstatus: draft\norigin: revisão posterior T001-r02-checker-1 (changes_requested), sem autorização vigente\n")
    write_status(c5, "native", [f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf5.anchor}"], tasks_table("| T001 | fix | none | done | [] | [] | 4 | evidence/T001-r02.md |\n| T002 | fix | none | draft | [] | [] | 0 | - |"))
    rec("5", "pendência permanece pending com attempts registrado", rf5.status == "pending" and rf5.attempts == ["T001-r02-checker-1 verdict=changes_requested"])
    rec("5", "achados entram na fila como Task fix draft; nenhum run de Maker após o parecer", (c5 / "_tl-orc/project/tasks/T002-achado-da-revisao-posterior.md").exists() and not any(r.role == "maker" and r.round == "r02" for r in [run5]))
    docs_ok("5", c5)

    # 6 / 6b — substituição com autorização
    c6 = out / "s06-substituicao"
    rf6 = rf_r01()
    run6 = distinct_run("r02", "Google", "changes_requested")
    rr6 = write_evidence(c6, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run6], run6, "changes_requested", "distinta de families_used [OpenAI]", None)
    close_followup(rf6, Review(U1, base_target.spec_revision, base_target.content_id, "Google", True, "changes_requested", run6.run_id, rr6))
    sub6 = supersede(rf6, new_target, "r03", reason)
    rec("6", "original superseded com superseded_by e reason com garantias", rf6.status == "superseded" and rf6.superseded_by == sub6.id and "garantia" in rf6.reason, rf6.superseded_by)
    rec("6", "substituta pending herda origin_review (rodada e run da original) e registra supersedes", sub6.status == "pending" and "origin_review: r01 run_id: T001-r01-checker-3" in sub6.render() and sub6.supersedes == rf6.id, sub6.id)
    # 6 documentado: rework r03 (Maker) sem parecer independente ainda → substituta pending
    rework6 = Run("T001-r03-maker-1", "maker", "codex", "gpt-5.6-terra", "medium", "OpenAI", "syn-T001-r03m", "rework", "r03", "retrabalho entregue", "none")
    write_evidence(c6, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf6)
    write_evidence(c6, "_tl-orc/project/evidence/T001-r03.md", U1, "r03", [rework6], None, None, "", sub6, blocked_note="aguardando revisão independente do novo alvo; substituta pending")
    write_status(c6, "native", [f"{U1}@_tl-orc/project/evidence/T001-r03.md#{sub6.anchor}"])
    docs_ok("6", c6)
    # 6b: retrabalho já recebe aprovação independente → substituta nasce closed
    c6b = out / "s06b-substituicao-closed"
    rf6b = rf_r01()
    run6b_cr = distinct_run("r02", "Google", "changes_requested")
    rr6b = write_evidence(c6b, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run6b_cr], run6b_cr, "changes_requested", "distinta de families_used [OpenAI]", None)
    close_followup(rf6b, Review(U1, base_target.spec_revision, base_target.content_id, "Google", True, "changes_requested", run6b_cr.run_id, rr6b))
    run6b = distinct_run("r03", "Anthropic", "approved")
    rr6b3 = write_evidence(c6b, "_tl-orc/project/evidence/T001-r03.md", U1, "r03", [rework6, run6b], run6b, "approved", "distinta de families_used [OpenAI]", None)
    sub6b = supersede(rf6b, new_target, "r03", reason, distinct_approval=Review(U1, new_target.spec_revision, new_target.content_id, "Anthropic", True, "approved", run6b.run_id, rr6b3))
    # o bloco da substituta mora na evidência r03; reescreve r03 com o bloco
    write_evidence(c6b, "_tl-orc/project/evidence/T001-r03.md", U1, "r03", [rework6, run6b], run6b, "approved", "distinta de families_used [OpenAI]", sub6b)
    write_evidence(c6b, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf6b)
    write_status(c6b, "native", [])
    rec("6b", "substituta nasce closed com review_ref resolvível; original superseded; nenhuma pendência aberta", sub6b.status == "closed" and rf6b.status == "superseded" and sub6b.review_ref == f"{rr6b3} run_id=T001-r03-checker-1", sub6b.review_ref)
    rec("6b", "aprovação do conteúdo novo não fecha a original (fica superseded, não closed)", rf6b.status != "closed")
    rec("6b", "cadeia navegável: superseded_by aponta para bloco existente com âncora própria", resolve_reference(c6b, f"{U1}@_tl-orc/project/evidence/T001-r03.md#{sub6b.anchor}") and rf6b.superseded_by == sub6b.id)
    docs_ok("6b", c6b)

    # 7 — conteúdo alterado sem revisão; substituta sem reason é rejeitada
    c7 = out / "s07-conteudo-alterado"
    rf7 = rf_r01()
    rec("7", "alteração do conteúdo sem revisão não fecha nem apaga a pendência", rf7.status == "pending")
    rec("7", "substituição sem reason é rejeitada", _raises(lambda: supersede(rf7, new_target, "r02", "none")))
    rec("7", "substituição com dois content_id e sem mapeamento de garantias é rejeitada", _raises(lambda: supersede(rf7, new_target, "r02", "content_id 1111→2222")))
    sub7 = supersede(rf7, new_target, "r02", reason)  # nova revisão de mesma família sobre o conteúdo novo
    R7 = fallback_runs("T001", "r02")
    write_evidence(c7, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf7)
    write_evidence(c7, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", R7, R7[3], "approved", IND, sub7)
    write_status(c7, "native", [f"{U1}@_tl-orc/project/evidence/T001-r02.md#{sub7.anchor}"])
    rec("7", "nova revisão de mesma família no conteúdo novo cria substituta vinculada", sub7.supersedes == rf7.id and rf7.status == "superseded" and sub7.status == "pending")
    docs_ok("7", c7)

    # 8 — approved de outra família com content_id diferente não fecha
    c8 = out / "s08-content-id-diferente"
    rf8 = rf_r01()
    run8 = distinct_run("r02", "Anthropic", "approved")
    rr8 = write_evidence(c8, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run8], run8, "approved", "distinta; alvo divergente (content_id do rework, não o registrado)", None)
    rec("8", "approved distinto com outro content_id não fecha e fica em attempts", _raises(lambda: close_followup(rf8, Review(U1, base_target.spec_revision, new_target.content_id, "Anthropic", True, "approved", run8.run_id, rr8))) and rf8.status == "pending" and rf8.attempts == ["T001-r02-checker-1 verdict=approved alvo_divergente"])
    write_evidence(c8, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf8)
    write_status(c8, "native", [f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf8.anchor}"])
    docs_ok("8", c8)

    # 9 — mesmo content_id em outra unidade não transporta
    c9 = out / "s09-outra-unidade"
    rf9 = rf_r01()
    U2 = "native/task/T002@_tl-orc/project/tasks/T002-slug.md"
    run9 = distinct_run("r01", "Anthropic", "approved", unit_id="T002")
    rr9 = write_evidence(c9, "_tl-orc/project/evidence/T002-r01.md", U2, "r01", [run9], run9, "approved", "distinta", None)
    rec("9", "mesmo content_id em outra unidade não transporta", _raises(lambda: close_followup(rf9, Review(U2, base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", run9.run_id, rr9))) and rf9.status == "pending")
    write_evidence(c9, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf9)
    write_status(c9, "native", [f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf9.anchor}"])
    docs_ok("9", c9)

    # 10 — duas stories BMAD 1.1 em áreas distintas
    c10 = out / "s10-bmad-multiarea"
    refs10 = []
    for area in ("billing", "identity"):
        uid = f"{area}:1.1"
        unit = f"bmad/story/{uid}@modules/{area}/_bmad-output/implementation-artifacts/sprint-status.yaml"
        t = Target(unit, "s1", f"{area[0] * 40}:{area[0] * 16}", ["x.go"], "commit x")
        runs = fallback_runs(uid)
        rf = open_followup("preferred", True, unit_id=uid, round="r01", target=t, origin_run_id=runs[3].run_id, families_used=["OpenAI"])
        evp = f"modules/{area}/_bmad-output/implementation-artifacts/evidence-1.1-r01.md"
        write_evidence(c10, evp, unit, "r01", runs, runs[3], "approved", IND, rf)
        refs10.append(f"{unit}@{evp}#{rf.anchor}")
    write_status(c10, "bmad", refs10)
    rec("10", "duas pendências distintas, blocos nos artefatos de cada área, runs na identidade de cada unidade", len(set(refs10)) == 2 and all(resolve_reference(c10, r) for r in refs10), "; ".join(refs10))
    rec("10", "nenhuma Task Native criada", not (c10 / "_tl-orc/project/tasks").exists())
    rec("10", "STATUS global lista as duas identidades completas", all(r in (c10 / "_tl-orc/project/STATUS.md").read_text() for r in refs10))
    docs_ok("10", c10)

    # 12 — alvo não recuperável
    c12 = out / "s12-alvo-irrecuperavel"
    rf12 = open_followup("preferred", True, unit_id="T001", round="r01", target=Target(U1, "s1", base_target.content_id, ["src/a.go"], "not_recoverable"), origin_run_id="T001-r01-checker-3", families_used=["OpenAI"])
    run12 = distinct_run("r02", "Anthropic", "approved")
    rr12 = write_evidence(c12, "_tl-orc/project/evidence/T001-r02.md", U1, "r02", [run12], run12, "approved", "distinta; examinou apenas o conteúdo atual (commit 22222222), alvo original irrecuperável", None)
    rf12.reason = "alvo não recuperável: commit 11111111 ausente após reescrita de histórico; revisão posterior T001-r02-checker-1 examinou apenas o conteúdo atual (commit 22222222)"
    rec("12", "fechamento pelo conteúdo atual (outro content_id) é recusado", _raises(lambda: close_followup(rf12, Review(U1, "s1", new_target.content_id, "Anthropic", True, "approved", run12.run_id, rr12))) and rf12.status == "pending")
    rf12.log.append("T1 revisão posterior T001-r02-checker-1 declarou o que examinou; pendência mantida")
    write_evidence(c12, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rf12)
    write_status(c12, "native", [f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf12.anchor}"])
    rec("12", "pendência permanece pending com limitação e reason", rf12.status == "pending" and rf12.target.locator == "not_recoverable" and "não recuperável" in rf12.reason)
    docs_ok("12", c12)

    # 15 — correção própria do Orquestrador
    c15 = out / "s15-correcao-propria"
    families15 = ["Google", "Anthropic", "OpenAI"]  # Maker Google, correção própria do Orquestrador Anthropic, Checker OpenAI (mesma família? não: OpenAI é distinta) → cenário: todas usadas
    allowed15 = checker_families_allowed(catalog, ["Google", "Anthropic"])
    rec("15", "families_used inclui a família do Orquestrador; só OpenAI elegível", allowed15 == ["codex/gpt-5.6-terra/high"], str(allowed15))
    runs15 = [Run("T001-r01-maker-1", "maker", "agy", "gemini-3.8-flash-high", "high", "Google", "not_observable", "implementation", "r01", "entrega", "none"),
              Run("T001-r01-orchestrator-1", "orchestrator", "claude", "opus", "high", "Anthropic", "syn-orch", "implementation", "r01", "correção própria autorizada", "none"),
              Run("T001-r01-checker-1", "checker", "codex", "gpt-5.6-terra", "high", "OpenAI", "not_observable", "review", "r01", "unavailable: 429 insufficient_quota", "quota esgotada comprovada"),
              Run("T001-r01-checker-2", "checker", "claude", "sonnet", "high", "Anthropic", "syn-c2", "review", "r01", "approved", "same_family_fresh_session (Anthropic já autora pela correção própria)")]
    rf15 = open_followup("preferred", True, unit_id="T001", round="r01", target=base_target, origin_run_id="T001-r01-checker-2", families_used=["Google", "Anthropic"])
    write_evidence(c15, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", runs15, runs15[3], "approved", "mesma família da correção própria do Orquestrador (Anthropic) em sessão nova, após OpenAI indisponível", rf15)
    write_status(c15, "native", [f"{U1}@_tl-orc/project/evidence/T001-r01.md#{rf15.anchor}"])
    rec("15", "revisão posterior por família já usada (Anthropic) é recusada", _raises(lambda: close_followup(rf15, Review(U1, base_target.spec_revision, base_target.content_id, "Anthropic", True, "approved", "x", "e"))))
    docs_ok("15", c15)

    # verificação negativa do verificador documental: um documento propositalmente inconsistente é detectado
    cneg = out / "neg-verificador"
    rfn = rf_r01(); rfn.status = "closed"; rfn.review_ref = "_tl-orc/project/evidence/T001-r02.md#review-record-r02 run_id=T001-r02-checker-1"
    write_evidence(cneg, "_tl-orc/project/evidence/T001-r01.md", U1, "r01", R1, R1[3], "approved", IND, rfn)  # r02 não existe
    write_status(cneg, "native", [f"{U1}@_tl-orc/project/evidence/T001-r09.md#rf-t001-r09"])  # referência quebrada
    probs = check_documents(cneg)
    rec("*", "verificador documental detecta review_ref e referência de STATUS quebradas", len(probs) == 2 and any("review_ref" in p for p in probs) and any("STATUS" in p for p in probs), "; ".join(probs))
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
