#!/usr/bin/env python3
"""Conferência mecânica do Orquestrador para um resultado de classificação (T009).

Baseado no protótipo de referência fornecido pelo Orquestrador (autoria original: Anthropic).
Evoluído por Maker agy (Google) em T009 (rework round 2):
  (a) R2: procedência verificável e não autodeclarada para IDs locais (registro efetivo no arquivo),
      extração estrita de IDs oficiais de MODEL_ROUTING.md (tabelas e cartões, excluindo marcadores como
      official-2026-09-05), e vinculação da categoria econômica ao conteúdo do cartão (custo por tarefa);
  (b) R3: conferência estrutural completa e recursiva contra schemas/classification-result.schema.json
      (required, type, enum, minItems, uniqueItems, additionalProperties: false, allOf/if/then);
  (c) R4: fallback sob preferred para mesma família condicionado à comprovação de indisponibilidade
      com prova literal de erro e procedência verificada; bloqueio com ponto de retomada se não comprovado;
  (d) R5: fluxo em três estágios explícitos: conferência mecânica -> julgamento registrado -> liberação
      de despacho; sem julgamento registrado, o despacho é bloqueado com status aguardando julgamento;
  (e) R6: modo --self-test estritamente sem escrita (compara em memória com pilot_summary.json já versionado);
      a gravação só ocorre mediante flag explícita --write-summary.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


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


def parse_routing_evidence(path: str = "docs/MODEL_ROUTING.md") -> Tuple[Set[str], Set[str], Set[str]]:
    """Lê docs/MODEL_ROUTING.md e extrai com procedência verificada:

    - official_ids: IDs registrados como linha de tabela (| `id` |), cartão (### `id`) ou transporte (- `id`:).
      Exclui marcadores documentais como official-2026-09-05.
    - price_ids: IDs da tabela de preços (price-*).
    - task_proxy_ids: IDs de cartões que contêm texto explícito de custo por tarefa.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")

    # Linhas de tabela (| `id` |)
    table_ids = set(re.findall(r"^\|\s*`([a-z0-9-]+)`\s*\|", text, re.M))
    price_ids = {i for i in table_ids if i.startswith("price-")}

    # Linhas de transporte sob 'Preços e capacidades de transporte' (- `id`:)
    transport_ids = set(re.findall(r"^-\s*`([a-z0-9-]+)`:", text, re.M))

    # Cartões de evidência (### `id`)
    card_matches = re.findall(r"^###\s*`([a-z0-9-]+)`[^\n]*\n(.*?)(?=\n###|\n##|\Z)", text, re.M | re.S)
    card_ids: Set[str] = set()
    task_proxy_ids: Set[str] = set()

    for cid, body in card_matches:
        card_ids.add(cid)
        # R2(c): ID só sustenta official_task_proxy se contiver texto de custo por tarefa
        if re.search(r"\bcusto\b[^\n]{0,50}\btarefa|\bpor\s+tarefa\b", body, re.I):
            task_proxy_ids.add(cid)

    # Marcadores de revisão documental como official-2026-09-05 são expressamente excluídos
    official_ids = (table_ids | transport_ids | card_ids) - {"official-2026-09-05"}
    official_ids = {i for i in official_ids if not i.startswith("official-")}

    return official_ids, price_ids, task_proxy_ids


def evidence_ids_from_routing(path: str = "docs/MODEL_ROUTING.md") -> Set[str]:
    """Compatibilidade retroativa: retorna o conjunto de IDs oficiais do MODEL_ROUTING.md."""
    official_ids, _, _ = parse_routing_evidence(path)
    return official_ids


def _strip_anchor_and_line(source_str: str) -> str:
    """Extrai o caminho de arquivo removendo #âncora ou :linha."""
    path_part = source_str.split("#")[0]
    path_part = path_part.split(":")[0]
    return path_part.strip()


def validate_id_entries_with_provenance(
    id_data: Any,
    field_name: str,
    base_dir: pathlib.Path,
    task_proxy_ids: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Valida procedência verificável e registro efetivo dos IDs (R2).

    Regras:
    - Rejeita lista solta de strings sem procedência;
    - Exige declaração de arquivo + âncora (#) ou linha (:);
    - O arquivo de procedência deve existir no repositório;
    - Para local_ids (R2-b): o arquivo de procedência deve conter o ID literal (registro efetivo);
    - Para proxy_ids (R2-c): o cartão em docs/MODEL_ROUTING.md deve conter custo por tarefa.
    """
    if id_data is None:
        return {}

    validated: Dict[str, Dict[str, Any]] = {}

    def _check_entry(id_val: str, meta_dict: Dict[str, Any]) -> None:
        source = meta_dict.get("source") or meta_dict.get("path")
        if not source:
            raise ValueError(f"ID '{id_val}' em '{field_name}' rejeitado: ausência de procedência ('source').")
        if not ("#" in source or ":" in source):
            raise ValueError(
                f"Procedência '{source}' do ID '{id_val}' em '{field_name}' incompleta: "
                f"deve declarar arquivo + âncora (#) ou linha (:)."
            )
        rel_path = _strip_anchor_and_line(source)
        filepath = base_dir / rel_path
        if not filepath.exists():
            raise FileNotFoundError(
                f"Caminho de procedência '{filepath}' do ID '{id_val}' em '{field_name}' não existe."
            )

        file_text = filepath.read_text(encoding="utf-8")

        # R2(b): ID local deve estar registrado efetivamente (ID literal presente no arquivo)
        if field_name == "local_ids":
            if id_val not in file_text:
                raise ValueError(
                    f"ID local '{id_val}' em '{field_name}' rejeitado: não registrado efetivamente "
                    f"no arquivo '{filepath}' (ID literal ausente no conteúdo)."
                )

        # R2(c): ID de proxy só pode sustentar official_task_proxy se o cartão contiver custo por tarefa
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


def unwrap_expected(
    expected_data: Dict[str, Any],
    base_dir: pathlib.Path = pathlib.Path("."),
    task_proxy_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Desempacota 'expected' verificando procedência obrigatória, registro efetivo e categorias."""
    unwrapped: Dict[str, Any] = {}

    # Validação de procedência de local_ids e proxy_ids
    unwrapped["local_ids"] = validate_id_entries_with_provenance(
        expected_data.get("local_ids", {}), "local_ids", base_dir
    )
    unwrapped["proxy_ids"] = validate_id_entries_with_provenance(
        expected_data.get("proxy_ids", {}), "proxy_ids", base_dir, task_proxy_ids
    )

    # Campos escalares e estruturados com procedência opcional ou direta
    for key in ("story_id", "phase", "context_revision", "catalog_revision", "policy", "authors"):
        item = expected_data.get(key)
        if isinstance(item, dict) and "value" in item:
            source = item.get("source")
            if source:
                filepath = base_dir / _strip_anchor_and_line(source)
                if not filepath.exists():
                    raise FileNotFoundError(f"Caminho de procedência de '{key}' ({filepath}) não existe.")
            unwrapped[key] = item["value"]
        else:
            unwrapped[key] = item

    # Roles
    roles_item = expected_data.get("roles")
    if isinstance(roles_item, dict) and "value" in roles_item:
        unwrapped["roles"] = roles_item["value"]
    elif isinstance(roles_item, list):
        unwrapped["roles"] = roles_item
    else:
        unwrapped["roles"] = []

    # Chains
    chains_raw = expected_data.get("chains", {})
    chains: Dict[str, List[str]] = {}
    for role, chain_val in chains_raw.items():
        if isinstance(chain_val, dict) and "value" in chain_val:
            chains[role] = chain_val["value"]
        elif isinstance(chain_val, list):
            chains[role] = chain_val
        else:
            chains[role] = []
    unwrapped["chains"] = chains

    # Pins
    pins_raw = expected_data.get("pins", {})
    pins: Dict[str, Any] = {}
    for role, pin_val in pins_raw.items():
        if isinstance(pin_val, dict) and "value" in pin_val:
            pins[role] = pin_val["value"]
        else:
            pins[role] = pin_val
    unwrapped["pins"] = pins

    # Families
    fam_raw = expected_data.get("families", {})
    families: Dict[str, str] = {}
    for model, val in fam_raw.items():
        if isinstance(val, dict) and "value" in val:
            families[model] = val["value"]
        elif isinstance(val, str):
            families[model] = val
    unwrapped["families"] = families

    # Availability (R4)
    unwrapped["availability"] = expected_data.get("availability", {})

    # Judgment (R5)
    unwrapped["judgment"] = expected_data.get("judgment")

    return unwrapped


def validate_schema_recursive(
    instance: Any,
    subschema: Dict[str, Any],
    path: str = "$",
    root_schema: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Verificador mínimo recursivo conforme schemas/classification-result.schema.json (R3).

    Suporta: $ref, type, const, enum, minItems, maxItems, uniqueItems, minLength,
    required, properties, additionalProperties: false e allOf/if/then/else.
    """
    errors: List[str] = []
    if root_schema is None:
        root_schema = subschema

    # 0. Constraint 'not'
    if "not" in subschema:
        not_errs = validate_schema_recursive(instance, subschema["not"], path, root_schema)
        if not not_errs:
            errors.append(f"schema: {path} violou restrição 'not'")
            return errors
        # Se houve erro no subschema de 'not', a negação é satisfeita
        if len(subschema) == 1:
            return []

    # 1. Resolução de $ref interno (#/$defs/...)
    if "$ref" in subschema:
        ref = subschema["$ref"]
        if ref.startswith("#/$defs/"):
            def_name = ref[len("#/$defs/"):]
            target_sub = root_schema.get("$defs", {}).get(def_name)
            if target_sub:
                return validate_schema_recursive(instance, target_sub, path, root_schema)
            else:
                return [f"schema: referência interna '{ref}' não encontrada no schema"]

    # 2. Type checking
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

    # 3. Const checking
    if "const" in subschema:
        if instance != subschema["const"]:
            errors.append(f"schema: {path} esperado valor constante {subschema['const']!r}, obtido {instance!r}")

    # 4. Enum checking
    if "enum" in subschema:
        if instance not in subschema["enum"]:
            errors.append(f"schema: {path} valor {instance!r} não pertence ao enum permitido {subschema['enum']}")

    # 5. String length
    if isinstance(instance, str):
        if "minLength" in subschema and len(instance) < subschema["minLength"]:
            errors.append(f"schema: {path} tamanho {len(instance)} menor que minLength {subschema['minLength']}")

    # 6. Array constraints
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

    # 7. Object constraints
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

    # 8. allOf constraints (if / then / else)
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
    base_dir: pathlib.Path = pathlib.Path("."),
) -> Tuple[List[str], List[Tuple[Any, ...]], str, str, str, str]:
    """Executa a conferência em três estágios explícitos (R5):

    1. Conferência mecânica (schema, catálogo, top-level fields, procedência econômica, pins).
    2. Julgamento registrado (verificação humana/documental de pertinência e âncora).
    3. Liberação de despacho (resolução de elegibilidade e fallback com prova de indisponibilidade).

    Retorna:
      (problems, candidate_rows, dispatch_summary, stage_1_str, stage_2_str, stage_3_str)
    """
    problems: List[str] = []
    rows: List[Tuple[Any, ...]] = []

    # =========================================================================
    # ESTÁGIO 1: CONFERÊNCIA MECÂNICA
    # =========================================================================
    schema_errors = validate_schema_structure(d)
    problems.extend(schema_errors)

    # Conferência de campos superiores
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

    # Conferência por papel e candidato
    for role, r in d.get("roles", {}).items():
        chain = expected.get("chains", {}).get(role, [])
        cand_harnesses = [c.get("harness") for c in r.get("candidates", [])]
        if cand_harnesses != chain:
            problems.append(f"{role}: ordem de harness {cand_harnesses} ≠ cadeia esperada {chain}")

        for idx, c in enumerate(r.get("candidates", [])):
            key = (c.get("harness"), c.get("model"), c.get("effort"))
            ev = set(c.get("evidence_ids", []))
            cb = c.get("cost_basis")

            in_cat = role in cat.get(key, set())
            unknown = ev - ids - local_id_keys

            price = any(e in price_ids for e in ev)
            proxy = ev & proxy_id_keys & task_proxy_ids
            local = ev & local_id_keys

            # R2(c): Regras estritas de sustentação econômica vinculadas ao conteúdo
            cb_ok = {
                "unknown": not (price or proxy or local),
                "token_price_only": price and not proxy and not local,
                "official_task_proxy": bool(proxy),
                "local_observed": bool(local),
            }.get(cb, False)

            pin = expected.get("pins", {}).get(role)
            pin_ok = (pin is None) or (list(key) == list(pin)) or (idx > 0)

            fam = families.get(c.get("model"))
            # Filtro de elegibilidade da independência (R4)
            if role == "checker" and fam in authors:
                if policy == "required":
                    eligibility_str = "inelegível(required, mesma família)"
                else:
                    eligibility_str = "elegível só com indisponibilidade comprovada (fallback)"
            else:
                eligibility_str = "elegível"

            cand_ok = in_cat and not unknown and cb_ok and pin_ok and (c.get("effort") is not None)
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

            if not cand_ok:
                problems.append(
                    f"{role} {key}: catálogo={in_cat} ids_desconhecidos={sorted(unknown)} "
                    f"cost_basis={cb} sustentado={cb_ok} pin={pin_ok}"
                )

        if role == "checker" and policy == "required":
            if all(families.get(c.get("model")) in authors for c in r.get("candidates", [])):
                problems.append("checker: nenhum candidato elegível sob required (todas as famílias são autoras)")

    # Se a conferência mecânica falhar, o fluxo para no gate imediatamente
    if problems:
        stage_1_str = "REJEITADA"
        stage_2_str = "N/A"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (bloqueado no gate de conferência mecânica)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    stage_1_str = "APROVADA"

    # =========================================================================
    # ESTÁGIO 2: JULGAMENTO REGISTRADO (R5)
    # =========================================================================
    judgment = expected.get("judgment")
    if not judgment:
        stage_2_str = "PENDENTE (aguardando julgamento)"
        stage_3_str = "NENHUM"
        dispatch_result = "nenhum (aceita mecanicamente; despacho não liberado (aguardando julgamento))"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    j_source = judgment.get("source") if isinstance(judgment, dict) else judgment
    j_anchor = judgment.get("anchor") or judgment.get("trecho") or "Validação pelo Orquestrador"

    j_file = base_dir / _strip_anchor_and_line(j_source)
    if not j_file.exists():
        stage_2_str = f"REJEITADO (arquivo de julgamento '{j_file}' não existe)"
        stage_3_str = "NENHUM"
        problems.append(stage_2_str)
        dispatch_result = "nenhum (bloqueado no gate de julgamento registrado)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    j_content = j_file.read_text(encoding="utf-8")
    if j_anchor not in j_content:
        stage_2_str = f"REJEITADO (registro de julgamento '{j_anchor}' ausente em '{j_file}')"
        stage_3_str = "NENHUM"
        problems.append(stage_2_str)
        dispatch_result = "nenhum (bloqueado no gate de julgamento registrado)"
        return problems, rows, dispatch_result, stage_1_str, stage_2_str, stage_3_str

    stage_2_str = "CONFIRMADO"

    # =========================================================================
    # ESTÁGIO 3: LIBERAÇÃO DE DESPACHO E RESOLUÇÃO DE FALLBACK (R4)
    # =========================================================================
    dispatched_cands: List[str] = []
    dispatch_blocked_reason: Optional[str] = None

    for role, r in d.get("roles", {}).items():
        role_dispatched: Optional[str] = None

        # 1. Tenta candidatos elegíveis de família distinta (ou qualquer se não for checker)
        for c in r.get("candidates", []):
            fam = families.get(c.get("model"))
            is_same = (fam in authors) if role == "checker" else False
            cand_id = f"{c.get('harness')}/{c.get('model')}"

            if not is_same:
                cand_avail = availability.get(cand_id, {})
                stat = cand_avail.get("status", "available") if isinstance(cand_avail, dict) else cand_avail
                if stat == "available":
                    role_dispatched = f"{c.get('harness')}/{c.get('model')}/{c.get('effort')}"
                    break

        # 2. Se nenhum candidato de família distinta foi despachado, avalia fallback de mesma família
        if role_dispatched is None and role == "checker":
            if policy == "required":
                dispatch_blocked_reason = "nenhum candidato elegível sob required (mesma família proibida)"
            elif policy == "preferred":
                # R4: fallback sob preferred só com indisponibilidade comprovada
                distinct_cands = [c for c in r.get("candidates", []) if families.get(c.get("model")) not in authors]
                all_proven_unavailable = True
                unavail_error: Optional[str] = None

                if not distinct_cands:
                    all_proven_unavailable = False
                    unavail_error = "ausência de candidatos de família distinta para comprovação"
                else:
                    for dc in distinct_cands:
                        dc_id = f"{dc.get('harness')}/{dc.get('model')}"
                        dc_avail = availability.get(dc_id)
                        if not dc_avail or not isinstance(dc_avail, dict):
                            all_proven_unavailable = False
                            unavail_error = f"candidato '{dc_id}' sem estado de disponibilidade declarado"
                            break
                        stat = dc_avail.get("status")
                        if stat != "unavailable":
                            all_proven_unavailable = False
                            unavail_error = f"candidato '{dc_id}' com status '{stat}' (exige 'unavailable')"
                            break
                        proof = dc_avail.get("proof") or dc_avail.get("error")
                        src = dc_avail.get("source")
                        if not proof or not src:
                            all_proven_unavailable = False
                            unavail_error = f"candidato '{dc_id}' sem prova literal de erro ou procedência ('source')"
                            break
                        src_file = base_dir / _strip_anchor_and_line(src)
                        if not src_file.exists():
                            all_proven_unavailable = False
                            unavail_error = f"arquivo de evidência de erro '{src_file}' não existe"
                            break
                        if proof not in src_file.read_text(encoding="utf-8"):
                            all_proven_unavailable = False
                            unavail_error = f"prova literal de erro não encontrada no arquivo '{src_file}'"
                            break

                if all_proven_unavailable:
                    # Encontra o primeiro candidato de mesma família elegível como fallback
                    for c in r.get("candidates", []):
                        fam = families.get(c.get("model"))
                        if fam in authors and c.get("effort") is not None:
                            role_dispatched = f"{c.get('harness')}/{c.get('model')}/{c.get('effort')} (fallback: same_family_fresh_session)"
                            break
                else:
                    dispatch_blocked_reason = (
                        f"bloqueado com ponto de retomada: fallback de mesma família sob preferred "
                        f"exige prova de indisponibilidade dos candidatos de família distinta ({unavail_error})"
                    )

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
    print("=== T009 MECHANICAL CHECK: INÍCIO DO SELF-TEST (REWORK ROUND 2) ===")
    cat = catalog_from_project()
    official_ids, price_ids, task_proxy_ids = parse_routing_evidence()

    # 1. Prova do requisito R2(a/b): Falha ao receber ID local com caminho inexistente
    print("\n[Teste de Robustez A] ID local com caminho de procedência inexistente:")
    bad_local = {"local-fake": {"source": "_tl-orc/project/evidence/arquivo-fantasma.md#L1"}}
    try:
        validate_id_entries_with_provenance(bad_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado caminho inexistente!")
        return 1
    except FileNotFoundError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    # 2. Prova do requisito R2(a/b): Falha ao receber lista solta de IDs passada na hora sem origem
    print("\n[Teste de Robustez B] Lista de IDs passada 'na hora' sem origem:")
    bad_bare_list = ["price-astra", "local-fake"]
    try:
        validate_id_entries_with_provenance(bad_bare_list, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado lista sem procedência!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    # 3. Prova do requisito R2(b): Falha ao receber ID local em caminho existente mas não registrado
    print("\n[Teste de Robustez C] ID local em caminho existente mas sem registro efetivo:")
    bad_unregistered_local = {"local-fake": {"source": "README.md#ancora-inexistente"}}
    try:
        validate_id_entries_with_provenance(bad_unregistered_local, "local_ids", pathlib.Path("."))
        print("FALHA: deveria ter recusado ID não registrado no arquivo!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    # 4. Prova do requisito R2(c): Falha ao declarar cartão sem custo por tarefa sob proxy_ids
    print("\n[Teste de Robustez D] Declaração indevida de sonnet-effort como proxy:")
    bad_proxy = {"sonnet-effort": {"source": "docs/MODEL_ROUTING.md#sonnet-effort"}}
    try:
        validate_id_entries_with_provenance(bad_proxy, "proxy_ids", pathlib.Path("."), task_proxy_ids)
        print("FALHA: deveria ter recusado sonnet-effort em proxy_ids!")
        return 1
    except ValueError as e:
        print(f"SUCESSO (recusa esperada): {e}")

    # 5. Manifesto completo dos 17 casos do piloto (7 iniciais + 10 controles de R2 a R5)
    cases_manifest = [
        # --- Casos Originais e Mutações Base ---
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
        # --- Novos Controles R2: Procedência Verificável ---
        {
            "id": "case_07_r2_unregistered_local_id",
            "name": "Controle R2: ID local fabricado em arquivo existente sem registro efetivo",
            "file": "case_07_r2_unregistered_local_id.json",
            "expected_file": "expected_r2_unregistered_local_id.json",
            "alteration": "controle R2: expected declara local-fake com source README.md sem que o ID exista no arquivo",
            "should_pass": False,
            "expected_reason_substr": "não registrado efetivamente no arquivo",
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
        # --- Novos Controles R3: Validação Completa do Schema ---
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
        # --- Novos Controles R4: Fallback sob Preferred e Prova de Indisponibilidade ---
        {
            "id": "case_13_r4_preferred_unproven_fallback",
            "name": "Controle R4: Fallback de mesma família sob preferred sem prova de indisponibilidade",
            "file": "case_13_r4_preferred_unproven_fallback.json",
            "expected_file": "expected_r4_preferred_unproven_fallback.json",
            "alteration": "controle R4: candidatos de família distinta sem disponibilidade comprovada (status unknown / sem prova)",
            "should_pass": False,
            "expected_reason_substr": "fallback de mesma família sob preferred exige prova de indisponibilidade",
        },
        {
            "id": "case_14_r4_preferred_proven_fallback",
            "name": "Controle R4: Fallback de mesma família sob preferred com indisponibilidade comprovada",
            "file": "case_14_r4_preferred_proven_fallback.json",
            "expected_file": "expected_r4_preferred_proven_fallback.json",
            "alteration": "controle R4: candidatos distintos indisponíveis com erro literal comprovado em evidência sintética",
            "should_pass": True,
            "expected_reason_substr": None,
        },
        {
            "id": "case_15_r4_required_same_family",
            "name": "Controle R4: Candidatos de mesma família sob required (inelegíveis)",
            "file": "case_15_r4_required_same_family.json",
            "expected_file": "expected_r4_required_same_family.json",
            "alteration": "controle R4: todos os candidatos pertencem a famílias autoras sob política required",
            "should_pass": False,
            "expected_reason_substr": "nenhum candidato elegível sob required (todas as famílias são autoras)",
        },
        # --- Novo Controle R5: Três Estágios e Julgamento Registrado ---
        {
            "id": "case_16_r5_valid_without_judgment",
            "name": "Controle R5: Caso válido sem julgamento registrado (despacho não liberado)",
            "file": "case_16_r5_valid_without_judgment.json",
            "expected_file": "expected_r5_valid_without_judgment.json",
            "alteration": "controle R5: caso estruturalmente válido mas sem entrada judgment (aguardando julgamento)",
            "should_pass": False,
            "expected_reason_substr": "despacho não liberado (aguardando julgamento)",
        },
    ]

    print("\n" + "=" * 140)
    print(
        f"{'Caso':<36} | {'Mecânica':<9} | {'Julgamento':<11} | {'Despacho':<9} | {'Status':<10} | {'Despacho Simulado'}"
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
                doc, expected, cat, official_ids, price_ids, task_proxy_ids
            )
        except (ValueError, FileNotFoundError) as e:
            err_msg = str(e)
            problems = [err_msg]
            cand_rows = []
            s1 = "REJEITADA"
            s2 = "N/A"
            s3 = "NENHUM"
            dispatch = "nenhum (bloqueado na procedência das entradas)"

        # Determinação do status operacional do caso
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
        print(f"{cdef['id']:<36} | {s1:<9} | {s2[:11]:<11} | {s3:<9} | {status_str:<10} | {short_dispatch}")

        # Verificação das expectativas do piloto
        if cdef["should_pass"]:
            if status_str != "ACEITA" or dispatch_str == "nenhum":
                print(f"  -> FALHA: Caso '{cdef['id']}' deveria ser ACEITO com despacho liberado, mas obteve {status_str}: {motivos_str}")
                all_passed = False
        else:
            if status_str == "ACEITA" and dispatch_str != "nenhum":
                print(f"  -> FALHA: Caso '{cdef['id']}' deveria ser REJEITADO/BLOQUEADO com despacho nenhum, mas despachou {dispatch_str}!")
                all_passed = False
            elif cdef["expected_reason_substr"]:
                matched_reason = any(cdef["expected_reason_substr"] in p for p in problems) or (
                    cdef["expected_reason_substr"] in motivos_str
                )
                if not matched_reason:
                    print(
                        f"  -> FALHA: Caso '{cdef['id']}' foi rejeitado/bloqueado mas motivo esperado "
                        f"'{cdef['expected_reason_substr']}' não apareceu em: {motivos_str}!"
                    )
                    all_passed = False

    print("=" * 140)

    # R6: Gravação sob demanda ou verificação de integridade sem escrita
    summary_path = cases_dir / "pilot_summary.json"
    if write_summary:
        print(f"\n[Modo --write-summary]: Atualizando '{summary_path}'...")
        summary_path.write_text(
            json.dumps(pilot_table_rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("Arquivo de resumo gravado com sucesso.")
    else:
        # Modo padrão: apenas compara em memória contra o JSON existente sem tocar no disco
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

    try:
        exp = unwrap_expected(raw_exp, base_dir=pathlib.Path("."), task_proxy_ids=proxy_id_set)
        probs, candidate_table, dispatch_summary, st1, st2, st3 = check_classification(
            classification_doc, exp, catalog, official_routing_ids, price_id_set, proxy_id_set
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
