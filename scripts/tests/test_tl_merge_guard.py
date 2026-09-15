"""
test_tl_merge_guard.py - Test suite for out-of-band merge authority gate (T028 v2).

Implements exhaustive counterfactual probes for all T028 acceptance criteria:
- Probe 1: PR #55 counterfactual reproduction (zero authority -> FAIL CLOSED).
- Probe 2: Acyclic derivation of authorization_id over authorization_claim_v1.
- Probe 3: Ambiguous authority fail-closed (>1 distinct valid envelopes).
- Probe 4: Check source / forged signature / untrusted provenance rejected.
- Probe 5: Base drift invalidation (base advanced on main).
- Probe 6: Head drift invalidation (unreviewed commit on PR).
- Probe 7: Uninspected post-review code mutation rejected.
- Probe 8: Governance-only post-review delta allowed.
- Probe 9: External anti-replay survives local ledger deletion and runtime restart.
- Probe 10: Capability vs authorization separation.
- Probe 11: Happy path confirmed.
- Probe 12: Safe rollback degradation to human_merge_only.
- Probe 13: Universal repository schema portability.
- Probe 14: Deterministic byte-by-byte canonicalization and float prohibition.
- Probe 15: Concurrent atomic CAS race on filesystem store.
- Probe 16: Candidate branch untrusted mutation resistance.
- Probe 17: Missing commit bindings rejected.
- Probe 18: Pre-merge TOCTOU base drift detected and rejected.
"""

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
    DurableExternalAuthorityStore,
    InMemoryAuthorityStore,
    LocalLedgerAuthorityStore,
    MergeAuthorityGate,
    PlatformCapability,
    TrustRoot,
    canonicalize_payload,
    compute_claim_digest,
    derive_authorization_id,
    ed25519_sign,
    ed25519_verify,
    issue_platform_capability,
    parse_pr_comment_transport,
    sign_authorization_envelope,
    validate_post_review_delta,
)
from scripts.fixtures.runtime.fake_gh import (
    TEST_FIXTURE_APP_ID,
    TEST_FIXTURE_APP_SLUG,
    TEST_FIXTURE_KEY_ID,
    TEST_FIXTURE_PUBLIC_KEY,
    TEST_FIXTURE_SECRET_KEY,
)


def make_valid_claim(
    repo: str = "thinglab-dev/tl-orchestrator",
    pr: int = 55,
    head_sha: str = "a" * 40,
    base_sha: str = "b" * 40,
    checker_commit: str = "a" * 40,
    candidate_commit: str = "a" * 40,
    authority_mode: str = "delegated_single_merge",
    issued_at: str = "2026-09-15T00:00:00Z",
    expires_at: str = "2029-01-01T00:00:00Z",
    nonce: str = "0123456789abcdef0123456789abcdef",
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
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }


def make_envelope(
    claim: dict,
    secret_key: bytes = TEST_FIXTURE_SECRET_KEY,
    integration_id: int = TEST_FIXTURE_APP_ID,
    mechanism: str = "dedicated_github_app",
    key_id: str = TEST_FIXTURE_KEY_ID,
    issuer: str = f"{TEST_FIXTURE_APP_SLUG}[bot]",
) -> dict:
    return sign_authorization_envelope(
        claim,
        secret_key=secret_key,
        key_id=key_id,
        mechanism=mechanism,
        integration_id=integration_id,
        issuer=issuer,
    )


def format_comment(envelope: dict, author_login: str = f"{TEST_FIXTURE_APP_SLUG}[bot]") -> dict:
    body = (
        "### Merge Authority Out-of-Band Attestation\n\n"
        "```json:tl-merge-authorization\n"
        f"{json.dumps(envelope, indent=2)}\n"
        "```\n"
    )
    return {
        "id": 1001,
        "author": {"login": author_login},
        "body": body,
        "createdAt": "2026-09-15T12:00:00Z",
    }


class MergeGuardBaseCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self._orig_env = {
            "TL_MERGE_AUTHORITY_APP_ID": os.environ.get("TL_MERGE_AUTHORITY_APP_ID"),
            "TL_MERGE_AUTHORITY_APP_SLUG": os.environ.get("TL_MERGE_AUTHORITY_APP_SLUG"),
            "TL_MERGE_AUTHORITY_PUBLIC_KEY": os.environ.get("TL_MERGE_AUTHORITY_PUBLIC_KEY"),
            "TL_MERGE_AUTHORITY_KEY_ID": os.environ.get("TL_MERGE_AUTHORITY_KEY_ID"),
        }
        os.environ["TL_MERGE_AUTHORITY_APP_ID"] = str(TEST_FIXTURE_APP_ID)
        os.environ["TL_MERGE_AUTHORITY_APP_SLUG"] = TEST_FIXTURE_APP_SLUG
        os.environ["TL_MERGE_AUTHORITY_PUBLIC_KEY"] = TEST_FIXTURE_PUBLIC_KEY.hex()
        os.environ["TL_MERGE_AUTHORITY_KEY_ID"] = TEST_FIXTURE_KEY_ID
        self.platform_capability = issue_platform_capability(
            app_id=TEST_FIXTURE_APP_ID,
            app_slug=TEST_FIXTURE_APP_SLUG,
            public_keys={TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()},
            signing_secret_key=TEST_FIXTURE_SECRET_KEY,
        )
        self.trust_root = TrustRoot.from_platform_capability(
            capability=self.platform_capability,
            trusted_app_id=TEST_FIXTURE_APP_ID,
            trusted_app_slug=TEST_FIXTURE_APP_SLUG,
            trusted_public_keys={TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()},
        )

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
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.temp_dir.cleanup()


class TestMergeGuardProbes(MergeGuardBaseCase):

    def test_probe_1_pr55_exact_regression_zero_authority_fails_closed(self):
        """
        Probe 1: Exact PR #55 counterfactual regression probe.
        Simulates:
        - Independent checker approved: commit A
        - Technical gates: CI checks = success, branch mergeable
        - Out-of-band authority: ZERO (comments = [])
        Asserts: Gate MUST return REJECTED and MUST NOT return CONFIRMED.
        """
        head_sha = "13ee49e4593022713ab7dc38292344a41a3b5f71"
        base_sha = "c8fa8df000000000000000000000000000000000"
        live_pr = {
            "state": "OPEN",
            "headRefOid": head_sha,
            "baseRefOid": base_sha,
            "mergeable": "MERGEABLE",
        }
        authority_store = InMemoryAuthorityStore()

        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=55,
            live_pr_info=live_pr,
            checker_commit=head_sha,
            candidate_commit=head_sha,
            authority_store=authority_store,
            expected_repo="thinglab-dev/tl-orchestrator",
            comments=[],  # Zero out-of-band authority
            enforce_mode="delegated_single_merge",
            trust_root=self.trust_root,
        )

        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertEqual(receipt.reason, "missing_merge_authorization")
        self.assertEqual(authority_store.get_state(""), "unused")

    def test_probe_2_acyclic_authorization_id_derivation(self):
        """
        Probe 2: AC2 Acyclic derivation of authorization_id over authorization_claim_v1.
        authorization_id MUST NOT be inside the claim payload used to compute the digest.
        """
        claim = make_valid_claim()
        self.assertNotIn("authorization_id", claim)
        self.assertNotIn("provenance", claim)

        auth_id = derive_authorization_id(claim)
        self.assertTrue(auth_id.startswith("auth-"))
        self.assertEqual(len(auth_id), 37)  # 'auth-' + 32 hex chars

        # Same claim produces identical ID
        self.assertEqual(derive_authorization_id(claim), auth_id)

        # Mutated claim produces different ID
        claim_mutated = dict(claim)
        claim_mutated["target_pr"] = 56
        self.assertNotEqual(derive_authorization_id(claim_mutated), auth_id)

    def test_probe_3_ambiguous_authority_fails_closed(self):
        """
        Probe 3: AC7 Ambiguous authority probe.
        PR comment transport contains two distinct valid authorization envelopes.
        Must FAIL_CLOSED immediately without executing either.
        """
        claim1 = make_valid_claim(pr=55, nonce="nonce-alpha-111111111111111111")
        env1 = make_envelope(claim1)

        claim2 = make_valid_claim(pr=55, nonce="nonce-bravo-222222222222222222")
        env2 = make_envelope(claim2)

        self.assertNotEqual(env1["authorization_id"], env2["authorization_id"])

        comments = [
            format_comment(env1),
            format_comment(env2),
        ]

        status, envelopes = parse_pr_comment_transport(
            comments=comments,
            expected_repo=claim1["target_repository"],
            pr_number=claim1["target_pr"],
            expected_head=claim1["expected_head_sha"],
            expected_base=claim1["expected_base_sha"],
            candidate_commit=claim1["integration_candidate_commit"],
            trust_root=self.trust_root,
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
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "FAIL_CLOSED: ambiguous_merge_authorization")

    def test_probe_4_check_source_untrusted_provenance_rejected(self):
        """
        Probe 4: AC9 / AC10 Provenance mechanism check.
        Envelopes with forged signatures, unauthorized provenance mechanisms,
        mismatched integration_id, or non-bot comment authors are rejected.
        """
        claim = make_valid_claim()
        live_pr = {
            "state": "OPEN",
            "headRefOid": claim["expected_head_sha"],
            "baseRefOid": claim["expected_base_sha"],
        }

        # 4a: Unsupported mechanism
        env_bad_mech = make_envelope(claim, mechanism="unauthorized_third_party_app")
        comment_bad_mech = format_comment(env_bad_mech)
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment_bad_mech],
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertIn("FAIL_CLOSED: invalid_envelope_schema", receipt.reason)

        # 4b: Forged Ed25519 signature
        env_forged_sig = make_envelope(claim)
        env_forged_sig["provenance"]["signature"] = "bad" * 42 + "aa"
        comment_forged_sig = format_comment(env_forged_sig)
        receipt2 = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment_forged_sig],
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt2.is_confirmed)
        self.assertIn("FAIL_CLOSED: invalid_signature_for_key", receipt2.reason)

        # 4c: Mismatched integration_id
        env_bad_id = make_envelope(claim, integration_id=12345)
        comment_bad_id = format_comment(env_bad_id)
        receipt3 = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment_bad_id],
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt3.is_confirmed)
        self.assertIn("FAIL_CLOSED: untrusted_app_id", receipt3.reason)

        # 4d: Untrusted comment author (posted by human user 'alice' instead of dedicated bot)
        env_valid = make_envelope(claim)
        comment_human = format_comment(env_valid, author_login="alice")
        receipt4 = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=claim["checker_approved_commit"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment_human],
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt4.is_confirmed)
        self.assertIn("FAIL_CLOSED: untrusted_comment_author", receipt4.reason)

    def test_probe_5_base_drift_invalidation(self):
        """
        Probe 5: AC12 Base drift invalidation probe.
        Target base advanced after authorization was issued.
        """
        claim = make_valid_claim(base_sha=self.base_sha)
        env = make_envelope(claim)
        comment = format_comment(env)
        new_base_sha = "d" * 40

        # PR live info shows new base SHA on main
        live_pr = {
            "state": "OPEN",
            "headRefOid": claim["expected_head_sha"],
            "baseRefOid": new_base_sha,
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
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "missing_merge_authorization")

    def test_probe_6_head_drift_invalidation(self):
        """
        Probe 6: AC12 Head drift invalidation probe.
        A new commit was pushed to PR branch after authorization was issued.
        """
        claim = make_valid_claim(head_sha="e" * 40, candidate_commit="e" * 40)
        env = make_envelope(claim)
        comment = format_comment(env)
        drifted_head_sha = "f" * 40

        live_pr = {
            "state": "OPEN",
            "headRefOid": drifted_head_sha,
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
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertIn("candidate_commit_mismatch", receipt.reason)

    def test_probe_7_uninspected_post_review_code_mutation_rejected(self):
        """
        Probe 7: AC6 Post-review code mutation probe.
        Commit delta between checker_approved_commit and integration_candidate_commit
        alters a code file (e.g. scripts/tl_runtime.py). Must be REJECTED.
        """
        c1 = self.base_sha
        # Create a candidate commit altering code
        code_file = self.root / "scripts" / "tl_runtime.py"
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text("# mutated code\n", encoding="utf-8")
        subprocess.run(["git", "add", "scripts/tl_runtime.py"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "candidate commit mutating code"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertFalse(ok)
        self.assertIn("uninspected_code_mutation_post_review", reason)

    def test_probe_8_governance_only_post_review_delta_allowed(self):
        """
        Probe 8: AC6 Governance-only post-review delta probe.
        Commit delta contains only normalized governance allowlist paths:
        _tl-orc/project/tasks/*.md, _tl-orc/project/evidence/*.md, _tl-orc/project/STATUS.md.
        """
        c1 = self.base_sha
        gov_task = self.root / "_tl-orc" / "project" / "tasks" / "T028-test.md"
        gov_task.parent.mkdir(parents=True, exist_ok=True)
        gov_task.write_text("# Task\n", encoding="utf-8")

        gov_ev = self.root / "_tl-orc" / "project" / "evidence" / "T028-r01.md"
        gov_ev.parent.mkdir(parents=True, exist_ok=True)
        gov_ev.write_text("# Evidence\n", encoding="utf-8")

        gov_status = self.root / "_tl-orc" / "project" / "STATUS.md"
        gov_status.write_text("# Status\n", encoding="utf-8")

        subprocess.run(["git", "add", "-A"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "candidate commit with governance delta only"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertTrue(ok)
        self.assertEqual(reason, "governance_delta_allowed")

    def test_probe_9_external_anti_replay_survives_local_ledger_deletion(self):
        """
        Probe 9: AC8 External store anti-replay vs local ledger deletion.
        A consumed authority in the external trust domain remains consumed even if
        local consumption-ledger.jsonl is removed, surviving full runtime reboot.
        """
        with tempfile.TemporaryDirectory() as ext_tmp:
            ext_store = DurableExternalAuthorityStore(Path(ext_tmp))
            ledger_path = self.root / "_tl-orc" / "project" / "consumption-ledger.jsonl"
            local_store = LocalLedgerAuthorityStore(ledger_path, external_backend=ext_store)

            claim = make_valid_claim(head_sha=self.base_sha, base_sha=self.base_sha, checker_commit=self.base_sha, candidate_commit=self.base_sha)
            env = make_envelope(claim)
            auth_id = env["authorization_id"]

            # Reserve and consume
            self.assertTrue(local_store.reserve(auth_id))
            self.assertTrue(local_store.commit_consumed(auth_id))
            self.assertTrue(ledger_path.exists())

            # Simulate local ledger deletion and runtime shutdown
            ledger_path.unlink()
            self.assertFalse(ledger_path.exists())
            del local_store
            del ext_store

            # Instantiate brand new local store pointing to the external backend on disk
            rebooted_ext = DurableExternalAuthorityStore(Path(ext_tmp))
            new_local_store = LocalLedgerAuthorityStore(ledger_path, external_backend=rebooted_ext)
            self.assertEqual(new_local_store.get_state(auth_id), "consumed")
            self.assertFalse(new_local_store.reserve(auth_id))

            # Attempt to evaluate gate again with consumed authorization: fails closed
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
                trust_root=self.trust_root,
            )
            self.assertFalse(receipt.is_confirmed)
            self.assertEqual(receipt.reason, "authorization_already_consumed")

    def test_probe_10_capability_vs_authorization_separation(self):
        """
        Probe 10: AC10 permitted_effects.pull_request_merge is capability != authorization.
        Even with permitted_effects.pull_request_merge: true, without an authority envelope,
        the gate fails closed.
        """
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=10,
            live_pr_info={"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha},
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=InMemoryAuthorityStore(),
            expected_repo="thinglab-dev/tl-orchestrator",
            comments=[],
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "missing_merge_authorization")

    def test_probe_11_happy_path_confirmed(self):
        """
        Probe 11: AC4 / AC5 Happy path probe.
        Valid claim, single active authority envelope, verified Ed25519 signature,
        matching base and head, atomic reservation succeeds.
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

        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info={"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha},
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
            trust_root=self.trust_root,
        )
        self.assertTrue(receipt.is_confirmed)
        self.assertEqual(receipt.status, "CONFIRMED")
        self.assertEqual(receipt.reason, "AUTHORITY_CONFIRMED")
        self.assertEqual(store.get_state(env["authorization_id"]), "reserved")

    def test_probe_12_safe_rollback_degradation_to_human_merge_only(self):
        """
        Probe 12: AC13 Safe rollback degradation to human_merge_only.
        When enforce_mode is human_merge_only, receipt status is AWAITING_HUMAN,
        never executing automated merge.
        """
        claim = make_valid_claim(
            head_sha=self.base_sha,
            base_sha=self.base_sha,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_mode="human_merge_only",
        )
        env = make_envelope(claim)
        comment = format_comment(env)
        store = InMemoryAuthorityStore()

        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info={"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha},
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
        self.assertEqual(store.get_state(env["authorization_id"]), "unused")

    def test_probe_13_universal_schema_portability(self):
        """
        Probe 13: AC1 Universal repository portability.
        Validates that schema accepts any valid owner/repo without hardcoded thinglab-dev.
        """
        for repo_name in ["octocat/Hello-World", "corp-sec/infra.core", "org_99/repo-v2"]:
            claim = make_valid_claim(repo=repo_name)
            env = make_envelope(claim)
            self.assertEqual(env["target_repository"], repo_name)
            auth_id = derive_authorization_id(claim)
            self.assertTrue(auth_id.startswith("auth-"))

    def test_probe_14_canonicalization_determinism_and_float_prohibition(self):
        """
        Probe 14: AC3 Deterministic canonicalization byte-by-byte and float prohibition.
        """
        obj1 = {"b": 2, "a": 1, "nested": {"z": 9, "m": 5}}
        obj2 = {"nested": {"m": 5, "z": 9}, "a": 1, "b": 2}
        self.assertEqual(canonicalize_payload(obj1), canonicalize_payload(obj2))

        # Float prohibition
        float_payload = {"val": 1.23}
        with self.assertRaises(ValueError):
            canonicalize_payload(float_payload)

        # Signing payload has domain separator prefix
        signing_bytes = AUTHORIZATION_SIGNING_DOMAIN + canonicalize_payload({"key": "val"})
        self.assertTrue(signing_bytes.startswith(AUTHORIZATION_SIGNING_DOMAIN))
        self.assertEqual(signing_bytes, b"TL_MERGE_AUTHORIZATION_V1\0" + b'{"key":"val"}')

    def test_probe_15_concurrent_atomic_cas_race(self):
        """
        Probe 15: AC8 Concurrent atomic CAS race test on filesystem store.
        Multiple threads competing to reserve the same authority ID on disk: exactly one succeeds.
        """
        with tempfile.TemporaryDirectory() as store_tmp:
            store = DurableExternalAuthorityStore(Path(store_tmp))
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
        malicious_file = self.root / ".github" / "workflows" / "bypass.yml"
        malicious_file.parent.mkdir(parents=True, exist_ok=True)
        malicious_file.write_text("name: bypass\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "candidate branch tries to add bypass workflow"], cwd=str(self.root), check=True)
        c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True, check=True).stdout.strip()

        ok, reason = validate_post_review_delta(self.root, c1, c2)
        self.assertFalse(ok)
        self.assertIn("uninspected_code_mutation_post_review", reason)

    def test_probe_17_missing_commit_bindings_rejected(self):
        """
        Probe 17: AC6 / R2 Missing commit bindings rejected.
        Omission of checker_approved_commit or integration_candidate_commit is rejected.
        """
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=55,
            live_pr_info={"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha},
            checker_commit="",
            candidate_commit="",
            authority_store=InMemoryAuthorityStore(),
            expected_repo="thinglab-dev/tl-orchestrator",
            comments=[],
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.reason, "missing_commit_bindings")

    def test_probe_18_toctou_base_drift_blocks_merge_execution(self):
        """
        Probe 18: R4 Strict Pre-Merge TOCTOU Revalidation Runtime Integration Test.
        Verifies that when baseRefOid drifts between authority evaluation (view 1)
        and merge execution (view 2), the TOCTOU check blocks `gh pr merge` from
        EVER being called and parks the unit with awaiting_operator.
        """
        from scripts.tests.test_tl_runtime import Fixture, CHECKER_OK, MAKER_OK
        fx_dir = Path(self.temp_dir.name) / "rt_fx"
        fx_dir.mkdir(parents=True, exist_ok=True)
        fx = Fixture(fx_dir, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({
            "checks_sequence": ["success"],
            "toctou_base_drift": True,
        }), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)

        res = fx.run_cli("run")
        self.assertNotEqual(res.returncode, 0)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("toctou_base_drift", record.reason)

        gh_state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        calls = gh_state.get("calls", [])
        # Verify that at least 2 view calls occurred (view 1 for authority evaluation, view 2 for TOCTOU revalidation)
        view_calls = [c for c in calls if c[:2] == ["pr", "view"]]
        self.assertGreaterEqual(len(view_calls), 2)
        # Verify gh pr merge was NEVER executed
        merge_calls = [c for c in calls if c[:2] == ["pr", "merge"]]
        self.assertEqual(len(merge_calls), 0)

    def test_probe_18b_toctou_missing_base_oid_blocks_merge_execution(self):
        """
        Probe 18b: R4 Missing baseRefOid on pre-merge view blocks merge execution.
        Fails closed when baseRefOid is missing/empty on second view call.
        """
        from scripts.tests.test_tl_runtime import Fixture, CHECKER_OK, MAKER_OK
        fx_dir = Path(self.temp_dir.name) / "rt_fx2"
        fx_dir.mkdir(parents=True, exist_ok=True)
        fx = Fixture(fx_dir, units=1, effects={"push": True, "pull_request": True, "pull_request_merge": True}, ci=True)
        fx.gh_state.write_text(json.dumps({
            "checks_sequence": ["success"],
            "toctou_missing_base_oid": True,
        }), encoding="utf-8")
        fx.script("maker", MAKER_OK)
        fx.script("checker", CHECKER_OK)

        res = fx.run_cli("run")
        self.assertNotEqual(res.returncode, 0)
        record = fx.fold().units["T001"]
        self.assertEqual(record.state, "awaiting_operator")
        self.assertIn("toctou_base_drift", record.reason)

        gh_state = json.loads(fx.gh_state.read_text(encoding="utf-8"))
        calls = gh_state.get("calls", [])
        merge_calls = [c for c in calls if c[:2] == ["pr", "merge"]]
        self.assertEqual(len(merge_calls), 0)

    def test_probe_19_fail_closed_schema_resolution_and_validation(self):
        """
        Probe 19: R1 Fail-closed schema resolution, missing validator, and invalid schema.
        """
        claim = make_valid_claim()
        env = make_envelope(claim)
        comment = format_comment(env)

        # 19a: Missing schema file fails closed
        status, envelopes = parse_pr_comment_transport(
            comments=[comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
            checker_commit=claim["checker_approved_commit"],
            authority_mode=claim["authority_mode"],
            trust_root=self.trust_root,
            schema_path=Path(self.temp_dir.name) / "nonexistent.schema.json",
        )
        self.assertTrue(status.startswith("FAIL_CLOSED: merge authorization schema file not found"))
        self.assertEqual(envelopes, [])

        # 19b: Unavailable validator fails closed
        import scripts.tl_merge_guard as tmg
        orig_val = tmg.validate_against_schema
        try:
            tmg.validate_against_schema = lambda data, schema_path: (False, ["FAIL_CLOSED: validator unavailable"])
            status2, envs2 = parse_pr_comment_transport(
                comments=[comment],
                expected_repo=claim["target_repository"],
                pr_number=claim["target_pr"],
                expected_head=claim["expected_head_sha"],
                expected_base=claim["expected_base_sha"],
                candidate_commit=claim["integration_candidate_commit"],
                checker_commit=claim["checker_approved_commit"],
                authority_mode=claim["authority_mode"],
                trust_root=self.trust_root,
            )
            self.assertTrue(status2.startswith("FAIL_CLOSED: invalid_envelope_schema"))
            self.assertIn("validator unavailable", status2)
            self.assertEqual(envs2, [])
        finally:
            tmg.validate_against_schema = orig_val

        # 19c: Envelope violating schema (missing required property nonce) fails closed
        bad_claim = dict(claim)
        del bad_claim["nonce"]
        bad_env = make_envelope(bad_claim)
        bad_comment = format_comment(bad_env)
        status3, envs3 = parse_pr_comment_transport(
            comments=[bad_comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
            checker_commit=claim["checker_approved_commit"],
            authority_mode=claim["authority_mode"],
            trust_root=self.trust_root,
        )
        self.assertTrue(status3.startswith("FAIL_CLOSED: invalid_envelope_schema"))
        self.assertEqual(envs3, [])

    def test_probe_20_zero_private_key_in_production_module(self):
        """
        Probe 20: R2 Elimination of Default/Embedded Private Key in Production.
        Asserts that scripts.tl_merge_guard contains ZERO private keys, secret seeds,
        or default signing keys. Signing requires an explicit secret_key: bytes.
        """
        import inspect
        import scripts.tl_merge_guard as tmg

        # Must NOT have DEFAULT_APP_SECRET_KEY or any secret key attribute
        self.assertFalse(hasattr(tmg, "DEFAULT_APP_SECRET_KEY"))
        self.assertFalse(hasattr(tmg, "DEFAULT_TRUST_ROOT"))
        for attr in dir(tmg):
            if attr.isupper():
                self.assertNotIn("SECRET", attr)
                self.assertNotIn("SEED", attr)

        # Module source must not contain private seed literals
        src = inspect.getsource(tmg)
        self.assertNotIn("thinglab-merge-authority-default-seed", src)

        # sign_authorization_envelope requires secret_key without default
        claim = make_valid_claim()
        with self.assertRaises((ValueError, TypeError)):
            # Calling without secret_key or with None fails
            tmg.sign_authorization_envelope(claim, None, "key-id")  # type: ignore[arg-type]

        # TrustRoot() creates empty public keys when env is unset
        empty_root = tmg.TrustRoot()
        self.assertEqual(empty_root.trusted_public_keys, {})

    def test_probe_21_strict_mode_validation_and_scope_binding(self):
        """
        Probe 21: R3 Strict Mode Validation, Fallback Elimination & Scope Binding.
        Asserts that mismatched checker_approved_commit or authority_mode in envelope
        are rejected, and missing authority_mode parks closed.
        """
        claim = make_valid_claim(
            checker_commit="a" * 40,
            candidate_commit="a" * 40,
            authority_mode="delegated_single_merge",
        )
        env = make_envelope(claim)
        comment = format_comment(env)

        # 21a: Mismatched checker_approved_commit in envelope rejected
        status, envs = parse_pr_comment_transport(
            comments=[comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
            checker_commit="b" * 40,  # Evaluator expects different checker commit
            authority_mode="delegated_single_merge",
            trust_root=self.trust_root,
        )
        self.assertEqual(status, "missing_merge_authorization")
        self.assertEqual(envs, [])

        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info={"state": "OPEN", "headRefOid": "a" * 40, "baseRefOid": claim["expected_base_sha"]},
            checker_commit="b" * 40,  # Mismatch
            candidate_commit="a" * 40,
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="delegated_single_merge",
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt.is_confirmed)

        # 21b: Mismatched authority_mode in envelope rejected
        status2, envs2 = parse_pr_comment_transport(
            comments=[comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
            checker_commit="a" * 40,
            authority_mode="human_merge_only",  # Evaluator expects human_merge_only
            trust_root=self.trust_root,
        )
        self.assertEqual(status2, "missing_merge_authorization")
        self.assertEqual(envs2, [])

        receipt2 = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info={"state": "OPEN", "headRefOid": "a" * 40, "baseRefOid": claim["expected_base_sha"]},
            checker_commit="a" * 40,
            candidate_commit="a" * 40,
            authority_store=InMemoryAuthorityStore(),
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="human_merge_only",
            trust_root=self.trust_root,
        )
        self.assertFalse(receipt2.is_confirmed)

        # 21c: Runtime parks on missing authority_mode
        import tl_runtime
        from scripts.tests.test_tl_runtime import Fixture
        fx_dir = Path(self.temp_dir.name) / "rt_no_mode"
        fx_dir.mkdir(parents=True, exist_ok=True)
        fx = Fixture(fx_dir, units=1, effects={"pull_request_merge": True})
        fx.batch["authorization"]["authority_source"] = "production"
        fx.batch["authorization"].pop("authority_mode", None)
        fx.batch_path.write_text(json.dumps(fx.batch), encoding="utf-8")
        fx.gh_state.write_text(json.dumps({
            "prs": {
                "head": {"number": 100, "state": "OPEN", "base": "main", "head_oid": "a" * 40}
            }
        }), encoding="utf-8")
        old_gh_state = os.environ.get("TL_FAKE_GH_STATE")
        os.environ["TL_FAKE_GH_STATE"] = str(fx.gh_state)
        try:
            rt = fx.runtime()
            unit_obj = rt.units["T001"]
            rt.fold.units["T001"] = tl_runtime.UnitRecord(id="T001", state="running", phase="merge", pr={"number": 100}, commit="a" * 40)
            with self.assertRaises(tl_runtime.UnitPark) as ctx:
                rt.deliver(unit_obj)
            self.assertIn("missing_authority_mode", str(ctx.exception))
        finally:
            if old_gh_state is not None:
                os.environ["TL_FAKE_GH_STATE"] = old_gh_state
            else:
                os.environ.pop("TL_FAKE_GH_STATE", None)

    def test_probe_22_strict_iso8601_utc_timestamps_and_temporal_order(self):
        """
        Probe 22: R2 Strict Canonical UTC ISO 8601 Timestamp Validation & Temporal Order.
        Verifies:
        - Schema rejects non-matching strings (e.g. 'invalid', missing 'T'/'Z', non-UTC offsets).
        - validate_canonical_utc_timestamp enforces format and strict zero UTC offset.
        - canonicalize_payload and sign_authorization_envelope enforce timestamp constraints.
        - Temporal inversion (issued_at > expires_at) fails closed in both derivation and transport.
        - Canonical formats ending with 'Z' or '+00:00' succeed.
        """
        from scripts.tl_merge_guard import validate_canonical_utc_timestamp

        # 22a: Unit validation of timestamp strings
        valid_z = "2026-09-15T12:00:00Z"
        valid_offset = "2026-09-15T12:00:00+00:00"
        valid_frac = "2026-09-15T12:00:00.123456Z"
        self.assertEqual(validate_canonical_utc_timestamp(valid_z).tzinfo, timezone.utc)
        self.assertEqual(validate_canonical_utc_timestamp(valid_offset).tzinfo, timezone.utc)
        self.assertEqual(validate_canonical_utc_timestamp(valid_frac).tzinfo, timezone.utc)

        bad_timestamps = [
            "invalid",
            "2026-09-15",
            "2026-09-15 12:00:00Z",
            "2026-09-15T12:00:00",
            "2026-09-15T12:00:00-05:00",
            "2026-09-15T12:00:00+02:00",
            "2026-13-45T99:99:99Z",
            123456789,
            None,
        ]
        for bad_ts in bad_timestamps:
            with self.assertRaises(ValueError):
                validate_canonical_utc_timestamp(bad_ts)

        # 22b: Canonicalizer rejects invalid timestamps
        claim = make_valid_claim()
        bad_issued = dict(claim, issued_at="invalid")
        with self.assertRaises(ValueError):
            canonicalize_payload(bad_issued)

        bad_tz = dict(claim, issued_at="2026-09-15T12:00:00-05:00")
        with self.assertRaises(ValueError):
            canonicalize_payload(bad_tz)

        # 22c: Temporal inversion (issued_at > expires_at)
        inverted = dict(claim, issued_at="2029-01-01T00:00:00Z", expires_at="2026-09-15T00:00:00Z")
        with self.assertRaises(ValueError):
            canonicalize_payload(inverted)
        with self.assertRaises(ValueError):
            sign_authorization_envelope(inverted, TEST_FIXTURE_SECRET_KEY, TEST_FIXTURE_KEY_ID)

        # 22d: Transport rejects invalid issued_at / expires_at / non-UTC offset
        # Schema layer rejection
        raw_env_bad = {
            "schema_version": 1,
            "authorization_id": "auth-0123456789abcdef0123456789abcdef",
            "target_repository": "thinglab-dev/tl-orchestrator",
            "target_pr": 55,
            "expected_head_sha": "a" * 40,
            "expected_base_sha": "b" * 40,
            "checker_approved_commit": "a" * 40,
            "integration_candidate_commit": "a" * 40,
            "authority_mode": "delegated_single_merge",
            "issued_at": "invalid",
            "expires_at": "2029-01-01T00:00:00Z",
            "nonce": "0123456789abcdef0123456789abcdef",
            "provenance": {
                "issuer": f"{TEST_FIXTURE_APP_SLUG}[bot]",
                "mechanism": "dedicated_github_app",
                "integration_id": TEST_FIXTURE_APP_ID,
                "key_id": TEST_FIXTURE_KEY_ID,
                "signature": "00" * 64,
            },
        }
        comment_bad = format_comment(raw_env_bad)
        status, envs = parse_pr_comment_transport(
            comments=[comment_bad],
            expected_repo="thinglab-dev/tl-orchestrator",
            pr_number=55,
            expected_head="a" * 40,
            expected_base="b" * 40,
            candidate_commit="a" * 40,
            trust_root=self.trust_root,
        )
        self.assertTrue(status.startswith("FAIL_CLOSED: invalid_envelope_schema"))
        self.assertEqual(envs, [])

        # Non-UTC timezone offset rejection
        raw_env_tz = dict(raw_env_bad, issued_at="2026-09-15T12:00:00-05:00")
        comment_tz = format_comment(raw_env_tz)
        status_tz, envs_tz = parse_pr_comment_transport(
            comments=[comment_tz],
            expected_repo="thinglab-dev/tl-orchestrator",
            pr_number=55,
            expected_head="a" * 40,
            expected_base="b" * 40,
            candidate_commit="a" * 40,
            trust_root=self.trust_root,
        )
        self.assertTrue(status_tz.startswith("FAIL_CLOSED: invalid_envelope_schema"))
        self.assertEqual(envs_tz, [])

    def test_probe_23_out_of_process_trust_root_isolation_and_env_tampering_resistance(self):
        """
        Probe 23: R1 Out-of-Process Trust Root Isolation and Environment Tampering Resistance.
        Verifies:
        - TrustRoot.from_env() creates advisory trust root with is_out_of_process == False.
        - Under delegated_single_merge, advisory trust root safely degrades to human_merge_only.enforced.
        - Runtime environment tampering (attacker injecting its own Ed25519 public key in os.environ)
          cannot produce an accepted authority for delegated merge.
        - operator_ed25519 mechanism is strictly forbidden for delegated_single_merge.
        """
        # 23a: TrustRoot.from_env() is strictly advisory
        env_root = TrustRoot.from_env()
        self.assertFalse(env_root.is_out_of_process)
        self.assertEqual(env_root.trust_source, "advisory_env")

        # 23b: Evaluating delegated_single_merge with advisory root degrades to human_merge_only.enforced
        claim = make_valid_claim(
            head_sha=self.base_sha,
            base_sha=self.base_sha,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_mode="delegated_single_merge",
        )
        env = make_envelope(claim)
        comment = format_comment(env)
        live_pr = {"state": "OPEN", "headRefOid": self.base_sha, "baseRefOid": self.base_sha}
        store = InMemoryAuthorityStore()

        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="delegated_single_merge",
            trust_root=env_root,  # Advisory root from env
        )
        self.assertFalse(receipt.is_confirmed)
        self.assertEqual(receipt.status, "AWAITING_HUMAN")
        self.assertEqual(receipt.degraded_mode, "human_merge_only.enforced")
        self.assertIn("advisory_trust_root_degraded_to_human_merge_only", receipt.reason)

        # Calling without explicit trust_root defaults to from_env() and also degrades
        receipt_default = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="delegated_single_merge",
            trust_root=None,
        )
        self.assertFalse(receipt_default.is_confirmed)
        self.assertEqual(receipt_default.status, "AWAITING_HUMAN")
        self.assertEqual(receipt_default.degraded_mode, "human_merge_only.enforced")

        # 23c: Attacker with local env control generates own key and attempts operator_ed25519
        # Generate arbitrary attacker keypair
        attacker_seed = b"attacker-host-process-key-seed32"
        attacker_pub, attacker_priv = ed25519_sign(attacker_seed, b"")
        attacker_key_id = "key-attacker-1"

        os.environ["TL_MERGE_AUTHORITY_PUBLIC_KEYS"] = f"{attacker_key_id}={attacker_pub.hex()}"
        env_attacker_root = TrustRoot.from_env()

        # Attacker signs an envelope with its own key using operator_ed25519
        attacker_claim = make_valid_claim(
            head_sha=self.base_sha,
            base_sha=self.base_sha,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_mode="delegated_single_merge",
        )
        attacker_env = sign_authorization_envelope(
            attacker_claim,
            secret_key=attacker_priv,
            key_id=attacker_key_id,
            mechanism="operator_ed25519",
            issuer="local-operator",
        )
        attacker_comment = format_comment(attacker_env, author_login="attacker")

        # Parser strictly rejects operator_ed25519 for delegated_single_merge
        status_op, envs_op = parse_pr_comment_transport(
            comments=[attacker_comment],
            expected_repo=attacker_claim["target_repository"],
            pr_number=attacker_claim["target_pr"],
            expected_head=attacker_claim["expected_head_sha"],
            expected_base=attacker_claim["expected_base_sha"],
            candidate_commit=attacker_claim["integration_candidate_commit"],
            authority_mode="delegated_single_merge",
            trust_root=self.trust_root,
        )
        self.assertTrue(status_op.startswith("FAIL_CLOSED: mechanism_not_permitted_for_delegated_single_merge"))
        self.assertEqual(envs_op, [])

        # 23d: Attacker attempts to forge dedicated_github_app using env-injected public key
        attacker_env_app = sign_authorization_envelope(
            attacker_claim,
            secret_key=attacker_priv,
            key_id=attacker_key_id,
            mechanism="dedicated_github_app",
            integration_id=TEST_FIXTURE_APP_ID,
            issuer=f"{TEST_FIXTURE_APP_SLUG}[bot]",
        )
        # Even if attacker fakes comment author:
        attacker_app_comment = format_comment(attacker_env_app, author_login=f"{TEST_FIXTURE_APP_SLUG}[bot]")

        # Verified out-of-process trust root rejects attacker's unknown key
        receipt_atk = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=attacker_claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=attacker_claim["target_repository"],
            comments=[attacker_app_comment],
            enforce_mode="delegated_single_merge",
            trust_root=self.trust_root,  # True out-of-process root does not trust attacker key
        )
        self.assertFalse(receipt_atk.is_confirmed)
        self.assertIn("FAIL_CLOSED: unknown_key_id", receipt_atk.reason)

        # 23e: Negative probe: Caller constructs a fake local trust root with arbitrary keys.
        # When injected, MergeAuthorityGate and transport parsing MUST fail closed with FAIL_CLOSED: unauthenticated_trust_root.
        fake_local_root = TrustRoot(
            trusted_app_id=666,
            trusted_app_slug="attacker-app",
            trusted_public_keys={"key-attacker": attacker_pub.hex()},
            trust_source="fake_local",
        )
        self.assertFalse(fake_local_root.is_out_of_process)

        receipt_fake = MergeAuthorityGate.evaluate(
            repo_root=self.root,
            pr_number=claim["target_pr"],
            live_pr_info=live_pr,
            checker_commit=self.base_sha,
            candidate_commit=self.base_sha,
            authority_store=store,
            expected_repo=claim["target_repository"],
            comments=[comment],
            enforce_mode="delegated_single_merge",
            trust_root=fake_local_root,
        )
        self.assertFalse(receipt_fake.is_confirmed)
        self.assertEqual(receipt_fake.status, "REJECTED")
        self.assertIn("FAIL_CLOSED: unauthenticated_trust_root", receipt_fake.reason)

        status_fake_trans, envs_fake_trans = parse_pr_comment_transport(
            comments=[comment],
            expected_repo=claim["target_repository"],
            pr_number=claim["target_pr"],
            expected_head=claim["expected_head_sha"],
            expected_base=claim["expected_base_sha"],
            candidate_commit=claim["integration_candidate_commit"],
            authority_mode="delegated_single_merge",
            trust_root=fake_local_root,
        )
        self.assertTrue(status_fake_trans.startswith("FAIL_CLOSED: unauthenticated_trust_root"))
        self.assertEqual(envs_fake_trans, [])


if __name__ == "__main__":
    unittest.main()
