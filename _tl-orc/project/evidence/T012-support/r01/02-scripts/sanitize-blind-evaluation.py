#!/usr/bin/env python3
"""
sanitize-blind-evaluation.py
Sanitização determinística e cegamento para avaliação comparativa A/B (T012).

Substitui raízes físicas absolutas por `<root>/`, remove identificadores de
harness e gera saídas cegas rotuladas como 'Decisão Alpha' e 'Decisão Beta'.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path


def sanitize_text(text: str, root_path: str) -> str:
    """
    Sanitiza um texto removendo caminhos absolutos locais e identificadores de harness.
    """
    out = text

    # 1. Normalizar barra final do root_path
    clean_root = os.path.abspath(root_path).rstrip("/")

    # 2. Substituir variações do caminho absoluto do root
    # Mac /private/var ou /var
    out = out.replace("/private" + clean_root, "<root>")
    out = out.replace(clean_root, "<root>")

    # Raiz home comum se vazar
    home_dir = str(Path.home())
    out = out.replace("/private" + home_dir, "<user_home>")
    out = out.replace(home_dir, "<user_home>")

    # 3. Remover UUIDs (harness session IDs, request IDs)
    uuid_pattern = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    out = uuid_pattern.sub("<sanitized-uuid>", out)

    # 4. Remover prefixos de request do harness (ex: req_011CepowWe9vebKhNUiqnxyA, msg_..., toolu_...)
    out = re.sub(r"\b(req|msg|toolu)_[a-zA-Z0-9]{20,}\b", "<sanitized-id>", out)

    # 5. Remover timestamps UTC ISO ou compactos (ex: 2026-09-07T21:38:30Z, 20260907T213830Z)
    iso_ts_pattern = re.compile(
        r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b"
    )
    out = iso_ts_pattern.sub("<sanitized-timestamp>", out)
    compact_ts_pattern = re.compile(r"\b\d{8}T\d{6}Z\b")
    out = compact_ts_pattern.sub("<sanitized-timestamp>", out)

    # 6. Remover menções explícitas a Braço A / Braço B ou dir_A / dir_B
    out = re.sub(r"\bdir_A\b", "<root>", out)
    out = re.sub(r"\bdir_B\b", "<root>", out)

    return out


def blind_outputs(
    text_a: str,
    text_b: str,
    root_a: str,
    root_b: str,
    seed: int | None = None,
) -> tuple[str, str, dict]:
    """
    Sanitiza os textos dos dois braços e associa aleatoriamente a Alpha e Beta.
    Retorna (decision_alpha, decision_beta, blinding_key).
    """
    sanitized_a = sanitize_text(text_a, root_a)
    sanitized_b = sanitize_text(text_b, root_b)

    rng = random.Random(seed)
    mapping = ["A_to_Alpha", "B_to_Alpha"]
    choice = rng.choice(mapping)

    if choice == "A_to_Alpha":
        alpha_text = f"# Decisão Alpha\n\n{sanitized_a}\n"
        beta_text = f"# Decisão Beta\n\n{sanitized_b}\n"
        key = {
            "alpha": "Braço A (Controle / Histórico Acumulado)",
            "beta": "Braço B (Sessão Nova + Pacote Curto)",
            "mapping": {"Alpha": "Arm_A", "Beta": "Arm_B"},
            "hash_raw_a": hashlib.sha256(text_a.encode()).hexdigest(),
            "hash_raw_b": hashlib.sha256(text_b.encode()).hexdigest(),
        }
    else:
        alpha_text = f"# Decisão Alpha\n\n{sanitized_b}\n"
        beta_text = f"# Decisão Beta\n\n{sanitized_a}\n"
        key = {
            "alpha": "Braço B (Sessão Nova + Pacote Curto)",
            "beta": "Braço A (Controle / Histórico Acumulado)",
            "mapping": {"Alpha": "Arm_B", "Beta": "Arm_A"},
            "hash_raw_a": hashlib.sha256(text_a.encode()).hexdigest(),
            "hash_raw_b": hashlib.sha256(text_b.encode()).hexdigest(),
        }

    return alpha_text, beta_text, key


def run_self_test():
    """Validação automatizada de sanitização e cegamento."""
    dummy_root_a = "/tmp/test-t012-pilot/dir_A"
    dummy_root_b = "/tmp/test-t012-pilot/dir_B"

    raw_a = f"""
Relatório do Orquestrador no diretório {dummy_root_a}.
Sessão claude-code b1467fdf-2d9f-49d9-9e69-806eced0db41 iniciada em 2026-09-07T21:38:30Z.
RequestId: req_011CepowWe9vebKhNUiqnxyA.
Veredito da rodada r02: changes_requested conforme {dummy_root_a}/_tl-orc/project/evidence/T009-r02.md.
"""

    raw_b = f"""
Relatório do Orquestrador no diretório {dummy_root_b}.
Sessão limpa 01a07dcf-32a7-7de1-9915-a960333427a7 iniciada em 20260907T220000Z.
RequestId: req_022DefghIjklMnopQrstUvwX.
Veredito da rodada r02: changes_requested conforme {dummy_root_b}/_tl-orc/project/evidence/T009-r02.md.
"""

    alpha, beta, key = blind_outputs(
        raw_a, raw_b, dummy_root_a, dummy_root_b, seed=42
    )

    for txt, label in [(alpha, "Alpha"), (beta, "Beta")]:
        assert dummy_root_a not in txt, (
            f"Vazou dummy_root_a em {label}!"
        )
        assert dummy_root_b not in txt, (
            f"Vazou dummy_root_b em {label}!"
        )
        assert "b1467fdf" not in txt, f"Vazou UUID em {label}!"
        assert "01a07dcf" not in txt, f"Vazou UUID em {label}!"
        assert "2026-09-07T21:38:30Z" not in txt, (
            f"Vazou ISO ts em {label}!"
        )
        assert "20260907T220000Z" not in txt, (
            f"Vazou compact ts em {label}!"
        )
        assert "req_" not in txt, f"Vazou req ID em {label}!"
        assert "<root>" in txt, f"Não inseriu <root> em {label}!"

    assert key["mapping"]["Alpha"] in ["Arm_A", "Arm_B"]
    assert key["mapping"]["Beta"] in ["Arm_A", "Arm_B"]
    assert key["mapping"]["Alpha"] != key["mapping"]["Beta"]

    print("SELF-TEST: OK (sanitização de caminhos, IDs, UUIDs e timestamps validada)")


def main():
    parser = argparse.ArgumentParser(
        description="Sanitização e cegamento T012"
    )
    parser.add_argument("--self-test", action="store_true", help="Executar autoteste")
    parser.add_argument("--file-a", type=str, help="Caminho da saída do Braço A")
    parser.add_argument("--file-b", type=str, help="Caminho da saída do Braço B")
    parser.add_argument("--root-a", type=str, help="Caminho absoluto da raiz de A")
    parser.add_argument("--root-b", type=str, help="Caminho absoluto da raiz de B")
    parser.add_argument("--out-dir", type=str, help="Diretório de saída para decisões cegas")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade")

    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        sys.exit(0)

    if not (args.file_a and args.file_b and args.root_a and args.root_b and args.out_dir):
        parser.error(
            "Argumentos --file-a, --file-b, --root-a, --root-b e --out-dir são obrigatórios (ou use --self-test)."
        )

    text_a = Path(args.file_a).read_text(encoding="utf-8")
    text_b = Path(args.file_b).read_text(encoding="utf-8")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    alpha_text, beta_text, key = blind_outputs(
        text_a, text_b, args.root_a, args.root_b, seed=args.seed
    )

    alpha_file = out_dir / "decision-alpha.md"
    beta_file = out_dir / "decision-beta.md"
    key_file = out_dir / "blinding-key.json"

    alpha_file.write_text(alpha_text, encoding="utf-8")
    beta_file.write_text(beta_text, encoding="utf-8")
    key_file.write_text(json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Salvo: {alpha_file}")
    print(f"Salvo: {beta_file}")
    print(f"Chave confidencial preservada em: {key_file}")


if __name__ == "__main__":
    main()
