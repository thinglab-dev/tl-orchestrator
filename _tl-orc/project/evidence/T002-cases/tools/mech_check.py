#!/usr/bin/env python3
"""Conferência mecânica do Orquestrador para um resultado de classificação (uso próprio nesta Task)."""
import json, re, sys, pathlib
def catalog_from_project(path="_tl-orc/PROJECT.md"):
    rows = re.findall(r"^\| (Classificador|Planner|Maker|Checker|Searcher) \| (\w+) \| `([^`]+)` \| ([^|]+) \|", pathlib.Path(path).read_text(), re.M)
    cat = {}
    for role, harness, model, efforts in rows:
        h = {"Codex": "codex", "Claude": "claude", "Agy": "agy"}[harness]
        for e in re.findall(r"\b(low|medium|high|xhigh|max|ultra)\b", efforts):
            cat.setdefault((h, model, e), set()).add({"Classificador": "classifier", "Planner": "planner", "Maker": "maker", "Checker": "checker", "Searcher": "searcher"}[role])
    return cat
def evidence_ids(path="docs/MODEL_ROUTING.md"):
    return set(re.findall(r"`([a-z0-9]+-[a-z0-9-]+)`", pathlib.Path(path).read_text()))
def check(d, expected, cat, ids, local_ids, families, authors, policy):
    problems = []; rows = []
    for k in ("story_id", "phase", "context_revision", "catalog_revision"):
        if d.get(k) != expected[k]: problems.append(f"{k}: esperado {expected[k]!r}, obtido {d.get(k)!r}")
    if set(d.get("roles", {})) != set(expected["roles"]): problems.append(f"papéis: esperado {expected['roles']}, obtido {list(d.get('roles', {}))}")
    for role, r in d.get("roles", {}).items():
        chain = expected["chains"][role]
        if [c["harness"] for c in r["candidates"]] != chain: problems.append(f"{role}: ordem de harness {[c['harness'] for c in r['candidates']]} ≠ cadeia {chain}")
        for c in r["candidates"]:
            key = (c["harness"], c["model"], c["effort"]); ev = set(c.get("evidence_ids", [])); cb = c.get("cost_basis")
            in_cat = role in cat.get(key, set()); unknown = ev - ids - set(local_ids); price = any(e.startswith("price-") for e in ev); proxy = ev & set(expected.get("proxy_ids", [])); local = ev & set(local_ids)
            cb_ok = {"unknown": not (price or proxy or local), "token_price_only": price and not proxy and not local, "official_task_proxy": bool(proxy), "local_observed": bool(local)}.get(cb, False)
            pin = expected.get("pins", {}).get(role); pin_ok = (pin is None) or (list(key) == list(pin)) or (c is not r["candidates"][0])
            fam = families.get(c["model"])
            # independência é filtro de RESOLUÇÃO (perfis: "a seleção pula candidatos inelegíveis conforme a política"),
            # não critério de validade do objeto: candidato de mesma família fica marcado inelegível sob required
            # (ou elegível só como fallback com indisponibilidade comprovada sob preferred); não rejeita a classificação.
            eligible = not (role == "checker" and fam in authors and policy == "required")
            ok = in_cat and not unknown and cb_ok and pin_ok and c["effort"] is not None
            rows.append((role, key, in_cat, sorted(unknown), cb, cb_ok, pin_ok, "elegível" if eligible else "inelegível(required, mesma família)", ok))
            if not ok: problems.append(f"{role} {key}: catálogo={in_cat} ids_desconhecidos={sorted(unknown)} cost_basis={cb} sustentado={cb_ok} pin={pin_ok}")
        if role == "checker" and policy == "required" and all(families.get(c["model"]) in authors for c in r["candidates"]):
            problems.append("checker: nenhum candidato elegível sob required (todas as famílias são autoras)")
    return problems, rows
if __name__ == "__main__":
    d = json.load(open(sys.argv[1])); expected = json.load(open(sys.argv[2]))
    cat = catalog_from_project(); ids = evidence_ids()
    problems, rows = check(d, expected, cat, ids, expected.get("local_ids", []), expected.get("families", {}), set(expected.get("authors", [])), expected.get("policy", "preferred"))
    for r in rows: print("  ", r)
    print("RESULT:", "ACEITA" if not problems else "REJEITADA"); [print("   -", p) for p in problems]
    sys.exit(0 if not problems else 1)
