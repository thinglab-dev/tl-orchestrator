#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


EXPECTED = [
    "status",
    "intent",
    "boundaries & constraints",
    "code map",
    "tasks & acceptance",
    "verification",
    "o que pedir a revisao independente",
]

DISPLAY = {
    "status": "Status",
    "intent": "Intent",
    "boundaries & constraints": "Boundaries & Constraints",
    "code map": "Code Map",
    "tasks & acceptance": "Tasks & Acceptance",
    "verification": "Verification",
    "o que pedir a revisao independente":
        "O que pedir a revisao independente",
}

ALIASES = {
    "boundaries e constraints": "boundaries & constraints",
    "tasks e acceptance": "tasks & acceptance",
    "o que pedir a revisão independente":
        "o que pedir a revisao independente",
    "o que pedir à revisão independente":
        "o que pedir a revisao independente",
    "o que pedir a revisao independente":
        "o que pedir a revisao independente",
}

HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
LOCATION = re.compile(
    r"(?<![\w:/])"
    r"(?P<path>[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_. -]+)*\.[A-Za-z0-9]+)"
    r":(?P<line>[1-9]\d*)"
    r"(?!\d)"
)
UNCHECKED = re.compile(r"^[ \t]*-[ \t]+\[[ \t]\][ \t]+\S", re.MULTILINE)
ANY_CHECKBOX = re.compile(r"^[ \t]*-[ \t]+\[[ xX]\][ \t]+\S", re.MULTILINE)
COMMAND = re.compile(
    r"^[ \t]*(?:```(?:bash|sh|powershell|pwsh)?[ \t]*$|"
    r"(?:go|git|python|python3|pytest|npm|pnpm|yarn|uv|make)\b)",
    re.MULTILINE | re.IGNORECASE,
)

VAGUE_TERMS = [
    (
        re.compile(r"\btratar\s+(?:os\s+)?erros?\s+adequadamente\b", re.I),
        "especifique resultado, tipo de erro e comportamento fail-closed",
    ),
    (
        re.compile(r"\bconforme\s+necess[aá]rio\b", re.I),
        "defina a condição exata",
    ),
    (
        re.compile(r"\b(?:deixar|ficar)\s+limp[oa]\b", re.I),
        "defina comando, formatter ou propriedade observável",
    ),
    (
        re.compile(r"\botimizar(?:\s+o)?\s+desempenho\b", re.I),
        "defina métrica, baseline e limiar",
    ),
    (
        re.compile(r"\balterar\s+(?:os\s+)?arquivos\s+necess[aá]rios\b", re.I),
        "liste uma fronteira fechada de escrita",
    ),
    (
        re.compile(r"\bfuncionar\s+corretamente\b", re.I),
        "defina entrada, saída e falha observável",
    ),
]


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    path: Path
    line: int
    detail: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: "
            f"{self.severity} [{self.category}]: {self.detail}"
        )


def normalize_heading(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    return ALIASES.get(normalized, normalized)


def mask_fenced_code(text: str) -> str:
    """Mantém linhas, mas remove o conteúdo de fences da análise estrutural."""
    output: list[str] = []
    inside = False
    fence_char = ""
    fence_len = 0

    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        match = re.match(r"(`{3,}|~{3,})", stripped)
        if match:
            marker = match.group(1)
            if not inside:
                inside = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                inside = False
            output.append("\n" if line.endswith("\n") else "")
        elif inside:
            output.append("\n" if line.endswith("\n") else "")
        else:
            output.append(line)

    return "".join(output)


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_sections(
    structural: str,
) -> tuple[list[tuple[str, int]], dict[str, tuple[str, int]]]:
    matches = list(HEADING.finditer(structural))
    ordered: list[tuple[str, int]] = []
    sections: dict[str, tuple[str, int]] = {}

    for index, match in enumerate(matches):
        name = normalize_heading(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(structural)
        line = line_at(structural, match.start())
        ordered.append((name, line))

        # Duplicatas são tratadas separadamente; preserva a primeira.
        sections.setdefault(name, (structural[start:end], line))

    return ordered, sections


def validate_location(
    spec_path: Path,
    raw_path: str,
    line: int,
) -> str | None:
    candidate = Path(raw_path.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = (spec_path.parent / candidate).resolve()

    if not candidate.is_file():
        return f"citação aponta para arquivo inexistente: {raw_path}:{line}"

    try:
        with candidate.open("r", encoding="utf-8", errors="strict") as handle:
            line_count = sum(1 for _ in handle)
    except (OSError, UnicodeError) as err:
        return f"não foi possível validar {raw_path}:{line}: {err}"

    if line > line_count:
        return (
            f"citação fora do arquivo: {raw_path}:{line}; "
            f"o arquivo possui {line_count} linha(s)"
        )
    return None


def audit_spec(path: Path, validate_paths: bool) -> list[Finding]:
    try:
        content = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as err:
        return [Finding(
            "BLOCKER", "leitura", path, 1,
            f"não foi possível ler a spec como UTF-8 válido: {err}",
        )]

    structural = mask_fenced_code(content)
    ordered, sections = extract_sections(structural)
    findings: list[Finding] = []

    names = [name for name, _ in ordered]
    for required in EXPECTED:
        count = names.count(required)
        if count == 0:
            findings.append(Finding(
                "BLOCKER", "seção ausente", path, 1,
                f"seção obrigatória ausente: {DISPLAY[required]}",
            ))
        elif count > 1:
            line = next(line for name, line in ordered if name == required)
            findings.append(Finding(
                "BLOCKER", "seção duplicada", path, line,
                f"seção aparece {count} vezes: {DISPLAY[required]}",
            ))

    recognized_order = [name for name in names if name in EXPECTED]
    if recognized_order != EXPECTED:
        findings.append(Finding(
            "BLOCKER", "ordem", path, 1,
            "as sete seções obrigatórias não aparecem exatamente na ordem canônica",
        ))

    extras = [(name, line) for name, line in ordered if name not in EXPECTED]
    for name, line in extras:
        findings.append(Finding(
            "BLOCKER", "seção extra", path, line,
            f"seção de nível 2 não autorizada: {name}",
        ))

    boundaries = sections.get("boundaries & constraints")
    if boundaries:
        text, heading_line = boundaries
        lower = text.casefold()
        for label in ("permitid", "proibid", "restri"):
            if label not in lower:
                findings.append(Finding(
                    "BLOCKER", "boundaries", path, heading_line,
                    f"Boundaries não explicita conteúdo referente a '{label}'",
                ))

    code_map = sections.get("code map")
    if code_map:
        text, heading_line = code_map
        locations = list(LOCATION.finditer(text))
        if not locations:
            findings.append(Finding(
                "BLOCKER", "code_map", path, heading_line,
                "Code Map não contém citação válida arquivo.ext:linha positiva",
            ))
        elif validate_paths:
            for match in locations:
                raw_path = match.group("path")
                line = int(match.group("line"))
                problem = validate_location(path, raw_path, line)
                if problem:
                    findings.append(Finding(
                        "BLOCKER", "code_map", path,
                        heading_line + line_at(text, match.start()) - 1,
                        problem,
                    ))

    tasks = sections.get("tasks & acceptance")
    if tasks:
        text, heading_line = tasks
        if not ANY_CHECKBOX.search(text):
            findings.append(Finding(
                "BLOCKER", "tasks", path, heading_line,
                "nenhum critério de aceite em formato de checkbox foi encontrado",
            ))
        if not UNCHECKED.search(text):
            findings.append(Finding(
                "BLOCKER", "tasks", path, heading_line,
                "não há critério pendente '- [ ]'; checkboxes concluídos não ratificam trabalho futuro",
            ))

    verification = sections.get("verification")
    if verification:
        text, heading_line = verification
        if not COMMAND.search(text):
            findings.append(Finding(
                "BLOCKER", "verification", path, heading_line,
                "Verification não contém comando executável reconhecível",
            ))

    review = sections.get("o que pedir a revisao independente")
    if review:
        text, heading_line = review
        nonempty_lines = [
            line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("<!--")
        ]
        if len(nonempty_lines) < 2:
            findings.append(Finding(
                "BLOCKER", "revisão independente", path, heading_line,
                "a seção não aponta pelo menos dois focos concretos de auditoria",
            ))

    for regex, recommendation in VAGUE_TERMS:
        for match in regex.finditer(structural):
            line = line_at(structural, match.start())
            findings.append(Finding(
                "BLOCKER" if tasks and match.start() >= content.find(tasks[0]) else "WARNING",
                "vague",
                path,
                line,
                f"termo vago '{match.group(0)}'; {recommendation}",
            ))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_paths", nargs="+")
    parser.add_argument(
        "--no-validate-locations",
        action="store_true",
        help="Valida o formato arquivo:linha, mas não consulta o filesystem.",
    )
    args = parser.parse_args()

    blockers = 0
    warnings = 0
    checked = 0

    for raw in args.spec_paths:
        path = Path(raw)
        if not path.is_file():
            print(
                f"{path}:1: BLOCKER [entrada]: arquivo inexistente ou inacessível"
            )
            blockers += 1
            continue
        if path.suffix.casefold() not in {".md", ".markdown"}:
            print(f"{path}:1: BLOCKER [entrada]: extensão Markdown esperada")
            blockers += 1
            continue

        checked += 1
        for finding in audit_spec(
            path, validate_paths=not args.no_validate_locations
        ):
            print(finding.render())
            if finding.severity == "BLOCKER":
                blockers += 1
            else:
                warnings += 1

    if checked == 0:
        print("[FALHA] Nenhuma spec elegível foi auditada.", file=sys.stderr)
        return 1

    if blockers:
        print(
            f"[FALHA] {blockers} blocker(s), {warnings} warning(s), "
            f"{checked} spec(s) auditada(s).",
            file=sys.stderr,
        )
        return 1

    if warnings:
        print(
            f"[SUCESSO COM AVISOS] {checked} spec(s), {warnings} warning(s)."
        )
    else:
        print(f"[SUCESSO] {checked} spec(s) em conformidade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
