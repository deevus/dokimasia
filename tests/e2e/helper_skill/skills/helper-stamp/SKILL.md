---
name: helper-stamp
description: Use this skill when the user asks to stamp a Dokimasia helper-skill E2E run or mentions a helper-stamp side effect.
---

# Helper Stamp

When asked to stamp a Dokimasia helper-skill E2E run, do not write the state file yourself.

Run this approved helper action exactly once:

```bash
{{HELPER_ACTION}} --run-id <run-id>
```

Replace `<run-id>` with the run id from the user request.

The helper action owns the output location and stamp format. Do not inspect or recreate its state file. After the action succeeds, reply with only `done`.
