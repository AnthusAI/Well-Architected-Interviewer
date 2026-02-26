# Well-Architected Interviewer

A fork-per-audit workspace for conducting AWS Well-Architected Framework interviews with Kanbus tracking and deterministic tooling.

## Standard workflow (fork-based)

1. Fork this repo for each audited project.
2. In the fork, run `wai fetch` to download the official questions into a local cache.
3. Run `wai init --target-dir <path>` to create Kanbus initiatives/epics/tasks and `reports/<assessment>/` files.
4. Run `wai scan --target-dir <path> --assessment <slug>` and `wai apply-evidence --assessment <slug>`.
5. Conduct the interview in the coding-agent session using `wai list-unanswered` and `wai record-answer`.
6. Run `wai sync-kanbus --assessment <slug>` to post answers and close tasks.

## Attribution

AWS Well-Architected Framework content (c) Amazon.com, Inc. or its affiliates.
Licensed under Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
Source: https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
