import { isValidOsdSelectMessage } from "./DeckCanvas";

/** Same behavior as `assert.equal` from `node:assert` (no @types/node in project). */
function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
}

// Valid case
assertEqual(
  isValidOsdSelectMessage({ type: "osd:select", target_id: "el-1", rect: { x: 1, y: 2, w: 3, h: 4 } }),
  true,
);

// Wrong type field
assertEqual(isValidOsdSelectMessage({ type: "osd:click", target_id: "el-1", rect: { x: 1, y: 2, w: 3, h: 4 } }), false);

// Missing target_id
assertEqual(isValidOsdSelectMessage({ type: "osd:select", rect: { x: 1, y: 2, w: 3, h: 4 } }), false);

// rect as a string (the original bug — would have been accepted by `data.rect && ...`)
assertEqual(isValidOsdSelectMessage({ type: "osd:select", target_id: "el-1", rect: "haha" }), false);

// rect with non-numeric fields
assertEqual(isValidOsdSelectMessage({ type: "osd:select", target_id: "el-1", rect: { x: "1", y: 2, w: 3, h: 4 } }), false);

// null / non-object
assertEqual(isValidOsdSelectMessage(null), false);
assertEqual(isValidOsdSelectMessage(undefined), false);
assertEqual(isValidOsdSelectMessage("string"), false);

console.log("All assertions passed");
