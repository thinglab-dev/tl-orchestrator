#!/usr/bin/env python3
import json
from pathlib import Path

session_path = Path.home() / ".claude/projects/-Users-albertiano-thinglab-tl-orchestrator/b1467fdf-2d9f-49d9-9e69-806eced0db41.jsonl"
out_file = Path("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/arm-a-history.md")

lines_to_extract = []
with open(session_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if 4407 <= idx <= 4595:
            d = json.loads(line)
            role = d.get("message", {}).get("role") or d.get("type")
            if role in ["user", "assistant", "system"] and "message" in d:
                lines_to_extract.append((idx, d["message"].get("role"), d["message"].get("content")))

print(f"Extracted {len(lines_to_extract)} turns from session b1467fdf.")

md_content = ["# Histórico da Sessão Oficial (Checkpoint T009 r02)\n"]
md_content.append("> Contexto acumulado reproduzindo a sessão oficial do Orquestrador (b1467fdf) desde o início de T009 até o recebimento da notificação de revisão r02 do Checker independente.\n")

for idx, role, content in lines_to_extract:
    md_content.append(f"### [Linha {idx} - {role.upper()}]")
    if isinstance(content, str):
        md_content.append(content.strip() + "\n")
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                txt = part.get("text", "").strip()
                if txt:
                    md_content.append(txt + "\n")
            elif ptype == "tool_use":
                tname = part.get("name")
                tinp = part.get("input")
                md_content.append(f"**Ferramenta invocada (`{tname}`):**\n```json\n{json.dumps(tinp, indent=2, ensure_ascii=False)}\n```\n")
            elif ptype == "tool_result":
                tc = str(part.get("content", "")).strip()
                md_content.append(f"**Resultado da ferramenta:**\n```\n{tc}\n```\n")

out_file.write_text("\n".join(md_content), encoding="utf-8")
print(f"Wrote {out_file} ({out_file.stat().st_size} bytes)")
