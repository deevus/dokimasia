# Project Context

## Coding style

Prefer readability over clever DRY abstractions when they conflict.

- Write explicit, step-by-step control flow for parser and normalization logic.
- Avoid inline ternary chains and expression golf.
- Avoid resolver objects or tuple-return helpers unless they make the domain clearer.
- Accept small, local duplication when it makes behavior easier to audit.
- Use helper functions when their names expose a clear domain concept.
