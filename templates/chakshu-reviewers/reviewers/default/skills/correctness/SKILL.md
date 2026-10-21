---
name: correctness
description: Logic errors, unhandled cases and broken contracts in the changed code.
---

Look at what the change does, then read enough of the surrounding code to know whether it does it correctly.

Check for:

- Off-by-one errors, wrong comparisons, inverted conditions.
- Missing handling for empty, null, zero, negative or very large inputs.
- Errors that are swallowed, or exceptions that escape where callers don't expect them.
- Changes to a function's behavior that its existing callers rely on. Search for the callers.
- Async code that forgets to await, or shared state changed without a lock.
- Resources (files, connections, locks) that aren't released on every path.
- Tests that were changed to match new behavior when the behavior itself looks wrong.

Don't report a finding unless you can point to the line and explain the failure in one or two sentences.
