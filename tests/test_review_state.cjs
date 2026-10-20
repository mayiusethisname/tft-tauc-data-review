const assert = require("node:assert/strict");
const ReviewState = require("../web/review-state.js");

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

const storage = new MemoryStorage();
const result = {
  domain: "tft",
  filename: "IGZO2004.csv",
  sha256: "aaa",
  analysis_version: "portfolio-1.0",
  decision_key: "first-config",
};

assert.equal(ReviewState.remember(result, "use", "확인 완료", storage), true);
assert.equal(ReviewState.get(result, storage).decision, "use");
assert.equal(ReviewState.count(storage), 1);

const sameNameChangedContent = { ...result, sha256: "bbb", decision_key: "changed-content" };
assert.equal(ReviewState.get(sameNameChangedContent, storage), null);

const sameContentChangedConfig = { ...result, analysis_version: "portfolio-1.1", decision_key: "new-config" };
assert.equal(ReviewState.get(sameContentChangedConfig, storage), null);
assert.equal(ReviewState.get({ ...result }, storage).note, "확인 완료");

ReviewState.clear(storage);
assert.equal(ReviewState.count(storage), 0);
process.stdout.write("REVIEW_STATE_CHECK_OK\n");
