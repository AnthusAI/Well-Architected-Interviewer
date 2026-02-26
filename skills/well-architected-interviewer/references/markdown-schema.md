# Markdown Schema

Each pillar report contains a header attribution block, followed by a list of questions.

Question entry schema:

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

The parser must preserve field order and allow multi-line values for Answer, Evidence, and Human Questions.
