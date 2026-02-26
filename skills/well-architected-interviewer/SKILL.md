---
name: well-architected-interviewer
description: Agent skill for conducting AWS Well-Architected Framework interviews with deterministic question ingestion, Kanbus tasking, and Markdown report workflows.
---

# Well-Architected Interviewer

Use this skill to conduct AWS Well-Architected Framework interviews by generating Kanbus tasks and Markdown reports from the official AWS questions, scanning a target repo for evidence, and driving a human interview inside the agent session.

## Standard workflow (fork-based)

1. Fork this repository per audited project so Kanbus data and reports live alongside the audit artifacts.
2. From the fork, run `wai fetch` to download the official AWS questions (cached outside the repo).
3. Run `wai init --target-dir <path>` to create an assessment folder under `reports/` and create Kanbus initiative/epics/tasks.
4. Run `wai scan --target-dir <path> --assessment <slug>` to gather repo evidence.
5. Run `wai apply-evidence --assessment <slug>` to populate Evidence blocks and mark questions `partial`.
6. Use `wai list-unanswered` and `wai record-answer` to conduct the human interview in-chat and update reports.
7. Run `wai sync-kanbus --assessment <slug>` to post answers as Kanbus comments and close tasks/epics as appropriate.

## Rules

- Do not store AWS source content in the repo except in generated reports under `reports/`.
- Always include attribution blocks in report files (header and footer).
- Use Kanbus tasks for every question; do not answer without tracking.
- Use the CLI tools for deterministic parsing and updates; avoid manual edits when possible.

## Files and schema

- Cache: `~/.cache/well-architected/questions.json`
- Reports: `reports/<assessment>/index.md` and `reports/<assessment>/<pillar>.md`
- Mappings: `reports/<assessment>/kanbus-map.json`, `reports/<assessment>/evidence.json`

Each question entry in a pillar report uses this schema:

```
## <QID>: <short title>
Question: <full AWS text>
Status: unanswered|partial|answered|needs_human
Confidence: low|medium|high|n/a
Answer:
Evidence:
Human Questions:
Kanbus Task: <kanbus-id>
Last Updated: <ISO date>
```

## CLI overview

- `wai fetch [--refresh] [--cache-dir <path>]`
- `wai init --target-dir <path> [--assessment <slug>] [--reports-dir reports]`
- `wai scan --target-dir <path> --assessment <slug> [--with semgrep,trivy,...]`
- `wai apply-evidence --assessment <slug>`
- `wai list-unanswered --assessment <slug>`
- `wai record-answer --assessment <slug> --question-id <id> --status <status> --answer-file <path>`
- `wai sync-kanbus --assessment <slug>`
- `wai validate --assessment <slug>`

## Attribution

AWS Well-Architected Framework content is licensed under CC BY-SA 4.0. Reports must include attribution blocks and link back to the source page.
