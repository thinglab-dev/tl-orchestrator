#!/usr/bin/env bash
set -e

DIR="/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t024-review"
BRIEFING="$DIR/checker-briefing.md"

echo ">>> Launching Checker Codex gpt-5.6-terra high for T024 review r01 (authorized model call)..."
cd /Users/albertiano/thinglab/tl-orchestrator

codex exec \
    -s read-only \
    -m gpt-5.6-terra \
    -c 'model_reasoning_effort="high"' \
    -c 'approval_policy="never"' \
    --output-last-message "$DIR/checker-last.txt" \
    - < "$BRIEFING" \
    > "$DIR/checker-stdout.txt" \
    2> "$DIR/checker-stderr.txt"

echo ">>> Validating output with AJV Draft 2020-12..."
node "$DIR/validate-checker.js"
