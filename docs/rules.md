# RHFest rules

This document is the canonical catalog of RHFest validation rules. Rule codes
are part of RHFest's public output and must not be reassigned to another meaning.

## Rule families

- `STRxxx` — repository and plugin structure
- `MANxxx` — `manifest.json` loading and validation
- `RHxxx` — RotorHazard-specific Python source analysis

## Structure rules

### STR001 — Custom plugins entry

Require a `custom_plugins` entry at the repository root.

### STR002 — Single plugin entry

Require exactly one entry below `custom_plugins`.

### STR003 — Manifest file

Require `manifest.json` below the discovered plugin entry.

### STR004 — Plugin entry point

Require the single plugin entry to be a directory containing a regular
`__init__.py` file so RotorHazard can load it as a plugin. Plugin directories
and entry points that resolve outside the repository are rejected. Replace a
non-directory entry with a plugin directory, or add a regular `__init__.py`
file inside the existing plugin directory.

## Manifest rules

### MAN000 — Manifest parsing

Read `manifest.json` once as UTF-8 and parse it once as JSON. The source and
parsed value are retained together in `ValidationContext` for all later manifest
rules. File access, Unicode decoding, repository-boundary, and JSON syntax
failures are emitted as `MAN000` errors through the shared reporter instead of
raising an unhandled exception.

JSON syntax diagnostics include a repository-relative path and one-based source
location. `MAN001` and later manifest rules run only when MAN000 produced a
parsed manifest document. A valid JSON `null` value is therefore distinguishable
from a parsing failure and still reaches schema validation.

### MAN001 — Manifest schema

Validate all required and optional fields and formats with the manifest schema.
One invalid manifest can produce multiple `MAN001` diagnostics. Extra fields are
rejected.

The dormant `zip_release` custom validation is not enabled. `zip_release`
therefore remains an extra manifest key under the active schema.

### MAN002 — Manifest domain

Require the manifest `domain` to match the name of its parent folder.

## RotorHazard source rules

### RH000 — Python source parsing

Discover all `.py` files below the validated plugin directory in deterministic
repository-relative path order. Each file is read and parsed once with Python's
standard `ast` module, then retained in `ValidationContext` for all subsequent
`RHxxx` rules.

Unreadable UTF-8 source and Python syntax errors produce `RH000` diagnostics
through the shared reporter. A parse failure in one file does not prevent rules
from analyzing other successfully parsed files. Python files outside the
discovered plugin directory are not analyzed. A plugin directory symlink that
resolves outside the repository is rejected with `RH000` before source discovery
starts.

### RH001 — Private RHAPI access

Reject access to `_racecontext` through an RHAPI-derived expression. RotorHazard
stores its internal race context on the root API object and its public namespace
implementations, but this is an implementation detail rather than part of the
plugin API contract. See the pinned RotorHazard
[`RHAPI.py` implementation](https://github.com/RotorHazard/RotorHazard/blob/main/src/server/RHAPI.py#L29).

For example, RH001 detects all of these accesses:

```python
def initialize(rhapi):
    context = rhapi._racecontext
    database_context = rhapi.db._racecontext

    database = rhapi.db
    alias_context = database._racecontext
```

The rule recognizes parameters named `rhapi`, following RotorHazard's documented
`initialize(rhapi)` and plugin callback convention. Provenance is retained
through simple local name aliases and attribute chains. Reassignment and local
parameter shadowing invalidate an alias; conditional aliases are retained only
when every branch establishes them.

Diagnostics retain the first non-private attribute traversed from RHAPI through
aliases. For example, both `rhapi.db._racecontext` and a `database = rhapi.db`
alias report that the value originated from `rhapi.db`. This is syntactic origin
information, not a hard-coded catalog of RotorHazard namespaces, so adding or
renaming namespaces does not require an RHFest release. Root access and
control-flow paths with different possible origins receive general public-RHAPI
guidance instead of an uncertain replacement. RH001 does not offer an automatic
fix because the intended public operation cannot be inferred safely from
`_racecontext` alone.

The analysis is deliberately conservative. It does not infer provenance through
function calls, containers, imports, tuple unpacking, lambdas, or
interprocedural data flow. It does not flag unrelated objects merely because
they expose `_racecontext`, and it does not prohibit other underscore-prefixed
attributes. Comments and string literals are naturally ignored by the AST
analysis.

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

Python source rules must consume the parsed `PythonSource` values exposed through
`Capability.PYTHON_SOURCES`; they must not rediscover files or parse source a
second time. Keep provenance helpers in `rhfest/source.py` reusable when a
future rule needs the same conservative symbol knowledge.

Structure errors prevent the manifest phase from running. MAN000 converts
manifest loading and JSON parsing failures to diagnostics; later manifest rules
require its successfully prepared document.

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

The `source` phase is independent of manifest policy. Python source rules can
therefore run when repository discovery succeeds, even if
`manifest.json` contains a schema or domain error.

Future diagnostic selection or ignore behavior must filter collected
diagnostics rather than blindly skipping prerequisite analysis. Context
discovery must remain available to dependent rules even when a prerequisite
rule's own diagnostic is not selected for display.
