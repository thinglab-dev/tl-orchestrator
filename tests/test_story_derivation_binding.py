#!/usr/bin/env python3
"""H) The registered derivation is the source of truth an executable batch binds to (T032 §2.4).

A digest in a batch file is a claim. These counterfactuals prove that the claim is only ever
honoured when the Story Authority journal registered a child proposal and a derivation proof
for exactly that batch id, that both documents still digest to what was registered, and that
the lineage they describe is the one the journal records: a declared parent exists and is
closed, and a later child cannot pass itself off as the first one.
"""

from __future__ import annotations

import copy
import json
import unittest

from story_authority_support import StoryCase, plan_validator, story

SPEC_PATH = "_tl-orc/project/tasks/connector-2-10.md"
SPEC_PATHS = (SPEC_PATH,)


class DerivationBindingCase(StoryCase):

    def setUp(self) -> None:
        super().setUp()
        self.auth = self.authority(self.baseline_authority(max_child_batches=4))
        self.residual = [self.patch_item("R5", location="src/connector.py:118")]
        self.commit, self.tree = self.git.head(), self.git.tree()

    # ---- scaffolding ----------------------------------------------------------------

    def derive(self, child_id: str, parent: str | None = None, *, items: list[dict] | None = None,
               budget: int = 2) -> dict:
        residual = self.residual if items is None else items
        return story.derive_child_proposal(
            authority=self.auth, child_batch_id=child_id, action_items=residual if parent else [],
            previous_child_id=parent, model_call_budget=budget, governance_base_commit=self.governance_base,
            story_baseline_commit=self.governance_base)

    def register(self, child_id: str, parent: str | None = None, **kwargs) -> tuple[dict, dict]:
        proposal = self.derive(child_id, parent, **kwargs)
        proof = story.verify_derivation(self.auth, proposal, action_items=self.residual if parent else None,
                                        spec_paths=SPEC_PATHS)
        self.auth.record_child_derived(proposal, proof)
        return proposal, proof

    def close(self, child_id: str, verdict: str = "changes_requested", items: list[dict] | None = None) -> None:
        residual = (self.residual if items is None else items) if verdict == "changes_requested" else []
        self.auth.record_child_closed(
            child_batch_id=child_id, governance_base_commit=self.governance_base,
            checker_reviewed_commit=self.commit, checker_reviewed_tree=self.tree,
            functional_checkpoint_commit=self.commit, functional_checkpoint_tree=self.tree,
            checker_verdict=verdict, unresolved_action_items=residual)

    def batch(self, child_id: str, proof: dict, **authorization) -> dict:
        declared = {
            "story_authority_mode": "AUTO_STORY", "story_authority_id": "A001",
            "root_authority_digest": self.auth.root_digest,
            "child_proposal_digest": proof["child_proposal_digest"],
            "derivation_proof_digest": proof["derivation_proof_digest"],
            "permitted_effects": {"local_write": True, "local_commit": True, "local_merge": False,
                                  "pull_request": False, "push": False, "tag": False, "release": False,
                                  "pull_request_merge": False, "ci_rerun": False},
        }
        declared.update(authorization)
        return {"id": child_id, "authorization": declared, "budget": {"max_model_calls": 2}}

    def units(self, **overrides) -> list[dict]:
        unit = {"work_ref": "connector:2-10", "scope_paths": ["src/connector.py"],
                "spec_sha256": self.auth.payload["authorized_spec_sha256"], "spec_path": SPEC_PATH}
        unit.update(overrides)
        return [unit]

    def assert_stop(self, reason: str, check: str, call, *args, **kwargs) -> story.HardStop:
        derived_before = [event["child_batch_id"] for event in self.auth.refold().derived]
        with self.assertRaises(story.HardStop) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.reason, reason, raised.exception.detail)
        self.assertIn(check, raised.exception.detail)
        self.auth.refold()
        self.assertEqual([event["child_batch_id"] for event in self.auth.state.derived], derived_before,
                         "a refusal must register no derivation")
        self.assertEqual(self.auth.state.hard_stops[-1]["reason"], reason, "the refusal must be journaled")
        return raised.exception


class LineageCounterfactualTest(DerivationBindingCase):

    def test_declared_parent_that_was_never_derived_is_refused(self) -> None:
        """A parent_child_batch_id is a reference into the journal, not a label."""
        proposal = self.derive("B014", parent="B999")
        self.assertIsNone(proposal["functional_parent_checkpoint"])  # nothing to inherit: B999 never closed
        self.assert_stop("state_integrity", "parent_child_is_registered", story.verify_derivation,
                         self.auth, proposal, action_items=self.residual, spec_paths=SPEC_PATHS)

        # The same holds when other children do exist: the named parent still has to be one of them.
        self.register("B013")
        self.close("B013")
        ghost = self.derive("B014", parent="B013")
        ghost["parent_child_batch_id"] = "B012"
        self.assert_stop("state_integrity", "parent_child_is_registered", story.verify_derivation,
                         self.auth, ghost, action_items=self.residual, spec_paths=SPEC_PATHS)

    def test_declared_parent_must_be_closed_before_a_child_is_derived(self) -> None:
        self.register("B013")
        # Still derived/open: the single-active-child rule already refuses it ...
        running = self.derive("B014", parent="B013")
        self.assert_stop("state_integrity", "max_active_child_batches", story.verify_derivation,
                         self.auth, running, action_items=self.residual, spec_paths=SPEC_PATHS)
        # ... and a parent that failed without any Checker review is not active, yet it is not
        # closed either: there is no reviewed commit and no recorded finding to derive from.
        self.auth.record_child_failed("B013", reason="unrecoverable_harness_failure", detail="never reviewed")
        self.assertEqual(self.auth.state.active_children(), [])
        self.assert_stop("state_integrity", "parent_child_is_closed", story.verify_derivation,
                         self.auth, self.derive("B014", parent="B013"), action_items=self.residual,
                         spec_paths=SPEC_PATHS)

    def test_second_child_cannot_pose_as_the_first_child(self) -> None:
        """Declaring no parent would skip the patch-only proof, the findings and the checkpoint."""
        self.register("B013")
        self.close("B013")
        impostor = self.derive("B014")  # parent None, checkpoint None, no residual finding
        self.assertIsNone(impostor["parent_child_batch_id"])
        self.assert_stop("state_integrity", "first_child_is_the_only_root", story.verify_derivation,
                         self.auth, impostor)
        # Handing it an empty residual set is refused even earlier: nothing derives from nothing.
        self.assert_stop("intent_gap", "patch_only_findings", story.verify_derivation,
                         self.auth, impostor, action_items=[], spec_paths=SPEC_PATHS)

        # The honest second child names its closed parent and carries its findings.
        proposal, proof = self.register("B014", parent="B013")
        self.assertEqual(proposal["parent_child_batch_id"], "B013")
        self.assertEqual(proof["parent_authority_digest"],
                         self.auth.state.derivation_of("B013")["derivation_proof_digest"])

    def test_child_of_a_parent_cannot_be_verified_without_its_findings(self) -> None:
        self.register("B013")
        self.close("B013")
        self.assert_stop("intent_gap", "residual_findings_supplied", story.verify_derivation,
                         self.auth, self.derive("B014", parent="B013"))

    def test_lineage_continues_from_the_latest_reviewed_child_only(self) -> None:
        self.register("B013")
        self.close("B013")
        self.register("B014", parent="B013")
        self.close("B014")
        fork = self.derive("B015", parent="B014")
        fork["parent_child_batch_id"] = "B013"  # would silently drop what B014's Checker reviewed
        self.assert_stop("state_integrity", "parent_is_the_latest_closed_child", story.verify_derivation,
                         self.auth, fork, action_items=self.residual, spec_paths=SPEC_PATHS)
        self.register("B015", parent="B014")

    def test_an_approved_parent_derives_nothing(self) -> None:
        self.register("B013")
        self.close("B013", verdict="approved")
        self.assert_stop("intent_gap", "parent_requested_changes", story.verify_derivation,
                         self.auth, self.derive("B014", parent="B013"), action_items=self.residual,
                         spec_paths=SPEC_PATHS)

    def test_a_blocker_the_checker_declared_cannot_be_dropped_on_the_way_to_the_child(self) -> None:
        """The closure digests what the Checker declared, so a stripped finding is a different one."""
        blocked = [self.patch_item("R5", location="src/connector.py:118", derivation_blockers=["migration"])]
        self.register("B013")
        self.close("B013", items=blocked)
        stripped = [{k: v for k, v in blocked[0].items() if k != "derivation_blockers"}]
        self.assertNotEqual(story.unresolved_action_items_digest(blocked),
                            story.unresolved_action_items_digest(stripped))
        proposal = self.derive("B014", parent="B013", items=stripped)
        self.assert_stop("state_integrity", "unresolved_items_match_closure", story.verify_derivation,
                         self.auth, proposal, action_items=stripped, spec_paths=SPEC_PATHS)
        # Submitted honestly, the same finding is refused for what it is.
        self.assert_stop("migration", "patch_only_findings", story.verify_derivation,
                         self.auth, self.derive("B014", parent="B013", items=blocked), action_items=blocked,
                         spec_paths=SPEC_PATHS)


class RegistrationCounterfactualTest(DerivationBindingCase):

    def test_registration_persists_the_documents_and_refolds_from_disk(self) -> None:
        proposal, proof = self.register("B013")
        event = self.auth.state.derivation_of("B013")
        self.assertEqual(event["child_proposal"], proposal)
        self.assertEqual(event["derivation_proof"], proof)
        self.assertEqual(event["child_proposal_digest"], plan_validator.digest_of(proposal))

        # A second process sees exactly the same registered derivation: the journal is the truth.
        self.auth.release()
        with story.StoryAuthority.open_for(self.root, "A001") as reopened:
            refolded = reopened.state.derivation_of("B013")
            self.assertEqual(refolded["child_proposal"], proposal)
            self.assertEqual(refolded["derivation_proof"], proof)
            self.assertEqual(plan_validator.digest_of(refolded["child_proposal"]), proof["child_proposal_digest"])
        self.auth.acquire()

        lines = [json.loads(line) for line in self.auth.journal.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([line["kind"] for line in lines], ["authority_open", "child_derived"])
        self.assertEqual([line["seq"] for line in lines], [1, 2])

    def test_registering_the_same_derivation_twice_appends_nothing(self) -> None:
        proposal, proof = self.register("B013")
        events_before = self.auth.state.events
        replayed = self.auth.record_child_derived(copy.deepcopy(proposal), copy.deepcopy(proof))
        self.assertEqual(replayed["derivation_proof_digest"], proof["derivation_proof_digest"])
        self.assertEqual(self.auth.refold().events, events_before)
        # Replay stays idempotent after the child moved on.
        self.close("B013")
        events_before = self.auth.state.events
        self.auth.record_child_derived(proposal, proof)
        self.assertEqual(self.auth.refold().events, events_before)
        self.assertEqual(self.auth.state.children["B013"]["state"], "closed")

    def test_a_registered_derivation_is_never_replaced(self) -> None:
        self.register("B013", budget=2)
        other = self.derive("B013", budget=3)
        other_proof = story.verify_derivation(self.auth, other)
        self.assert_stop("state_integrity", "never replaced", self.auth.record_child_derived, other, other_proof)
        self.assertEqual(self.auth.state.derivation_of("B013")["granted_model_calls"], 2)

    def test_proposal_edited_after_it_was_proven_is_not_registered(self) -> None:
        proposal = self.derive("B013")
        proof = story.verify_derivation(self.auth, proposal)
        widened = copy.deepcopy(proposal)
        widened["model_call_budget"] = 9
        self.assert_stop("state_integrity", "child_proposal_digest_recomputed",
                         self.auth.record_child_derived, widened, proof)

        # Re-sealing the proof over the edited proposal does not help: the proof also states the
        # grant, and a proof rewritten to agree is re-proven against the envelope, not believed.
        resealed = dict(proof, child_proposal_digest=plan_validator.digest_of(widened))
        resealed["derivation_proof_digest"] = story._proof_digest(resealed)
        self.assert_stop("state_integrity", "proof_binds_this_derivation",
                         self.auth.record_child_derived, widened, resealed)

    def test_fabricated_proof_for_an_unprovable_proposal_is_not_registered(self) -> None:
        """A self-consistent proof is still only a claim: registration re-proves what it can."""
        def fabricate(proposal: dict) -> dict:
            proof = {
                "schema_version": 1, "authority_id": "A001", "work_ref": self.auth.payload["work_ref"],
                "child_batch_id": proposal["child_batch_id"],
                "parent_child_batch_id": proposal["parent_child_batch_id"],
                "root_authority_digest": self.auth.root_digest, "parent_authority_digest": self.auth.root_digest,
                "parent_batch_digest": "", "child_proposal_digest": plan_validator.digest_of(proposal),
                "functional_parent_checkpoint": proposal["functional_parent_checkpoint"],
                "unresolved_action_items_digest": "", "granted_model_calls": proposal["model_call_budget"],
                "checks": [{"check": "everything", "result": "pass"}],
            }
            proof["derivation_proof_digest"] = story._proof_digest(proof)
            return proof

        outside = self.derive("B013")
        outside["conditional_mutation_targets"] = sorted(outside["conditional_mutation_targets"] + ["infra"])
        self.assert_stop("scope_expansion", "scope_subset", self.auth.record_child_derived,
                         outside, fabricate(outside))

        pushing = self.derive("B013")
        pushing["allowed_effects"] = dict(pushing["allowed_effects"], release=True)
        self.assert_stop("effect_expansion", "effects_subset", self.auth.record_child_derived,
                         pushing, fabricate(pushing))

        unforbidden = self.derive("B013")
        unforbidden["forbidden_paths"] = []
        self.assert_stop("scope_expansion", "forbidden_monotonic", self.auth.record_child_derived,
                         unforbidden, fabricate(unforbidden))

        failing = fabricate(self.derive("B013"))
        failing["checks"].append({"check": "scope_subset", "result": "fail"})
        failing["derivation_proof_digest"] = story._proof_digest(failing)
        self.assert_stop("state_integrity", "proof_records_only_passes", self.auth.record_child_derived,
                         self.derive("B013"), failing)

        # And a fabricated first-child proof for what is really a second child.
        self.register("B013")
        self.close("B013")
        impostor = self.derive("B014")
        self.assert_stop("state_integrity", "first_child_is_the_only_root", self.auth.record_child_derived,
                         impostor, fabricate(impostor))

    def test_proof_with_a_foreign_chain_is_not_registered(self) -> None:
        self.register("B013")
        self.close("B013")
        proposal = self.derive("B014", parent="B013")
        proof = story.verify_derivation(self.auth, proposal, action_items=self.residual, spec_paths=SPEC_PATHS)
        for field in ("parent_authority_digest", "parent_batch_digest"):
            forged = dict(proof)
            forged[field] = "e" * 64
            forged["derivation_proof_digest"] = story._proof_digest(forged)
            self.assert_stop("state_integrity", "derivation_chain_recomputed",
                             self.auth.record_child_derived, proposal, forged)
        foreign_root = dict(proof, root_authority_digest="e" * 64)
        foreign_root["derivation_proof_digest"] = story._proof_digest(foreign_root)
        self.assert_stop("state_integrity", "proof_binds_this_derivation",
                         self.auth.record_child_derived, proposal, foreign_root)


class ExecutableBindingTest(DerivationBindingCase):

    def test_registered_batch_binds_and_exposes_the_childs_prohibitions(self) -> None:
        proposal, proof = self.register("B013")
        binding = story.bind_child_batch(self.auth, self.batch("B013", proof), self.units())
        self.assertEqual(binding["child_proposal"], proposal)
        self.assertEqual(binding["derivation_proof"], proof)
        self.assertIsNone(binding["functional_parent_checkpoint"])
        self.assertNotIn("fail", {check["result"] for check in binding["checks"]})
        # Forbidden and protected paths of the child, as the policy the runtime must enforce.
        self.assertEqual(binding["do_not_touch"],
                         sorted(set(proposal["forbidden_paths"]) | {p["pattern"] for p in proposal["protected_paths"]}))
        self.assertIn("secrets", binding["do_not_touch"])
        self.assertIn("docs/ARCH.md", binding["do_not_touch"])

    def test_binding_requires_the_authority_lease(self) -> None:
        _proposal, proof = self.register("B013")
        self.auth.release()
        with self.assertRaises(story.Refusal) as raised:
            story.bind_child_batch(self.auth, self.batch("B013", proof), self.units())
        self.assertIn("coordinator_conflict", str(raised.exception))
        self.auth.acquire()

    def test_batch_that_was_never_derived_has_no_authority(self) -> None:
        proposal = self.derive("B013")
        proof = story.verify_derivation(self.auth, proposal)  # proven, but never registered
        self.assert_stop("authority_missing_or_ambiguous", "child_is_registered", story.bind_child_batch,
                         self.auth, self.batch("B013", proof), self.units())

        # A registered sibling does not lend its derivation to another batch id.
        self.auth.record_child_derived(proposal, proof)
        self.assert_stop("authority_missing_or_ambiguous", "child_is_registered", story.bind_child_batch,
                         self.auth, self.batch("B777", proof), self.units())

    def test_batch_declaring_digests_other_than_the_registered_ones_is_refused(self) -> None:
        _proposal, proof = self.register("B013")
        for field in ("child_proposal_digest", "derivation_proof_digest"):
            self.assert_stop("state_integrity", "batch_declares_registered_digests", story.bind_child_batch,
                             self.auth, self.batch("B013", proof, **{field: "f" * 64}), self.units())
        self.assert_stop("authority_missing_or_ambiguous", "batch_names_this_authority", story.bind_child_batch,
                         self.auth, self.batch("B013", proof, root_authority_digest="f" * 64), self.units())
        self.assert_stop("authority_missing_or_ambiguous", "batch_names_this_authority", story.bind_child_batch,
                         self.auth, self.batch("B013", proof, story_authority_id="A002"), self.units())

    def rewrite_journal(self, mutate) -> None:
        """An attacker with write access to the journal who also re-links the hash chain."""
        self.auth.release()
        path = self.auth.journal.path
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        mutate(events)
        prev, lines = "", []
        for event in events:
            event["prev"] = prev
            line = plan_validator.canonical_json(event)
            prev = plan_validator.sha256_hex(line)[:16]
            lines.append(line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_registered_documents_edited_on_disk_are_recomputed_not_believed(self) -> None:
        _proposal, proof = self.register("B013")
        batch = self.batch("B013", proof)
        path = self.auth.journal.path

        # Edited in place while it is the last line: a hash chain only notices an edit through the
        # line that follows it, so the ledger opens. Recomputing the digest is what catches it.
        tail = path.read_text(encoding="utf-8")
        self.auth.release()
        path.write_text(tail.replace('"model_call_budget":2', '"model_call_budget":9'), encoding="utf-8")
        self.assertNotEqual(path.read_text(encoding="utf-8"), tail)
        self.auth.acquire()
        self.assertEqual(self.auth.state.invalid_lines, 0)
        self.assertEqual(self.auth.state.derivation_of("B013")["child_proposal"]["model_call_budget"], 9)
        self.assert_stop("state_integrity", "child_proposal_digest_recomputed", story.bind_child_batch,
                         self.auth, batch, self.units())
        self.auth.release()
        path.write_text(tail, encoding="utf-8")
        self.auth.acquire()

        # Once the line has a successor the same edit breaks the chain and the ledger refuses to open.
        story.budgeted_authority_dispatch(
            self.auth, child_batch_id="B013", logical_call_id="B013-maker-r01", role="maker",
            phase="implementation", dispatch=lambda _attempt: {"state": "completed"})
        original = path.read_text(encoding="utf-8")
        self.auth.release()
        path.write_text(original.replace('"model_call_budget":2', '"model_call_budget":9'), encoding="utf-8")
        self.assertNotEqual(path.read_text(encoding="utf-8"), original)
        with self.assertRaises(story.HardStop) as broken:
            self.auth.acquire()
        self.assertEqual(broken.exception.reason, "state_integrity")
        self.assertIn("hash chain is broken", broken.exception.detail)
        path.write_text(original, encoding="utf-8")

        # Edited and re-linked: the chain is valid again, so only recomputation can notice.
        def widen(events: list[dict]) -> None:
            derived = next(event for event in events if event["kind"] == "child_derived")
            derived["child_proposal"]["model_call_budget"] = 9
            derived["child_proposal"]["conditional_mutation_targets"].append("infra")

        self.rewrite_journal(widen)
        self.auth.acquire()
        self.assertEqual(self.auth.state.invalid_lines, 0)
        self.assert_stop("scope_expansion", "scope_subset", story.bind_child_batch, self.auth, batch, self.units())
        self.auth.release()
        path.write_text(original, encoding="utf-8")

        def regrant(events: list[dict]) -> None:
            derived = next(event for event in events if event["kind"] == "child_derived")
            derived["child_proposal"]["model_call_budget"] = 9

        self.rewrite_journal(regrant)
        self.auth.acquire()
        self.assert_stop("state_integrity", "child_proposal_digest_recomputed", story.bind_child_batch,
                         self.auth, batch, self.units())
        self.auth.release()
        path.write_text(original, encoding="utf-8")

        # The event's own digest columns are not a second truth either.
        def relabel(events: list[dict]) -> None:
            derived = next(event for event in events if event["kind"] == "child_derived")
            derived["child_proposal_digest"] = "f" * 64

        self.rewrite_journal(relabel)
        self.auth.acquire()
        self.assert_stop("state_integrity", "journal_digests_match_documents", story.bind_child_batch,
                         self.auth, self.batch("B013", proof, child_proposal_digest="f" * 64), self.units())
        self.auth.release()
        path.write_text(original, encoding="utf-8")

        # A legacy-shaped event that carries digests but no documents cannot be recomputed.
        def strip(events: list[dict]) -> None:
            derived = next(event for event in events if event["kind"] == "child_derived")
            derived.pop("child_proposal")
            derived.pop("derivation_proof")

        self.rewrite_journal(strip)
        self.auth.acquire()
        self.assert_stop("state_integrity", "derivation_documents_present", story.bind_child_batch,
                         self.auth, batch, self.units())

    def test_second_derivation_written_around_the_gateway_blocks_the_ledger(self) -> None:
        proposal, proof = self.register("B013")
        other = copy.deepcopy(proposal)
        other["model_call_budget"] = 9
        self.auth.journal.append(
            "child_derived", authority_id="A001", child_batch_id="B013", parent_child_batch_id=None,
            root_authority_digest=self.auth.root_digest, parent_authority_digest=self.auth.root_digest,
            parent_batch_digest="", child_proposal_digest=plan_validator.digest_of(other),
            derivation_proof_digest="f" * 64, granted_model_calls=9, child_proposal=other, derivation_proof={})
        # The first registration stays the registered one ...
        self.assertEqual(self.auth.refold().derivation_of("B013")["child_proposal"], proposal)
        self.assertEqual(self.auth.state.derivation_conflicts, ["B013"])
        # ... and no ledger opens on a journal that was written around `record_child_derived`.
        self.auth.release()
        with self.assertRaises(story.HardStop) as raised:
            self.auth.acquire()
        self.assertEqual(raised.exception.reason, "state_integrity")
        self.assertIn("never replaced", raised.exception.detail)
        self.assertIsNone(self.auth._lease, "a ledger that refused to open must not keep the lease")

    def forge_registration(self, proposal: dict) -> dict:
        """Write a self-consistent derivation straight into the journal, around every gateway."""
        proof = {
            "schema_version": 1, "authority_id": "A001", "work_ref": self.auth.payload["work_ref"],
            "child_batch_id": proposal["child_batch_id"], "parent_child_batch_id": proposal["parent_child_batch_id"],
            "root_authority_digest": self.auth.root_digest, "parent_authority_digest": self.auth.root_digest,
            "parent_batch_digest": "", "child_proposal_digest": plan_validator.digest_of(proposal),
            "functional_parent_checkpoint": proposal["functional_parent_checkpoint"],
            "unresolved_action_items_digest": "", "granted_model_calls": proposal["model_call_budget"],
            "checks": [{"check": "everything", "result": "pass"}],
        }
        proof["derivation_proof_digest"] = story._proof_digest(proof)
        self.auth.journal.append(
            "child_derived", authority_id="A001", child_batch_id=proposal["child_batch_id"],
            parent_child_batch_id=proposal["parent_child_batch_id"], root_authority_digest=self.auth.root_digest,
            parent_authority_digest=proof["parent_authority_digest"], parent_batch_digest="",
            child_proposal_digest=proof["child_proposal_digest"],
            derivation_proof_digest=proof["derivation_proof_digest"],
            granted_model_calls=proposal["model_call_budget"], functional_parent_checkpoint=None,
            unresolved_action_items_digest="", child_proposal=proposal, derivation_proof=proof)
        return proof

    def test_forged_journal_entries_do_not_survive_the_bind(self) -> None:
        """Even a journal the attacker wrote is re-proven against the envelope and the lineage."""
        self.register("B013")
        self.close("B013")

        impostor = self.derive("B014")  # poses as a first child to restart from the governance base
        proof = self.forge_registration(impostor)
        self.assert_stop("state_integrity", "first_child_is_the_only_root", story.bind_child_batch,
                         self.auth, self.batch("B014", proof), self.units())

        orphan = self.derive("B015", parent="B013")
        orphan["parent_child_batch_id"] = "B404"
        orphan["functional_parent_checkpoint"] = None
        proof = self.forge_registration(orphan)
        self.assert_stop("state_integrity", "parent_child_is_registered", story.bind_child_batch,
                         self.auth, self.batch("B015", proof), self.units())

    def test_batch_may_ask_for_nothing_beyond_the_derived_child(self) -> None:
        proposal, proof = self.register("B013")
        self.assertEqual(proposal["model_call_budget"], 2)
        bind = story.bind_child_batch

        self.assert_stop("next_story_without_authorization", "batch_within_story", bind, self.auth,
                         self.batch("B013", proof), self.units(work_ref="connector:2-11"))
        self.assert_stop("unexpected_revision_drift", "batch_spec_is_the_authorized_spec", bind, self.auth,
                         self.batch("B013", proof), self.units(spec_sha256="b" * 64))
        self.assert_stop("scope_expansion", "batch_scope_within_child", bind, self.auth,
                         self.batch("B013", proof), self.units(scope_paths=["src/connector.py", "infra"]))
        # A scope path may contain a forbidden path, never the other way round.
        for denied in ("secrets", "secrets/prod", "docs/ARCH.md"):
            stop = self.assert_stop("scope_expansion", "batch_scope", bind, self.auth,
                                    self.batch("B013", proof), self.units(scope_paths=[denied]))
            self.assertIn(denied, stop.detail)

        effects = self.batch("B013", proof)["authorization"]["permitted_effects"]
        for effect in ("release", "tag", "ci_rerun"):
            self.assertFalse(proposal["allowed_effects"].get(effect, False))
            stop = self.assert_stop("effect_expansion", "batch_effects_within_child", bind, self.auth,
                                    self.batch("B013", proof, permitted_effects=dict(effects, **{effect: True})),
                                    self.units())
            self.assertIn(effect, stop.detail)
        # pull_request_merge is the runtime's name for the envelope's `merge` capability.
        self.assertTrue(proposal["allowed_effects"]["merge"])
        bind(self.auth, self.batch("B013", proof, permitted_effects=dict(effects, pull_request_merge=True)),
             self.units())

        for ceiling in (3, 14, 0, True, "2", None):
            batch = self.batch("B013", proof)
            batch["budget"]["max_model_calls"] = ceiling
            self.assert_stop("model_call_budget_exhausted", "batch_budget_within_grant", bind, self.auth, batch,
                             self.units())

    def test_derived_child_binds_with_the_checkpoint_the_journal_recorded(self) -> None:
        self.register("B013")
        self.close("B013")
        proposal, proof = self.register("B014", parent="B013")
        binding = story.bind_child_batch(self.auth, self.batch("B014", proof), self.units())
        self.assertEqual(binding["functional_parent_checkpoint"],
                         {"commit": self.commit, "tree": self.tree, "child_batch_id": "B013"})
        # The bind answers the same way after the child closed: a re-run re-proves, it does not drift.
        self.close("B014", verdict="approved")
        rebound = story.bind_child_batch(self.auth, self.batch("B014", proof), self.units())
        self.assertEqual(rebound["child_proposal"], proposal)

        # A finding that points into the specification is caught at bind time, where the unit's
        # spec path is known, even if whoever registered the child did not say so.
        self.assert_stop("bad_spec", "patch_only_findings", story.bind_child_batch, self.auth,
                         self.batch("B014", proof), self.units(spec_path="src/connector.py"))


if __name__ == "__main__":
    unittest.main()
