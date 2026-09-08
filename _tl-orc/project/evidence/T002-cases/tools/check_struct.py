#!/usr/bin/env python3
"""Validador estrutural mínimo (sem dependências) para classification-result.schema.json:
suporta type, enum, const, required, properties, additionalProperties, items, minItems, maxItems,
uniqueItems, minLength, $ref (#/$defs/...), allOf, if/then, not. Uso: check_struct.py schema.json resposta.json"""
import json, sys
schema = json.load(open(sys.argv[1])); errors = []
def resolve(ref): 
    o = schema
    for part in ref.lstrip("#/").split("/"): o = o[part]
    return o
def typ(v):
    return {bool:"boolean", int:"integer", float:"number", str:"string", list:"array", dict:"object", type(None):"null"}[type(v)]
def matches(sch, v):
    e=[]; val(sch, v, "$", e); return not e
def val(sch, v, path, errs):
    if "$ref" in sch: sch = {**resolve(sch["$ref"]), **{k:x for k,x in sch.items() if k!="$ref"}}
    if "allOf" in sch:
        for s in sch["allOf"]: val(s, v, path, errs)
    if "if" in sch and matches(sch["if"], v) and "then" in sch: val(sch["then"], v, path, errs)
    if "not" in sch and matches(sch["not"], v): errs.append(f"{path}: viola 'not'")
    if "type" in sch:
        t = sch["type"]; ts = t if isinstance(t, list) else [t]; tv = typ(v)
        if tv=="integer" and "number" in ts: tv="number"
        if tv not in ts: errs.append(f"{path}: tipo {tv}, esperado {ts}"); return
    if "const" in sch and v != sch["const"]: errs.append(f"{path}: const {sch['const']!r}, obtido {v!r}")
    if "enum" in sch and v not in sch["enum"]: errs.append(f"{path}: {v!r} fora do enum {sch['enum']}")
    if isinstance(v, str) and "minLength" in sch and len(v) < sch["minLength"]: errs.append(f"{path}: string curta")
    if isinstance(v, dict):
        for r in sch.get("required", []):
            if r not in v: errs.append(f"{path}: campo obrigatório ausente '{r}'")
        props = sch.get("properties", {})
        for k, x in v.items():
            if k in props: val(props[k], x, f"{path}.{k}", errs)
            elif sch.get("additionalProperties") is False: errs.append(f"{path}: propriedade extra '{k}'")
            elif isinstance(sch.get("additionalProperties"), dict): val(sch["additionalProperties"], x, f"{path}.{k}", errs)
    if isinstance(v, list):
        if "minItems" in sch and len(v) < sch["minItems"]: errs.append(f"{path}: menos de {sch['minItems']} itens")
        if "maxItems" in sch and len(v) > sch["maxItems"]: errs.append(f"{path}: mais de {sch['maxItems']} itens")
        if sch.get("uniqueItems") and len({json.dumps(i, sort_keys=True) for i in v}) != len(v): errs.append(f"{path}: itens repetidos")
        if "items" in sch:
            for i, x in enumerate(v): val(sch["items"], x, f"{path}[{i}]", errs)
raw = open(sys.argv[2]).read().strip()
try: obj = json.loads(raw)
except Exception as ex: print(f"JSON inválido: {ex}"); sys.exit(2)
val(schema, obj, "$", errors)
print("ESTRUTURA:", "válida" if not errors else "INVÁLIDA"); [print(" -", e) for e in errors]; sys.exit(1 if errors else 0)
