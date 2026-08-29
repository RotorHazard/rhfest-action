# RHFest rules

This document is the canonical catalog of RHFest validation rules. Rule codes
are part of RHFest's public output and must not be reassigned to another meaning.

## Rule families

- `STRxxx` — repository and plugin structure
- `MANxxx` — `manifest.json` loading and validation
- `RHxxx` — reserved for future RotorHazard-specific Python rules

## Structure rules

### STR001 — Custom plugins entry

Require a `custom_plugins` entry at the repository root.

### STR002 — Single plugin entry

Require exactly one entry below `custom_plugins`.

### STR003 — Manifest file

Require `manifest.json` below the discovered plugin entry.

## Manifest rules

### MAN001 — Manifest schema

Validate all required and optional fields and formats with the manifest schema.
One invalid manifest can produce multiple `MAN001` diagnostics. Extra fields are
rejected.

The dormant `zip_release` custom validation is not enabled. `zip_release`
therefore remains an extra manifest key under the active schema.

### MAN002 — Manifest domain

Require the manifest `domain` to match the name of its parent folder.

## Diagnostic output

Every diagnostic contains a stable code, severity, message, family, and optional
repository-relative path, one-based source range, and help text.

Local output follows the Ruff/ty full-diagnostic layout, including ANSI color on
interactive terminals, source ranges, and help text when available:

```text
error: MAN002 Manifest domain 'other' does not match folder 'example'.
 --> custom_plugins/example/manifest.json:2:3
  |
2 |   "domain": "other",
  |   ^^^^^^^^
  |
help: Change the manifest domain to 'example'.
```

On GitHub Actions, the same information is emitted as workflow-command metadata:

```text
::error title=rhfest (MAN002),file=custom_plugins/example/manifest.json,line=2,col=3,endLine=2,endColumn=11::custom_plugins/example/manifest.json:2:3: MAN002 Manifest domain 'other' does not match folder 'example'.%0A  help: Change the manifest domain to 'example'.
```

`NO_COLOR` disables local ANSI styling. Non-interactive output is uncolored
automatically.

## Adding a rule

1. Add a `Rule` subclass in `rhfest/rules.py` with a new stable code, family,
   phase, and order.
2. Declare required context values as a `frozenset` of typed `Capability`
   members in `requires`. Use `ValidationContext` for shared discovery data
   instead of another rule instance.
3. Return `Diagnostic` values from `check()`; do not log or exit from a rule.
4. Register the rule in `DEFAULT_RULES`.
5. Document its stable code in this catalog.
6. Add focused engine, rule, reporter, and outcome tests as appropriate.

Structure errors prevent the manifest phase from running. Invalid JSON and
file-read errors retain their existing exception behavior; the rule-engine
migration does not define a new recovery policy for them.

## Engine contract

The engine validates its complete registry before analyzing a repository. It
rejects malformed or duplicate codes, unknown phases, family/phase conflicts,
non-integer order values, and prerequisites that are not typed `Capability`
members. A rule is also prevented from emitting a diagnostic under another
rule's code or family.

Phases and their success dependencies are declarative:

| Phase | Family | Requires successful phase |
| --- | --- | --- |
| `structure` | `STRxxx` | — |
| `manifest` | `MANxxx` | `structure` |
| `source` | `RHxxx` | `structure` |

The reserved `source` phase is independent of manifest policy. A future Python
source rule can therefore run when repository discovery succeeds, even if
`manifest.json` contains a schema or domain error.

Future diagnostic selection or ignore behavior must filter collected
diagnostics rather than blindly skipping prerequisite analysis. Context
discovery must remain available to dependent rules even when a prerequisite
rule's own diagnostic is not selected for display.
