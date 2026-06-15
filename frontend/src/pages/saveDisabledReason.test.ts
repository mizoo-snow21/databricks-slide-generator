import { saveDisabledReason } from "./adminTemplatePayload";

/** Same behavior as `assert.equal` from `node:assert` (no @types/node in project). */
function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
}

// empty name -> name message
{
  const reason = saveDisabledReason({
    name: "",
    googleSlidesTemplateId: "",
    hasPptx: false,
  });
  assertEqual(reason, "Enter a template name to save.");
}

// whitespace-only name -> name message (locks the trim contract)
{
  const reason = saveDisabledReason({
    name: "   ",
    googleSlidesTemplateId: "abc123",
    hasPptx: false,
  });
  assertEqual(reason, "Enter a template name to save.");
}

// name present + no id + no pptx -> id/pptx message
{
  const reason = saveDisabledReason({
    name: "My Template",
    googleSlidesTemplateId: "",
    hasPptx: false,
  });
  assertEqual(
    reason,
    "Add a Google Slides Template ID above, or upload a PPTX, to save.",
  );
}

// name + id -> null
{
  const reason = saveDisabledReason({
    name: "My Template",
    googleSlidesTemplateId: "abc123",
    hasPptx: false,
  });
  assertEqual(reason, null);
}

// name + pptx (hasPptx true, no id) -> null
{
  const reason = saveDisabledReason({
    name: "My Template",
    googleSlidesTemplateId: "",
    hasPptx: true,
  });
  assertEqual(reason, null);
}

console.log("All assertions passed");
