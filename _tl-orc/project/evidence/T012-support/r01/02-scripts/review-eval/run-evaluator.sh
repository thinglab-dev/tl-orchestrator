#!/usr/bin/env bash
set -e

DIR="/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/review-eval"
REPO="/Users/albertiano/thinglab/tl-orchestrator"

BRIEFING_FILE="$DIR/evaluator-briefing.md"

echo ">>> Launching Blind Evaluator Codex gpt-5.6-terra (effort: high, read-only)..."
codex exec \
    -s read-only \
    -m gpt-5.6-terra \
    -c 'model_reasoning_effort="high"' \
    -c 'approval_policy="never"' \
    "$(cat "$BRIEFING_FILE")" \
    < /dev/null \
    > "$DIR/evaluator-stdout.txt" \
    2> "$DIR/evaluator-stderr.txt"

echo ">>> Evaluator completed with exit 0."
