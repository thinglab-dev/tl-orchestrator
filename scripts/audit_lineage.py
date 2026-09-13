#!/usr/bin/env python3
"""
scripts/audit_lineage.py - Guarda mecânica determinística de linhagem, board e integridade relacional.
Valida as 14 checagens relacionais L01-L14 sobre _tl-orc/project/tasks/, STATUS.md e lineage-map.md.
"""

import os
import sys
import re
import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

def compute_lineage_digest(content: str) -> str:
    """Calcula deterministamente o SHA-256[:16] do corpo canônico de lineage-map.md."""
    lines = content.strip().splitlines()
    body_lines = []
    for l in lines:
        if l.startswith("lineage_digest:"):
            continue
        body_lines.append(l.rstrip())
    canonical_body = "\n".join(body_lines) + "\n"
    return hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()[:16]

def parse_yaml_frontmatter(file_path: Path) -> Tuple[Dict[str, Any], int]:
    """Parse simples e determinístico do YAML frontmatter de arquivos de task."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"_parse_error": str(e)}, 1

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        # Se não começar com '---', verifica se o próprio topo é YAML chave: valor
        fm_lines = []
        for l in lines:
            if l.startswith("## ") or l.startswith("# "):
                break
            fm_lines.append(l)
    else:
        fm_lines = []
        for l in lines[1:]:
            if l.strip() == "---":
                break
            fm_lines.append(l)

    data: Dict[str, Any] = {}
    current_key = None

    for idx, line in enumerate(fm_lines):
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue

        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()

            # Tratar listas inline [a, b]
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                if not inner:
                    data[key] = []
                else:
                    data[key] = [item.strip() for item in inner.split(",") if item.strip()]
            elif val == "":
                data[key] = []
                current_key = key
            else:
                # Conversão simples de int/bool
                if val.isdigit():
                    data[key] = int(val)
                elif val.lower() == "true":
                    data[key] = True
                elif val.lower() == "false":
                    data[key] = False
                elif val.lower() == "none" or val.lower() == "null":
                    data[key] = None
                else:
                    data[key] = val
        elif line_str.startswith("- ") and current_key:
            data[current_key].append(line_str[2:].strip())

    return data, len(fm_lines)

def parse_status_board(status_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Parse da tabela ## Tasks e do cabeçalho de STATUS.md."""
    if not status_path.exists():
        return {}, [], ["STATUS.md não encontrado"]

    lines = status_path.read_text(encoding="utf-8").splitlines()
    header: Dict[str, Any] = {}
    tasks: List[Dict[str, Any]] = []
    errors: List[str] = []

    in_tasks = False
    in_header = True

    in_tasks = False
    in_header = True
    table_found = False
    header_checked = False
    expected_header = ["id", "type", "deliverable", "status", "depends_on", "blocked_by", "state_revision", "last_evidence"]

    for line_idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "## Tasks":
            in_tasks = True
            in_header = False
            table_found = True
            continue
        elif stripped.startswith("## ") and in_tasks:
            in_tasks = False
            continue

        if in_header:
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v.isdigit():
                    header[k] = int(v)
                else:
                    header[k] = v

        elif in_tasks:
            if not stripped.startswith("|"):
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if not cells:
                continue

            if not header_checked:
                header_checked = True
                if cells != expected_header:
                    errors.append(f"{status_path}:{line_idx}: BLOCKER [L10]: cabeçalho da tabela fora de ordem ou inválido: encontrado {cells}, esperado {expected_header}")
                continue

            if cells[0].startswith(":-") or cells[0].startswith("-"):
                continue

            if len(cells) != 8:
                errors.append(f"{status_path}:{line_idx}: BLOCKER [L10]: linha do board possui {len(cells)} células, esperadas 8 colunas: {line.strip()}")
                continue

            # Parse cell values: id | type | deliverable | status | depends_on | blocked_by | state_revision | last_evidence
            t_id, t_type, t_deliv, t_status, t_dep, t_blk, t_srev, t_ev = cells

            def parse_list(s: str) -> List[str]:
                if s.startswith("[") and s.endswith("]"):
                    inner = s[1:-1].strip()
                    if not inner:
                        return []
                    return [x.strip() for x in inner.split(",") if x.strip()]
                return [s] if s and s != "-" else []

            tasks.append({
                "line": line_idx,
                "id": t_id,
                "type": t_type,
                "deliverable": t_deliv,
                "status": t_status,
                "depends_on": parse_list(t_dep),
                "blocked_by": parse_list(t_blk),
                "state_revision": int(t_srev) if t_srev.isdigit() else t_srev,
                "last_evidence": t_ev
            })

    if not table_found:
        errors.append(f"{status_path}:1: BLOCKER [L02]: tabela ## Tasks não encontrada no STATUS.md")

    return header, tasks, errors

def parse_lineage_map(map_path: Path) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], List[str]]:
    """Parse de _tl-orc/project/lineage-map.md."""
    if not map_path.exists():
        return {}, {}, {}, ["lineage-map.md não encontrado"]

    text = map_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    retired_map: Dict[str, str] = {} # retired_id -> live_id
    retired_files: Dict[str, str] = {} # retired_id -> retired_file
    retired_reasons: Dict[str, str] = {} # retired_id -> reason
    errors: List[str] = []

    # Validar digest
    digest_val = None
    for l in lines:
        if l.startswith("lineage_digest:"):
            digest_val = l.split(":", 1)[1].strip()
            break

    if not digest_val:
        errors.append(f"{map_path}:1: BLOCKER [L08]: lineage_digest ausente no cabeçalho")
    else:
        calculated = compute_lineage_digest(text)
        if digest_val != calculated:
            errors.append(f"{map_path}:1: BLOCKER [L08]: lineage_digest inválido: declarado {digest_val} != calculado {calculated}")

    in_retired = False
    for line_idx, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("## Retired identities"):
            in_retired = True
            continue
        elif s.startswith("## ") and in_retired:
            in_retired = False
            continue

        if in_retired and s.startswith("|"):
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if len(cells) >= 4 and cells[0] != "retired_id" and not cells[0].startswith(":-"):
                ret_id = cells[0]
                ret_file = cells[1]
                live_id = cells[3]
                reason = cells[5] if len(cells) >= 6 else ""
                retired_map[ret_id] = live_id
                retired_files[ret_id] = ret_file
                retired_reasons[ret_id] = reason

    return retired_map, retired_files, retired_reasons, errors

def run_audits(root: Path, selected_checks: Optional[Set[str]] = None) -> Tuple[List[str], List[str]]:
    blockers: List[str] = []
    warnings: List[str] = []

    tasks_dir = root / "_tl-orc" / "project" / "tasks"
    status_file = root / "_tl-orc" / "project" / "STATUS.md"
    lineage_file = root / "_tl-orc" / "project" / "lineage-map.md"
    evidence_dir = root / "_tl-orc" / "project" / "evidence"

    # L08 & lineage map parsing
    if not lineage_file.exists():
        blockers.append(f"{lineage_file}:1: BLOCKER [L08]: lineage-map.md ausente")
        retired_map, retired_files, retired_reasons = {}, {}, {}
    else:
        retired_map, retired_files, retired_reasons, l08_errs = parse_lineage_map(lineage_file)
        blockers.extend(l08_errs)

    # L10 & STATUS.md parsing
    if not status_file.exists():
        blockers.append(f"{status_file}:1: BLOCKER [L02]: STATUS.md ausente")
        board_header, board_tasks = {}, []
    else:
        board_header, board_tasks, l10_errs = parse_status_board(status_file)
        blockers.extend(l10_errs)

    # Coletar arquivos de tasks
    if not tasks_dir.exists():
        blockers.append(f"{tasks_dir}:1: BLOCKER [L02]: diretório de tasks ausente")
        task_files = []
    else:
        task_files = sorted(list(tasks_dir.glob("T*.md")))

    # Mapear tasks
    tasks_by_id: Dict[str, List[Tuple[Path, Dict[str, Any]]]] = {}
    id_to_file: Dict[str, Path] = {}

    for tf in task_files:
        fm, _ = parse_yaml_frontmatter(tf)
        tid = fm.get("id")
        if not tid or not isinstance(tid, str):
            blockers.append(f"{tf}:1: BLOCKER [L01]: frontmatter não declara id válido")
            continue

        if tid not in tasks_by_id:
            tasks_by_id[tid] = []
        tasks_by_id[tid].append((tf, fm))
        id_to_file[tid] = tf

        # L02: prefixo do nome de arquivo deve casar com o id
        expected_prefix = f"{tid}-"
        if not tf.name.startswith(expected_prefix):
            blockers.append(f"{tf}:1: BLOCKER [L02]: nome de arquivo {tf.name} não inicia com prefixo {expected_prefix}")

    # L01: Unicidade de task id
    for tid, instances in tasks_by_id.items():
        if len(instances) > 1:
            paths = ", ".join(str(p.relative_to(root)) for p, _ in instances)
            for p, _ in instances:
                blockers.append(f"{p}:1: BLOCKER [L01]: task id duplicado '{tid}' encontrado em múltiplos arquivos: {paths}")

    # L02: Bijeção id <-> arquivo <-> board
    board_tasks_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for bt in board_tasks:
        bt_id = bt["id"]
        if bt_id not in board_tasks_by_id:
            board_tasks_by_id[bt_id] = []
        board_tasks_by_id[bt_id].append(bt)

    for bt_id, b_list in board_tasks_by_id.items():
        if len(b_list) > 1:
            blockers.append(f"{status_file}:{b_list[0]['line']}: BLOCKER [L02]: múltiplas linhas de board para o mesmo id '{bt_id}'")
        if bt_id not in id_to_file:
            blockers.append(f"{status_file}:{b_list[0]['line']}: BLOCKER [L02]: linha de board para id '{bt_id}' sem arquivo correspondente em tasks/")

    for tid, tf in id_to_file.items():
        if tid not in board_tasks_by_id:
            blockers.append(f"{tf}:1: BLOCKER [L02]: task file '{tf.name}' sem linha correspondente no board STATUS.md")

    # L08 Adicional: retired_file não pode existir, live_id deve existir,
    # e retired_id não pode ser id vivo EXCETO quando reason documenta colisão/duplicata legítima
    # e o arquivo vivo for diferente do retired_file.
    for ret_id, live_id in retired_map.items():
        if live_id not in id_to_file:
            blockers.append(f"{lineage_file}:1: BLOCKER [L08]: live_id de destino '{live_id}' para retired_id '{ret_id}' não existe no disco")
        ret_file = retired_files.get(ret_id)
        if ret_file and (root / ret_file).exists():
            blockers.append(f"{lineage_file}:1: BLOCKER [L08]: retired_file '{ret_file}' ainda existe fisicamente no disco")
        if ret_id in id_to_file:
            reason = retired_reasons.get(ret_id, "")
            is_valid_collision = (
                ("collision" in reason or "duplicate" in reason)
                and ret_file
                and str(id_to_file[ret_id].relative_to(root)) != ret_file
            )
            if not is_valid_collision:
                blockers.append(f"{lineage_file}:1: BLOCKER [L08]: retired_id '{ret_id}' ainda existe como task viva no disco: {id_to_file[ret_id]}")

    # L03, L04, L05, L07, L09, L11, L13 sobre tasks vivas
    live_ids = set(id_to_file.keys())
    board_by_id = {bt["id"]: bt for bt in board_tasks if bt["id"] in live_ids}

    # Grafo para checagem de aciclicidade (L06)
    graph: Dict[str, List[str]] = {}

    for tid, instances in tasks_by_id.items():
        if len(instances) != 1:
            continue
        tf, fm = instances[0]
        deps = fm.get("depends_on", [])
        if not isinstance(deps, list):
            deps = [deps] if deps else []
        blks = fm.get("blocked_by", [])
        if not isinstance(blks, list):
            blks = [blks] if blks else []
        provs = fm.get("provenance", [])
        if not isinstance(provs, list):
            provs = [provs] if provs else []

        status = fm.get("status")
        t_type = fm.get("type")
        s_rev = fm.get("state_revision")

        graph[tid] = deps

        # L03: unresolved depends_on / blocked_by
        for d in deps:
            if d not in live_ids:
                if d in retired_map:
                    # L04: ambiguous depends_on (citando retired identity)
                    blockers.append(f"{tf}:1: BLOCKER [L04]: depends_on referencia identidade aposentada '{d}' (substituída por '{retired_map[d]}')")
                else:
                    blockers.append(f"{tf}:1: BLOCKER [L03]: depends_on referencia id inexistente '{d}'")

        for b in blks:
            if b not in live_ids:
                if b in retired_map:
                    blockers.append(f"{tf}:1: BLOCKER [L04]: blocked_by referencia identidade aposentada '{b}' (substituída por '{retired_map[b]}')")
                else:
                    blockers.append(f"{tf}:1: BLOCKER [L03]: blocked_by referencia id inexistente '{b}'")

        # L07: done-depends-on-open
        if status == "done":
            for d in deps:
                if d in live_ids:
                    target_status = tasks_by_id[d][0][1].get("status")
                    if target_status != "done":
                        blockers.append(f"{tf}:1: BLOCKER [L07]: task concluída (done) depende operacionalmente de task não concluída '{d}' (status: {target_status})")

        # L09: provenance sanity
        for p in provs:
            if p not in live_ids:
                blockers.append(f"{tf}:1: BLOCKER [L09]: provenance referencia id inexistente '{p}'")
            if p in deps:
                blockers.append(f"{tf}:1: BLOCKER [L09]: id '{p}' está declarado simultaneamente em depends_on e provenance")

        # L13: blocked eligibility
        if blks and status == "done":
            blockers.append(f"{tf}:1: BLOCKER [L13]: task com status 'done' não pode ter blocked_by não-vazio ({blks})")

        # Regra específica de projeto para T019: enquanto T024 != done, T019 deve declarar bloqueio por T024
        if tid == "T019":
            t024_status = tasks_by_id.get("T024", [(None, {})])[0][1].get("status")
            if t024_status != "done":
                if "T024" not in blks:
                    blockers.append(f"{tf}:1: BLOCKER [L13]: T019 deve declarar blocked_by: [T024] enquanto T024 não estiver concluída")

        # L05: Board parity
        bt = board_by_id.get(tid)
        if bt:
            # Paridade de status
            if str(bt.get("status")) != str(status):
                blockers.append(f"{tf}:1: BLOCKER [L05]: divergência de status entre arquivo ({status}) e board ({bt.get('status')})")
            # Paridade de state_revision
            if bt.get("state_revision") != s_rev:
                blockers.append(f"{tf}:1: BLOCKER [L05]: divergência de state_revision entre arquivo ({s_rev}) e board ({bt.get('state_revision')})")
            # Paridade de type
            if str(bt.get("type")) != str(t_type):
                blockers.append(f"{tf}:1: BLOCKER [L05]: divergência de type entre arquivo ({t_type}) e board ({bt.get('type')})")
            # Paridade de depends_on
            if sorted(bt.get("depends_on", [])) != sorted(deps):
                blockers.append(f"{tf}:1: BLOCKER [L05]: divergência de depends_on entre arquivo ({deps}) e board ({bt.get('depends_on')})")
            # Paridade de blocked_by
            if sorted(bt.get("blocked_by", [])) != sorted(blks):
                blockers.append(f"{tf}:1: BLOCKER [L05]: divergência de blocked_by entre arquivo ({blks}) e board ({bt.get('blocked_by')})")

            # L11: last_evidence resolvability
            last_ev = bt.get("last_evidence")
            if last_ev and last_ev != "-":
                ev_path = root / "_tl-orc" / "project" / last_ev
                if not ev_path.exists():
                    # Tentar relativo à raiz se já incluir _tl-orc
                    ev_path2 = root / last_ev
                    if not ev_path2.exists():
                        blockers.append(f"{status_file}:{bt['line']}: BLOCKER [L11]: last_evidence aponta para arquivo inexistente '{last_ev}'")

        # L11: content_paths de task done deve existir (ou estar declarado no lineage-map)
        if status == "done":
            cps = fm.get("content_paths", [])
            if isinstance(cps, list):
                for cp in cps:
                    if not (root / cp).exists():
                        declared_historical = (
                            cp in retired_files.values()
                            or any(cp in rf for rf in retired_files.values())
                        )
                        if not declared_historical:
                            blockers.append(f"{tf}:1: BLOCKER [L11]: content_path '{cp}' de task concluída não existe no disco")

    # L06: Acyclicity via TopoSort (Kahn's algorithm)
    in_degree = {u: 0 for u in graph}
    adj: Dict[str, List[str]] = {u: [] for u in graph}

    for u, edges in graph.items():
        for v in edges:
            if v in graph:
                adj[v].append(u)
                in_degree[u] += 1

    queue = [u for u, deg in in_degree.items() if deg == 0]
    visited_count = 0

    while queue:
        curr = queue.pop(0)
        visited_count += 1
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited_count < len(graph):
        cycle_nodes = [u for u, deg in in_degree.items() if deg > 0]
        blockers.append(f"{tasks_dir}:1: BLOCKER [L06]: ciclo de dependências detectado envolvendo nós: {cycle_nodes}")

    # L14: next_task_id sanity
    declared_next = board_header.get("next_task_id")
    numeric_ids = []
    for tid in live_ids:
        m = re.match(r"^T(\d+)$", tid)
        if m:
            numeric_ids.append(int(m.group(1)))

    if numeric_ids and declared_next is not None:
        max_id = max(numeric_ids)
        if declared_next <= max_id:
            blockers.append(f"{status_file}:1: BLOCKER [L14]: next_task_id ({declared_next}) deve ser estritamente maior que o maior ID numérico existente ({max_id})")

    # L12: Alertas de referências a identidades aposentadas fora de lineage-map.md
    # Apenas verificação rápida opcional
    for tf in task_files:
        content = tf.read_text(encoding="utf-8")
        for ret_id in retired_map:
            # Busca por palavra inteira
            pattern = r"\b" + re.escape(ret_id) + r"\b"
            if re.search(pattern, content):
                warnings.append(f"{tf}:1: WARNING [L12]: referência textual à identidade aposentada '{ret_id}'")

    if selected_checks:
        blockers = [b for b in blockers if any(f"[{c}]" in b for c in selected_checks)]
        warnings = [w for w in warnings if any(f"[{c}]" in w for c in selected_checks)]

    return blockers, warnings

def main():
    parser = argparse.ArgumentParser(description="Guarda mecânica de linhagem e board.")
    parser.add_argument("--root", default=".", help="Raiz do repositório")
    parser.add_argument("--check", action="append", help="Filtrar checagens específicas (ex: L01, done-depends-on-open)")
    parser.add_argument("--verify-digest", action="store_true", help="Validar digest do lineage-map")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Formato de saída")

    args = parser.parse_args()
    root_path = Path(args.root).resolve()

    selected = set()
    if args.check:
        alias_map = {
            "done-depends-on-open": "L07",
            "board-parity": "L05",
            "blocked-eligibility": "L13"
        }
        for c in args.check:
            selected.add(alias_map.get(c, c))

    if args.verify_digest:
        selected.add("L08")

    blockers, warnings = run_audits(root_path, selected_checks=selected if selected else None)

    if args.format == "json":
        import json
        print(json.dumps({"blockers": blockers, "warnings": warnings}, indent=2, ensure_ascii=False))
    else:
        for w in warnings:
            print(w)
        for b in blockers:
            print(b)

    if blockers:
        sys.exit(1)
    else:
        if not warnings and args.format == "text":
            print("OK: audit_lineage passou sem BLOCKERs")
        sys.exit(0)

if __name__ == "__main__":
    main()
