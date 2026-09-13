#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

SUPPORTED = {".html", ".htm", ".css", ".scss", ".sass"}

COMMENTS = re.compile(r"/\*.*?\*/", re.DOTALL)
DECLARATION = re.compile(
    r"(?P<name>[-\w]+)\s*:\s*(?P<value>.*?)(?=;|})",
    re.IGNORECASE | re.DOTALL,
)
NUMBER_EM = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?em$",
    re.IGNORECASE,
)
PURE_COLOR = re.compile(r"^#(?:000|000000|fff|ffffff)$", re.IGNORECASE)
FOCUS_VISIBLE = re.compile(r":focus-visible\b", re.IGNORECASE)
OUTLINE_DISABLED = re.compile(
    r"^(?:none|0(?:[a-z%]+)?)(?:\s*!important)?$",
    re.IGNORECASE,
)
BOX_SHADOW_PART = re.compile(
    r"""
    ^\s*
    (?:inset\s+)?
    (?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em)?|0)\s+
    (?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em)?|0)\s+
    (?P<blur>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em)?|0)
    (?:\s+.*)?$
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def strip_css_comments(css: str) -> str:
    # Preserva linhas para manter localizações corretas.
    return COMMENTS.sub(lambda m: "\n" * m.group(0).count("\n"), css)


def split_css_blocks(css: str) -> list[tuple[str, str, int]]:
    """Extrai blocos simples; falha se as chaves forem desbalanceadas."""
    blocks: list[tuple[str, str, int]] = []
    stack: list[int] = []

    for pos, char in enumerate(css):
        if char == "{":
            stack.append(pos)
        elif char == "}":
            if not stack:
                raise ValueError(f"chave '}}' sem abertura na linha {line_number(css, pos)}")
            start = stack.pop()
            if not stack:
                selector_start = css.rfind("}", 0, start) + 1
                selector = css[selector_start:start].strip()
                blocks.append((selector, css[start + 1:pos], start + 1))

    if stack:
        raise ValueError(
            f"chave '{{' sem fechamento na linha {line_number(css, stack[-1])}"
        )

    return blocks


def audit_css(css: str, path: Path, base_line: int = 1) -> list[Finding]:
    findings: list[Finding] = []
    css = strip_css_comments(css)

    try:
        blocks = split_css_blocks(css)
    except ValueError as err:
        return [Finding(path, base_line, f"ERRO [css inválido]: {err}")]

    focus_visible_selectors = {
        selector
        for selector, _, _ in blocks
        if FOCUS_VISIBLE.search(selector)
    }

    for selector, body, body_offset in blocks:
        for match in DECLARATION.finditer(body + "}"):
            name = match.group("name").lower()
            value = match.group("value").strip()
            normalized = re.sub(r"\s+", " ", value)
            absolute_offset = body_offset + match.start()
            line = base_line + line_number(css, absolute_offset) - 1

            if name in {"background-clip", "-webkit-background-clip"}:
                if re.search(r"\btext\b", normalized, re.IGNORECASE):
                    findings.append(Finding(
                        path, line,
                        "ANTI-PATTERN: background-clip:text detectado."
                    ))

            elif name == "letter-spacing":
                compact = re.sub(r"\s*!important\s*$", "", normalized,
                                 flags=re.IGNORECASE).strip()
                if NUMBER_EM.fullmatch(compact):
                    amount = float(compact[:-2])
                    if amount < -0.04:
                        findings.append(Finding(
                            path, line,
                            f"ANTI-PATTERN: letter-spacing {compact} é menor que -0.04em."
                        ))

            elif name == "box-shadow":
                for shadow in normalized.split(","):
                    parsed = BOX_SHADOW_PART.match(shadow)
                    if parsed:
                        blur = parsed.group("blur").lower()
                        numeric = re.match(
                            r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", blur
                        )
                        if numeric and float(numeric.group()) == 0:
                            findings.append(Finding(
                                path, line,
                                "ANTI-PATTERN: box-shadow com blur zero."
                            ))
                            break

            elif name == "outline" and OUTLINE_DISABLED.fullmatch(normalized):
                if ":focus" in selector.lower() and not FOCUS_VISIBLE.search(selector):
                    # Exige ao menos uma regra focus-visible no documento.
                    # Correlação perfeita entre seletores exigiria parser CSS completo.
                    if not focus_visible_selectors:
                        findings.append(Finding(
                            path, line,
                            "ANTI-PATTERN: outline removido em foco sem regra :focus-visible."
                        ))

            elif name in {"background", "background-color", "color"}:
                color = re.sub(
                    r"\s*!important\s*$", "", normalized, flags=re.IGNORECASE
                ).strip()
                if PURE_COLOR.fullmatch(color):
                    findings.append(Finding(
                        path, line,
                        f"AVISO: cor pura {color} detectada em {name}."
                    ))

    return findings


class UIHTMLParser(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.stack: list[tuple[str, bool]] = []
        self.card_depth = 0
        self.findings: list[Finding] = []
        self.style_chunks: list[tuple[str, int]] = []
        self.in_style = False
        self.style_start_line = 1

    @staticmethod
    def classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        for name, value in attrs:
            if name.lower() == "class" and value:
                return set(value.split())
        return set()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        classes = self.classes(attrs)
        is_card = "card" in classes

        if is_card and self.card_depth:
            self.findings.append(Finding(
                self.path,
                self.getpos()[0],
                "ANTI-PATTERN: card estruturalmente aninhado em outro card."
            ))

        if classes & {"eyebrow", "kicker"}:
            self.findings.append(Finding(
                self.path,
                self.getpos()[0],
                "ANTI-PATTERN: classe kicker/eyebrow detectada."
            ))

        for name, value in attrs:
            if name.lower() == "style" and value:
                wrapped = f"x {{{value}}}"
                self.findings.extend(
                    audit_css(wrapped, self.path, self.getpos()[0])
                )

        self.stack.append((tag.lower(), is_card))
        if is_card:
            self.card_depth += 1

        if tag.lower() == "style":
            self.in_style = True
            self.style_start_line = self.getpos()[0]

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # Elementos autocontidos não permanecem na pilha.
        self.handle_starttag(tag, attrs)
        popped_tag, is_card = self.stack.pop()
        assert popped_tag == tag.lower()
        if is_card:
            self.card_depth -= 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "style":
            self.in_style = False

        # Recupera-se de HTML malformado fechando até o elemento encontrado.
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                removed = self.stack[index:]
                del self.stack[index:]
                self.card_depth -= sum(1 for _, is_card in removed if is_card)
                return

    def handle_data(self, data: str) -> None:
        if self.in_style:
            self.style_chunks.append((data, self.style_start_line))


def audit_file(path: Path) -> list[Finding]:
    try:
        content = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as err:
        return [Finding(path, 1, f"ERRO [leitura]: {err}")]

    suffix = path.suffix.lower()
    if suffix in {".css", ".scss", ".sass"}:
        return audit_css(content, path)

    if suffix in {".html", ".htm"}:
        parser = UIHTMLParser(path)
        try:
            parser.feed(content)
            parser.close()
        except Exception as err:
            return [Finding(path, 1, f"ERRO [html inválido]: {err}")]

        findings = list(parser.findings)
        for css, start_line in parser.style_chunks:
            findings.extend(audit_css(css, path, start_line))
        return findings

    return [Finding(path, 1, f"ERRO [entrada]: extensão não suportada: {suffix}")]


def collect_targets(inputs: list[str]) -> tuple[list[Path], list[str]]:
    targets: set[Path] = set()
    errors: list[str] = []

    for raw in inputs:
        path = Path(raw)
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED:
                errors.append(f"Entrada sem extensão suportada: {path}")
            else:
                targets.add(path.resolve())
        elif path.is_dir():
            try:
                targets.update(
                    candidate.resolve()
                    for candidate in path.rglob("*")
                    if candidate.is_file()
                    and candidate.suffix.lower() in SUPPORTED
                )
            except OSError as err:
                errors.append(f"Erro ao percorrer {path}: {err}")
        else:
            errors.append(f"Caminho inexistente ou inacessível: {path}")

    return sorted(targets), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    targets, operational_errors = collect_targets(args.paths)
    if not targets:
        operational_errors.append("Nenhum arquivo de UI elegível foi encontrado.")

    findings: list[Finding] = []
    for path in targets:
        findings.extend(audit_file(path))

    for error in operational_errors:
        print(f"BLOCKER [operacional]: {error}", file=sys.stderr)
    for finding in findings:
        print(finding.render())

    if operational_errors or findings:
        print(
            f"[FALHA] {len(operational_errors)} erro(s) operacional(is), "
            f"{len(findings)} achado(s), {len(targets)} arquivo(s) verificado(s).",
            file=sys.stderr,
        )
        return 1

    print(f"[SUCESSO] {len(targets)} arquivo(s) de UI verificado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
