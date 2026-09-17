#!/usr/bin/env python3
"""A) Authority and digest without circularity (T032 §2.13), counterfactuals 1-4."""

from __future__ import annotations

import copy
import json
import unittest

from story_authority_support import StoryCase, freeze, make_payload, plan_validator, story


class RootAuthorityDigestTest(StoryCase):

    def test_root_authority_digest_has_no_self_reference(self) -> None:
        """1. The digest is computed over the authorized payload alone, never over itself."""
        payload = make_payload()
        digest = story.root_authority_digest(payload)
        canonical = story.canonical_authority_payload(payload)
        self.assertEqual(digest, plan_validator.sha256_hex(canonical))
        self.assertNotIn("root_authority_digest", canonical)
        self.assertEqual(sorted(json.loads(canonical)), sorted(story.AUTHORITY_PAYLOAD_FIELDS))

        for contaminant in ("root_authority_digest", "operator_authorization_ref", "authorized_at",
                            "authorized_literal", "authority_source"):
            polluted = dict(payload)
            polluted[contaminant] = digest if "digest" in contaminant else "2026-09-17T09:00:00Z"
            with self.assertRaises(story.Refusal) as raised:
                story.root_authority_digest(polluted)
            self.assertIn("post-authorization field", str(raised.exception))

        envelope = freeze(payload)
        self.assertEqual(envelope["root_authority_digest"], digest)
        self.assertNotIn("root_authority_digest", envelope["authority_payload"])
        self.assertNotIn("operator_authorization", envelope["authority_payload"])

    def test_authorization_metadata_does_not_change_root_digest(self) -> None:
        """2. Capture timestamp and literal are produced after the decision and never digested."""
        payload = make_payload()
        digest = story.root_authority_digest(payload)
        early = freeze(payload, source="operator-terminal", at="2026-09-17T09:00:00Z")
        late = freeze(payload, source="operator-web-console", at="2026-12-31T23:59:59Z")
        self.assertEqual(early["root_authority_digest"], digest)
        self.assertEqual(late["root_authority_digest"], digest)
        self.assertNotEqual(early["operator_authorization"], late["operator_authorization"])
        self.assertEqual(early["authority_payload"], late["authority_payload"])
        # And recomputing from either persisted envelope still lands on the same digest.
        for envelope in (early, late):
            self.assertEqual(story.root_authority_digest(envelope["authority_payload"]), digest)

    def test_mutated_authority_payload_invalidates_operator_authorization(self) -> None:
        """3. A single mutated byte in the payload voids the human decision bound to it."""
        envelope = self.frozen_authority()
        path = story.authority_envelope_path(self.root, "A001")
        self.assertEqual(story.load_authority(path)["root_authority_digest"], envelope["root_authority_digest"])

        for mutate in (
            lambda p: p.__setitem__("global_model_call_budget", p["global_model_call_budget"] + 1),
            lambda p: p["authorized_write_scope"]["forbidden_paths"].remove("secrets"),
            lambda p: p["allowed_effects"].__setitem__("release", True),
            lambda p: p.__setitem__("authorized_spec_sha256", "f" * 64),
            lambda p: p["protected_paths"].clear(),
        ):
            tampered = copy.deepcopy(envelope)
            mutate(tampered["authority_payload"])
            path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
            with self.assertRaises(story.HardStop) as raised:
                story.load_authority(path)
            self.assertEqual(raised.exception.reason, "state_integrity")
            self.assertIn("mutated after the human decision", raised.exception.detail)
            # And no ledger can be opened on a payload the operator never approved.
            with self.assertRaises(story.HardStop):
                story.StoryAuthority(tampered, self.root / "runtime" / "A001")

    def test_auto_story_cannot_start_without_exact_root_digest_authorization(self) -> None:
        """4. Only the exact canonical literal grants authority; nothing near it does."""
        payload = make_payload()
        digest = story.root_authority_digest(payload)
        other_digest = story.root_authority_digest(make_payload(global_model_call_budget=20))

        for literal in (
            "",
            "AUTORIZO",
            "AUTORIZO STORY connector:2-10",
            f"AUTORIZO STORY connector:2-10 sha256:{digest[:32]}",
            f"AUTORIZO STORY connector:2-10 {digest}",
            f"autorizo story connector:2-10 sha256:{digest}",
            f"AUTORIZO STORY connector:2-10 sha256:{digest.upper()}",
            f"AUTORIZO STORY connector:2-11 sha256:{digest}",
            f"AUTORIZO STORY connector:2-10 sha256:{other_digest}",
            f"AUTORIZO STORY connector:2-10 sha256:{digest} --force",
        ):
            with self.assertRaises(story.Refusal, msg=literal):
                story.freeze_authority(payload, authorized_literal=literal, authority_source="operator-terminal",
                                       authorized_at="2026-09-17T09:00:00Z")

        granted = story.freeze_authority(
            payload, authorized_literal=story.authorization_literal("connector:2-10", digest),
            authority_source="operator-terminal", authorized_at="2026-09-17T09:00:00Z")
        self.assertEqual(granted["root_authority_digest"], digest)

        # A hand-assembled wrapper whose literal names a different payload never opens a ledger.
        forged = copy.deepcopy(granted)
        forged["operator_authorization"]["authorized_literal"] = story.authorization_literal(
            "connector:2-10", other_digest)
        with self.assertRaises(story.HardStop) as raised:
            story.verify_authority_envelope(forged)
        self.assertEqual(raised.exception.reason, "authority_missing_or_ambiguous")

    def test_presentation_shows_the_operator_exactly_what_will_be_digested(self) -> None:
        """The read-only presentation step grants nothing and states the literal required."""
        payload = make_payload()
        presented = story.present_for_authorization(payload)
        self.assertEqual(presented["authority_mode"], "AUTO_STORY")
        self.assertEqual(presented["root_authority_digest"], story.root_authority_digest(payload))
        self.assertEqual(presented["required_operator_literal"],
                         f"AUTORIZO STORY connector:2-10 sha256:{presented['root_authority_digest']}")
        self.assertFalse(story.authority_envelope_path(self.root, "A001").exists())


if __name__ == "__main__":
    unittest.main()
