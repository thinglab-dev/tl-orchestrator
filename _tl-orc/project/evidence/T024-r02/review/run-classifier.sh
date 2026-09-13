#!/usr/bin/env bash
set -e

DIR="/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t024-r02-review"
BRIEFING=$(cat "$DIR/classifier-briefing.md")

echo ">>> Launching Classifier via agy gemini-3.8-flash-medium for T024 review r02..."
cd /Users/albertiano/thinglab/tl-orchestrator

agy --dangerously-skip-permissions \
    --model gemini-3.8-flash-medium \
    -p "$BRIEFING" \
    > "$DIR/classifier-raw.txt" \
    2> "$DIR/classifier-stderr.txt"

echo ">>> Validating output with AJV Draft 2020-12..."
node "$DIR/validate-classifier.js"
