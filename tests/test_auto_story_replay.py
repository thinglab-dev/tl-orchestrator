#!/usr/bin/env python3
"""Canonical AUTO_STORY replay: the Lynvia B013 → B014 cycle (T032 §3).

The real cycle stopped between B013 and B014 only because authority was per-proposal. This
replay runs the same two batches under one Story Authority and proves, against real files and
a real git repository, that the second batch is authorized by derivation rather than by a
second human signature, that it starts at the exact unmerged commit the first Checker
reviewed, and that fourteen authorized model calls are spent once each.
"""

from __future__ import annotations

import json
import os
import unittest

from story_authority_support import (  # noqa: E402
    CONNECTOR_TESTS_V2,
    CONNECTOR_V2,
    FIXTURES,
    StoryCase,
    load_fixture,
    plan_validator,
    story,
)

from scripts.fixtures.runtime.fake_gh import (  # noqa: E402
    TEST_FIXTURE_APP_ID,
    TEST_FIXTURE_APP_SLUG,
    TEST_FIXTURE_KEY_ID,
    TEST_FIXTURE_PUBLIC_KEY,
    TEST_FIXTURE_SECRET_KEY,
)
from scripts.tl_merge_guard import (  # noqa: E402
    InMemoryAuthorityStore,
    MergeAuthorityGate,
    TrustRoot,
    issue_platform_capability,
    sign_authorization_envelope,
    temporary_platform_anchor_for_testing,
)

TARGET_REPOSITORY = "thinglab-dev/tl-orchestrator"
# The eight physical provider attempts B013 made before it hit the rework limit.
B013_LOGICAL_CALLS = (
    ("B013-classifier-r01", "classifier", "planning"),
    ("B013-planner-r01", "planner", "planning"),
    ("B013-maker-r01", "maker", "implementation"),
    ("B013-checker-r01", "checker", "review"),
    ("B013-classifier-rework-r02", "classifier", "rework"),
    ("B013-maker-r02", "maker", "rework"),
    ("B013-checker-r02", "checker", "review"),
    ("B013-advisor-r02", "advisor", "debate"),
)


def completed_dispatch(_attempt_id: str) -> dict:
    """Stand-in transport: the call completed and is charged. No network, no provider."""
    return {"state": "completed", "exit_code": 0}


class AutoStoryReplayTest(StoryCase):
    def setUp(self) -> None:
        super().setUp()
        self.envelope = self.baseline_authority()
        self.payload = self.envelope["authority_payload"]
        self.auth = self.authority(self.envelope)
        self.story_baseline = self.governance_base

    # ---- 1. the authority ------------------------------------------------------------

    def test_replay_b013_to_b014_under_one_story_authority(self) -> None:
        self.assertEqual(self.payload["authority_id"], "A001")
        self.assertEqual(self.payload["work_ref"], "connector:2-10")
        self.assertEqual(self.payload["global_model_call_budget"], 14)
        self.assertEqual(self.payload["max_child_batches"], 2)
        self.assertEqual(self.auth.remaining_global_budget, 14)

        # 2. B013 runs under the authority, consumes eight calls and exhausts its rework limit.
        b013 = story.derive_child_proposal(
            authority=self.auth, child_batch_id="B013", action_items=[], previous_child_id=None,
            model_call_budget=8, governance_base_commit=self.governance_base,
            story_baseline_commit=self.story_baseline)
        b013_proof = story.verify_derivation(self.auth, b013)
        self.auth.record_child_derived(b013, b013_proof)

        branch_b013 = "auto-story/A001/B013"
        self.git("checkout", "-q", "-b", branch_b013, self.governance_base)
        self.auth.record_child_open("B013", branch=branch_b013, head_commit=self.git.head(), tree=self.git.tree())

        for logical_call_id, role, phase in B013_LOGICAL_CALLS:
            story.budgeted_authority_dispatch(
                self.auth, child_batch_id="B013", logical_call_id=logical_call_id, role=role, phase=phase,
                dispatch=completed_dispatch)
        self.assertEqual(self.auth.state.consumed_calls, 8)

        # B013 leaves a real, reviewed, *unmerged* commit on disk.
        self.write("src/connector.py", CONNECTOR_V2.replace("if attempt + 1 < attempts:\n                ", ""))
        b013_reviewed_commit = self.git.commit_all("B013: bounded retry with backoff")
        b013_reviewed_tree = self.git.tree()

        b013_review = load_fixture("b013-review-result.json")
        self.assertEqual(b013_review["verdict"], "changes_requested")
        residual = b013_review["action_items"]
        self.assertEqual([item["id"] for item in residual], ["R5", "R6"])

        # 3. The runtime intercepts the close, journals the lineage and debits the parent.
        self.auth.record_child_closed(
            child_batch_id="B013", governance_base_commit=self.governance_base,
            checker_reviewed_commit=b013_reviewed_commit, checker_reviewed_tree=b013_reviewed_tree,
            functional_checkpoint_commit=b013_reviewed_commit, functional_checkpoint_tree=b013_reviewed_tree,
            checker_verdict="changes_requested", unresolved_action_items=residual)
        self.assertEqual(self.auth.remaining_global_budget, 6)

        b014 = story.derive_child_proposal(
            authority=self.auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
            model_call_budget=6, governance_base_commit=self.governance_base,
            story_baseline_commit=self.story_baseline)
        # Derivation is deterministic: the same inputs formulate the identical proposal.
        self.assertEqual(
            b014,
            story.derive_child_proposal(
                authority=self.auth, child_batch_id="B014", action_items=residual, previous_child_id="B013",
                model_call_budget=6, governance_base_commit=self.governance_base,
                story_baseline_commit=self.story_baseline))

        # 4. verify_derivation proves the four properties at once.
        spec_paths = ["_tl-orc/project/tasks/connector-2-10.md"]
        proof = story.verify_derivation(self.auth, b014, action_items=residual, spec_paths=spec_paths)
        results = {check["check"]: check["result"] for check in proof["checks"]}
        self.assertNotIn("fail", set(results.values()))
        #   (a) B014 is inside the root envelope
        self.assertEqual(results["scope_subset"], "pass")
        self.assertEqual(results["effects_subset"], "pass")
        self.assertEqual(results["protected_paths_monotonic"], "pass")
        self.assertEqual(results["spec_immutable"], "pass")
        #   (b) B014 is derived from B013's action items
        self.assertEqual(results["patch_only_findings"], "pass")
        self.assertEqual(proof["unresolved_action_items_digest"], story.unresolved_action_items_digest(residual))
        #   (c) B014 inherits exactly the reviewed functional checkpoint
        self.assertEqual(b014["functional_parent_checkpoint"],
                         {"commit": b013_reviewed_commit, "tree": b013_reviewed_tree, "child_batch_id": "B013"})
        #   (d) no new authority exists because B013 existed
        self.assertEqual(proof["root_authority_digest"], self.envelope["root_authority_digest"])
        self.assertEqual(proof["parent_authority_digest"], b013_proof["derivation_proof_digest"])
        self.assertEqual(proof["parent_batch_digest"], plan_validator.digest_of(b013))
        published = sorted((self.root / story.PROJECT_AUTHORITY_DIR).glob("*.json"))
        self.assertEqual([path.name for path in published], ["A001.json"])

        # 5. B014 opens automatically, branching from the functional checkpoint.
        self.auth.record_child_derived(b014, proof)
        branch_b014 = "auto-story/A001/B014"
        self.git("checkout", "-q", "-b", branch_b014, b013_reviewed_commit)
        story.verify_functional_checkpoint(self.root, b014["functional_parent_checkpoint"])
        self.auth.record_child_open("B014", branch=branch_b014, head_commit=self.git.head(), tree=self.git.tree())
        self.assertEqual(self.git.head(), b013_reviewed_commit)

        # 6. Maker patches R5/R6, the Checker approves the cumulative candidate, merge, close.
        for logical_call_id, role, phase in (("B014-maker-r01", "maker", "rework"),
                                             ("B014-checker-r01", "checker", "review")):
            story.budgeted_authority_dispatch(
                self.auth, child_batch_id="B014", logical_call_id=logical_call_id, role=role, phase=phase,
                dispatch=completed_dispatch)
        self.write("src/connector.py", CONNECTOR_V2)
        self.write("tests/test_connector.py", CONNECTOR_TESTS_V2)
        integration_candidate = self.git.commit_all("B014: resolve Checker R5 and R6")

        cumulative = story.cumulative_review_range(self.story_baseline, integration_candidate)
        self.assertEqual(cumulative, f"{self.story_baseline}..{integration_candidate}")
        reviewed_files = set(self.git("diff", "--name-only", self.story_baseline, integration_candidate).split())
        # The final Checker sees the whole Story, B013's work included, not only B014's patch.
        self.assertEqual(reviewed_files, {"src/connector.py", "tests/test_connector.py"})

        b014_review = load_fixture("b014-review-result.json")
        self.assertEqual(b014_review["verdict"], "approved")
        self.assertEqual(b014_review["action_items"], [])

        receipt = self.confirmed_merge_receipt(checker_commit=integration_candidate,
                                               candidate_commit=integration_candidate)
        story.assert_merge_authority(self.payload, receipt, trust_root=self.trust_root,
                                     expected_repo=TARGET_REPOSITORY)
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "--no-edit", "-q", branch_b014)
        merge_commit = self.git.head()

        self.auth.record_child_closed(
            child_batch_id="B014", governance_base_commit=self.governance_base,
            checker_reviewed_commit=integration_candidate, checker_reviewed_tree=self.git.tree(integration_candidate),
            functional_checkpoint_commit=integration_candidate,
            functional_checkpoint_tree=self.git.tree(integration_candidate),
            checker_verdict="approved", unresolved_action_items=[])
        self.auth.close_authority(state="done", reason="story connector:2-10 reached CLOSE")

        projection = json.loads((self.auth.runtime_dir / "status.json").read_text(encoding="utf-8"))
        self.assertTrue(projection["closed"])
        self.assertEqual(projection["close_state"], "done")
        self.assertEqual(projection["budget"]["consumed_model_calls"], 10)
        self.assertEqual(projection["budget"]["remaining_global_budget"], 4)
        self.assertEqual(projection["children"]["B013"]["checker_verdict"], "changes_requested")
        self.assertEqual(projection["children"]["B014"]["checker_verdict"], "approved")
        self.assertEqual(projection["children"]["B013"]["budget"]["consumed_model_calls"], 8)
        self.assertEqual(projection["children"]["B014"]["budget"]["consumed_model_calls"], 2)
        # B013 was never merged to carry state forward: main moved exactly once, at the end.
        self.assertEqual(self.git("rev-list", "--count", f"{self.governance_base}..main"), "3")
        self.assertIn(b013_reviewed_commit, self.git("rev-list", "main").split())
        self.assertEqual(self.git("rev-parse", f"{merge_commit}^2"), integration_candidate)

    # ---- T028 receipt ------------------------------------------------------------------

    def confirmed_merge_receipt(self, *, checker_commit: str, candidate_commit: str):
        anchor = temporary_platform_anchor_for_testing({TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()})
        anchor.__enter__()
        self.addCleanup(anchor.__exit__, None, None, None)
        previous = {key: os.environ.get(key) for key in (
            "TL_MERGE_AUTHORITY_APP_ID", "TL_MERGE_AUTHORITY_APP_SLUG",
            "TL_MERGE_AUTHORITY_PUBLIC_KEY", "TL_MERGE_AUTHORITY_KEY_ID")}

        def restore() -> None:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)
        os.environ["TL_MERGE_AUTHORITY_APP_ID"] = str(TEST_FIXTURE_APP_ID)
        os.environ["TL_MERGE_AUTHORITY_APP_SLUG"] = TEST_FIXTURE_APP_SLUG
        os.environ["TL_MERGE_AUTHORITY_PUBLIC_KEY"] = TEST_FIXTURE_PUBLIC_KEY.hex()
        os.environ["TL_MERGE_AUTHORITY_KEY_ID"] = TEST_FIXTURE_KEY_ID
        capability = issue_platform_capability(
            app_id=TEST_FIXTURE_APP_ID, app_slug=TEST_FIXTURE_APP_SLUG,
            public_keys={TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()},
            signing_secret_key=TEST_FIXTURE_SECRET_KEY)
        self.trust_root = TrustRoot.from_platform_capability(
            capability=capability, trusted_app_id=TEST_FIXTURE_APP_ID, trusted_app_slug=TEST_FIXTURE_APP_SLUG,
            trusted_public_keys={TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()})
        base_sha = self.git("rev-parse", "main")
        claim = {
            "schema_version": 1, "target_repository": TARGET_REPOSITORY, "target_pr": 101,
            "expected_head_sha": candidate_commit, "expected_base_sha": base_sha,
            "checker_approved_commit": checker_commit, "integration_candidate_commit": candidate_commit,
            "authority_mode": "delegated_single_merge", "issued_at": "2026-09-17T09:30:00Z",
            "expires_at": "2027-01-01T00:00:00Z", "nonce": "0123456789abcdef0123456789abcdef",
        }
        envelope = sign_authorization_envelope(
            claim, secret_key=TEST_FIXTURE_SECRET_KEY, key_id=TEST_FIXTURE_KEY_ID,
            mechanism="dedicated_github_app", integration_id=TEST_FIXTURE_APP_ID,
            issuer=f"{TEST_FIXTURE_APP_SLUG}[bot]")
        comment = {
            "id": 2001, "author": {"login": f"{TEST_FIXTURE_APP_SLUG}[bot]"},
            "body": "### Merge Authority Out-of-Band Attestation\n\n"
                    "```json:tl-merge-authorization\n" + json.dumps(envelope, indent=2) + "\n```\n",
            "createdAt": "2026-09-17T09:31:00Z",
        }
        receipt = MergeAuthorityGate.evaluate(
            repo_root=self.root, pr_number=101,
            live_pr_info={"state": "OPEN", "headRefOid": candidate_commit, "baseRefOid": base_sha,
                          "mergeable": "MERGEABLE"},
            checker_commit=checker_commit, candidate_commit=candidate_commit,
            authority_store=InMemoryAuthorityStore(), expected_repo=TARGET_REPOSITORY, comments=[comment],
            enforce_mode="delegated_single_merge", trust_root=self.trust_root)
        self.assertTrue(receipt.is_confirmed, receipt.reason)
        return receipt


class ReplayFixtureIntegrityTest(StoryCase):
    """The fixture must describe the Story it claims to describe, or the replay proves nothing."""

    def test_fixture_digests_match_their_source_files(self) -> None:
        payload = load_fixture("authority-payload.json")
        spec_sha = plan_validator.sha256_hex((FIXTURES / "spec.md").read_bytes())
        arch_sha = plan_validator.sha256_hex((FIXTURES / "docs-arch.md").read_bytes())
        self.assertEqual(payload["authorized_spec_sha256"], spec_sha)
        self.assertEqual(payload["protected_paths"][0]["sha256"], arch_sha)
        self.assertEqual(
            plan_validator.sha256_hex((self.root / "_tl-orc/project/tasks/connector-2-10.md").read_bytes()),
            spec_sha)

    def test_fixture_execution_plan_is_approved_by_the_validator(self) -> None:
        result = plan_validator.validate_execution_plan(load_fixture("execution-plan.json"))
        self.assertTrue(result["approved"], result["errors"])


if __name__ == "__main__":
    unittest.main()
