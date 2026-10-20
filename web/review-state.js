(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ReviewState = factory();
  }
})(globalThis, function () {
  "use strict";

  const STORAGE_KEY = "measurement-review-notes-v1";

  function recordKey(result) {
    if (!result || !result.domain || !result.sha256 || !result.analysis_version || !result.decision_key) {
      return "";
    }
    return [result.domain, result.sha256, result.analysis_version, result.decision_key].join(":");
  }

  function read(storage) {
    try {
      const value = JSON.parse(storage.getItem(STORAGE_KEY) || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_error) {
      return {};
    }
  }

  function get(result, storage) {
    const key = recordKey(result);
    return key ? read(storage).byKey?.[key] || null : null;
  }

  function remember(result, decision, note, storage, candidate = null) {
    const key = recordKey(result);
    if (!key || !["use", "hold"].includes(decision)) return false;
    const saved = read(storage);
    saved.byKey = saved.byKey || {};
    saved.byKey[key] = {
      key,
      domain: result.domain,
      filename: result.filename,
      sha256: result.sha256,
      analysisVersion: result.analysis_version,
      decision,
      candidate,
      note: String(note || "").trim().slice(0, 240),
      updatedAt: new Date().toISOString(),
    };
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(saved));
      return true;
    } catch (_error) {
      return false;
    }
  }

  function clear(storage) {
    try {
      storage.removeItem(STORAGE_KEY);
      return true;
    } catch (_error) {
      return false;
    }
  }

  function count(storage) {
    return Object.keys(read(storage).byKey || {}).length;
  }

  return { STORAGE_KEY, recordKey, get, remember, clear, count };
});
