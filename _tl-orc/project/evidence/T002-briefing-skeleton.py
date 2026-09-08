#!/usr/bin/env python3
"""
T002-briefing-skeleton.py

Protótipo não distribuído que lê o schema JSON de classificação
(schemas/classification-result.schema.json) e imprime o esqueleto literal mínimo
para os papéis solicitados (--roles planner,maker,checker[,searcher]), com todos
os campos obrigatórios, enums formatados como "a|b|c", listas de strings,
um candidato por harness na ordem da cadeia configurada (--chain), e um bloco
de regras fixas de preenchimento.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_CHAINS: dict[str, list[str]] = {
    "planner": ["claude", "codex", "agy"],
    "maker": ["codex", "claude", "agy"],
    "checker": ["agy", "claude", "codex"],
    "searcher": ["agy", "claude", "codex"],
}


def load_schema(schema_path: Path) -> dict[str, Any]:
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        sys.stderr.write(f"Erro ao carregar schema {schema_path}: {exc}\n")
        sys.exit(1)


SUPPORTED_ROOT_REQUIRED = {
    "schema_version",
    "story_id",
    "phase",
    "context_revision",
    "catalog_revision",
    "confidence",
    "facts",
    "uncertainties",
    "reclassify_when",
    "roles",
}
SUPPORTED_ROLE_REQUIRED = {"tier", "reason", "candidates"}
SUPPORTED_CANDIDATE_REQUIRED = {
    "harness",
    "model",
    "effort",
    "evidence_ids",
    "cost_basis",
    "reason",
}


def admits_null(def_dict: dict[str, Any]) -> bool:
    """`type` e `enum` são restrições cumulativas no JSON Schema: null só é admitido quando
    o tipo o permite E, havendo enum, o enum o contém."""
    t = def_dict.get("type")
    by_type = t == "null" or (isinstance(t, list) and "null" in t) or t is None
    if "enum" in def_dict:
        enum = def_dict["enum"]
        if not isinstance(enum, list):
            return False
        return by_type and (None in enum)
    return bool(by_type) and t is not None


def require_string_list(props: dict[str, Any], name: str, where: str) -> None:
    """Interrompe se a lista não for de strings (os placeholders emitidos são strings)."""
    d = props.get(name)
    if not isinstance(d, dict) or d.get("type") != "array":
        sys.stderr.write(f"Schema não suportado: tipo de '{name}' {where} incompatível (esperado array)\n")
        sys.exit(1)
    items = d.get("items")
    if not isinstance(items, dict) or items.get("type") != "string":
        sys.stderr.write(f"Schema não suportado: itens de '{name}' {where} incompatíveis com os placeholders emitidos (esperado items.type string)\n")
        sys.exit(1)


def build_skeleton(schema: dict[str, Any], roles: list[str], chains: dict[str, list[str]]) -> dict[str, Any]:
    props = schema.get("properties", {})
    defs = schema.get("$defs", {})
    role_schema = defs.get("role", {})
    cand_schema = defs.get("candidate", {})
    role_def = role_schema.get("properties", {})
    cand_def = cand_schema.get("properties", {})

    # Verificação bidirecional de campos obrigatórios (required)
    root_required = set(schema.get("required", []))
    unsupported_root = root_required - SUPPORTED_ROOT_REQUIRED
    if unsupported_root:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios desconhecidos na raiz: {sorted(unsupported_root)}\n")
        sys.exit(1)
    missing_root = SUPPORTED_ROOT_REQUIRED - root_required
    if missing_root:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios esperados ausentes na raiz: {sorted(missing_root)}\n")
        sys.exit(1)

    role_required = set(role_schema.get("required", []))
    unsupported_role = role_required - SUPPORTED_ROLE_REQUIRED
    if unsupported_role:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios desconhecidos em $defs/role: {sorted(unsupported_role)}\n")
        sys.exit(1)
    missing_role = SUPPORTED_ROLE_REQUIRED - role_required
    if missing_role:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios esperados ausentes em $defs/role: {sorted(missing_role)}\n")
        sys.exit(1)

    cand_required = set(cand_schema.get("required", []))
    unsupported_cand = cand_required - SUPPORTED_CANDIDATE_REQUIRED
    if unsupported_cand:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios desconhecidos em $defs/candidate: {sorted(unsupported_cand)}\n")
        sys.exit(1)
    missing_cand = SUPPORTED_CANDIDATE_REQUIRED - cand_required
    if missing_cand:
        sys.stderr.write(f"Schema não suportado: campos obrigatórios esperados ausentes em $defs/candidate: {sorted(missing_cand)}\n")
        sys.exit(1)

    # Verificação de presença de propriedades geradas
    missing_root_props = SUPPORTED_ROOT_REQUIRED - set(props.keys())
    if missing_root_props:
        sys.stderr.write(f"Schema não suportado: propriedades esperadas ausentes na raiz: {sorted(missing_root_props)}\n")
        sys.exit(1)

    missing_role_props = SUPPORTED_ROLE_REQUIRED - set(role_def.keys())
    if missing_role_props:
        sys.stderr.write(f"Schema não suportado: propriedades esperadas ausentes em $defs/role: {sorted(missing_role_props)}\n")
        sys.exit(1)

    missing_cand_props = SUPPORTED_CANDIDATE_REQUIRED - set(cand_def.keys())
    if missing_cand_props:
        sys.stderr.write(f"Schema não suportado: propriedades esperadas ausentes em $defs/candidate: {sorted(missing_cand_props)}\n")
        sys.exit(1)

    # 1. schema_version
    sv_def = props.get("schema_version")
    if not isinstance(sv_def, dict) or ("const" not in sv_def and "enum" not in sv_def):
        sys.stderr.write("Schema não suportado: definição ou formato incompatível para 'schema_version' na raiz\n")
        sys.exit(1)
    schema_version = sv_def["const"] if "const" in sv_def else sv_def["enum"][0]

    # 2. story_id
    story_def = props.get("story_id")
    if not isinstance(story_def, dict):
        sys.stderr.write("Schema não suportado: definição ausente ou incompatível para 'story_id' na raiz\n")
        sys.exit(1)
    story_type = story_def.get("type")
    accepts_str = story_type == "string" or (isinstance(story_type, list) and "string" in story_type)
    if not accepts_str:
        sys.stderr.write("Schema não suportado: tipo de 'story_id' na raiz incompatível (esperado string)\n")
        sys.exit(1)
    story_id = "<story_id ou null>" if admits_null(story_def) else "<story_id literal>"

    # 3. phase enum
    phase_def = props.get("phase")
    if not isinstance(phase_def, dict) or "enum" not in phase_def or not isinstance(phase_def["enum"], list) or not phase_def["enum"]:
        sys.stderr.write("Schema não suportado: enum de 'phase' ausente, vazio ou inválido na raiz\n")
        sys.exit(1)
    phase = "|".join(str(x) for x in phase_def["enum"])

    # 4. revisions
    ctx_def = props.get("context_revision")
    if not isinstance(ctx_def, dict) or ctx_def.get("type") != "string":
        sys.stderr.write("Schema não suportado: tipo de 'context_revision' na raiz incompatível (esperado string)\n")
        sys.exit(1)
    context_rev = "<context_revision literal recebida>"

    cat_def = props.get("catalog_revision")
    if not isinstance(cat_def, dict) or cat_def.get("type") != "string":
        sys.stderr.write("Schema não suportado: tipo de 'catalog_revision' na raiz incompatível (esperado string)\n")
        sys.exit(1)
    catalog_rev = "<catalog_revision literal recebida>"

    # 5. confidence enum
    conf_def = props.get("confidence")
    if not isinstance(conf_def, dict) or "enum" not in conf_def or not isinstance(conf_def["enum"], list) or not conf_def["enum"]:
        sys.stderr.write("Schema não suportado: enum de 'confidence' ausente, vazio ou inválido na raiz\n")
        sys.exit(1)
    confidence = "|".join(str(x) for x in conf_def["enum"])

    # 6. lists
    require_string_list(props, "facts", "na raiz")
    facts = ["<fato 1>", "<fato 2>"]

    require_string_list(props, "uncertainties", "na raiz")
    uncertainties = ["<incerteza 1>"]

    require_string_list(props, "reclassify_when", "na raiz")
    reclassify_when = ["<condição de reclassificação 1>"]

    # 7. roles
    roles_def = props.get("roles")
    if not isinstance(roles_def, dict) or roles_def.get("type") != "object" or "properties" not in roles_def or not isinstance(roles_def["properties"], dict):
        sys.stderr.write("Schema não suportado: definição ou formato incompatível para 'roles' na raiz\n")
        sys.exit(1)

    tier_def = role_def.get("tier")
    if not isinstance(tier_def, dict) or "enum" not in tier_def or not isinstance(tier_def["enum"], list) or not tier_def["enum"]:
        sys.stderr.write("Schema não suportado: enum de 'tier' ausente, vazio ou inválido em $defs/role\n")
        sys.exit(1)
    tier_str = "|".join(str(x) for x in tier_def["enum"])

    role_reason_def = role_def.get("reason")
    if not isinstance(role_reason_def, dict) or role_reason_def.get("type") != "string":
        sys.stderr.write("Schema não suportado: tipo de 'reason' incompatível em $defs/role (esperado string)\n")
        sys.exit(1)

    cands_def = role_def.get("candidates")
    if not isinstance(cands_def, dict) or cands_def.get("type") != "array":
        sys.stderr.write("Schema não suportado: tipo de 'candidates' incompatível em $defs/role (esperado array)\n")
        sys.exit(1)

    harness_def = cand_def.get("harness")
    if not isinstance(harness_def, dict) or "enum" not in harness_def or not isinstance(harness_def["enum"], list) or not harness_def["enum"]:
        sys.stderr.write("Schema não suportado: enum de 'harness' ausente, vazio ou inválido em $defs/candidate\n")
        sys.exit(1)
    allowed_harnesses = set(harness_def["enum"])

    model_def = cand_def.get("model")
    if not isinstance(model_def, dict):
        sys.stderr.write("Schema não suportado: definição ausente ou incompatível para 'model' em $defs/candidate\n")
        sys.exit(1)
    model_type = model_def.get("type")
    model_accepts_str = model_type == "string" or (isinstance(model_type, list) and "string" in model_type) or "enum" in model_def
    if not model_accepts_str:
        sys.stderr.write("Schema não suportado: tipo de 'model' em $defs/candidate incompatível (esperado string)\n")
        sys.exit(1)
    model_admits_null = admits_null(model_def)

    effort_def = cand_def.get("effort")
    if not isinstance(effort_def, dict) or "enum" not in effort_def or not isinstance(effort_def["enum"], list):
        sys.stderr.write("Schema não suportado: enum de 'effort' ausente ou inválido em $defs/candidate\n")
        sys.exit(1)
    effort_options = [str(e) for e in effort_def["enum"] if e is not None]
    effort_admits_null = admits_null(effort_def)
    if not effort_options and not effort_admits_null:
        sys.stderr.write("Schema não suportado: enum de 'effort' vazio em $defs/candidate\n")
        sys.exit(1)
    if effort_admits_null:
        effort_str = "|".join(effort_options + ["null"]) if effort_options else "null"
    else:
        effort_str = "|".join(effort_options)

    evidence_ids_def = cand_def.get("evidence_ids")
    if not isinstance(evidence_ids_def, dict) or evidence_ids_def.get("type") != "array":
        sys.stderr.write("Schema não suportado: tipo de 'evidence_ids' incompatível em $defs/candidate (esperado array)\n")
        sys.exit(1)

    cost_basis_def = cand_def.get("cost_basis")
    if not isinstance(cost_basis_def, dict) or "enum" not in cost_basis_def or not isinstance(cost_basis_def["enum"], list) or not cost_basis_def["enum"]:
        sys.stderr.write("Schema não suportado: enum de 'cost_basis' ausente, vazio ou inválido em $defs/candidate\n")
        sys.exit(1)
    cost_basis_str = "|".join(str(e) for e in cost_basis_def["enum"] if e is not None)

    cand_reason_def = cand_def.get("reason")
    if not isinstance(cand_reason_def, dict) or cand_reason_def.get("type") != "string":
        sys.stderr.write("Schema não suportado: tipo de 'reason' incompatível em $defs/candidate (esperado string)\n")
        sys.exit(1)

    roles_obj: dict[str, Any] = {}
    for role in roles:
        chain = chains.get(role, DEFAULT_CHAINS.get(role, ["codex", "claude", "agy"]))
        candidates = []
        for harness in chain:
            if harness not in allowed_harnesses:
                sys.stderr.write(f"Harness inválido na cadeia de {role}: '{harness}'. Permitidos pelo schema: {sorted(allowed_harnesses)}\n")
                sys.exit(1)
            model_placeholder = (
                f"<ID do modelo no catálogo para {harness} ou null se lacuna>"
                if model_admits_null
                else f"<ID do modelo no catálogo para {harness}>"
            )
            candidate = {
                "harness": harness,
                "model": model_placeholder,
                "effort": effort_str,
                "evidence_ids": ["<ID de evidência pertinente do MODEL_ROUTING ou medição local>"],
                "cost_basis": cost_basis_str,
                "reason": f"<justificativa da escolha ou da lacuna/inelegibilidade no harness {harness}>",
            }
            candidates.append(candidate)

        roles_obj[role] = {
            "tier": tier_str,
            "reason": f"<justificativa do dimensionamento de tier para {role}>",
            "candidates": candidates,
        }

    return {
        "schema_version": schema_version,
        "story_id": story_id,
        "phase": phase,
        "context_revision": context_rev,
        "catalog_revision": catalog_rev,
        "confidence": confidence,
        "facts": facts,
        "uncertainties": uncertainties,
        "reclassify_when": reclassify_when,
        "roles": roles_obj,
    }


def parse_chain_arg(chain_args: list[str] | None) -> dict[str, list[str]]:
    chains = dict(DEFAULT_CHAINS)
    if not chain_args:
        return chains
    for arg in chain_args:
        if "=" not in arg:
            sys.stderr.write(f"Argumento --chain inválido (esperado papel=harness1,harness2,...): {arg}\n")
            sys.exit(1)
        role, harness_list = arg.split("=", 1)
        role = role.strip().lower()
        harnesses = [h.strip().lower() for h in harness_list.split(",") if h.strip()]
        if not harnesses:
            sys.stderr.write(f"Lista de harnesses vazia em --chain {arg}\n")
            sys.exit(1)
        chains[role] = harnesses
    return chains


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera o esqueleto literal mínimo do briefing do Classificador derivado do schema JSON."
    )
    parser.add_argument(
        "schema_path",
        type=Path,
        help="Caminho para o schema JSON (schemas/classification-result.schema.json).",
    )
    parser.add_argument(
        "--roles",
        type=str,
        default="planner,maker,checker",
        help="Lista de papéis solicitados separados por vírgula (ex: planner,maker,checker ou planner,maker,checker,searcher).",
    )
    parser.add_argument(
        "--chain",
        action="append",
        dest="chains",
        metavar="ROLE=H1,H2,H3",
        help="Cadeia operacional para um papel (ex: --chain maker=agy,codex,claude). Pode ser repetido.",
    )
    parser.add_argument(
        "--raw-json",
        action="store_true",
        help="Imprime exclusivamente o objeto JSON sem o bloco de regras fixas.",
    )

    args = parser.parse_args()

    if not args.schema_path.is_file():
        sys.stderr.write(f"Arquivo de schema não encontrado: {args.schema_path}\n")
        sys.exit(1)

    schema = load_schema(args.schema_path)
    roles_prop = schema.get("properties", {}).get("roles", {}).get("properties", {})
    allowed_roles = set(roles_prop.keys())
    if not allowed_roles:
        sys.stderr.write("Schema não suportado: nenhuma propriedade de papel encontrada em properties.roles.properties\n")
        sys.exit(1)

    requested_roles = [r.strip().lower() for r in args.roles.split(",") if r.strip()]
    invalid = [r for r in requested_roles if r not in allowed_roles]
    if invalid:
        sys.stderr.write(f"Papéis inválidos solicitados: {', '.join(invalid)}. Permitidos pelo schema: {', '.join(sorted(allowed_roles))}\n")
        sys.exit(1)

    chains = parse_chain_arg(args.chains)
    skeleton = build_skeleton(schema, requested_roles, chains)

    skeleton_json = json.dumps(skeleton, indent=2, ensure_ascii=False)

    if args.raw_json:
        print(skeleton_json)
        return

    print("```json")
    print(skeleton_json)
    print("```")
    print()
    print("### Regras fixas de preenchimento do resultado")
    print("1. Candidatos por cadeia: inclua exatamente um candidato por harness na ordem da cadeia informada, inclusive candidatos inelegíveis pela política vigente (que devem ser mantidos na cadeia com o motivo da inelegibilidade explicitado no campo \"reason\").")
    print("2. Lacuna no catálogo: se não houver par modelo/effort adequado e autorizado no catálogo para um determinado harness, devolva \"model\": null e \"effort\": null, com a justificativa da lacuna em \"reason\".")
    print("3. Pertinência de evidências: o campo \"evidence_ids\" deve conter exclusivamente identificadores únicos presentes no briefing, pertinentes ao modelo e à tarefa avaliada.")
    print("4. Base de custo (\"cost_basis\"): use \"local_observed\" para medição local fornecida; \"official_task_proxy\" para proxy oficial de tarefa; \"token_price_only\" para tarifa de token publicada; ou \"unknown\" quando não houver base econômica. Quando diferente de \"unknown\", \"evidence_ids\" deve conter ao menos um ID econômico pertinente.")
    print("5. Sem propriedades extras: o schema impõe \"additionalProperties: false\" em todos os níveis. É estritamente proibido emitir propriedades não previstas no schema.")
    print("6. Fechamento obrigatório: responda exclusivamente com o objeto JSON íntegro, garantindo o fechamento correto de todas as chaves e colchetes. Sem texto introdutório, sem comentários, sem dados adicionais e sem truncamento ou fechamento prematuro.")


if __name__ == "__main__":
    main()
