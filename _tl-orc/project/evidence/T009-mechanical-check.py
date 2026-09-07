#!/usr/bin/env python3
"""Conferência mecânica do Orquestrador para um resultado de classificação (T009).

Baseado no protótipo de referência fornecido pelo Orquestrador (autoria original: Anthropic).
Evoluído por Maker agy (Google) em T009 (rework round 5 após parecer changes_requested Checker r04):
  (a) R1: procedência obrigatória para TODAS as listas de referência em 'expected' (roles, chains,
      pins, authors, families, policy) em envelope {"value": ..., "source": "arquivo#âncora|arquivo:linha"};
      rejeição de lista solta sem envelope; resolução estrita da origem (arquivo existente, âncora exata
      por slug ou linha existente); para roles e chains, origem em PROJECT.md (perfil de despacho: tabela
      de cadeias) com conferência de coincidência de cadeia; para pins, origem em PROJECT.md ou Task;
      para authors, origem em linha de tabela Agent runs em arquivo de evidência;
  (b) R2: null/null como lacuna permitida (model: null e effort: null com reason não vazio); objeto
      permanece válido mecanicamente, candidato marcado "lacuna: sem opção adequada no harness" e pulado
      na resolução; nulidade inconsistente rejeitada; primeiro candidato null/null com par autorizado
      no catálogo marcado "lacuna suspeita de normalizar escolha inválida" e resolução bloqueada;
  (c) R3: julgamento registrado vinculado ao objeto e às entradas conferidas via hashes SHA-256;
  (d) R4/R5: separação estrita entre validade mecânica e resolução de despacho; provas de indisponibilidade;
  (e) R6: modo --self-test estritamente sem escrita (compara em memória com pilot_summary.json);
      atualização do arquivo versionado exclusivamente com flag --write-summary.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple


def github_slug(heading: str) -> str:
    """Gera o slug GitHub para um título Markdown (regra canônica de scripts/validate_repository.py)."""
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[`*~]", "", heading).strip().lower()
    heading = "".join(char for char in heading if unicodedata.category(char)[0] not in {"P", "S"} or char in "-_ ")
    return re.sub(r"\s", "-", heading).strip("-")


def catalog_from_project(path: str = "_tl-orc/PROJECT.md") -> Dict[Tuple[str, str, str], Set[str]]:
    """Lê o catálogo autorizado de PROJECT.md#perfil-de-despacho."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| (Classificador|Planner|Maker|Checker|Searcher) \| (\w+) \| `([^`]+)` \| ([^|]+) \|",
        text,
        re.M,
    )
    cat: Dict[Tuple[str, str, str], Set[str]] = {}
    harness_map = {"Codex": "codex", "Claude": "claude", "Agy": "agy"}
    role_map = {
        "Classificador": "classifier",
        "Planner": "planner",
        "Maker": "maker",
        "Checker": "checker",
        "Searcher": "searcher",
    }
    for role_pt, harness_pt, model, efforts in rows:
        h = harness_map[harness_pt]
        role = role_map[role_pt]
        for e in re.findall(r"\b(low|medium|high|xhigh|max|ultra)\b", efforts):
            cat.setdefault((h, model, e), set()).add(role)
    return cat


def parse_chains_from_project(path: str = "_tl-orc/PROJECT.md") -> Dict[str, List[str]]:
    """Lê e extrai a tabela de cadeias autorizadas de PROJECT.md (seção 'Cadeias')."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(r"###\s*Cadeias.*?\n(.*?)(?=\n###|\n##|\Z)", text, re.S)
    section_text = m.group(1) if m else text
    rows = re.findall(
        r"^\|\s*(Classificador|Planner|Maker|Checker\s+report-only|Checker)\s*\|\s*([^|]+)\|",
        section_text,
        re.M,
    )
    role_map = {
        "Classificador": "classifier",
        "Planner": "planner",
        "Maker": "maker",
        "Checker report-only": "checker",
        "Checker": "checker",
    }
    chains: Dict[str, List[str]] = {}
    for role_pt, chain_str in rows:
        role = role_map[role_pt]
        harnesses = [h.lower() for h in re.findall(r"\b(Codex|Claude|Agy)\b", chain_str)]
        chains[role] = harnesses
    return chains


def derive_task_proxies(path: str = "docs/MODEL_ROUTING.md") -> Dict[str, str]:
    """Derivação verificável de cartões que qualificam como official_task_proxy (R2).

    Exige co-ocorrência de 'custo' com 'tarefa' na mesma frase E ausência de restrição explícita.
    'astra-domain' (minutos por tarefa, sem custo) NÃO qualifica.
    Retorna mapeamento {card_id: frase_qualificante}.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    card_matches = re.findall(r"^###\s*`([a-z0-9-]+)`[^\n]*\n(.*?)(?=\n###|\n##|\Z)", text, re.M | re.S)

    qualifications: Dict[str, str] = {}
    for cid, body in card_matches:
        clean_body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
        sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", clean_body)
        for s in sentences:
            s_clean = s.strip().replace("\n", " ")
            if not s_clean:
                continue
            has_cost = bool(re.search(r"\bcustos?\b", s_clean, re.I))
            has_task = bool(re.search(r"\btarefas?\b", s_clean, re.I))
            if has_cost and has_task:
                has_restriction = bool(re.search(
                    r"\b(?:não|sem|proibido|rejeita|nunca)\b[^\n.!?]{0,40}\b(?:extrapolar|custo|proxy|usar)\b",
                    s_clean,
                    re.I,
                ))
                if not has_restriction:
                    qualifications[cid] = s_clean
                    break
    return qualifications


# Procedência: Mapeamento explícito modelo-id (usado nos catálogos de PROJECT.md e nas classificações)
# para a palavra-chave de modelo identificada na especificação normativa e em docs/MODEL_ROUTING.md
# (Astra, Terra, Luna, Sol, Sonnet, Opus, Flash, "3.1 Pro").
MODEL_KEYWORD_MAP: Dict[str, str] = {
    "gpt-6-astra": "Astra",
    "gpt-5.6-terra": "Terra",
    "gpt-5.6-luna": "Luna",
    "gpt-5.6-sol": "Sol",
    "sonnet": "Sonnet",
    "claude-opus-5": "Opus",
    "gemini-3.8-flash-high": "Flash",
    "gemini-3.8-flash": "Flash",
    "gemini-3.1-pro-high": "3.1 Pro",
    "gemini-3.1-pro": "3.1 Pro",
}


def derive_evidence_model_map(path: str = "docs/MODEL_ROUTING.md") -> Dict[str, Set[str]]:
    """Deriva de docs/MODEL_ROUTING.md o mapeamento id_evidência -> conjunto de modelos pertinentes (R3-a).

    Modelos alvo: Astra, Terra, Luna, Sol, Sonnet, Opus, Flash, 3.1 Pro.
    - Linhas de tabela (| `price-*` |): modelo declarado na coluna de modelo;
    - Linhas de transporte (- `transport-*`): modelos suportados pela API/família;
    - Cartões (### `card-id`): modelo foco do cartão conforme seu título e corpo.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    keywords = ["Astra", "Terra", "Luna", "Sol", "Sonnet", "Opus", "Flash", "3.1 Pro"]
    mapping: Dict[str, Set[str]] = {}

    # 1. Tabela de preços
    for m in re.finditer(r"^\|\s*`([a-z0-9-]+)`\s*\|\s*([^|]+)\|", text, re.M):
        eid = m.group(1)
        col2 = m.group(2)
        mods = set()
        for kw in keywords:
            if kw.lower() in col2.lower():
                mods.add(kw)
        mapping[eid] = mods

    # 2. Linhas de transporte
    for m in re.finditer(r"^-\s*`([a-z0-9-]+)`:\s*(.+)", text, re.M):
        eid = m.group(1)
        line = m.group(2)
        mods = set()
        for kw in keywords:
            if kw.lower() in line.lower():
                mods.add(kw)
        if "gpt-5.6" in line.lower():
            mods.update(["Terra", "Luna", "Sol"])
        mapping[eid] = mods

    # 3. Cartões de evidência
    cards = re.findall(r"^###\s*`([a-z0-9-]+)`\s*—\s*([^\n]+)\n(.*?)(?=\n###|\n##|\Z)", text, re.M | re.S)
    for cid, title, _ in cards:
        mods = set()
        if "astra" in cid:
            mods.add("Astra")
        elif "gpt56" in cid:
            mods.update(["Terra", "Luna", "Sol"])
        elif "sonnet" in cid:
            mods.add("Sonnet")
        elif "opus" in cid:
            mods.add("Opus")
        elif "flash" in cid:
            mods.add("Flash")
        else:
            for kw in keywords:
                if kw.lower() in title.lower():
                    mods.add(kw)
        mapping[cid] = mods

    return mapping


def parse_routing_evidence(path: str = "docs/MODEL_ROUTING.md") -> Tuple[Set[str], Set[str], Set[str]]:
    """Lê docs/MODEL_ROUTING.md e extrai com procedência verificada:

    - official_ids: IDs registrados como linha de tabela (| `id` |), cartão (### `id`) ou transporte (- `id`:).
      Exclui marcadores documentais como official-2026-09-05.
    - price_ids: IDs da tabela de preços (price-*).
    - task_proxy_ids: IDs de cartões que contêm comprovação verificável de custo por tarefa (R2).
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")

    table_ids = set(re.findall(r"^\|\s*`([a-z0-9-]+)`\s*\|", text, re.M))
    price_ids = {i for i in table_ids if i.startswith("price-")}
    transport_ids = set(re.findall(r"^-\s*`([a-z0-9-]+)`:", text, re.M))
    card_matches = re.findall(r"^###\s*`([a-z0-9-]+)`[^\n]*\n(.*?)(?=\n###|\n##|\Z)", text, re.M | re.S)
    card_ids = {cid for cid, _ in card_matches}

    task_proxy_ids = set(derive_task_proxies(path).keys())

    official_ids = (table_ids | transport_ids | card_ids) - {"official-2026-09-05"}
    official_ids = {i for i in official_ids if not i.startswith("official-")}

    return official_ids, price_ids, task_proxy_ids


def evidence_ids_from_routing(path: str = "docs/MODEL_ROUTING.md") -> Set[str]:
    """Compatibilidade retroativa: retorna o conjunto de IDs oficiais do MODEL_ROUTING.md."""
    official_ids, _, _ = parse_routing_evidence(path)
    return official_ids


def _strip_anchor_and_line(source_str: str) -> str:
    """Extrai o caminho de arquivo removendo #âncora ou :linha."""
    path_part = source_str.split("#")[0].split(":")[0].strip()
    return path_part


def check_provenance_and_id(
    id_val: str,
    source: str,
    field_name: str,
    base_dir: pathlib.Path,
) -> None:
    """Verifica resolução e conferência estrita da localização declarada (R1 e R2).

    Regras:
    - Com #âncora: o arquivo deve conter um título Markdown cujo slug (regra canônica github_slug)
      seja exatamente igual à âncora (nunca por prefixo), e o ID literal deve aparecer na seção sob esse título;
    - Com :linha: o ID literal deve aparecer naquela linha específica;
    - Para local_ids (R1): só é aceito se apontar para uma LINHA DE TABELA de registro estruturado
      (| <id> | ... |) com cabeçalho contendo 'run_id' (Agent runs) ou 'measurement_id'/'id' de medição,
      com o ID na primeira coluna, em arquivo de evidência sob _tl-orc/project/evidence/ ou _tl-orc/evidence/
      (excluindo T009-cases/, T009-analysis.md, docs/MODEL_ROUTING.md e o próprio protótipo).
    """
    if not ("#" in source or ":" in source):
        raise ValueError(
            f"Procedência '{source}' do ID '{id_val}' em '{field_name}' incompleta: "
            f"deve declarar arquivo + âncora (#) ou linha (:)."
        )

    if "#" in source:
        rel_path, target_anchor = source.split("#", 1)
        rel_path = rel_path.strip()
        target_anchor = target_anchor.strip()
        is_anchor = True
    else:
        rel_path, line_part = source.split(":", 1)
        rel_path = rel_path.strip()
        line_part = line_part.strip().lstrip("L")
        is_anchor = False

    # Validação de caminho restrito para medição local (R1)
    if field_name == "local_ids":
        is_in_evidence = rel_path.startswith("_tl-orc/project/evidence/") or rel_path.startswith("_tl-orc/evidence/")
        is_model_routing = "MODEL_ROUTING.md" in rel_path
        is_prototype = "T009-mechanical-check.py" in rel_path or rel_path.endswith(".py")
        is_cases = "T009-cases/" in rel_path or rel_path.startswith("_tl-orc/project/evidence/T009-cases")
        is_analysis = "T009-analysis.md" in rel_path
        if not is_in_evidence or is_model_routing or is_prototype or is_cases or is_analysis:
            if is_analysis:
                raise ValueError(
                    f"Registro de medição local '{id_val}' em '{rel_path}' rejeitado: T009-analysis.md é documento de análise "
                    f"e não constitui registro estruturado de medição."
                )
            if is_cases:
                raise ValueError(
                    f"Registro de medição local '{id_val}' em '{rel_path}' rejeitado: só é aceito em arquivo de evidência "
                    f"estruturada sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/' (excluindo T009-cases/, T009-analysis.md e o próprio protótipo)."
                )
            raise ValueError(
                f"Registro de medição local '{id_val}' em '{rel_path}' rejeitado: só é aceito em arquivo de "
                f"evidência sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/' (nunca em docs/MODEL_ROUTING.md, "
                f"T009-cases/, T009-analysis.md ou no protótipo)."
            )

    filepath = base_dir / rel_path
    if not filepath.exists():
        raise FileNotFoundError(
            f"Caminho de procedência '{filepath}' do ID '{id_val}' em '{field_name}' não existe."
        )

    file_text = filepath.read_text(encoding="utf-8")
    lines = file_text.splitlines()

    if is_anchor:
        heading_indices: List[Tuple[int, int, str, str]] = []
        occurrences: Dict[str, int] = {}
        for idx, line in enumerate(lines):
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                base_slug = github_slug(title)
                cnt = occurrences.get(base_slug, 0)
                occurrences[base_slug] = cnt + 1
                slug = base_slug if cnt == 0 else f"{base_slug}-{cnt}"
                heading_indices.append((idx, level, slug, title))

        target_heading_idx = -1
        target_level = -1
        heading_pos = -1
        for pos, (idx, level, slug, title) in enumerate(heading_indices):
            if slug == target_anchor:
                target_heading_idx = idx
                target_level = level
                heading_pos = pos
                break

        if target_heading_idx == -1:
            raise ValueError(
                f"ID '{id_val}' em '{field_name}' rejeitado: âncora '#{target_anchor}' não encontrada "
                f"como título Markdown em '{rel_path}'."
            )

        start_idx = target_heading_idx + 1
        end_idx = len(lines)
        for next_idx, next_level, _, _ in heading_indices[heading_pos + 1:]:
            if next_level <= target_level:
                end_idx = next_idx
                break

        if field_name == "local_ids":
            section_lines = lines[start_idx:end_idx]
            found_table_row = False
            for s_idx, s_line in enumerate(section_lines):
                s_line_str = s_line.strip()
                if s_line_str.startswith("|") and s_line_str.endswith("|"):
                    parts = [p.strip().strip("`") for p in s_line_str.split("|")[1:-1]]
                    if parts and parts[0] == id_val:
                        for up_idx in range(s_idx - 1, -1, -1):
                            up_line = section_lines[up_idx].strip()
                            if not up_line.startswith("|"):
                                break
                            h_cols = [p.strip().lower() for p in up_line.split("|")[1:-1]]
                            if any("run_id" in h or "measurement_id" in h or h == "id" for h in h_cols):
                                found_table_row = True
                                break
                        if found_table_row:
                            break
            if not found_table_row:
                raise ValueError(
                    f"ID literal '{id_val}' em '{field_name}' rejeitado: não encontrado como linha de tabela de "
                    f"medição estruturada (| <id> | ... | com cabeçalho run_id/measurement_id/id) na seção "
                    f"'#{target_anchor}' de '{rel_path}'."
                )
        elif field_name == "proxy_ids":
            heading_title = heading_indices[heading_pos][3]
            if id_val != target_anchor and id_val not in heading_title:
                raise ValueError(
                    f"ID literal '{id_val}' em '{field_name}' rejeitado: não corresponde ao cartão "
                    f"'#{target_anchor}' em '{rel_path}'."
                )

    else:
        try:
            line_num = int(line_part)
        except ValueError:
            raise ValueError(f"Número de linha inválido '{line_part}' na procedência '{source}'.")

        if line_num < 1 or line_num > len(lines):
            raise ValueError(
                f"ID '{id_val}' em '{field_name}' rejeitado: linha {line_num} inexistente no "
                f"arquivo '{rel_path}' (total de linhas: {len(lines)})."
            )

        target_line = lines[line_num - 1].strip()
        if field_name == "local_ids":
            if not (target_line.startswith("|") and target_line.endswith("|")):
                raise ValueError(
                    f"ID local '{id_val}' em '{field_name}' rejeitado: linha {line_num} de '{rel_path}' não é uma linha "
                    f"de tabela de registro estruturado (| <id> | ... |)."
                )
            cols = [p.strip().strip("`") for p in target_line.split("|")[1:-1]]
            if not cols or cols[0] != id_val:
                raise ValueError(
                    f"ID local '{id_val}' em '{field_name}' rejeitado: linha {line_num} de '{rel_path}' não contém o ID "
                    f"na primeira coluna (encontrado: '{cols[0] if cols else ''}')."
                )
            has_valid_header = False
            for up_idx in range(line_num - 2, -1, -1):
                up_line = lines[up_idx].strip()
                if not up_line.startswith("|"):
                    break
                h_cols = [p.strip().lower() for p in up_line.split("|")[1:-1]]
                if any("run_id" in h or "measurement_id" in h or h == "id" for h in h_cols):
                    has_valid_header = True
                    break
            if not has_valid_header:
                raise ValueError(
                    f"ID local '{id_val}' em '{field_name}' rejeitado: a tabela na linha {line_num} de '{rel_path}' "
                    f"não possui cabeçalho com run_id ou measurement_id/id."
                )
        else:
            if id_val not in target_line:
                raise ValueError(
                    f"ID literal '{id_val}' em '{field_name}' rejeitado: não encontrado na linha {line_num} "
                    f"de '{rel_path}'."
                )


def validate_id_entries_with_provenance(
    id_data: Any,
    field_name: str,
    base_dir: pathlib.Path,
    task_proxy_ids: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Valida procedência verificável e registro efetivo dos IDs (R1/R2)."""
    if id_data is None:
        return {}

    validated: Dict[str, Dict[str, Any]] = {}

    def _check_entry(id_val: str, meta_dict: Dict[str, Any]) -> None:
        source = meta_dict.get("source") or meta_dict.get("path")
        if not source:
            raise ValueError(f"ID '{id_val}' em '{field_name}' rejeitado: ausência de procedência ('source').")

        check_provenance_and_id(id_val, source, field_name, base_dir)

        if field_name == "proxy_ids":
            if task_proxy_ids is not None and id_val not in task_proxy_ids:
                raise ValueError(
                    f"ID '{id_val}' em '{field_name}' rejeitado: cartão em docs/MODEL_ROUTING.md "
                    f"não contém comprovação de custo por tarefa (incompatível com official_task_proxy)."
                )

    if isinstance(id_data, list):
        for item in id_data:
            if isinstance(item, str):
                raise ValueError(
                    f"ID '{item}' em '{field_name}' rejeitado: lista de IDs passada 'na hora' sem origem "
                    f"declarada (proibido; toda entrada deve declarar arquivo + âncora ou linha)."
                )
            if isinstance(item, dict):
                id_val = item.get("id")
                if not id_val:
                    raise ValueError(f"Item {item} em '{field_name}' inválido: ausência de 'id'.")
                _check_entry(id_val, item)
                validated[id_val] = item
            else:
                raise TypeError(f"Tipo inesperado para item em '{field_name}': {type(item)}")

    elif isinstance(id_data, dict):
        for id_val, meta in id_data.items():
            if isinstance(meta, str):
                meta_dict = {"source": meta}
            elif isinstance(meta, dict):
                meta_dict = meta
            else:
                raise TypeError(f"Metadados inválidos para ID '{id_val}' em '{field_name}': {type(meta)}")
            _check_entry(id_val, meta_dict)
            validated[id_val] = meta_dict
    else:
        raise TypeError(f"Formato inválido para '{field_name}': {type(id_data)}")

    return validated


def resolve_provenance_source(
    source: str,
    field_name: str,
    base_dir: pathlib.Path,
) -> Tuple[pathlib.Path, Optional[str], Optional[int], List[str]]:
    """Resolve a procedência declarada: arquivo existente, âncora exata por slug ou linha existente (R1).

    Rejeita ausência de origem, formato sem # ou :, caminhos inexistentes, âncoras não encontradas
    ou linhas fora dos limites do arquivo. Retorna (filepath, target_anchor, line_num, file_lines).
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"Procedência de '{field_name}' ausente ou vazia.")

    source_clean = source.strip()
    if "#" not in source_clean and ":" not in source_clean:
        raise ValueError(
            f"Procedência de '{field_name}' ('{source_clean}') inválida: deve conter âncora (#) ou linha (:)."
        )

    if "#L" in source_clean:
        rel_path, line_str = source_clean.split("#L", 1)
        line_part = line_str.split("-")[0].strip()
        is_anchor = False
    elif "#" in source_clean:
        rel_path, target_anchor = source_clean.split("#", 1)
        target_anchor = target_anchor.strip()
        is_anchor = True
    else:
        rel_path, line_part = source_clean.rsplit(":", 1)
        line_part = line_part.strip().lstrip("L")
        is_anchor = False

    rel_path = rel_path.strip()
    filepath = base_dir / rel_path
    if not filepath.is_file():
        raise ValueError(f"arquivo de procedência '{rel_path}' de '{field_name}' não existe.")

    lines = filepath.read_text(encoding="utf-8").splitlines()

    if is_anchor:
        heading_indices: List[Tuple[int, int, str, str]] = []
        occurrences: Dict[str, int] = {}
        for idx, line in enumerate(lines):
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                base_slug = github_slug(title)
                cnt = occurrences.get(base_slug, 0)
                occurrences[base_slug] = cnt + 1
                slug = base_slug if cnt == 0 else f"{base_slug}-{cnt}"
                heading_indices.append((idx, level, slug, title))

        matched = any(slug == target_anchor for _, _, slug, _ in heading_indices)
        if not matched:
            raise ValueError(
                f"Âncora '#{target_anchor}' na procedência de '{field_name}' não encontrada como título Markdown em '{rel_path}'."
            )
        return filepath, target_anchor, None, lines
    else:
        try:
            line_num = int(line_part)
        except ValueError:
            raise ValueError(f"Número de linha inválido '{line_part}' na procedência '{source_clean}' de '{field_name}'.")

        if line_num < 1 or line_num > len(lines):
            raise ValueError(
                f"Linha {line_num} na procedência de '{field_name}' inexistente em '{rel_path}' (total de linhas: {len(lines)})."
            )
        return filepath, None, line_num, lines


def unwrap_expected(
    expected_data: Dict[str, Any],
    base_dir: pathlib.Path = pathlib.Path("."),
    task_proxy_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Desempacota 'expected' conferindo procedência obrigatória de todas as listas de referência (R1)."""
    unwrapped: Dict[str, Any] = {}

    # 1. IDs locais e proxies econômicos (R1/R2)
    unwrapped["local_ids"] = validate_id_entries_with_provenance(
        expected_data.get("local_ids", {}), "local_ids", base_dir
    )
    unwrapped["proxy_ids"] = validate_id_entries_with_provenance(
        expected_data.get("proxy_ids", {}), "proxy_ids", base_dir, task_proxy_ids
    )

    # 2. story_id, phase, context_revision, catalog_revision (envelopes obrigatórios)
    for key in ("story_id", "phase", "context_revision", "catalog_revision"):
        item = expected_data.get(key)
        if not (isinstance(item, dict) and "value" in item and "source" in item):
            raise ValueError(
                f"'{key}' fornecida sem envelope de procedência (proibido; deve ser envelope {{'value': ..., 'source': ...}})."
            )
        resolve_provenance_source(item["source"], key, base_dir)
        unwrapped[key] = item["value"]

    # 3. policy (envelope obrigatório)
    policy_item = expected_data.get("policy")
    if not (isinstance(policy_item, dict) and "value" in policy_item and "source" in policy_item):
        raise ValueError(
            "policy fornecida sem envelope de procedência (proibido; deve ser envelope {'value': ..., 'source': ...})."
        )
    resolve_provenance_source(policy_item["source"], "policy", base_dir)
    unwrapped["policy"] = policy_item["value"]

    # 4. roles (envelope obrigatório com conferência de origem e papéis autorizados)
    roles_item = expected_data.get("roles")
    if isinstance(roles_item, list):
        raise ValueError(
            "roles fornecida como lista solta sem envelope (proibido; toda lista de referência deve vir em envelope {'value': ..., 'source': ...})."
        )
    if not (isinstance(roles_item, dict) and "value" in roles_item and "source" in roles_item):
        raise ValueError(
            "roles ausente ou sem envelope de procedência (proibido; deve ser envelope {'value': ..., 'source': ...})."
        )
    r_val = roles_item["value"]
    if not isinstance(r_val, list):
        raise ValueError(f"Valor de 'roles' ({type(r_val).__name__}) deve ser uma lista de papéis.")
    r_filepath, _, _, _ = resolve_provenance_source(roles_item["source"], "roles", base_dir)
    norm_r_rel = str(r_filepath.relative_to(base_dir)) if r_filepath.is_relative_to(base_dir) else str(r_filepath)
    if norm_r_rel != "_tl-orc/PROJECT.md":
        raise ValueError(
            f"Origem de 'roles' ({roles_item['source']}) inválida: deve ser a política autorizada em '_tl-orc/PROJECT.md'."
        )
    authorized_roles = {"classifier", "planner", "maker", "checker", "searcher"}
    for r_role in r_val:
        if r_role not in authorized_roles:
            raise ValueError(
                f"Papel '{r_role}' em 'roles' não é um papel autorizado na política de PROJECT.md ({sorted(authorized_roles)})."
            )
    unwrapped["roles"] = r_val

    # 5. chains (dicionário de envelopes por papel; confere coincidência exata com a tabela de PROJECT.md)
    chains_raw = expected_data.get("chains")
    if isinstance(chains_raw, list):
        raise ValueError(
            "chains fornecida como lista solta sem envelope (proibido; toda lista de referência deve vir em envelope {'value': ..., 'source': ...})."
        )
    if not isinstance(chains_raw, dict) or not chains_raw:
        raise ValueError(
            "chains ausente ou com formato inválido (deve ser dicionário de envelopes por papel)."
        )

    project_chains = parse_chains_from_project(base_dir / "_tl-orc/PROJECT.md")
    chains: Dict[str, List[str]] = {}
    for role, chain_item in chains_raw.items():
        if isinstance(chain_item, list):
            raise ValueError(
                f"chains['{role}'] fornecida como lista solta sem envelope (proibido; deve ser envelope {{'value': ..., 'source': ...}})."
            )
        if not (isinstance(chain_item, dict) and "value" in chain_item and "source" in chain_item):
            raise ValueError(
                f"chains['{role}'] sem envelope de procedência (proibido; deve ser envelope {{'value': ..., 'source': ...}})."
            )
        c_val = chain_item["value"]
        if not isinstance(c_val, list):
            raise ValueError(f"Valor de chains['{role}'] ({type(c_val).__name__}) deve ser uma lista de harnesses.")
        c_filepath, _, _, _ = resolve_provenance_source(chain_item["source"], f"chains[{role}]", base_dir)
        norm_c_rel = str(c_filepath.relative_to(base_dir)) if c_filepath.is_relative_to(base_dir) else str(c_filepath)
        if norm_c_rel != "_tl-orc/PROJECT.md":
            raise ValueError(
                f"Origem de chains['{role}'] ({chain_item['source']}) inválida: deve ser a política autorizada em '_tl-orc/PROJECT.md'."
            )
        expected_table_chain = project_chains.get(role)
        if expected_table_chain is None:
            raise ValueError(
                f"Papel '{role}' em 'chains' não encontrado na tabela de cadeias de PROJECT.md."
            )
        if c_val != expected_table_chain:
            raise ValueError(
                f"cadeia declarada para '{role}' ({c_val}) diverge da tabela de PROJECT.md ({expected_table_chain})."
            )
        chains[role] = c_val
    unwrapped["chains"] = chains

    # 6. pins (dicionário de envelopes por papel; origem em PROJECT.md ou Task)
    pins_raw = expected_data.get("pins")
    if isinstance(pins_raw, list):
        raise ValueError(
            "pins fornecida como lista solta sem envelope (proibido; deve declarar envelope {'value': ..., 'source': ...})."
        )
    if not isinstance(pins_raw, dict):
        raise ValueError("pins ausente ou com formato inválido.")

    pins: Dict[str, Any] = {}
    for role, pin_item in pins_raw.items():
        if isinstance(pin_item, list):
            raise ValueError(
                f"pins['{role}'] fornecida como lista solta sem envelope (proibido; deve ser envelope {{'value': ..., 'source': ...}})."
            )
        if not (isinstance(pin_item, dict) and "value" in pin_item and "source" in pin_item):
            raise ValueError(
                f"pins['{role}'] sem envelope de procedência (proibido; deve ser envelope {{'value': ..., 'source': ...}})."
            )
        p_val = pin_item["value"]
        p_filepath, _, _, _ = resolve_provenance_source(pin_item["source"], f"pins[{role}]", base_dir)
        norm_p_rel = str(p_filepath.relative_to(base_dir)) if p_filepath.is_relative_to(base_dir) else str(p_filepath)
        is_in_project = (norm_p_rel == "_tl-orc/PROJECT.md")
        is_in_task = (norm_p_rel.startswith("_tl-orc/project/tasks/") or norm_p_rel.startswith("_tl-orc/tasks/"))
        if not (is_in_project or is_in_task):
            raise ValueError(
                f"Origem de pins['{role}'] ({pin_item['source']}) inválida: deve ser em PROJECT.md (piloto) ou no registro da Task."
            )
        pins[role] = p_val
    unwrapped["pins"] = pins

    # 7. families (envelope obrigatório com mapeamento modelo -> família)
    fam_raw = expected_data.get("families")
    if isinstance(fam_raw, dict) and "value" in fam_raw and "source" in fam_raw:
        resolve_provenance_source(fam_raw["source"], "families", base_dir)
        f_val = fam_raw["value"]
        if not isinstance(f_val, dict):
            raise ValueError(f"Valor de 'families' ({type(f_val).__name__}) deve ser um dicionário modelo -> família.")
        unwrapped["families"] = f_val
    else:
        raise ValueError(
            "families fornecida sem envelope de procedência (proibido; deve ser envelope {'value': ..., 'source': ...})."
        )

    # 8. authors (envelope obrigatório; origem em linha de tabela Agent runs em arquivo de evidência)
    authors_item = expected_data.get("authors")
    if isinstance(authors_item, list):
        raise ValueError(
            "authors fornecida como lista solta sem envelope (proibido; toda lista de referência deve vir em envelope {'value': ..., 'source': ...})."
        )
    if not (isinstance(authors_item, dict) and "value" in authors_item and "source" in authors_item):
        raise ValueError(
            "authors ausente ou sem envelope de procedência (proibido; deve ser envelope {'value': ..., 'source': ...})."
        )
    a_val = authors_item["value"]
    if not isinstance(a_val, list):
        raise ValueError(f"Valor de 'authors' ({type(a_val).__name__}) deve ser uma lista de famílias autoras.")
    a_filepath, _, a_line, a_lines = resolve_provenance_source(authors_item["source"], "authors", base_dir)
    norm_a_rel = str(a_filepath.relative_to(base_dir)) if a_filepath.is_relative_to(base_dir) else str(a_filepath)

    is_in_evidence = (
        (norm_a_rel.startswith("_tl-orc/project/evidence/") or norm_a_rel.startswith("_tl-orc/evidence/"))
        and "T009-cases/" not in norm_a_rel
        and not norm_a_rel.endswith("T009-analysis.md")
        and not norm_a_rel.endswith("T009-mechanical-check.py")
        and "MODEL_ROUTING.md" not in norm_a_rel
    )
    if not is_in_evidence:
        raise ValueError(
            f"Origem de 'authors' ({authors_item['source']}) rejeitada: só é aceita em arquivo de evidência sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/'."
        )

    if a_line is None:
        raise ValueError(
            f"Origem de 'authors' ({authors_item['source']}) deve apontar para uma linha específica (:linha ou #Llinha) de tabela Agent runs."
        )

    target_line = a_lines[a_line - 1].strip()
    if not (target_line.startswith("|") and target_line.endswith("|")):
        raise ValueError(
            f"Linha {a_line} de '{norm_a_rel}' indicada como origem de 'authors' não é uma linha de tabela estruturada (| ... |)."
        )

    has_agent_runs_hdr = False
    for up_i in range(a_line - 2, -1, -1):
        up_l = a_lines[up_i].strip()
        if not up_l.startswith("|"):
            if "## Agent runs" in up_l or "Agent runs" in up_l:
                has_agent_runs_hdr = True
            break
        if "run_id" in up_l.lower() and "family" in up_l.lower():
            has_agent_runs_hdr = True
            break
    if not has_agent_runs_hdr:
        raise ValueError(
            f"Linha {a_line} de '{norm_a_rel}' não pertence a uma tabela com cabeçalho 'Agent runs'/'run_id'/'family'."
        )

    unwrapped["authors"] = a_val

    # 9. availability e judgment
    unwrapped["availability"] = expected_data.get("availability", {})
    unwrapped["judgment"] = expected_data.get("judgment")

    return unwrapped


def verify_unavailability_proof(
    harness: str,
    model: str,
    avail_data: Any,
    base_dir: pathlib.Path,
) -> Optional[str]:
    """Valida prova de indisponibilidade de infraestrutura do candidato (R3)."""
    cand_id = f"{harness}/{model}"
    if not avail_data or not isinstance(avail_data, dict):
        return f"candidato '{cand_id}' sem estado de disponibilidade declarado"

    stat = avail_data.get("status")
    if stat != "unavailable":
        return f"candidato '{cand_id}' com status '{stat}' (exige 'unavailable')"

    proof = avail_data.get("proof") or avail_data.get("error")
    src = avail_data.get("source")
    if not proof or not src:
        return f"candidato '{cand_id}' sem prova literal de erro ou procedência ('source')"

    if ":" not in src:
        return f"procedência da prova '{src}' inválida: deve ser localizada por 'arquivo:linha'"

    rel_path, line_part = src.split(":", 1)
    rel_path = rel_path.strip()
    line_part = line_part.strip().lstrip("L")

    if not (rel_path.startswith("_tl-orc/project/evidence/") or rel_path.startswith("_tl-orc/evidence/")):
        return (
            f"arquivo de prova '{rel_path}' rejeitado: deve estar sob '_tl-orc/project/evidence/' "
            f"ou '_tl-orc/evidence/' (README ou outros arquivos não são registros de Agent runs)"
        )

    src_file = base_dir / rel_path
    if not src_file.exists():
        return f"arquivo de evidência de erro '{src_file}' não existe"

    try:
        line_num = int(line_part)
    except ValueError:
        return f"número de linha inválido '{line_part}' na procedência da prova"

    lines = src_file.read_text(encoding="utf-8").splitlines()
    if line_num < 1 or line_num > len(lines):
        return f"linha {line_num} inexistente no arquivo de evidência '{rel_path}' (total: {len(lines)})"

    line_text = lines[line_num - 1]

    if not line_text.strip().startswith("|"):
        return f"linha {line_num} de '{rel_path}' não é uma linha de tabela de Agent runs"

    if harness not in line_text or model not in line_text:
        return (
            f"linha {line_num} de '{rel_path}' não é pertinente ao candidato '{cand_id}' "
            f"(harness '{harness}' ou modelo '{model}' ausente no registro de execução)"
        )

    if proof not in line_text:
        return f"prova literal '{proof}' não encontrada na linha {line_num} de '{rel_path}'"

    proof_lower = proof.lower()
    non_proving = ["timeout", "timed out", "saída vazia", "empty output", "empty response", "processo vivo", "process alive"]
    for np in non_proving:
        if np in proof_lower:
            return (
                "prova rejeitada: timeout isolado, saída vazia ou processo vivo não comprovam indisponibilidade "
                "(perfis, Fallback e interrupção, linhas 161-166)"
            )

    proving = [
        "quota", "insufficient_quota", "rate_limit", "rate limit",
        "429", "401", "authentication", "auth_error", "authentication_error",
        "unauthorized", "harness ausente", "command not found", "failed to start",
        "init_error", "initialization_error"
    ]
    if not any(p in proof_lower for p in proving):
        return (
            f"texto da prova '{proof}' não corresponde a uma categoria comprovante de indisponibilidade "
            "(quota esgotada, autenticação recusada, harness ausente/erro de inicialização)"
        )

    return None


def validate_schema_recursive(
    instance: Any,
    subschema: Dict[str, Any],
    path: str = "$",
    root_schema: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Verificador mínimo recursivo conforme schemas/classification-result.schema.json (R3)."""
    errors: List[str] = []
    if root_schema is None:
        root_schema = subschema

    if "not" in subschema:
        not_errs = validate_schema_recursive(instance, subschema["not"], path, root_schema)
        if not not_errs:
            errors.append(f"schema: {path} violou restrição 'not'")
            return errors
        if len(subschema) == 1:
            return []

    if "$ref" in subschema:
        ref = subschema["$ref"]
        if ref.startswith("#/$defs/"):
            def_name = ref[len("#/$defs/"):]
            target_sub = root_schema.get("$defs", {}).get(def_name)
            if target_sub:
                return validate_schema_recursive(instance, target_sub, path, root_schema)
            else:
                return [f"schema: referência interna '{ref}' não encontrada no schema"]

    if "type" in subschema:
        stype = subschema["type"]
        types = [stype] if isinstance(stype, str) else stype
        type_ok = False
        for t in types:
            if t == "object" and isinstance(instance, dict):
                type_ok = True
            elif t == "array" and isinstance(instance, list):
                type_ok = True
            elif t == "string" and isinstance(instance, str):
                type_ok = True
            elif t == "null" and instance is None:
                type_ok = True
            elif t == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                type_ok = True
            elif t == "number" and isinstance(instance, (int, float)) and not isinstance(instance, bool):
                type_ok = True
            elif t == "boolean" and isinstance(instance, bool):
                type_ok = True
        if not type_ok:
            errors.append(f"schema: {path} esperado tipo {stype}, obtido {type(instance).__name__}")
            return errors

    if "const" in subschema:
        if instance != subschema["const"]:
            errors.append(f"schema: {path} esperado valor constante {subschema['const']!r}, obtido {instance!r}")

    if "enum" in subschema:
        if instance not in subschema["enum"]:
            errors.append(f"schema: {path} valor {instance!r} não pertence ao enum permitido {subschema['enum']}")

    if isinstance(instance, str):
        if "minLength" in subschema and len(instance) < subschema["minLength"]:
            errors.append(f"schema: {path} tamanho {len(instance)} menor que minLength {subschema['minLength']}")

    if isinstance(instance, list):
        if "minItems" in subschema and len(instance) < subschema["minItems"]:
            errors.append(
                f"schema: {path} deve ter no mínimo {subschema['minItems']} itens, obtido {len(instance)} (minItems: {subschema['minItems']})"
            )
        if "maxItems" in subschema and len(instance) > subschema["maxItems"]:
            errors.append(f"schema: {path} deve ter no máximo {subschema['maxItems']} itens, obtido {len(instance)}")
        if subschema.get("uniqueItems") is True:
            seen = set()
            for item in instance:
                item_key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else item
                if item_key in seen:
                    errors.append(f"schema: {path} contém itens duplicados (violação de uniqueItems)")
                    break
                seen.add(item_key)
        if "items" in subschema:
            item_sub = subschema["items"]
            for idx, item in enumerate(instance):
                errors.extend(validate_schema_recursive(item, item_sub, f"{path}[{idx}]", root_schema))

    if isinstance(instance, dict):
        if "minProperties" in subschema and len(instance) < subschema["minProperties"]:
            errors.append(f"schema: {path} deve ter no mínimo {subschema['minProperties']} propriedades, obtido {len(instance)}")
        if "required" in subschema:
            for req in subschema["required"]:
                if req not in instance:
                    errors.append(f"schema: {path} faltando campo obrigatório '{req}'")
        if subschema.get("additionalProperties") is False:
            allowed_props = set(subschema.get("properties", {}).keys())
            extra_props = set(instance.keys()) - allowed_props
            for ep in sorted(extra_props):
                errors.append(f"schema: propriedade adicional não permitida '{ep}' em {path}")
        if "properties" in subschema:
            for prop_name, prop_sub in subschema["properties"].items():
                if prop_name in instance:
                    errors.extend(validate_schema_recursive(instance[prop_name], prop_sub, f"{path}.{prop_name}", root_schema))

    if "allOf" in subschema:
        for cond_sub in subschema["allOf"]:
            if "if" in cond_sub:
                if_errs = validate_schema_recursive(instance, cond_sub["if"], path, root_schema)
                if not if_errs:
                    if "then" in cond_sub:
                        errors.extend(validate_schema_recursive(instance, cond_sub["then"], path, root_schema))
                else:
                    if "else" in cond_sub:
                        errors.extend(validate_schema_recursive(instance, cond_sub["else"], path, root_schema))
            else:
                errors.extend(validate_schema_recursive(instance, cond_sub, path, root_schema))

    return errors


def validate_schema_structure(
    d: Dict[str, Any],
    schema_path: str = "schemas/classification-result.schema.json",
) -> List[str]:
    """Conferência estrutural completa e recursiva contra schemas/classification-result.schema.json."""
    try:
        schema = json.loads(pathlib.Path(schema_path).read_text(encoding="utf-8"))
    except Exception as e:
        return [f"Falha ao carregar schema '{schema_path}': {e}"]
    return validate_schema_recursive(d, schema, path="$", root_schema=schema)


def check_classification(
    d: Dict[str, Any],
    expected: Dict[str, Any],
    cat: Dict[Tuple[str, str, str], Set[str]],
    ids: Set[str],
    price_ids: Set[str],
    task_proxy_ids: Set[str],
    evidence_model_map: Optional[Dict[str, Set[str]]] = None,
    base_dir: pathlib.Path = pathlib.Path("."),
) -> Tuple[List[str], List[Tuple[Any, ...]], str, str, str, str]:
    """Executa a conferência em três estágios explícitos (R5/R3):

    1. Conferência mecânica (schema, catálogo, campos esperados, procedência econômica, pertinência por modelo, pins).
    2. Julgamento registrado (verificação criptográfica vinculada ao objeto e entradas).
    3. Liberação de despacho (resolução de elegibilidade e fallback com prova de indisponibilidade).

    Retorna:
      (problems, candidate_rows, dispatch_summary, stage_1_str, stage_2_str, stage_3_str)
    """
    if evidence_model_map is None:
        evidence_model_map = derive_evidence_model_map()

    problems: List[str] = []
    rows: List[Tuple[Any, ...]] = []

    # =========================================================================
    # ESTÁGIO 1: CONFERÊNCIA MECÂNICA
    # =========================================================================
    schema_errors = validate_schema_structure(d)
    problems.extend(schema_errors)

    for k in ("story_id", "phase", "context_revision", "catalog_revision"):
        if d.get(k) != expected.get(k):
            problems.append(f"{k}: esperado {expected.get(k)!r}, obtido {d.get(k)!r}")

    expected_roles = set(expected.get("roles", []))
    actual_roles = set(d.get("roles", {}).keys())
    if actual_roles != expected_roles:
        problems.append(f"papéis: esperado {sorted(expected_roles)}, obtido {sorted(actual_roles)}")

    local_id_keys = set(expected.get("local_ids", {}).keys())
    proxy_id_keys = set(expected.get("proxy_ids", {}).keys())
    families = expected.get("families", {})
    authors = set(expected.get("authors", []))
    policy = expected.get("policy", "preferred")
    availability = expected.get("availability", {})

    for role, r in d.get("roles", {}).items():
        chain = expected.get("chains", {}).get(role, [])
        cand_harnesses = [c.get("harness") for c in r.get("candidates", [])]
        if cand_harnesses != chain:
            problems.append(f"{role}: ordem de harness {cand_harnesses} ≠ cadeia esperada {chain}")

        for idx, c in enumerate(r.get("candidates", [])):
            c_harness = c.get("harness")
            c_model = c.get("model")
            c_effort = c.get("effort")
            c_reason = c.get("reason")
            key = (c_harness, c_model, c_effort)
            ev = set(c.get("evidence_ids", []))
            cb = c.get("cost_basis")

            # Verificação de nulidade inconsistente (R2: schema e contrato exigem model null sse effort null)
            if (c_model is None) != (c_effort is None):
                problems.append(
                    f"{role} {key}: nulidade inconsistente (model é null se e somente se effort é null; "
                    f"obtido model={c_model!r}, effort={c_effort!r})"
                )

            is_lacuna = (c_model is None and c_effort is None)
            is_suspicious_lacuna = False

            if is_lacuna:
                # Lacuna declarada: reason não vazio obrigatório
                if not (isinstance(c_reason, str) and c_reason.strip()):
                    problems.append(
                        f"{role} candidato {idx+1}: lacuna declarada com model:null e effort:null exige 'reason' não vazio explicativo"
                    )

                # Verifica se há par autorizado no catálogo para este harness e papel
                harness_has_authorized_pair = any(
                    k[0] == c_harness and role in cat.get(k, set()) for k in cat
                )

                if idx == 0 and harness_has_authorized_pair:
                    eligibility_str = "lacuna suspeita de normalizar escolha inválida"
                    is_suspicious_lacuna = True
                else:
                    eligibility_str = "lacuna: sem opção adequada no harness"

                in_cat = False
                unknown = set()
                unrelated_evs = []
                cb_ok = (cb == "unknown" and not ev)
                pin_ok = (expected.get("pins", {}).get(role) is None) or (idx > 0)
                cand_ok = bool(c_reason and c_reason.strip()) and cb_ok

                rows.append(
                    (
                        role,
                        key,
                        in_cat,
                        sorted(unknown),
                        cb,
                        cb_ok,
                        pin_ok,
                        eligibility_str,
                        cand_ok,
                    )
                )

                if not cb_ok:
                    problems.append(
                        f"{role} candidato {idx+1} (lacuna): cost_basis deve ser 'unknown' e evidence_ids vazio, obtido cb={cb}, ev={sorted(ev)}"
                    )

            else:
                in_cat = role in cat.get(key, set())
                unknown = ev - ids - local_id_keys

                # Pertinência mecânica por modelo (R3-a)
                cand_model = c_model
                cand_kw = MODEL_KEYWORD_MAP.get(cand_model)
                unrelated_evs = []
                for e in ev:
                    if e in evidence_model_map:
                        pertinent_kws = evidence_model_map[e]
                        if cand_kw and cand_kw not in pertinent_kws:
                            unrelated_evs.append(e)

                price = any(e in price_ids for e in ev)
                proxy = ev & proxy_id_keys & task_proxy_ids
                local = ev & local_id_keys

                cb_ok = {
                    "unknown": not (price or proxy or local),
                    "token_price_only": price and not proxy and not local,
                    "official_task_proxy": bool(proxy),
                    "local_observed": bool(local),
                }.get(cb, False)

                pin = expected.get("pins", {}).get(role)
                pin_ok = (pin is None) or (list(key) == list(pin)) or (idx > 0)

                fam = families.get(c_model)
                if fam is None:
                    eligibility_str = "família não resolvida (exige conferência)"
                elif role == "checker" and fam in authors:
                    if policy == "required":
                        eligibility_str = "inelegível(required, mesma família)"
                    else:
                        eligibility_str = "elegível só com indisponibilidade comprovada (fallback)"
                else:
                    eligibility_str = "elegível"

                cand_ok = in_cat and not unknown and not unrelated_evs and cb_ok and pin_ok and (c_effort is not None)
                rows.append(
                    (
                        role,
                        key,
                        in_cat,
                        sorted(unknown),
                        cb,
                        cb_ok,
                        pin_ok,
                        eligibility_str,
                        cand_ok,
                    )
                )

                if unrelated_evs:
                    for uev in sorted(unrelated_evs):
                        problems.append(
                            f"{role} {key}: evidence_id '{uev}' não pertinente ao modelo '{cand_model}' "
                            f"(modelos pertinentes: {sorted(evidence_model_map.get(uev, set()))}, modelo do candidato: '{cand_kw}')"
                        )

                if not cand_ok and not unrelated_evs:
                    problems.append(
                        f"{role} {key}: catálogo={in_cat} ids_desconhecidos={sorted(unknown)} "
                        f"cost_basis={cb} sustentado={cb_ok} pin={pin_ok}"
                    )

    if problems:
        stage_1_str = "REJEITADA"
        stage_2_str = "N/A"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado no gate de conferência mecânica)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    stage_1_str = "APROVADA"

    # =========================================================================
    # ESTÁGIO 2: JULGAMENTO REGISTRADO (R3-b)
    # =========================================================================
    judgment = expected.get("judgment")
    if not judgment:
        stage_2_str = "PENDENTE (aguardando julgamento)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (aceita mecanicamente; despacho não liberado (aguardando julgamento))"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    j_source = judgment.get("source") if isinstance(judgment, dict) else str(judgment)
    if not j_source or not ("#" in j_source or ":" in j_source):
        stage_2_str = "PENDENTE (registro de julgamento sem procedência válida (# ou :): pendente)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado: julgamento pendente)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    if "#" in j_source:
        j_rel_path, j_target_anchor = j_source.split("#", 1)
        j_rel_path = j_rel_path.strip()
        j_target_anchor = j_target_anchor.strip()
        j_is_anchor = True
    else:
        j_rel_path, j_line_part = j_source.split(":", 1)
        j_rel_path = j_rel_path.strip()
        j_line_part = j_line_part.strip().lstrip("L")
        j_is_anchor = False

    j_file = base_dir / j_rel_path
    if not j_file.exists():
        stage_2_str = f"PENDENTE (arquivo de julgamento '{j_rel_path}' não existe: localização inexistente)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado: julgamento pendente)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    j_lines = j_file.read_text(encoding="utf-8").splitlines()
    j_search_text = ""

    if j_is_anchor:
        j_headings: List[Tuple[int, int, str, str]] = []
        j_occ: Dict[str, int] = {}
        for idx, line in enumerate(j_lines):
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                bs = github_slug(title)
                cnt = j_occ.get(bs, 0)
                j_occ[bs] = cnt + 1
                sl = bs if cnt == 0 else f"{bs}-{cnt}"
                j_headings.append((idx, level, sl, title))

        j_pos = -1
        for pos, (idx, level, sl, title) in enumerate(j_headings):
            if sl == j_target_anchor:
                j_pos = pos
                break

        if j_pos == -1:
            stage_2_str = f"PENDENTE (âncora '#{j_target_anchor}' não encontrada em '{j_rel_path}': localização inexistente)"
            stage_3_str = "NENHUM"
            dispatch_result = "nenhum (bloqueado: julgamento pendente)"
            return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

        j_start = j_headings[j_pos][0] + 1
        j_target_level = j_headings[j_pos][1]
        j_end = len(j_lines)
        for next_idx, next_level, _, _ in j_headings[j_pos + 1:]:
            if next_level <= j_target_level:
                j_end = next_idx
                break
        j_search_text = "\n".join(j_lines[j_start:j_end])

    else:
        try:
            j_line_num = int(j_line_part)
        except ValueError:
            stage_2_str = f"PENDENTE (linha inválida '{j_line_part}': localização inexistente)"
            stage_3_str = "NENHUM"
            dispatch_result = "nenhum (bloqueado: julgamento pendente)"
            return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

        if j_line_num < 1 or j_line_num > len(j_lines):
            stage_2_str = f"PENDENTE (linha {j_line_num} inexistente em '{j_rel_path}': localização inexistente)"
            stage_3_str = "NENHUM"
            dispatch_result = "nenhum (bloqueado: julgamento pendente)"
            return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

        j_search_text = "\n".join(j_lines[j_line_num - 1: min(len(j_lines), j_line_num + 30)])

    # Extração literal dos três campos vinculados
    m_for = re.search(r"^\s*judgment_for:\s*([a-f0-9]{64})\s*$", j_search_text, re.M)
    m_verdict = re.search(r"^\s*judgment_verdict:\s*([a-zA-Zçãéóíá]+)\s*$", j_search_text, re.M)
    m_inputs = re.search(r"^\s*judged_inputs:\s*([a-f0-9]{64})\s*$", j_search_text, re.M)

    if not (m_for and m_verdict and m_inputs):
        stage_2_str = f"PENDENTE (registro de julgamento em '{j_source}' não contém bloco formal judgment_for/judgment_verdict/judged_inputs)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado: julgamento pendente)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    target_obj_hash = m_for.group(1)
    target_verdict = m_verdict.group(1).strip().lower()
    target_inputs_hash = m_inputs.group(1)

    actual_d_hash = hashlib.sha256(
        json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    actual_exp_hash = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    expected_without_judgment = {k: v for k, v in expected.items() if k != "judgment"}
    actual_exp_no_j_hash = hashlib.sha256(
        json.dumps(expected_without_judgment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    hashes_match = (target_obj_hash == actual_d_hash) and (
        target_inputs_hash in (actual_exp_hash, actual_exp_no_j_hash)
    )

    if not hashes_match:
        stage_2_str = "PENDENTE (julgamento não se aplica a este objeto: pendente)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado: julgamento não se aplica a este objeto: pendente)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    if target_verdict != "aprovado":
        stage_2_str = f"REJEITADO (registro de julgamento com veredito '{target_verdict}': não liberado)"
        stage_3_str = "NENHUM"
        problems.append(f"julgamento com veredito '{target_verdict}': não liberado")
        dispatch_result = "nenhum (bloqueado no gate de julgamento: veredito rejeitado)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    stage_2_str = "CONFIRMADO"

    # =========================================================================
    # ESTÁGIO 3: LIBERAÇÃO DE DESPACHO E RESOLUÇÃO DE FALLBACK (R3/R4/R5)
    # =========================================================================
    dispatched_cands: List[str] = []
    dispatch_blocked_reason: Optional[str] = None

    for role, r in d.get("roles", {}).items():
        role_dispatched: Optional[str] = None

        # R2: Verifica se há lacuna suspeita de normalizar escolha inválida (candidato 1 com pares autorizados no catálogo)
        has_suspicious_lacuna = any(
            (c.get("model") is None and c.get("effort") is None and c_idx == 0 and any(k[0] == c.get("harness") and role in cat.get(k, set()) for k in cat))
            for c_idx, c in enumerate(r.get("candidates", []))
        )
        if has_suspicious_lacuna:
            first_c = r.get("candidates", [{}])[0]
            dispatch_blocked_reason = (
                f"bloqueado com ponto de retomada: lacuna suspeita de normalizar escolha inválida no candidato 1 "
                f"({role}: {first_c.get('harness')}) exige julgamento prévio"
            )
            break

        # R2: Pula candidatos que são lacunas declaradas (model: null e effort: null)
        candidates_to_resolve = [
            c for c in r.get("candidates", [])
            if not (c.get("model") is None and c.get("effort") is None)
        ]

        if role == "checker":
            unresolved_cands = [c for c in candidates_to_resolve if c.get("model") not in families]
            if unresolved_cands:
                unres_models = [c.get("model") for c in unresolved_cands]
                dispatch_blocked_reason = (
                    f"bloqueado com ponto de retomada: família não resolvida para modelo(s) {unres_models} "
                    f"(exige conferência antes da escolha)"
                )
                break

            distinct_cands = [c for c in candidates_to_resolve if families.get(c.get("model")) not in authors]
            for c in distinct_cands:
                cand_id = f"{c.get('harness')}/{c.get('model')}"
                cand_avail = availability.get(cand_id, {})
                stat = cand_avail.get("status", "available") if isinstance(cand_avail, dict) else cand_avail
                if stat == "available":
                    role_dispatched = f"{c.get('harness')}/{c.get('model')}/{c.get('effort')}"
                    break

            if role_dispatched is None:
                if policy == "required":
                    dispatch_blocked_reason = (
                        "bloqueado com ponto de retomada: nenhum candidato elegível sob required "
                        "(todas as famílias são autoras ou indisponíveis)"
                    )
                elif policy == "preferred":
                    all_proven_unavailable = True
                    unavail_error: Optional[str] = None

                    if not distinct_cands:
                        all_proven_unavailable = False
                        unavail_error = "ausência de candidatos de família distinta para comprovação"
                    else:
                        for dc in distinct_cands:
                            dc_id = f"{dc.get('harness')}/{dc.get('model')}"
                            dc_avail = availability.get(dc_id)
                            proof_err = verify_unavailability_proof(
                                dc.get("harness"), dc.get("model"), dc_avail, base_dir
                            )
                            if proof_err:
                                all_proven_unavailable = False
                                unavail_error = proof_err
                                break

                    if all_proven_unavailable:
                        same_family_cands = [c for c in candidates_to_resolve if families.get(c.get("model")) in authors]
                        selected_fallback = None
                        fallback_block_cause = None

                        for c in same_family_cands:
                            cand_id = f"{c.get('harness')}/{c.get('model')}"
                            cand_avail = availability.get(cand_id, {})
                            c_stat = cand_avail.get("status", "available") if isinstance(cand_avail, dict) else str(cand_avail)

                            if c_stat == "disabled":
                                fallback_block_cause = f"candidato de mesma família '{cand_id}' marcado disabled"
                                continue
                            elif c_stat == "unknown":
                                fallback_block_cause = f"candidato de mesma família '{cand_id}' com status unknown"
                                continue
                            elif c_stat == "available":
                                selected_fallback = c
                                break

                        if selected_fallback:
                            role_dispatched = (
                                f"{selected_fallback.get('harness')}/{selected_fallback.get('model')}/"
                                f"{selected_fallback.get('effort')} (fallback: same_family_fresh_session)"
                            )
                        else:
                            dispatch_blocked_reason = (
                                f"bloqueado com ponto de retomada: fallback de mesma família sob preferred não liberado "
                                f"({fallback_block_cause or 'nenhum candidato de mesma família disponível'})"
                            )
                    else:
                        dispatch_blocked_reason = (
                            f"bloqueado com ponto de retomada: fallback de mesma família sob preferred "
                            f"exige prova de indisponibilidade dos candidatos de família distinta ({unavail_error})"
                        )

        else:
            for c in candidates_to_resolve:
                cand_id = f"{c.get('harness')}/{c.get('model')}"
                cand_avail = availability.get(cand_id, {})
                stat = cand_avail.get("status", "available") if isinstance(cand_avail, dict) else cand_avail
                if stat == "available":
                    role_dispatched = f"{c.get('harness')}/{c.get('model')}/{c.get('effort')}"
                    break
            if role_dispatched is None:
                dispatch_blocked_reason = f"nenhum candidato disponível para o papel '{role}'"

        if role_dispatched:
            dispatched_cands.append(f"{role}:{role_dispatched}")

    if dispatched_cands:
        stage_3_str = "LIBERADO"
        dispatch_result = ", ".join(dispatched_cands)
    else:
        stage_3_str = "BLOQUEADO"
        reason_txt = dispatch_blocked_reason or "nenhum candidato elegível despachado"
        dispatch_result = f"nenhum ({reason_txt})"

    return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str


def run_self_test(
    cases_dir: pathlib.Path = pathlib.Path("_tl-orc/project/evidence/T009-cases"),
    write_summary: bool = False,
) -> int:
    """Modo --self-test que reproduz o piloto e compara em memória com pilot_summary.json (R6)."""
    print("=== T009 MECHANICAL CHECK: INÍCIO DO SELF-TEST (REWORK ROUND 5) ===")
    cat = catalog_from_project()
    official_ids, price_ids, task_proxy_ids = parse_routing_evidence()
    evidence_model_map = derive_evidence_model_map()

    proxy_quals = derive_task_proxies()
    print("\n=== QUALIFICAÇÃO VERIFICÁVEL DE CARTÕES PROXY ECONÔMICO (R2) ===")
    print("Cartões que qualificaram como 'official_task_proxy' por afirmação de custo por tarefa:")
    for cid, phrase in sorted(proxy_quals.items()):
        print(f"  - '{cid}': \"{phrase}\"")
    print("Cartões que NÃO qualificaram (sem custo por tarefa): astra-domain, gpt56-coding, opus-effort, sonnet-effort.")

    print("\n=== DERIVAÇÃO DE PERTINÊNCIA DE EVIDÊNCIAS POR MODELO (R3-a) ===")
    for eid, mods in sorted(evidence_model_map.items()):
        print(f"  - '{eid}': modelos pertinentes {sorted(mods)}")

    print("\n[Teste de Robustez A] ID local com caminho inexistente:")
    bad_local = {"local-fake": {"source": "_tl-orc/project/evidence/arquivo-fantasma.md#L1"}}
    try:
        validate_id_entries_with_provenance(bad_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado caminho inexistente!")
        return 1
    except FileNotFoundError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez B] Lista de IDs passada 'na hora' sem origem:")
    bad_bare_list = ["price-astra", "local-fake"]
    try:
        validate_id_entries_with_provenance(bad_bare_list, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado lista sem procedência!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez C] ID local em docs/MODEL_ROUTING.md (R1):")
    bad_routing_local = {"sonnet-effort": {"source": "docs/MODEL_ROUTING.md#ancora-inexistente"}}
    try:
        validate_id_entries_with_provenance(bad_routing_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado MODEL_ROUTING.md como fonte local!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez D] ID local no protótipo com linha inexistente (R1):")
    bad_prototype_local = {"local-fake": {"source": "_tl-orc/project/evidence/T009-mechanical-check.py:999999"}}
    try:
        validate_id_entries_with_provenance(bad_prototype_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado protótipo como fonte local!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez E] ID local legítimo apontando para tabela Agent runs em T005-r01.md:16 (R1):")
    good_local = {"T005-r01-checker-1": {"source": "_tl-orc/project/evidence/T005-r01.md:16"}}
    try:
        val_local = validate_id_entries_with_provenance(good_local, "local_ids", pathlib.Path("."))
        if "T005-r01-checker-1" in val_local:
            print("SUCESSO (aceitação esperada): ID local registrado e localizado com sucesso na tabela Agent runs.")
        else:
            print("FALHA: ID local não retornado!")
            return 1
    except Exception as e:
        print(f"FALHA: recusou ID local legítimo: {e}")
        return 1

    print("\n[Teste de Robustez F] Declaração indevida de astra-domain como proxy (R2):")
    bad_astra_proxy = {"astra-domain": {"source": "docs/MODEL_ROUTING.md#astra-domain--sinais-específicos-não-ranking-de-revisão"}}
    try:
        validate_id_entries_with_provenance(bad_astra_proxy, "proxy_ids", pathlib.Path("."), task_proxy_ids)
        print("FALHA: deveria ter recusado astra-domain em proxy_ids!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez G] ID local fabricado em arquivo JSON de caso (R1):")
    bad_json_local = {"local-fake": {"source": "_tl-orc/project/evidence/T009-cases/expected_r2_unregistered_local_id.json:55"}}
    try:
        validate_id_entries_with_provenance(bad_json_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado ID local em arquivo de caso JSON!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez H] ID local fabricado em T009-analysis.md (R1):")
    bad_analysis_local = {"local-fake": {"source": "_tl-orc/project/evidence/T009-analysis.md:181"}}
    try:
        validate_id_entries_with_provenance(bad_analysis_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado ID local em T009-analysis.md!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez I] Âncora declarada por prefixo em T009-classification.md (R2):")
    bad_anchor_prefix = {"local-t005-checker-astra": {"source": "_tl-orc/project/evidence/T009-classification.md#conferência-mecânica-pelo"}}
    try:
        validate_id_entries_with_provenance(bad_anchor_prefix, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado âncora declarada por prefixo!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez J] Âncora exata completa em T009-classification.md (R2):")
    try:
        c_lines = (pathlib.Path(".") / "_tl-orc/project/evidence/T009-classification.md").read_text(encoding="utf-8").splitlines()
        found_exact = False
        occ: Dict[str, int] = {}
        for l in c_lines:
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", l)
            if m:
                bs = github_slug(m.group(2).strip())
                cnt = occ.get(bs, 0)
                occ[bs] = cnt + 1
                sl = bs if cnt == 0 else f"{bs}-{cnt}"
                if sl == "conferência-mecânica-pelo-orquestrador":
                    found_exact = True
                    break
        if found_exact:
            print("SUCESSO (aceitação esperada): âncora exata '#conferência-mecânica-pelo-orquestrador' validada com sucesso.")
        else:
            print("FALHA: âncora exata não localizada!")
            return 1
    except Exception as e:
        print(f"FALHA na verificação de âncora exata: {e}")
        return 1

    # Carregar caso válido para sondas de julgamento e pertinência
    c1_doc = json.loads((cases_dir / "case_01_valid.json").read_text(encoding="utf-8"))
    c1_raw_exp = json.loads((cases_dir / "expected_t005_review.json").read_text(encoding="utf-8"))
    c1_exp = unwrap_expected(c1_raw_exp, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)

    print("\n[Teste de Robustez K] Evidência não pertinente ao modelo (Astra com flash-deepswe) (R3-a):")
    test_d_k = json.loads(json.dumps(c1_doc))
    test_d_k["roles"]["checker"]["candidates"][0]["evidence_ids"] = ["price-astra", "transport-openai", "flash-deepswe"]
    probs_k, _, disp_k, s1_k, _, _ = check_classification(test_d_k, c1_exp, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map)
    if s1_k == "REJEITADA" and any("flash-deepswe" in p and "não pertinente" in p for p in probs_k) and disp_k.startswith("nenhum"):
        print(f"SUCESSO (recusa esperada): candidato Astra com flash-deepswe rejeitado mecanicamente: {probs_k[0]}")
    else:
        print(f"FALHA: Astra com flash-deepswe não foi rejeitado corretamente! s1={s1_k} probs={probs_k}")
        return 1

    print("\n[Teste de Robustez L] Objeto alterado com mesmo registro de julgamento (R3-b):")
    test_d_l = json.loads(json.dumps(c1_doc))
    test_d_l["facts"].append("Fato alterado para teste de divergência de hash.")
    probs_l, _, disp_l, s1_l, s2_l, s3_l = check_classification(test_d_l, c1_exp, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map)
    if s2_l.startswith("PENDENTE") and "julgamento não se aplica a este objeto: pendente" in s2_l and disp_l.startswith("nenhum"):
        print(f"SUCESSO (bloqueio esperado): objeto alterado resultou em julgamento pendente: {s2_l}")
    else:
        print(f"FALHA: objeto alterado não resultou em pendente! s2={s2_l}, disp={disp_l}")
        return 1

    print("\n[Teste de Robustez M] Registro de julgamento com veredito rejeitado (R3-b):")
    test_exp_m = json.loads(json.dumps(c1_raw_exp))
    test_exp_m["judgment"] = {"source": "_tl-orc/project/evidence/T009-cases/judgment_case_30_rejected.md#julgamento-do-orquestrador"}
    test_exp_m_unw = unwrap_expected(test_exp_m, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
    probs_m, _, disp_m, s1_m, s2_m, s3_m = check_classification(c1_doc, test_exp_m_unw, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map)
    if s2_m.startswith("REJEITADO") and "não liberado" in s2_m and disp_m.startswith("nenhum"):
        print(f"SUCESSO (bloqueio esperado): julgamento com veredito rejeitado não liberado: {s2_m}")
    else:
        print(f"FALHA: julgamento com veredito rejeitado não bloqueou despacho! s2={s2_m}, disp={disp_m}")
        return 1

    print("\n[Teste de Robustez N] Registro de julgamento com localização inexistente (:999999) (R3-b):")
    test_exp_n = json.loads(json.dumps(c1_raw_exp))
    test_exp_n["judgment"] = {"source": "_tl-orc/project/evidence/T005-classification.md:999999"}
    test_exp_n_unw = unwrap_expected(test_exp_n, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
    probs_n, _, disp_n, s1_n, s2_n, s3_n = check_classification(c1_doc, test_exp_n_unw, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map)
    if s2_n.startswith("PENDENTE") and "linha 999999 inexistente" in s2_n and disp_n.startswith("nenhum"):
        print(f"SUCESSO (bloqueio esperado): localização inexistente resultou em julgamento pendente: {s2_n}")
    else:
        print(f"FALHA: localização inexistente não resultou em pendente! s2={s2_n}, disp={disp_n}")
        return 1

    print("\n[Teste de Robustez O] Lista solta sem envelope para roles em expected (R1):")
    bad_exp_bare_roles = json.loads(json.dumps(c1_raw_exp))
    bad_exp_bare_roles["roles"] = ["checker"]
    try:
        unwrap_expected(bad_exp_bare_roles, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
        print("FALHA: deveria ter recusado lista solta para 'roles' em expected!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez P] Procedência de roles apontando para arquivo inexistente (R1):")
    bad_exp_nonexistent = json.loads(json.dumps(c1_raw_exp))
    bad_exp_nonexistent["roles"] = {"value": ["checker"], "source": "arquivo-inexistente.md#inventado"}
    try:
        unwrap_expected(bad_exp_nonexistent, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
        print("FALHA: deveria ter recusado arquivo de procedência inexistente!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez Q] Cadeia declarada divergente da tabela de PROJECT.md (R1):")
    bad_exp_divergent_chain = json.loads(json.dumps(c1_raw_exp))
    bad_exp_divergent_chain["chains"] = {
        "checker": {
            "value": ["agy", "codex", "claude"],
            "source": "_tl-orc/PROJECT.md#cadeias-preferência-operacional-fallbacks-autorizados-preservados",
        }
    }
    try:
        unwrap_expected(bad_exp_divergent_chain, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
        print("FALHA: deveria ter recusado cadeia divergente da tabela de PROJECT.md!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    print("\n[Teste de Robustez R] 3º candidato com model:null e effort:null com reason (lacuna legítima) (R2):")
    c35_doc = json.loads((cases_dir / "case_35_r2_null_candidate_lacuna.json").read_text(encoding="utf-8"))
    c35_raw_exp = json.loads((cases_dir / "expected_r2_null_candidate_lacuna.json").read_text(encoding="utf-8"))
    c35_exp = unwrap_expected(c35_raw_exp, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
    probs_r, rows_r, disp_r, s1_r, s2_r, s3_r = check_classification(
        c35_doc, c35_exp, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map
    )
    lacuna_row_r = [r for r in rows_r if r[0] == "checker" and r[1] == ("agy", None, None)]
    if (
        s1_r == "APROVADA"
        and s2_r == "CONFIRMADO"
        and s3_r == "LIBERADO"
        and lacuna_row_r
        and lacuna_row_r[0][7] == "lacuna: sem opção adequada no harness"
        and lacuna_row_r[0][8] is True
        and "checker:codex/gpt-6-astra/high" in disp_r
    ):
        print(f"SUCESSO (aceitação esperada de lacuna legítima): s1={s1_r}, s2={s2_r}, s3={s3_r}, disp={disp_r}")
    else:
        print(f"FALHA: lacuna legítima não foi tratada corretamente! s1={s1_r}, s2={s2_r}, s3={s3_r}, disp={disp_r}")
        return 1

    print("\n[Teste de Robustez S] Candidato com nulidade inconsistente (model: null e effort: 'high') (R2):")
    test_d_s = json.loads(json.dumps(c1_doc))
    test_d_s["roles"]["checker"]["candidates"][2]["model"] = None
    test_d_s["roles"]["checker"]["candidates"][2]["effort"] = "high"
    probs_s, _, disp_s, s1_s, _, _ = check_classification(
        test_d_s, c1_exp, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map
    )
    if s1_s == "REJEITADA" and any("nulidade inconsistente" in p for p in probs_s) and disp_s.startswith("nenhum"):
        print(f"SUCESSO (recusa esperada): nulidade inconsistente rejeitada mecanicamente: {probs_s[0]}")
    else:
        print(f"FALHA: nulidade inconsistente não foi rejeitada! s1={s1_s}, probs={probs_s}")
        return 1

    print("\n[Teste de Robustez T] 1º candidato com model:null e effort:null havendo par no catálogo (lacuna suspeita) (R2):")
    c37_doc = json.loads((cases_dir / "case_37_r2_suspicious_first_cand_lacuna.json").read_text(encoding="utf-8"))
    c37_raw_exp = json.loads((cases_dir / "expected_r2_suspicious_first_cand_lacuna.json").read_text(encoding="utf-8"))
    c37_exp = unwrap_expected(c37_raw_exp, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
    probs_t, rows_t, disp_t, s1_t, s2_t, s3_t = check_classification(
        c37_doc, c37_exp, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map
    )
    lacuna_row_t = [r for r in rows_t if r[0] == "checker" and r[1] == ("codex", None, None)]
    if (
        s1_t == "APROVADA"
        and s2_t == "CONFIRMADO"
        and s3_t == "BLOQUEADO"
        and lacuna_row_t
        and lacuna_row_t[0][7] == "lacuna suspeita de normalizar escolha inválida"
        and "lacuna suspeita de normalizar escolha inválida" in disp_t
    ):
        print(f"SUCESSO (bloqueio esperado de lacuna suspeita): s1={s1_t}, s2={s2_t}, s3={s3_t}, disp={disp_t}")
    else:
        print(f"FALHA: lacuna suspeita não foi bloqueada corretamente! s1={s1_t}, s2={s2_t}, s3={s3_t}, disp={disp_t}")
        return 1

    cases_manifest = [
        {
            "id": "case_01_valid",
            "name": "Caso válido real (T005 review classification sob restrição required)",
            "file": "case_01_valid.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "nenhuma (objeto íntegro adotado em T005 review sob restrição required e julgamento confirmado)",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_02_invalid_catalog",
            "name": "Alteração (i): Par fora do catálogo",
            "file": "case_02_invalid_catalog.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "candidato 2 trocado para claude/claude-opus-5/medium (fora do catálogo de Checker)",
            "should_pass": False,
            "expected_reason_substr": "catálogo=False",
        },
        {
            "id": "case_03_invalid_story_id",
            "name": "Alteração (ii): story_id indevido (esperado 'T005', obtido null)",
            "file": "case_03_invalid_story_id.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "story_id preenchido com null quando briefing exigia 'T005'",
            "should_pass": False,
            "expected_reason_substr": "story_id: esperado 'T005', obtido None",
        },
        {
            "id": "case_03b_invalid_story_id_null",
            "name": "Alteração (ii-b): story_id indevido inverso (esperado null, obtido 'T005')",
            "file": "case_03b_invalid_story_id_null.json",
            "expected_file": "expected_null_story.json",
            "alteration": "story_id preenchido com 'T005' quando briefing exigia null (smoke platform v0.5.0 r3)",
            "should_pass": False,
            "expected_reason_substr": "story_id: esperado None, obtido 'T005'",
        },
        {
            "id": "case_04_invalid_evidence_id",
            "name": "Alteração (iii): ID de evidência inexistente",
            "file": "case_04_invalid_evidence_id.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "candidato 3 cita 'price-gemini-pro' (não existe em MODEL_ROUTING)",
            "should_pass": False,
            "expected_reason_substr": "ids_desconhecidos=['price-gemini-pro']",
        },
        {
            "id": "case_05_incompatible_evidence",
            "name": "Alteração (iv): Evidência existente sustentando conclusão incompatível",
            "file": "case_05_incompatible_evidence.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "candidato 2 sonnet com cost_basis official_task_proxy sustentado só por sonnet-effort",
            "should_pass": False,
            "expected_reason_substr": "cost_basis=official_task_proxy sustentado=False",
        },
        {
            "id": "case_06_control_preserved_rules",
            "name": "Controle: Regras preservadas (mesma família sob preferred + unknown com [])",
            "file": "case_06_control_preserved_rules.json",
            "expected_file": "expected_control_preferred.json",
            "alteration": "controle: agy Google sob preferred marcado elegível como fallback; cost_basis unknown com [] aceito",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_07_r2_unregistered_local_id",
            "name": "Controle R2: ID local fabricado em arquivo fora de evidence",
            "file": "case_07_r2_unregistered_local_id.json",
            "expected_file": "expected_r2_unregistered_local_id.json",
            "alteration": "controle R2: expected declara local-fake com source README.md (fora de evidence)",
            "should_pass": False,
            "expected_reason_substr": "só é aceito em arquivo de evidência",
        },
        {
            "id": "case_08_r2_invalid_proxy_card",
            "name": "Controle R2: Cartão de capacidade (sonnet-effort) declarado como proxy econômico",
            "file": "case_08_r2_invalid_proxy_card.json",
            "expected_file": "expected_r2_invalid_proxy_card.json",
            "alteration": "controle R2: expected declara sonnet-effort em proxy_ids, mas cartão não contém custo por tarefa",
            "should_pass": False,
            "expected_reason_substr": "não contém comprovação de custo por tarefa",
        },
        {
            "id": "case_09_r2_official_marker_as_evidence",
            "name": "Controle R2: Marcador documental 'official-2026-09-05' citado como evidence_id",
            "file": "case_09_r2_official_marker_as_evidence.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "controle R2: candidato 1 cita marcador de revisão documental official-2026-09-05 como evidência",
            "should_pass": False,
            "expected_reason_substr": "ids_desconhecidos=['official-2026-09-05']",
        },
        {
            "id": "case_10_r3_missing_candidate_reason",
            "name": "Controle R3: Candidato sem campo obrigatório 'reason'",
            "file": "case_10_r3_missing_candidate_reason.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "controle R3: candidato 1 sem a propriedade obrigatória 'reason'",
            "should_pass": False,
            "expected_reason_substr": "faltando campo obrigatório 'reason'",
        },
        {
            "id": "case_11_r3_empty_facts",
            "name": "Controle R3: Lista de fatos vazia ('facts: []')",
            "file": "case_11_r3_empty_facts.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "controle R3: array 'facts' vazio violando minItems: 1",
            "should_pass": False,
            "expected_reason_substr": "minItems: 1",
        },
        {
            "id": "case_12_r3_extra_property",
            "name": "Controle R3: Propriedade adicional proibida por additionalProperties: false",
            "file": "case_12_r3_extra_property.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "controle R3: objeto raiz com propriedade extra não permitida 'extra_property'",
            "should_pass": False,
            "expected_reason_substr": "propriedade adicional não permitida 'extra_property'",
        },
        {
            "id": "case_13_r4_preferred_unproven_fallback",
            "name": "Controle R4: Fallback de mesma família sob preferred sem prova de indisponibilidade",
            "file": "case_13_r4_preferred_unproven_fallback.json",
            "expected_file": "expected_r4_preferred_unproven_fallback.json",
            "alteration": "controle R4: candidatos de família distinta sem disponibilidade comprovada (status unknown / sem prova)",
            "should_pass": False,
            "expected_reason_substr": "candidato 'codex/gpt-6-astra' com status 'unknown'",
        },
        {
            "id": "case_14_r4_preferred_proven_fallback",
            "name": "Controle R4: Fallback de mesma família sob preferred com indisponibilidade comprovada",
            "file": "case_14_r4_preferred_proven_fallback.json",
            "expected_file": "expected_r4_preferred_proven_fallback.json",
            "alteration": "controle R4: candidatos distintos indisponíveis com erro literal comprovado em evidência sintética (R3 corrigido)",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_15_r4_required_same_family",
            "name": "Controle R5: Validade mecânica aprovada e resolução bloqueada sob required (validade ≠ resolução)",
            "file": "case_15_r4_required_same_family.json",
            "expected_file": "expected_r4_required_same_family.json",
            "alteration": "controle R5: ausência de candidato independente sob required resulta APROVADA na mecânica e BLOQUEADO no despacho",
            "should_pass": False,
            "expected_reason_substr": "nenhum candidato elegível sob required",
        },
        {
            "id": "case_16_r5_valid_without_judgment",
            "name": "Controle R5: Caso válido sem julgamento registrado (despacho não liberado)",
            "file": "case_16_r5_valid_without_judgment.json",
            "expected_file": "expected_r5_valid_without_judgment.json",
            "alteration": "controle R5: caso estruturalmente válido mas sem entrada judgment (aguardando julgamento)",
            "should_pass": False,
            "expected_reason_substr": "despacho não liberado (aguardando julgamento)",
        },
        {
            "id": "case_17_r1_local_routing_anchor",
            "name": "Controle R1: sonnet-effort declarado local com docs/MODEL_ROUTING.md#ancora-inexistente",
            "file": "case_17_r1_local_routing_anchor.json",
            "expected_file": "expected_r1_local_routing_anchor.json",
            "alteration": "sonda R1: registro local apontando para docs/MODEL_ROUTING.md com âncora inexistente",
            "should_pass": False,
            "expected_reason_substr": "só é aceito em arquivo de evidência sob '_tl-orc/project/evidence/' ou '_tl-orc/evidence/'",
        },
        {
            "id": "case_18_r1_local_prototype_line",
            "name": "Controle R1: local-fake declarado local com T009-mechanical-check.py:999999",
            "file": "case_18_r1_local_prototype_line.json",
            "expected_file": "expected_r1_local_prototype_line.json",
            "alteration": "sonda R1: registro local apontando para o próprio protótipo com linha inexistente",
            "should_pass": False,
            "expected_reason_substr": "nunca em docs/MODEL_ROUTING.md",
        },
        {
            "id": "case_19_r1_local_valid_reference",
            "name": "Controle R1: T005-r01-checker-1 registrado em linha de tabela de T005-r01.md:16",
            "file": "case_19_r1_local_valid_reference.json",
            "expected_file": "expected_r1_local_valid_reference.json",
            "alteration": "controle R1 positivo: medição local apontando para linha de tabela Agent runs real em arquivo de evidência",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_20_r2_astra_domain_proxy",
            "name": "Controle R2: astra-domain como única sustentação de official_task_proxy",
            "file": "case_20_r2_astra_domain_proxy.json",
            "expected_file": "expected_r2_astra_domain_proxy.json",
            "alteration": "sonda R2: cartão astra-domain (minutos por tarefa, sem custo) declarado como proxy",
            "should_pass": False,
            "expected_reason_substr": "não contém comprovação de custo por tarefa",
        },
        {
            "id": "case_21_r3_unproven_text_readme",
            "name": "Controle R3: Prova por texto sem erro ('tl-orchestrator' em README.md)",
            "file": "case_21_r3_unproven_text_readme.json",
            "expected_file": "expected_r3_unproven_text_readme.json",
            "alteration": "sonda R3: texto sem erro em README.md como suposta prova de indisponibilidade",
            "should_pass": False,
            "expected_reason_substr": "README ou outros arquivos não são registros de Agent runs",
        },
        {
            "id": "case_22_r3_timeout_as_proof",
            "name": "Controle R3: Timeout isolado fornecido como prova de indisponibilidade",
            "file": "case_22_r3_timeout_as_proof.json",
            "expected_file": "expected_r3_timeout_as_proof.json",
            "alteration": "sonda R3: erro de timeout isolado fornecido como prova (não aceito pelo contrato)",
            "should_pass": False,
            "expected_reason_substr": "timeout isolado, saída vazia ou processo vivo não comprovam indisponibilidade",
        },
        {
            "id": "case_23_r3_same_family_disabled",
            "name": "Controle R3: Candidato de mesma família marcado disabled na seleção de fallback",
            "file": "case_23_r3_same_family_disabled.json",
            "expected_file": "expected_r3_same_family_disabled.json",
            "alteration": "sonda R3: candidato de mesma família (Agy) marcado disabled sob fallback",
            "should_pass": False,
            "expected_reason_substr": "candidato de mesma família 'agy/gemini-3.1-pro-high' marcado disabled",
        },
        {
            "id": "case_24_r4_unresolved_family",
            "name": "Controle R4: Modelo gpt-6-astra removido do mapa de famílias sob required",
            "file": "case_24_r4_unresolved_family.json",
            "expected_file": "expected_r4_unresolved_family.json",
            "alteration": "sonda R4: candidato com família desconhecida/não resolvida bloqueia despacho sob required",
            "should_pass": False,
            "expected_reason_substr": "família não resolvida",
        },
        # --- Novos Controles Rework 4 (R1 a R3) ---
        {
            "id": "case_25_r1_local_json_case",
            "name": "Controle R1: ID local apontando para arquivo JSON de caso (fora de tabela estruturada)",
            "file": "case_25_r1_local_json_case.json",
            "expected_file": "expected_r1_local_json_case.json",
            "alteration": "sonda R1: candidato Astra com ID local-fake apontando para T009-cases/expected_r2_unregistered_local_id.json:55",
            "should_pass": False,
            "expected_reason_substr": "só é aceito em arquivo de evidência estruturada",
        },
        {
            "id": "case_26_r1_local_analysis",
            "name": "Controle R1: ID local apontando para T009-analysis.md (documento de análise)",
            "file": "case_26_r1_local_analysis.json",
            "expected_file": "expected_r1_local_analysis.json",
            "alteration": "sonda R1: candidato Astra com ID local-fake apontando para T009-analysis.md:181",
            "should_pass": False,
            "expected_reason_substr": "T009-analysis.md é documento de análise",
        },
        {
            "id": "case_27_r2_anchor_prefix",
            "name": "Controle R2: Âncora declarada por prefixo (#conferência-mecânica-pelo)",
            "file": "case_27_r2_anchor_prefix.json",
            "expected_file": "expected_r2_anchor_prefix.json",
            "alteration": "sonda R2: candidato Astra com procedência usando prefixo inexistente #conferência-mecânica-pelo",
            "should_pass": False,
            "expected_reason_substr": "não encontrada como título Markdown",
        },
        {
            "id": "case_28_r3_unrelated_model_evidence",
            "name": "Controle R3-a: Evidência de outro modelo (Astra com flash-deepswe)",
            "file": "case_28_r3_unrelated_model_evidence.json",
            "expected_file": "expected_r3_unrelated_model_evidence.json",
            "alteration": "sonda R3-a: candidato Astra com flash-deepswe como proxy em vez de astra-coding",
            "should_pass": False,
            "expected_reason_substr": "não pertinente ao modelo 'gpt-6-astra'",
        },
        {
            "id": "case_29_r3_altered_object_judgment",
            "name": "Controle R3-b: Objeto alterado com registro de julgamento do caso válido",
            "file": "case_29_r3_altered_object_judgment.json",
            "expected_file": "expected_r3_altered_object_judgment.json",
            "alteration": "sonda R3-b: objeto com candidato alterado submetido ao registro de julgamento de case_01 (hash divergente)",
            "should_pass": False,
            "expected_reason_substr": "julgamento não se aplica a este objeto: pendente",
        },
        {
            "id": "case_30_r3_rejected_judgment",
            "name": "Controle R3-b: Registro de julgamento com veredito rejeitado",
            "file": "case_30_r3_rejected_judgment.json",
            "expected_file": "expected_r3_rejected_judgment.json",
            "alteration": "sonda R3-b: registro de julgamento vinculado com judgment_verdict: rejeitado",
            "should_pass": False,
            "expected_reason_substr": "julgamento com veredito 'rejeitado': não liberado",
        },
        {
            "id": "case_31_r3_missing_judgment_location",
            "name": "Controle R3-b: Registro de julgamento com localização inexistente (:999999)",
            "file": "case_31_r3_missing_judgment_location.json",
            "expected_file": "expected_r3_missing_judgment_location.json",
            "alteration": "sonda R3-b: judgment com procedência T005-classification.md:999999 (linha inexistente)",
            "should_pass": False,
            "expected_reason_substr": "linha 999999 inexistente",
        },
        # --- Novos Controles Rework 5 (R1 e R2) ---
        {
            "id": "case_32_r1_bare_list_roles",
            "name": "Controle R1: Lista solta sem envelope para 'roles' em expected",
            "file": "case_32_r1_bare_list_roles.json",
            "expected_file": "expected_r1_bare_list_roles.json",
            "alteration": "sonda R1: roles fornecida como lista solta sem envelope de procedência",
            "should_pass": False,
            "expected_reason_substr": "lista solta sem envelope",
        },
        {
            "id": "case_33_r1_nonexistent_source",
            "name": "Controle R1: Procedência de 'roles' apontando para arquivo inexistente",
            "file": "case_33_r1_nonexistent_source.json",
            "expected_file": "expected_r1_nonexistent_source.json",
            "alteration": "sonda R1: roles com procedência apontando para arquivo-inexistente.md#inventado",
            "should_pass": False,
            "expected_reason_substr": "arquivo de procedência 'arquivo-inexistente.md'",
        },
        {
            "id": "case_34_r1_divergent_chain",
            "name": "Controle R1: Cadeia declarada divergente da tabela de PROJECT.md",
            "file": "case_34_r1_divergent_chain.json",
            "expected_file": "expected_r1_divergent_chain.json",
            "alteration": "sonda R1: cadeia declarada para checker [agy, codex, claude] diverge de PROJECT.md",
            "should_pass": False,
            "expected_reason_substr": "diverge da tabela de PROJECT.md",
        },
        {
            "id": "case_35_r2_null_candidate_lacuna",
            "name": "Controle R2: 3º candidato com model:null e effort:null com reason (lacuna legítima)",
            "file": "case_35_r2_null_candidate_lacuna.json",
            "expected_file": "expected_r2_null_candidate_lacuna.json",
            "alteration": "controle R2 positivo: agy como 3º candidato declarado como lacuna legítima de harness; despacha pin codex",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_36_r2_inconsistent_null",
            "name": "Controle R2: Nulidade inconsistente (model: null com effort preenchido)",
            "file": "case_36_r2_inconsistent_null.json",
            "expected_file": "expected_t005_review.json",
            "alteration": "sonda R2: candidato com model: null e effort: 'high' (nulidade inconsistente)",
            "should_pass": False,
            "expected_reason_substr": "nulidade inconsistente",
        },
        {
            "id": "case_37_r2_suspicious_first_cand_lacuna",
            "name": "Controle R2: 1º candidato com model:null/effort:null havendo par no catálogo (lacuna suspeita)",
            "file": "case_37_r2_suspicious_first_cand_lacuna.json",
            "expected_file": "expected_r2_suspicious_first_cand_lacuna.json",
            "alteration": "sonda R2: candidato 1 (codex) com model:null/effort:null havendo par no catálogo (resolução bloqueada)",
            "should_pass": False,
            "expected_reason_substr": "lacuna suspeita de normalizar escolha inválida",
        },
    ]

    print("\n" + "=" * 140)
    print(
        f"{'Caso':<38} | {'Mecânica':<9} | {'Julgamento':<11} | {'Despacho':<9} | {'Status':<10} | {'Despacho Simulado'}"
    )
    print("=" * 140)

    all_passed = True
    pilot_table_rows = []

    for cdef in cases_manifest:
        case_path = cases_dir / cdef["file"]
        exp_path = cases_dir / cdef["expected_file"]

        if not case_path.exists():
            print(f"ERRO: Arquivo do caso não encontrado: {case_path}")
            return 1
        if not exp_path.exists():
            print(f"ERRO: Arquivo expected não encontrado: {exp_path}")
            return 1

        doc = json.loads(case_path.read_text(encoding="utf-8"))
        raw_expected = json.loads(exp_path.read_text(encoding="utf-8"))

        try:
            expected = unwrap_expected(raw_expected, base_dir=pathlib.Path("."), task_proxy_ids=task_proxy_ids)
            problems, cand_rows, dispatch, s1, s2, s3 = check_classification(
                doc, expected, cat, official_ids, price_ids, task_proxy_ids, evidence_model_map
            )
        except (ValueError, FileNotFoundError) as e:
            err_msg = str(e)
            problems = [err_msg]
            cand_rows = []
            s1 = "REJEITADA"
            s2 = "N/A"
            s3 = "NENHUM"
            dispatch = "nenhum (bloqueado na procedência das entradas)"

        if problems:
            status_str = "REJEITADA"
            dispatch_str = "nenhum"
        elif s2.startswith("PENDENTE"):
            status_str = "ACEITA (aguardando julgamento)"
            dispatch_str = "nenhum"
        elif s3 == "BLOQUEADO":
            status_str = "BLOQUEADO"
            dispatch_str = "nenhum"
        else:
            status_str = "ACEITA"
            dispatch_str = dispatch

        motivos_str = "; ".join(problems) if problems else (
            dispatch if status_str in ("BLOQUEADO", "ACEITA (aguardando julgamento)")
            else "Conforme catálogo, schema, evidências e julgamento confirmado"
        )

        pilot_table_rows.append(
            {
                "case": cdef["id"],
                "name": cdef["name"],
                "alteration": cdef["alteration"],
                "stage_1_mechanical": s1,
                "stage_2_judgment": s2,
                "stage_3_dispatch": s3,
                "status": status_str,
                "dispatch": dispatch_str,
                "motivos": motivos_str,
                "problems": problems,
                "cand_rows": cand_rows,
            }
        )

        short_dispatch = (dispatch_str[:32] + "...") if len(dispatch_str) > 32 else dispatch_str
        print(f"{cdef['id']:<38} | {s1:<9} | {s2[:11]:<11} | {s3:<9} | {status_str:<10} | {short_dispatch}")

        if cdef["should_pass"]:
            if status_str != "ACEITA" or dispatch_str == "nenhum":
                print(f"  -> FALHA: Caso '{cdef['id']}' deveria ser ACEITO com despacho liberado, mas obteve {status_str}: {motivos_str}")
                all_passed = False
        else:
            if status_str == "ACEITA" and dispatch_str != "nenhum":
                print(f"  -> FALHA: Caso '{cdef['id']}' deveria ser REJEITADO/BLOQUEADO com despacho nenhum, mas despachou {dispatch_str}!")
                all_passed = False
            elif cdef["expected_reason_substr"]:
                matched_reason = (
                    any(cdef["expected_reason_substr"] in p for p in problems)
                    or (cdef["expected_reason_substr"] in motivos_str)
                    or (cdef["expected_reason_substr"] in s2)
                )
                if not matched_reason:
                    print(
                        f"  -> FALHA: Caso '{cdef['id']}' foi rejeitado/bloqueado mas motivo esperado "
                        f"'{cdef['expected_reason_substr']}' não apareceu em: {motivos_str} (s2={s2})!"
                    )
                    all_passed = False

    print("=" * 140)

    summary_path = cases_dir / "pilot_summary.json"
    if write_summary:
        print(f"\n[Modo --write-summary]: Atualizando '{summary_path}'...")
        summary_path.write_text(
            json.dumps(pilot_table_rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("Arquivo de resumo gravado com sucesso.")
    else:
        if not summary_path.exists():
            print(f"FALHA: '{summary_path}' não existe. Execute com --write-summary uma vez para gerá-lo.")
            return 1
        existing_rows = json.loads(summary_path.read_text(encoding="utf-8"))
        normalized_computed = json.loads(json.dumps(pilot_table_rows))
        if existing_rows != normalized_computed:
            print("FALHA: Resumo calculado em memória diverge do 'pilot_summary.json' versionado!")
            for idx, (ex, cur) in enumerate(zip(existing_rows, normalized_computed)):
                if ex != cur:
                    print(f"Divergência no caso {idx} ({cur.get('case')}):")
                    for k in cur:
                        if ex.get(k) != cur.get(k):
                            print(f"  Campo '{k}':\n    esperado: {ex.get(k)!r}\n    obtido:   {cur.get(k)!r}")
            if len(existing_rows) != len(normalized_computed):
                print(f"Tamanho diferente: versionado={len(existing_rows)}, calculado={len(normalized_computed)}")
            return 1
        print("\n[Modo estrito sem escrita]: Resumo em memória coincide 100% com 'pilot_summary.json' (R6 cumprido).")

    if all_passed:
        print(
            f"\n=== AUTO-TESTE DO PILOTO: TODOS OS {len(cases_manifest)} CASOS PASSARAM "
            f"COM AS REJEIÇÕES, BLOQUEIOS E APROVAÇÕES ESPERADAS (EXIT 0) ==="
        )
        return 0
    else:
        print("\n=== AUTO-TESTE DO PILOTO: FALHA EM UMA OU MAIS ASSERÇÕES (EXIT 1) ===")
        return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        do_write = "--write-summary" in sys.argv
        sys.exit(run_self_test(write_summary=do_write))

    if len(sys.argv) < 3:
        print("Uso: python3 T009-mechanical-check.py <classification.json> <expected.json>")
        print("     python3 T009-mechanical-check.py --self-test [--write-summary]")
        sys.exit(2)

    doc_file = pathlib.Path(sys.argv[1])
    exp_file = pathlib.Path(sys.argv[2])

    classification_doc = json.loads(doc_file.read_text(encoding="utf-8"))
    raw_exp = json.loads(exp_file.read_text(encoding="utf-8"))

    catalog = catalog_from_project()
    official_routing_ids, price_id_set, proxy_id_set = parse_routing_evidence()
    evidence_models = derive_evidence_model_map()

    try:
        exp = unwrap_expected(raw_exp, base_dir=pathlib.Path("."), task_proxy_ids=proxy_id_set)
        probs, candidate_table, dispatch_summary, st1, st2, st3 = check_classification(
            classification_doc, exp, catalog, official_routing_ids, price_id_set, proxy_id_set, evidence_models
        )
    except (ValueError, FileNotFoundError) as e:
        probs = [f"esperado/procedência inválida: {e}"]
        candidate_table = []
        dispatch_summary = "nenhum (bloqueado na procedência das entradas)"
        st1, st2, st3 = "REJEITADA", "N/A", "NENHUM"

    print("Candidatos avaliados:")
    for row in candidate_table:
        print("  ", row)

    print(f"ESTÁGIO 1 (Mecânica):   {st1}")
    print(f"ESTÁGIO 2 (Julgamento): {st2}")
    print(f"ESTÁGIO 3 (Despacho):   {st3}")

    if probs:
        print("RESULT: REJEITADA")
        for p in probs:
            print(f"   - {p}")
        print(f"DESPACHO: {dispatch_summary}")
        sys.exit(1)
    elif st3 == "BLOQUEADO" or st2.startswith("PENDENTE"):
        print(f"RESULT: {st1} (despacho bloqueado)")
        print(f"DESPACHO: {dispatch_summary}")
        sys.exit(1)
    else:
        print("RESULT: ACEITA")
        print(f"DESPACHO: {dispatch_summary}")
        sys.exit(0)
