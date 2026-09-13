const fs = require("fs");
const path = require("path");

const SCRATCH_DIR = "/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t024-review";
const Ajv2020 = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv/dist/2020");
const addFormats = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv-formats");

const ajv = new Ajv2020({ allErrors: true });
addFormats(ajv);

const schema = JSON.parse(fs.readFileSync("/Users/albertiano/thinglab/tl-orchestrator/schemas/review-result.schema.json", "utf-8"));
let raw = "";

const stdoutFile = path.join(SCRATCH_DIR, "checker-stdout.txt");
const lastMsgFile = path.join(SCRATCH_DIR, "checker-last.txt");

if (fs.existsSync(stdoutFile)) {
  raw = fs.readFileSync(stdoutFile, "utf-8").trim();
}

if (!raw && fs.existsSync(lastMsgFile)) {
  raw = fs.readFileSync(lastMsgFile, "utf-8").trim();
}

if (!raw) {
  console.error("ERROR: No output found in checker-stdout.txt or checker-last.txt");
  process.exit(1);
}

// Strip markdown fences if present
if (raw.startsWith("```json")) {
  raw = raw.replace(/^```json\s*/, "").replace(/\s*```$/, "");
} else if (raw.startsWith("```")) {
  raw = raw.replace(/^```\s*/, "").replace(/\s*```$/, "");
}

// Extract JSON substring
const firstBrace = raw.indexOf("{");
const lastBrace = raw.lastIndexOf("}");
if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
  raw = raw.substring(firstBrace, lastBrace + 1);
}

let data;
try {
  data = JSON.parse(raw);
} catch (e) {
  console.error("JSON parse error:", e.message);
  console.error("Raw content:", raw);
  process.exit(1);
}

const validate = ajv.compile(schema);
const valid = validate(data);

console.log("AJV Draft 2020-12 validation result for Checker T024 review r01:", valid);
if (!valid) {
  console.error("Validation errors:", JSON.stringify(validate.errors, null, 2));
  process.exit(1);
} else {
  console.log("SUCCESS: Checker T024 review r01 JSON strictly valid under Draft 2020-12!");
  console.log("Verdict:", data.verdict);
  console.log("Action items count:", data.action_items ? data.action_items.length : 0);
  console.log("Deferred count:", data.deferred ? data.deferred.length : 0);
  console.log("Rejected count:", data.rejected ? data.rejected.length : 0);
  const outFile = path.join(SCRATCH_DIR, "review-result.json");
  fs.writeFileSync(outFile, JSON.stringify(data, null, 2), "utf-8");
  console.log("Saved review result to:", outFile);
  process.exit(0);
}
