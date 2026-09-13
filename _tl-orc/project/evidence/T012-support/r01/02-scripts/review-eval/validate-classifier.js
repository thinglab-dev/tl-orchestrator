const fs = require("fs");
const Ajv2020 = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv/dist/2020");
const addFormats = require("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/review-classifier-pref/node_modules/ajv-formats");

const ajv = new Ajv2020({ allErrors: true });
addFormats(ajv);

const schema = JSON.parse(fs.readFileSync("/Users/albertiano/thinglab/tl-orchestrator/schemas/classification-result.schema.json", "utf-8"));
let raw = fs.readFileSync("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/review-eval/classifier-stdout.txt", "utf-8").trim();

// Strip markdown fences if present
if (raw.startsWith("```json")) {
  raw = raw.replace(/^```json\s*/, "").replace(/\s*```$/, "");
} else if (raw.startsWith("```")) {
  raw = raw.replace(/^```\s*/, "").replace(/\s*```$/, "");
}

const data = JSON.parse(raw);

const validate = ajv.compile(schema);
const valid = validate(data);

console.log("AJV Draft 2020-12 validation result for Classifier T012 Evaluator:", valid);
if (!valid) {
  console.error("Validation errors:", validate.errors);
  process.exit(1);
} else {
  console.log("SUCCESS: Classifier T012 Evaluator JSON strictly valid under Draft 2020-12!");
  fs.writeFileSync("/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot/review-eval/classifier-output.json", JSON.stringify(data, null, 2));
}
