const fs = require("fs");
const path = require("path");

const SCRATCH_DIR = "/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t024-review";
const Ajv2020 = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv/dist/2020");
const addFormats = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv-formats");

const ajv = new Ajv2020({ allErrors: true });
addFormats(ajv);

const schema = JSON.parse(fs.readFileSync("/Users/albertiano/thinglab/tl-orchestrator/schemas/classification-result.schema.json", "utf-8"));
const rawFile = path.join(SCRATCH_DIR, "classifier-raw.txt");

if (!fs.existsSync(rawFile)) {
  console.error("ERROR: Raw file does not exist:", rawFile);
  process.exit(1);
}

let raw = fs.readFileSync(rawFile, "utf-8").trim();

if (raw.startsWith("```json")) {
  raw = raw.replace(/^```json\s*/, "").replace(/\s*```$/, "");
} else if (raw.startsWith("```")) {
  raw = raw.replace(/^```\s*/, "").replace(/\s*```$/, "");
}

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

console.log("AJV Draft 2020-12 validation result for Classifier T024 review r01:", valid);
if (!valid) {
  console.error("Validation errors:", JSON.stringify(validate.errors, null, 2));
  process.exit(1);
}

console.log("SUCCESS: Classifier T024 review r01 JSON strictly valid under Draft 2020-12!");
console.log("Story ID:", data.story_id);
console.log("Phase:", data.phase);
console.log("Roles classified:", Object.keys(data.roles));
const outFile = path.join(SCRATCH_DIR, "classifier-output.json");
fs.writeFileSync(outFile, JSON.stringify(data, null, 2), "utf-8");
console.log("Wrote validated output to:", outFile);
process.exit(0);
