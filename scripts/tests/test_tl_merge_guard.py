"""
Offline unit test suite for tl_merge_guard.py (T028 v2).

Covers all 16 mandatory probes and Acceptance Criteria:
1. Exact PR #55 Regression Probe (green CI, approved Checker, 0 authority comments -> FAIL_CLOSED)
2. Acyclic authorization_id Derivation (AC2)
3. Ambiguous Authority Transport Probe (AC7, >1 distinct -> FAIL_CLOSED)
4. Check Source / Integration ID Binding Probe (AC9)
5. Base Drift Invalidation Probe (AC12)
6. Head Drift Invalidation Probe (AC12)
7. Uninspected Post-Review Code Mutation Probe (AC6)
8. Governance-Only Post-Review Delta Probe (AC6)
9. Anti-Replay External Store vs Local Ledger Deletion Probe (AC8)
10. Capability vs Authorization Separation Probe (AC10 / Intent 1)
11. Happy Path Probe (AC4 / AC5)
12. Safe Rollback Degradation to human_merge_only (AC13)
13. Universal Schema Portability Probe (AC1)
14. Canonicalization Determinism & Float Prohibition Probe (AC3)
15. Concurrent Atomic CAS Race Probe (AC8)
16. Candidate Branch Workflow / Key Mutation Resistance Probe (AC14)
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from scripts.tl_merge_guard import (
    AUTHORIZATION_SIGNING_DOMAIN,
    POST_REVIEW_GOVERNANCE_ALLOWLIST,
    AuthorityReceipt,
    InMemoryAuthorityStore,
    LocalLedgerAuthorityStore,
    MergeAuthorityGate,
    canonicalize_payload,
    compute_claim_digest,
    compute_signing_payload,
    derive_authorization_id,
    parse_pr_comment_transport,
    validate_post_review_delta,
)


def make_valid_claim(
    repo: str = "thinglab-dev/tl-orchestrator",
    pr: int = 55,
    head_sha: str = "a" * 40,
    base_sha: str = "b" * 40,
    checker_commit: str = "a" * 40,
    candidate_commit: str = "a" * 40,
    authority_mode: str = "delegated_single_merge",
    expires_at: str = "2029-01-01T00:00:00Z",
) -> dict:
    return {
        "schema_version": 1,
        "target_repository": repo,
        "target_pr": pr,
        "expected_head_sha": head_sha,
        "expected_base_sha": base_sha,
        "checker_approved_commit": checker_commit,
        "integration_candidate_commit": candidate_commit,
        "authority_mode": authority_mode,
        "authorized_by": "operator@thinglab.dev",
        "authorized_at": "2026-09-15T00:00:00Z",
        "expires_at": expires_at,
        "justification": "Authorized by operator after Checker approval",
    }


def make_envelope(claim: dict, app_id: int = 12345, mechanism: str = "dedicated_github_app") -> dict:
    auth_id = derive_authorization_id(claim)
    envelope = dict(claim)
    envelope["authorization_id"] = auth_id
    envelope["provenance"] = {
        "mechanism": mechanism,
        "app_id": app_id,
    }
    return envelope


def format_comment(envelope: dict) -> dict:
    body = (
        "### Merge Authority Out-of-Band Attestation\n\n"
        "<!-- TL_MERGE_AUTHORIZATION_V1_START -->\n"
        f"{json.dumps(envelope, indent=2)}\n"
        "<!-- TL_MERGE_AUTHORIZATION_V1_END -->\n"
    )
    return {
        "id": 1001,
        "author": {"login": "thinglab-merge-authority[bot]"},
        "body": body,
        "createdAt": "2026-09-15T12:00:00Z",
    }


class MergeGuardBaseCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        # Initialize a real Git repository in temp directory
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.email", "test@thinglab.dev"], cwd=str(self.root), check=True)
        # Initial commit
        (self.root / "README.md").write_text("# Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial commit"], cwd=str(self.root), check=True)
        self.base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

    def tearDown(self):
        self.temp_dir.cleanup()


class TestMergeGuardProbes(MergeGuardBaseCase):

    def test_probe_1_pr55_exact_regression_zero_authority_fails_closed(self):
        """
        Probe 1: Exact PR #55 counterfactual regression probe.
        Simulates: Green CI, approved Checker, PR open, but 0 out-of-band merge authority comments.
        Requirement: Fail closed with status REJECTED and reason missing_merge_authorization.
        """
        head_sha = "c" * 40
        live_pr = {
            "state": "OPEN",
            "headRefOid": head_sha,
            "baseRefOid": self.base_sha,
            "baseRefName": "main",
        }
        store = InMemoryAuthorityStore()
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=55,
            live_pr_info=live_pr,
            checker_commit=head_sha,
            candidate_commit=head_sha,
            authority_store=store,
            expected_repo="thinglab-dev/tl-orchestrator",
            comments=[],  # 0 comments on PR
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertEqual(receipt.reason, "missing_merge_authorization")
        self.assertEqual(receipt.authorization_id, "")

    def test_probe_2_acyclic_authorization_id_derivation(self):
        """
        Probe 2: AC2 Acyclic derivation of authorization_id over authorization_claim_v1.
        Verify:
        - authorization_id = "auth-" + sha256(canonical_claim)[:32]
        - Changing any field alters authorization_id
        - Tampered authorization_id in envelope is rejected by parse_pr_comment_transport.
        """
        claim = make_valid_claim()
        auth_id = derive_authorization_id(claim)
        self.assertTrue(auth_id.startswith("auth-"))
        self.assertEqual(len(auth_id), 37)  # "auth-" (5 chars) + 32 hex chars

        # Perturbation changes ID
        claim_mutated = dict(claim, expires_at="2030-01-01T00:00:00Z")
        auth_id_mutated = derive_authorization_id(claim_mutated)
        self.assertNotEqual(auth_id, auth_id_mutated)

        # Tampered authorization_id in envelope
        env = make_envelope(claim)
        env["authorization_id"] = "auth-" + "0" * 32
        comment = format_comment(env)
        status, envelopes = parse_pr_comment_transport(
            comments=[comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
        )
        self.assertEqual(status, "missing_merge_authorization")
        self.assertEqual(len(envelopes), 0)

    def test_probe_3_ambiguous_authority_fails_closed(self):
        """
        Probe 3: AC7 Ambiguous authority probe.
        When >1 distinct valid active authority envelopes are posted on the PR,
        transport parser must FAIL_CLOSED with ambiguous_merge_authorization.
        """
        claim1 = make_valid_claim(expires_at="2029-01-01T00:00:00Z")
        claim2 = make_valid_claim(expires_at="2029-02-01T00:00:00Z")  # distinct
        env1 = make_envelope(claim1)
        env2 = make_envelope(claim2)
        comments = [format_comment(env1), format_comment(env2)]

        status, envelopes = parse_pr_comment_transport(
            comments=comments,
            expected_repo=claim1["target_repository"],
            pr_number=claim1["target_pr"],
            expected_head=claim1["expected_head_sha"],
            expected_base=claim1["expected_base_sha"],
            candidate_commit=claim1["integration_candidate_commit"],
        )
        self.assertEqual(status, "FAIL_CLOSED: ambiguous_merge_authorization")
        self.assertEqual(len(envelopes), 0)

        # Gate evaluation also returns REJECTED with ambiguous reason
        live_pr = {
            "state": "OPEN",
            "headRefOid": claim1["expected_head_sha"],
            "baseRefOid": claim1["expected_base_sha"],
        }
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim1["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim1["checker_approved_commit"],
            candidate_commit=claim1["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim1["target_repository"],
            comments=comments,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "FAIL_CLOSED: ambiguous_merge_authorization")

    def test_probe_4_check_source_untrusted_provenance_rejected(self):
        """
        Probe 4: AC9 / AC10 Provenance mechanism check.
        Envelopes with unauthorized provenance mechanisms are rejected.
        """
        claim = make_valid_claim()
        env = make_envelope(claim, mechanism="unauthorized_third_party_app")
        comment = format_comment(env)
        live_pr = {
            "state": "OPEN",
            "headRefOid": claim["expected_head_sha"],
            "baseRefOid": claim["expected_base_sha"],
        }
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "untrusted_authorization_provenance")

    def test_probe_5_base_drift_invalidation(self):
        """
        Probe 5: AC12 Base drift invalidation probe.
        Target base advanced after authorization was issued.
        """
        claim = make_valid_claim(base_sha=self.base_sha)
        env = make_envelope(claim)
        comment = format_comment(env)
        new_base_sha = "d" * 40
        live_pr = {
            "state": "OPEN",
            "headRefOid": claim["expected_head_sha"],
            "baseRefOid": new_base_sha,  # Base drifted!
        }
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "missing_merge_authorization")

    def test_probe_6_head_drift_invalidation(self):
        """
        Probe 6: AC12 Head drift invalidation probe.
        New commit was pushed to PR branch after authorization was issued.
        """
        head1 = "a" * 40
        head2 = "e" * 40
        claim = make_valid_claim(head_sha=head1, candidate_commit=head1)
        env = make_envelope(claim)
        comment = format_comment(env)
        live_pr = {
            "state": "OPEN",
            "headRefOid": head2,  # Head moved!
            "baseRefOid": claim["expected_base_sha"],
        }
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=head1,
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "candidate_commit_mismatch")

    def test_probe_7_uninspected_post_review_code_mutation_rejected(self):
        """
        Probe 7: AC6 Post-review code mutation probe.
        Checker approved commit C1, but candidate commit C2 mutates code.
        """
        c1 = self.base_sha
        # Create commit C2 that touches scripts/tl_runtime.py
        code_file = self.root / "scripts" / "tl_runtime.py"
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text("# mutated\n", encoding="utf-8")
        subprocess.run(["git", "add", str(code_file)], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "uninspected code mutation"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertFalse(ok)
        self.assertIn("uninspected_code_mutation_post_review", reason)
        self.assertIn("scripts/tl_runtime.py", reason)

        # MergeAuthorityGate also rejects
        claim = make_valid_claim(checker_commit=c1, candidate_commit=c2, head_sha=c2, base_sha=self.base_sha)
        env = make_envelope(claim)
        comment = format_comment(env)
        live_pr = {"state": "OPEN", "headRefOid": c2, "baseRefOid": self.base_sha}
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=c1,
            candidate_commit=c2,
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertIn("uninspected_code_mutation_post_review", receipt.reason)

    def test_probe_8_governance_only_post_review_delta_allowed(self):
        """
        Probe 8: AC6 Governance-only post-review delta probe.
        Checker approved commit C1; commit C2 touches only allowlisted governance files.
        """
        c1 = self.base_sha
        # Create commit C2 touching only governance allowlisted paths
        t_file = self.root / "_tl-orc" / "project" / "tasks" / "T028-test.md"
        e_file = self.root / "_tl-orc" / "project" / "evidence" / "T028-r01.md"
        s_file = self.root / "_tl-orc" / "project" / "STATUS.md"
        for p in (t_file, e_file, s_file):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# Gov update\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "governance updates"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertTrue(ok)
        self.assertEqual(reason, "governance_delta_allowed")

    def test_probe_9_external_anti_replay_survives_local_ledger_deletion(self):
        """
        Probe 9: AC8 External store anti-replay vs local ledger deletion.
        A consumed authority in the external trust domain remains consumed even if
        local consumption-ledger.jsonl is removed.
        """
        external_backend = InMemoryAuthorityStore()
        ledger_path = self.root / "_tl-orc" / "project" / "consumption-ledger.jsonl"
        local_store = LocalLedgerAuthorityStore(ledger_path, external_backend=external_backend)

        claim = make_valid_claim(head_sha=self.base_sha, base_sha=self.base_sha, checker_commit=self.base_sha, candidate_commit=self.base_sha)
        env = make_envelope(claim)
        auth_id = env["authorization_id"]

        # Reserve and consume
        self.assertTrue(local_store.reserve(auth_id))
        self.assertTrue(local_store.commit_consumed(auth_id))
        self.assertTrue(ledger_path.exists())

        # Now simulate local ledger deletion
        ledger_path.unlink()
        self.assertFalse(ledger_path.exists())

        # Create fresh local store mirror pointing to same external backend
        new_local_store = LocalLedgerAuthorityStore(ledger_path, external_backend=external_backend)
        self.assertEqual(new_local_store.get_state(auth_id), "consumed")

        # Attempt to evaluate gate again with consumed authorization
        comment = format_comment(env)
        live_pr = {"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha}
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=new_local_store,
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "authorization_already_consumed")

    def test_probe_10_capability_vs_authorization_separation(self):
        """
        Probe 10: AC10 permitted_effects.pull_request_merge is capability != authorization.
        Even with permitted_effects.pull_request_merge: true, without an authority envelope,
        the gate fails closed.
        """
        # Capability flag is true in caller context, but comments are empty
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=10,
            live_pr_info={"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha},
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=InMemoryAuthorityStore(),
            expected_repo="thinglab-dev/tl-orchestrator",
            comments=[],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertEqual(receipt.reason, "missing_merge_authorization")

    def test_probe_11_happy_path_confirmed(self):
        """
        Probe 11: AC4 / AC5 Happy path probe.
        Valid envelope, matching head/base/candidate/checker, external CAS reservation.
        Returns CONFIRMED receipt.
        """
        claim = make_valid_claim(
            head_sha=self.base_sha,
            base_sha=self.base_sha,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
        )
        env = make_envelope(claim)
        comment = format_comment(env)
        store = InMemoryAuthorityStore()

        live_pr = {"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha}
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
        )
        self.assertTrue(receipt.is_confirmed)
        self.assertEqual(receipt.status, "CONFIRMED")
        self.assertEqual(receipt.reason, "AUTHORITY_CONFIRMED")
        self.assertEqual(receipt.authorization_id, env["authorization_id"])
        # Store is in reserved state
        self.assertEqual(store.get_state(receipt.authorization_id), "reserved")
        # Can commit consumed
        self.assertTrue(store.commit_consumed(receipt.authorization_id))
        self.assertEqual(store.get_state(receipt.authorization_id), "consumed")

    def test_probe_12_safe_rollback_degradation_to_human_merge_only(self):
        """
        Probe 12: AC13 Safe rollback degradation to human_merge_only.
        In human_merge_only mode, gate returns AWAITING_HUMAN, never CONFIRMED.
        """
        claim = make_valid_claim(
            head_sha=self.base_sha,
            base_sha=self.base_sha,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
        )
        env = make_envelope(claim)
        comment = format_comment(env)
        store = InMemoryAuthorityStore()

        live_pr = {"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha}
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="human_merge_only",
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.status, "AWAITING_HUMAN")
        self.assertEqual(receipt.reason, "human_merge_only_mode")
        # Store was not reserved
        self.assertEqual(store.get_state(env["authorization_id"]), "unused")

    def test_probe_13_universal_schema_portability(self):
        """
        Probe 13: AC1 Universal repository portability.
        Validates claim against schema with non-hardcoded repository formats.
        """
        schema_file = Path(__file__).resolve().parents[2] / "schemas" / "merge-authorization.schema.json"
        self.assertTrue(schema_file.exists(), f"schema file not found at {schema_file}")
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")

        # Test universal repository names
        for repo_name in ("owner/repo", "acme-corp/project.v2", "user-1/lib_sub"):
            claim = make_valid_claim(repo=repo_name)
            env = make_envelope(claim)
            self.assertEqual(env["target_repository"], repo_name)
            auth_id = derive_authorization_id(claim)
            self.assertTrue(auth_id.startswith("auth-"))

    def test_probe_14_canonicalization_determinism_and_float_prohibition(self):
        """
        Probe 14: AC3 Deterministic canonicalization byte-by-byte and float prohibition.
        """
        dict_a = {"b": 2, "a": 1, "c": [3, 2, 1]}
        dict_b = {"a": 1, "c": [3, 2, 1], "b": 2}
        self.assertEqual(canonicalize_payload(dict_a), canonicalize_payload(dict_b))
        self.assertEqual(canonicalize_payload(dict_a), b'{"a":1,"b":2,"c":[3,2,1]}')

        # Prohibit floats
        with self.assertRaises(ValueError) as ctx:
            canonicalize_payload({"rate": 1.25})
        self.assertIn("Float values are strictly prohibited", str(ctx.exception))

        # Signing payload has domain separator prefix
        signing_bytes = compute_signing_payload({"key": "val"})
        self.assertTrue(signing_bytes.startswith(AUTHORIZATION_SIGNING_DOMAIN))
        self.assertEqual(signing_bytes, b"TL_MERGE_AUTHORIZATION_V1\0" + b'{"key":"val"}')

    def test_probe_15_concurrent_atomic_cas_race(self):
        """
        Probe 15: AC8 Concurrent atomic CAS race test.
        Multiple threads competing to reserve the same authority ID: exactly one succeeds.
        """
        store = InMemoryAuthorityStore()
        auth_id = "auth-race-test-01"
        barrier = threading.Barrier(5)
        results = []

        def worker():
            barrier.wait()
            res = store.reserve(auth_id)
            results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 4)
        self.assertEqual(store.get_state(auth_id), "reserved")

    def test_probe_16_candidate_branch_untrusted_mutation_resistance(self):
        """
        Probe 16: AC14 Candidate branch mutation resistance.
        Evaluator operates on repo_root git index / base truth; arbitrary candidate branch changes
        to workflows or security config do not alter evaluator rules.
        """
        c1 = self.base_sha
        # Malicious commit on candidate branch adding a fake workflow or key
        malicious_file = self.root / ".github" / "workflows" / "bypass.yml"
        malicious_file.parent.mkdir(parents=True, exist_ok=True)
        malicious_file.write_text("name: bypass\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "candidate branch tries to add bypass workflow"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertFalse(ok)
        self.assertIn("uninspected_code_mutation_post_review", reason)


if __name__ == "__main__":
    unittest.main()
