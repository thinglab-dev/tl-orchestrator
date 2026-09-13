#!/usr/bin/env python3
"""
T014 Deterministic Participant Policy Tests
Verifica regras da política global de participantes, herança e resolução de cadeias
no tl-orchestrator e seus consumidores.
"""

import os
import re
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
PERFIS_PATH = os.path.join(BASE_DIR, "prompts/orchestrator-perfis.md")
README_PATH = os.path.join(BASE_DIR, "README.md")
PROJECT_PATH = os.path.join(BASE_DIR, "_tl-orc/PROJECT.md")
CHANGELOG_PATH = os.path.join(BASE_DIR, "CHANGELOG.md")

# Model definitions and families
HARNESS_FAMILY = {
    "agy": "google",
    "claude": "anthropic",
    "codex": "openai"
}

# Global published default chains
DEFAULT_CHAINS = {
    "classifier": ["agy", "codex", "claude"],
    "planner": ["claude", "codex", "agy"],
    "maker": ["agy", "codex", "claude"],
    "checker": ["codex", "claude", "agy"],
    "searcher": ["agy", "claude", "codex"]
}

DEFAULT_CANDIDATES = {
    "classifier": {
        "agy": ("gemini-3.8-flash-medium", "medium"),
        "codex": ("gpt-5.6-luna", "medium"),
        "claude": ("sonnet", "medium")
    },
    "planner": {
        "claude": ("sonnet", "medium"),
        "codex": ("gpt-5.6-terra", "medium"),
        "agy": ("gemini-3.1-pro-high", "high")
    },
    "maker": {
        "agy": ("gemini-3.8-flash-high", "high"),
        "codex": ("gpt-5.6-terra", "high"),
        "claude": ("sonnet", "high")
    },
    "checker": {
        "codex": ("gpt-5.6-terra", "high"),
        "claude": ("sonnet", "high"),
        "agy": ("gemini-3.1-pro-high", "high")
    }
}

class RoutingResolver:
    """Simulador formal da resolução de despacho sob a política global do tl-orchestrator."""
    def __init__(self, available_harnesses=None, user_instructions=None, project_config=None):
        self.available = set(available_harnesses) if available_harnesses is not None else {"agy", "claude", "codex"}
        self.user_instructions = user_instructions or {}
        self.project_config = project_config or {}

    def resolve_chain(self, role):
        # Precedence: user instruction > project config > published default
        if role in self.user_instructions and "chain" in self.user_instructions[role]:
            chain = self.user_instructions[role]["chain"]
        elif role in self.project_config and "chain" in self.project_config[role]:
            chain = self.project_config[role]["chain"]
        else:
            chain = DEFAULT_CHAINS[role]
        return [h for h in chain if h in self.available]

    def resolve_participant(self, role, authors=None, independence="required"):
        chain = self.resolve_chain(role)
        authors = set(authors or [])

        # User pin check
        if role in self.user_instructions and "pin" in self.user_instructions[role]:
            pin_harness, pin_model, pin_effort = self.user_instructions[role]["pin"]
            if pin_harness in self.available:
                if role == "checker" and independence == "required":
                    pin_family = HARNESS_FAMILY[pin_harness]
                    if pin_family in authors:
                        raise ValueError(f"User pin {pin_harness} violates required independence against authors {authors}")
                return pin_harness, pin_model, pin_effort

        # Project pin check
        if role in self.project_config and "pin" in self.project_config[role]:
            pin_harness, pin_model, pin_effort = self.project_config[role]["pin"]
            if pin_harness in self.available:
                if role == "checker" and independence == "required":
                    pin_family = HARNESS_FAMILY[pin_harness]
                    if pin_family in authors:
                        # Pin cannot violate required independence
                        pass
                    else:
                        return pin_harness, pin_model, pin_effort
                else:
                    return pin_harness, pin_model, pin_effort

        # Normal chain resolution
        for harness in chain:
            family = HARNESS_FAMILY[harness]
            if role == "checker" and independence == "required":
                if family in authors:
                    continue  # Ineligible under independence
            model, effort = DEFAULT_CANDIDATES[role][harness]
            return harness, model, effort

        return None, None, None


def test_textual_invariants():
    print("\n--- Running Textual Invariant Checks ---")
    with open(PERFIS_PATH, "r", encoding="utf-8") as f:
        perfis = f.read()
    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()
    with open(PROJECT_PATH, "r", encoding="utf-8") as f:
        project = f.read()
    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        changelog = f.read()

    # Invariant 1: perfis Maker and Checker order in default profile table
    assert re.search(r"\|\s*Maker\s*\|\s*Agy\s*→\s*Codex\s*→\s*Claude\s*\|", perfis), "Perfis: Maker chain incorrect"
    assert re.search(r"\|\s*Checker report-only\s*\|\s*Codex\s*→\s*Claude\s*→\s*Agy", perfis), "Perfis: Checker chain incorrect"
    print("  OK: perfis.md table contains Maker Agy→Codex→Claude and Checker Codex→Claude→Agy")

    # Invariant 2: perfis details on model/effort pairs
    assert "Agy `gemini-3.8-flash-high` (`high`)" in perfis, "Perfis: Maker Agy pair missing"
    assert "Codex `gpt-5.6-terra` (`high`)" in perfis, "Perfis: Checker Codex Terra pair missing"
    assert "Codex → Claude → Agy" in perfis, "Perfis: Checker independence order missing"
    print("  OK: perfis.md declares specific model/effort pairs for Maker and Checker")

    # Invariant 3: README.md reflections (Quick Start, intro and Mermaid diagram)
    assert re.search(r"-\s*Maker:\s*Agy\s*→\s*Codex\s*→\s*Claude;", readme), "README: Maker chain incorrect in Quick Start"
    assert re.search(r"-\s*Checker report-only:\s*Codex\s*→\s*Claude\s*→\s*Agy", readme), "README: Checker chain incorrect in Quick Start"
    assert "**Maker Agy → Codex → Claude**" in readme, "README: Maker chain incorrect in intro"
    assert "**Checker Codex → Claude → Agy**" in readme, "README: Checker chain incorrect in intro"
    assert 'M["Maker · Agy → Codex → Claude"]' in readme, "README: Maker chain incorrect in Mermaid diagram"
    assert 'C["Checker · Codex → Claude → Agy"]' in readme, "README: Checker chain incorrect in Mermaid diagram"
    assert "Maker Codex → Claude → Agy" not in readme, "README: legacy Maker chain still present"
    assert "Checker Agy → Claude → Codex" not in readme, "README: legacy Checker chain still present"
    print("  OK: README.md correctly mirrors Maker Agy and Checker Codex in intro, diagram and Quick Start, with legacy chains purged")

    # Invariant 3b: prompts/orchestrator.md and docs/PROJECT_CONFIGURATION.md reflections
    ORCH_PATH = os.path.join(BASE_DIR, "prompts/orchestrator.md")
    DOC_CONF_PATH = os.path.join(BASE_DIR, "docs/PROJECT_CONFIGURATION.md")
    with open(ORCH_PATH, "r", encoding="utf-8") as f:
        orch = f.read()
    with open(DOC_CONF_PATH, "r", encoding="utf-8") as f:
        doc_conf = f.read()
    assert "**Maker Agy → Codex → Claude**" in orch, "orchestrator.md: Maker chain incorrect"
    assert "**Checker Codex → Claude → Agy**" in orch, "orchestrator.md: Checker chain incorrect"
    assert "Maker Agy → Codex → Claude" in doc_conf, "PROJECT_CONFIGURATION.md: Maker chain incorrect"
    assert "Checker\nCodex → Claude → Agy" in doc_conf or "Checker Codex → Claude → Agy" in doc_conf, "PROJECT_CONFIGURATION.md: Checker chain incorrect"
    assert "Maker Codex → Claude → Agy" not in orch, "orchestrator.md: legacy Maker chain still present"
    assert "Checker Agy → Claude → Codex" not in orch, "orchestrator.md: legacy Checker chain still present"
    print("  OK: orchestrator.md and PROJECT_CONFIGURATION.md correctly aligned with Maker Agy and Checker Codex")

    # Invariant 4: _tl-orc/PROJECT.md reflection
    assert "| Checker report-only | Codex → Claude → Agy" in project, "PROJECT.md: Checker chain incorrect"
    assert "gpt-5.6-terra" in project, "PROJECT.md: Terra reference missing"
    assert "sem pin rígido obrigatório" in project, "PROJECT.md: Astra pin relaxation missing"
    print("  OK: _tl-orc/PROJECT.md aligns Checker to Codex and relaxes Astra mandatory pin")

    # Invariant 5: CHANGELOG.md records
    assert "Maker passa a ter como preferência Agy `gemini-3.8-flash-high`" in changelog, "CHANGELOG: Maker missing"
    assert "Checker report-only passa a ter como preferência nominal Codex `gpt-5.6-terra`" in changelog, "CHANGELOG: Checker missing"
    print("  OK: CHANGELOG.md registers the new global participant policy under Unreleased")


def test_functional_probes():
    print("\n--- Running Functional Decision Probes ---")

    # Probe 1: 4 roles default priority when all 3 harnesses available
    resolver = RoutingResolver()
    c_h, c_m, c_e = resolver.resolve_participant("classifier")
    p_h, p_m, p_e = resolver.resolve_participant("planner")
    m_h, m_m, m_e = resolver.resolve_participant("maker")
    k_h, k_m, k_e = resolver.resolve_participant("checker", authors=[])

    assert (c_h, c_m, c_e) == ("agy", "gemini-3.8-flash-medium", "medium"), f"Classifier expected agy, got {c_h}"
    assert (p_h, p_m, p_e) == ("claude", "sonnet", "medium"), f"Planner expected claude, got {p_h}"
    assert (m_h, m_m, m_e) == ("agy", "gemini-3.8-flash-high", "high"), f"Maker expected agy, got {m_h}"
    assert (k_h, k_m, k_e) == ("codex", "gpt-5.6-terra", "high"), f"Checker expected codex, got {k_h}"
    print("  OK: Probe 1 passed (Classifier Agy, Planner Claude, Maker Agy, Checker Codex)")

    # Probe 2: Fallback when a harness is absent
    # Scenario A: Codex is absent
    res_no_codex = RoutingResolver(available_harnesses=["agy", "claude"])
    k_h2, k_m2, _ = res_no_codex.resolve_participant("checker", authors=["google"])
    assert k_h2 == "claude" and k_m2 == "sonnet", f"Expected fallback to Claude, got {k_h2}"
    print("  OK: Probe 2A passed (Codex absent -> Checker falls back to Claude)")

    # Scenario B: Agy is absent
    res_no_agy = RoutingResolver(available_harnesses=["claude", "codex"])
    m_h2, m_m2, _ = res_no_agy.resolve_participant("maker")
    assert m_h2 == "codex" and m_m2 == "gpt-5.6-terra", f"Expected fallback to Codex, got {m_h2}"
    print("  OK: Probe 2B passed (Agy absent -> Maker falls back to Codex Terra)")

    # Probe 3: Checker Codex after Maker Google
    res_google_author = RoutingResolver()
    k_h3, k_m3, k_e3 = res_google_author.resolve_participant("checker", authors=["google"])
    assert k_h3 == "codex" and k_m3 == "gpt-5.6-terra", f"Expected Codex Terra after Google Maker, got {k_h3}"
    print("  OK: Probe 3 passed (Maker Google -> Checker Codex Terra)")

    # Probe 4: Checker Claude when Google + OpenAI participated in authorship
    k_h4, k_m4, k_e4 = resolver.resolve_participant("checker", authors=["google", "openai"])
    assert k_h4 == "claude" and k_m4 == "sonnet", f"Expected Claude Sonnet after Google+OpenAI authorship, got {k_h4}"
    print("  OK: Probe 4 passed (Google + OpenAI authors -> Checker Claude Sonnet)")

    # Probe 5: Impossibility of Checker of same family as any author under required independence
    k_h5, _, _ = resolver.resolve_participant("checker", authors=["google", "openai", "anthropic"])
    assert k_h5 is None, f"Expected None when all 3 families participated, got {k_h5}"
    print("  OK: Probe 5 passed (All 3 families participated -> Despacho bloqueado sem auto-revisão)")

    # Probe 6: Precedence User > Project > Published Default
    # Project overrides Maker to Claude
    res_proj = RoutingResolver(project_config={"maker": {"pin": ("claude", "claude-opus-5", "high")}})
    m_proj_h, m_proj_m, _ = res_proj.resolve_participant("maker")
    assert (m_proj_h, m_proj_m) == ("claude", "claude-opus-5"), "Project override failed"

    # User overrides Maker to Codex Terra (overriding project)
    res_user = RoutingResolver(
        project_config={"maker": {"pin": ("claude", "claude-opus-5", "high")}},
        user_instructions={"maker": {"pin": ("codex", "gpt-5.6-terra", "xhigh")}}
    )
    m_user_h, m_user_m, _ = res_user.resolve_participant("maker")
    assert (m_user_h, m_user_m) == ("codex", "gpt-5.6-terra"), "User override failed"
    print("  OK: Probe 6 passed (Precedence User > Project > Published Default enforced)")


if __name__ == "__main__":
    print("=== T014 Deterministic Participant Policy Tests ===")
    test_textual_invariants()
    test_functional_probes()
    print("\nALL INVARIANTS AND PROBES PASSED SUCCESSFULLY (exit 0).\n")
    sys.exit(0)
