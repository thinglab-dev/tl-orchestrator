#!/usr/bin/env python3
"""Scripted stand-in for the GitHub CLI, used by the runtime tests.

State lives in the JSON file named by TL_FAKE_GH_STATE. `checks` answers are consumed from
the `checks_sequence` list so a test can script pending → failure → success. Every call is
appended to `calls` so a test can prove an effect happened exactly once.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import hashlib

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TEST_FIXTURE_SECRET_KEY = hashlib.sha256(b"thinglab-test-fixture-seed-v1").digest()
TEST_FIXTURE_KEY_ID = "key-test-fixture-v1"
TEST_FIXTURE_APP_ID = 998811
TEST_FIXTURE_APP_SLUG = "thinglab-merge-authority"

try:
    from scripts.tl_merge_guard import ed25519_sign
    TEST_FIXTURE_PUBLIC_KEY, fixture_sig = ed25519_sign(TEST_FIXTURE_SECRET_KEY, b"")
except Exception:
    try:
        from tl_merge_guard import ed25519_sign  # type: ignore[no-redef]
        TEST_FIXTURE_PUBLIC_KEY, fixture_sig = ed25519_sign(TEST_FIXTURE_SECRET_KEY, b"")
    except Exception:
        TEST_FIXTURE_PUBLIC_KEY = b"\x00" * 32


def main(argv: list[str]) -> int:
    state_path = Path(os.environ["TL_FAKE_GH_STATE"])
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    state.setdefault("prs", {})
    state.setdefault("calls", [])
    state.setdefault("checks_sequence", ["success"])
    state.setdefault("failed_log", "")
    state["calls"].append(argv)
    out = ""
    code = 0
    if argv[:2] == ["pr", "create"]:
        head = argv[argv.index("--head") + 1]
        number = len(state["prs"]) + 100
        base = argv[argv.index("--base") + 1]
        head_oid = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip()
        state["prs"][head] = {"number": number, "url": f"https://example.invalid/pr/{number}", "state": "OPEN", "mergedAt": None, "base": base, "head_oid": head_oid}
        out = state["prs"][head]["url"]
    elif argv[:2] == ["pr", "list"]:
        head = argv[argv.index("--head") + 1]
        pr = state["prs"].get(head)
        if pr and pr["state"] == "OPEN":
            pr["head_oid"] = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip() or pr.get("head_oid")
        out = json.dumps([{"number": pr["number"], "url": pr["url"], "baseRefName": pr.get("base"), "headRefOid": pr.get("head_oid"), "state": pr["state"]}] if pr else [])
    elif argv[:2] == ["pr", "view"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        if pr and pr["state"] == "OPEN":
            head = next(h for h, p in state["prs"].items() if p is pr)
            pr["head_oid"] = subprocess.run(["git", "rev-parse", head], capture_output=True, text=True).stdout.strip() or pr.get("head_oid")
        base_name = pr.get("base", "main") if pr else "main"
        base_oid = subprocess.run(["git", "rev-parse", base_name], capture_output=True, text=True).stdout.strip() if pr else ""

        # TOCTOU simulation support for runtime integration testing
        view_count = state.get("pr_view_count", 0) + 1
        state["pr_view_count"] = view_count
        if state.get("toctou_base_drift") and view_count >= 2:
            base_oid = state.get("toctou_base_oid", "9" * 40)
        if state.get("toctou_missing_base_oid") and view_count >= 2:
            base_oid = ""
        if state.get("toctou_head_drift") and view_count >= 2:
            if pr:
                pr["head_oid"] = state.get("toctou_head_oid", "8" * 40)

        comments = []
        if "comments" in state:
            comments = state["comments"]
        elif pr and "comments" in pr:
            comments = pr["comments"]
        elif state.get("auto_authorize_merge", True) and pr:
            head_sha = pr.get("head_oid") or ""
            target_repo = state.get("target_repository")
            if not target_repo:
                try:
                    origin_url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
                    m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", origin_url)
                    target_repo = m.group(1) if m else "thinglab-dev/tl-orchestrator"
                except Exception:
                    target_repo = "thinglab-dev/tl-orchestrator"
            claim = {
                "schema_version": 1,
                "target_repository": target_repo,
                "target_pr": pr["number"],
                "expected_head_sha": head_sha,
                "expected_base_sha": base_oid,
                "checker_approved_commit": head_sha,
                "integration_candidate_commit": head_sha,
                "authority_mode": "delegated_single_merge",
                "issued_at": "2026-09-15T00:00:00Z",
                "expires_at": "2029-09-15T00:00:00Z",
                "nonce": "0123456789abcdef0123456789abcdef",
            }
            try:
                from scripts.tl_merge_guard import sign_authorization_envelope
                env = sign_authorization_envelope(
                    claim,
                    secret_key=TEST_FIXTURE_SECRET_KEY,
                    key_id=TEST_FIXTURE_KEY_ID,
                    mechanism="dedicated_github_app",
                    integration_id=TEST_FIXTURE_APP_ID,
                    issuer=f"{TEST_FIXTURE_APP_SLUG}[bot]",
                )
            except Exception:
                import hashlib
                auth_id = "auth-" + hashlib.sha256(json.dumps(claim, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
                env = dict(claim)
                env["authorization_id"] = auth_id
                env["provenance"] = {
                    "issuer": f"{TEST_FIXTURE_APP_SLUG}[bot]",
                    "mechanism": "dedicated_github_app",
                    "integration_id": TEST_FIXTURE_APP_ID,
                    "key_id": TEST_FIXTURE_KEY_ID,
                    "signature": "0" * 128,
                }
            comment_body = f"```json:tl-merge-authorization\n{json.dumps(env, indent=2)}\n```"
            comments = [{"id": 1, "body": comment_body, "author": {"login": f"{TEST_FIXTURE_APP_SLUG}[bot]"}}]

        out = json.dumps({
            "state": pr.get("state", "OPEN"),
            "mergedAt": pr.get("mergedAt"),
            "headRefOid": pr.get("head_oid"),
            "baseRefName": pr.get("base"),
            "baseRefOid": base_oid,
            "comments": comments,
        } if pr else {})
        code = 0 if pr else 1
    elif argv[:2] == ["pr", "merge"]:
        number = int(argv[2])
        pr = next((p for p in state["prs"].values() if p["number"] == number), None)
        expected = argv[argv.index("--match-head-commit") + 1] if "--match-head-commit" in argv else None
        head_now = subprocess.run(["git", "rev-parse", next(h for h, p in state["prs"].items() if p is pr)], capture_output=True, text=True).stdout.strip() if pr else ""
        if pr is None or state.get("merge_fails") or (expected and expected != head_now):
            code = 1
            sys.stderr.write("merge refused" + chr(10))
        else:
            if state.get("merge_queues"):
                state["queued"] = state.get("queued", 0) + 1  # success reply, PR stays OPEN (merge queue)
                pr["head_oid"] = head_now
            else:
                pr["state"], pr["mergedAt"], pr["head_oid"] = "MERGED", "2026-01-01T00:00:00Z", head_now
            if state.get("retarget_on_merge"):
                pr["base"] = state["retarget_on_merge"]
    elif argv[:2] == ["pr", "checks"]:
        seq = state["checks_sequence"]
        current = seq.pop(0) if len(seq) > 1 else seq[0]
        mapping = {"success": "SUCCESS", "failure": "FAILURE", "pending": "PENDING"}
        out = json.dumps([{"name": "ci", "state": mapping.get(current, current), "link": "", "workflow": "Validate"}])
        code = 0 if current == "success" else 1
    elif argv[:2] == ["run", "list"]:
        commit = argv[argv.index("--commit") + 1] if "--commit" in argv else ""
        out = json.dumps([{"databaseId": 6, "conclusion": "failure", "status": "completed", "headSha": "0" * 40},
                          {"databaseId": 7, "conclusion": "failure", "status": "completed", "headSha": commit}])
    elif argv[:2] == ["run", "view"]:
        out = state["failed_log"]
    elif argv[:2] == ["run", "rerun"]:
        state["reruns"] = state.get("reruns", 0) + 1
    elif len(argv) > 0 and argv[0] == "api":
        endpoint = argv[1] if len(argv) > 1 else ""
        clean_endpoint = endpoint.lstrip("/")
        if clean_endpoint in {f"apps/{TEST_FIXTURE_APP_SLUG}", "app"}:
            out = json.dumps({
                "id": TEST_FIXTURE_APP_ID,
                "slug": TEST_FIXTURE_APP_SLUG,
                "name": "ThingLab Merge Authority",
                "public_keys": {TEST_FIXTURE_KEY_ID: TEST_FIXTURE_PUBLIC_KEY.hex()},
            })
            code = 0
        else:
            out = json.dumps({"message": "Not Found", "status": "404"})
            code = 1
    else:
        code = 2
        sys.stderr.write("unsupported fake gh call\n")
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
