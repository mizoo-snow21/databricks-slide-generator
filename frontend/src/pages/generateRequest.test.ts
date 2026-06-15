import { resolveQuestions } from "./generateRequest";

/** Same behavior as `assert.equal` from `node:assert` (no @types/node in project). */
function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}

// Case 1: selected only — trimmed, order preserved
assertEqual(resolveQuestions(["  Revenue trend?  ", "Top customers"], []), [
  "Revenue trend?",
  "Top customers",
]);

// Case 2: selected + added, duplicate across lists, empty/whitespace dropped
assertEqual(
  resolveQuestions(["Q1", "  Q2  ", ""], ["Q2", "  ", "Q3"]),
  ["Q1", "Q2", "Q3"],
);

// Case 3: all empty
assertEqual(resolveQuestions(["", "   "], ["", "\t"]), []);

console.log("All assertions passed");
