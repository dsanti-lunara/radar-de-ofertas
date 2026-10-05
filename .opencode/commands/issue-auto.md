---
description: Manually inspect and implement one GitHub Issue with the issue-runner agent
agent: issue-runner
model: opencode-go/deepseek-v4.1-flash
---

Implement GitHub Issue #$1 in the current repository.

Fetch and read the complete issue, including comments, with GitHub CLI before making changes:

!`gh issue view $1 --comments`

This slash command is intended for manual/debug execution only. Do not mutate GitHub labels, close the issue, commit, or push. Follow the issue-runner contract exactly.
