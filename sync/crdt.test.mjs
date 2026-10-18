import test from "node:test";
import assert from "node:assert/strict";
import * as Y from "yjs";
import { transform, decode, encode } from "./crdt.mjs";
test("Arabic/emoji relative anchors survive insertions before the reviewed range", () => {
  const original = transform({
    action: "template",
    text: "# اختبار\n🙂 سبب الخلل واضح",
  });
  const anchors = transform({
    state: original.state,
    action: "anchor",
    expected_text: "الخلل",
  });
  const doc = decode(original.state);
  doc.getXmlFragment("default").get(1).get(0).insert(0, "English prefix ");
  const value = transform({
    state: encode(doc),
    action: "apply",
    expected_text: "الخلل",
    replacement: "العطل",
    from_anchor: anchors.from_anchor,
    to_anchor: anchors.to_anchor,
  });
  assert.equal(value.stale, undefined);
  assert.ok(value.text.includes("English prefix 🙂 سبب العطل واضح"));
});
test("changed anchored text is stale and no replacement is produced", () => {
  const original = transform({
    action: "template",
    text: "Original reviewed text",
  });
  const anchors = transform({
    state: original.state,
    action: "anchor",
    expected_text: "reviewed",
  });
  const doc = decode(original.state);
  doc.getXmlFragment("default").get(0).get(0).delete(9, 8);
  const result = transform({
    state: encode(doc),
    action: "apply",
    expected_text: "reviewed",
    replacement: "changed",
    ...{ from_anchor: anchors.from_anchor, to_anchor: anchors.to_anchor },
  });
  assert.deepEqual(result, { stale: true });
});
test("restore creates a new mergeable update without altering the saved snapshot", () => {
  const prior = transform({ action: "template", text: "Prior version" }),
    current = transform({ action: "template", text: "Current version" });
  const restored = transform({
    state: current.state,
    action: "restore",
    previous: prior.state,
  });
  assert.equal(restored.text, "Prior version");
  const reader = decode(current.state);
  Y.applyUpdate(reader, Buffer.from(restored.state, "base64"));
  assert.equal(transform({ state: encode(reader) }).text, "Prior version");
  assert.equal(transform({ state: prior.state }).text, "Prior version");
});
test("unsupported embedded nodes and malformed binary updates are rejected", () => {
  const doc = new Y.Doc(),
    script = new Y.XmlElement("script");
  doc.getXmlFragment("default").insert(0, [script]);
  assert.throws(() => transform({ state: encode(doc) }));
  assert.throws(() =>
    transform({ state: Buffer.from("invalid").toString("base64") }),
  );
});
