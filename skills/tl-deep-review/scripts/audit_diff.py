#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import difflib
import re
import subprocess
import sys


@dataclass(frozen=True)
class Finding:
    severity: str
    lens: str
    file: str
    line: int | None
    detail: str

    def render(self) -> str:
        location = self.file
        if self.line is not None:
            location += f":{self.line}"
        return f"{location}: {self.severity} [{self.lens}]: {self.detail}"


class AuditError(RuntimeError):
    pass


def run_git(args: list[str], binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
        check=False,
    )
    if result.returncode != 0:
        stderr = (
            result.stderr.decode(errors="replace")
            if binary
            else result.stderr
        )
        raise AuditError(
            f"git {' '.join(args)} falhou ({result.returncode}): {stderr.strip()}"
        )
    return result.stdout


def assert_repository() -> None:
    output = run_git(["rev-parse", "--is-inside-work-tree"])
    if output.strip() != "true":
        raise AuditError("o diretório atual não é um worktree Git")


def normalize_path(raw: str) -> str:
    return raw.replace("\\", "/").removeprefix("./")


def is_sensitive(raw: str) -> bool:
    path = normalize_path(raw).lower()
    parts = PurePosixPath(path).parts
    basename = parts[-1] if parts else ""

    if basename in {
        "config.json",
        "config-teste.json",
        "cookies.json",
        "tokens.json",
    }:
        return True
    if basename == ".env" or basename.startswith(".env."):
        return True
    return bool(parts and parts[0] == "data")


def nul_names(args: list[str]) -> list[str]:
    output = run_git([*args, "-z"], binary=True)
    assert isinstance(output, bytes)
    return [
        normalize_path(part.decode("utf-8", errors="surrogateescape"))
        for part in output.split(b"\0")
        if part
    ]


def get_diff(base: str, cached: bool) -> tuple[str, list[str], list[str]]:
    if cached:
        diff = run_git(["diff", "--no-ext-diff", "--binary", "--cached", base, "--"])
        names = nul_names(["diff", "--cached", "--name-only", base, "--"])
        return str(diff), names, []

    # Compara a árvore de trabalho completa, incluindo staged, contra a base.
    diff = run_git(["diff", "--no-ext-diff", "--binary", base, "--"])
    names = nul_names(["diff", "--name-only", base, "--"])
    untracked = nul_names(
        ["ls-files", "--others", "--exclude-standard"]
    )

    synthetic: list[str] = []
    for filename in untracked:
        path = Path(filename)
        try:
            if b"\0" in path.read_bytes():
                synthetic.append(
                    f"diff --git a/{filename} b/{filename}\n"
                    f"new file mode 100644\n"
                    f"Binary files /dev/null and b/{filename} differ\n"
                )
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as err:
            raise AuditError(f"não foi possível auditar untracked {filename}: {err}")

        generated = difflib.unified_diff(
            [],
            text.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/{filename}",
            lineterm="\n",
        )
        synthetic.append("".join(generated))

    return str(diff) + "".join(synthetic), names, untracked


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<line>\d+)(?:,\d+)? @@")
DISCARDED_ERROR = re.compile(
    r"^\s*(?:_\s*=|(?:[\w]+\s*,\s*)+_\s*=|_\s*,\s*_\s*=)\s*"
)
TIME_AFTER = re.compile(r"\btime\.After\s*\(")
HTTP_SHORTCUT = re.compile(r"\bhttp\.(?:Get|Post|PostForm|Head)\s*\(")
TODO = re.compile(r"\b(?:TODO|FIXME)\b", re.IGNORECASE)
LOG_SECRET = re.compile(
    r"""
    \b(?:fmt\.(?:Print|Printf|Println|Sprintf)|
       log\.(?:Print|Printf|Println)|
       logger\.\w+)\s*\(
    .*?\b(?:password|passwd|token|secret|cookie|api[_-]?key)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
FOR_LINE = re.compile(r"^\s*for\b")


def check_added_line(
    filename: str,
    line_no: int,
    code: str,
    inside_added_loop: bool,
) -> list[Finding]:
    findings: list[Finding] = []

    if DISCARDED_ERROR.search(code):
        findings.append(Finding(
            "BLOCKER", "fail_closed", filename, line_no,
            "possível retorno descartado por atribuição ao identificador em branco"
        ))

    if TIME_AFTER.search(code):
        severity = "BLOCKER" if inside_added_loop else "WARNING"
        detail = (
            "time.After dentro de loop adicionado; use timer reutilizável"
            if inside_added_loop
            else "time.After adicionado; confirme que não ocorre em loop ou hot path"
        )
        findings.append(Finding(severity, "leaks", filename, line_no, detail))

    if LOG_SECRET.search(code):
        findings.append(Finding(
            "BLOCKER", "hygiene", filename, line_no,
            "possível credencial ou cookie enviado a log/print"
        ))

    if HTTP_SHORTCUT.search(code):
        findings.append(Finding(
            "WARNING", "concurrency", filename, line_no,
            "atalho HTTP não demonstra context nem timeout; use request com context e client configurado"
        ))

    if TODO.search(code):
        findings.append(Finding(
            "WARNING", "tests", filename, line_no,
            "TODO/FIXME adicionado; vincule-o a issue/story ou resolva antes do merge"
        ))

    return findings


def check_diff(diff: str) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    filename = "<desconhecido>"
    new_line: int | None = None
    added_lines = 0
    added_loop_depth = 0
    brace_depth = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            candidate = raw[4:]
            filename = (
                candidate[2:] if candidate.startswith("b/") else candidate
            )
            continue

        hunk = HUNK.match(raw)
        if hunk:
            new_line = int(hunk.group("line"))
            added_loop_depth = 0
            brace_depth = 0
            continue

        if new_line is None:
            continue

        if raw.startswith("+") and not raw.startswith("+++"):
            code = raw[1:]
            added_lines += 1

            if FOR_LINE.search(code):
                added_loop_depth = brace_depth + code.count("{")

            inside_loop = added_loop_depth > 0
            findings.extend(
                check_added_line(filename, new_line, code, inside_loop)
            )

            brace_depth += code.count("{") - code.count("}")
            if added_loop_depth and brace_depth < added_loop_depth:
                added_loop_depth = 0
            new_line += 1

        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        elif raw.startswith("\\ No newline"):
            continue
        else:
            code = raw[1:] if raw.startswith(" ") else raw
            brace_depth += code.count("{") - code.count("}")
            if added_loop_depth and brace_depth < added_loop_depth:
                added_loop_depth = 0
            new_line += 1

    return findings, added_lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Audita apenas o índice contra --base.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Permite diff vazio sem alegar que conteúdo foi auditado.",
    )
    args = parser.parse_args()

    try:
        assert_repository()
        run_git(["rev-parse", "--verify", f"{args.base}^{{commit}}"])
        diff, tracked_names, untracked_names = get_diff(args.base, args.cached)
    except AuditError as err:
        print(f"[ERRO] Auditoria não executada: {err}", file=sys.stderr)
        return 2

    all_names = sorted(set(tracked_names + untracked_names))
    findings = [
        Finding(
            "BLOCKER", "hygiene", filename, None,
            "arquivo protegido/sensível alterado"
        )
        for filename in all_names
        if is_sensitive(filename)
    ]

    diff_findings, added_lines = check_diff(diff)
    findings.extend(diff_findings)

    for finding in findings:
        print(finding.render())

    blockers = [f for f in findings if f.severity == "BLOCKER"]
    warnings = [f for f in findings if f.severity == "WARNING"]

    if blockers:
        print(
            f"[FALHA] {len(blockers)} blocker(s), "
            f"{len(warnings)} warning(s), {added_lines} linha(s) adicionada(s).",
            file=sys.stderr,
        )
        return 1

    if not all_names:
        if args.allow_empty:
            print("[SEM ALTERAÇÕES] Nenhum arquivo no escopo do diff.")
            return 0
        print(
            "[FALHA] Diff vazio: nenhuma alteração foi auditada. "
            "Use --allow-empty somente quando isso for esperado.",
            file=sys.stderr,
        )
        return 1

    if warnings:
        print(
            f"[AVISO] {len(warnings)} warning(s), nenhum blocker; "
            f"{len(all_names)} arquivo(s) e {added_lines} linha(s) adicionada(s)."
        )
    else:
        print(
            f"[SUCESSO] {len(all_names)} arquivo(s) e "
            f"{added_lines} linha(s) adicionada(s) auditada(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
