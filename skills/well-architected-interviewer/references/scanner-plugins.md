# Scanner Plugins

Optional scanner plugins are invoked by name when present on PATH.

Proposed adapters:
- semgrep: run with a default config or repo-local config; capture JSON output.
- trivy: run filesystem scan; capture JSON output.

Plugins must be optional. If missing, the tool should skip and note in evidence.json.
