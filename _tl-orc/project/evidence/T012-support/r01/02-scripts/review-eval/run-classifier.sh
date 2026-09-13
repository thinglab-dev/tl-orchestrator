#!/usr/bin/env bash
set -e

DIR="/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/review-eval"
REPO="/Users/albertiano/thinglab/tl-orchestrator"

BRIEFING=$(cat "$DIR/classifier-briefing.md")

echo ">>> Launching Classifier Agy gemini-3.8-flash-medium..."
agy --print "$BRIEFING" \
    --model gemini-3.8-flash-medium \
    --dangerously-skip-permissions \
    < /dev/null \
    > "$DIR/classifier-stdout.txt" \
    2> "$DIR/classifier-stderr.txt"

echo ">>> Validating output with AJV Draft 2020-12..."
node "$DIR/validate-classifier.js"
