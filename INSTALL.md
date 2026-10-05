# OpenCode GitHub Issue Runner

Target: OpenCode 2.0.23+ using `opencode-go/deepseek-v4.1-flash`.

GitHub Issues are the source of truth. There is no local issue backlog directory.

## 1. Copy into the repository root

Expected layout:

```text
project/
├── .git/
├── .opencode/
│   ├── agents/
│   │   └── issue-runner.md
│   └── commands/
│       └── issue-auto.md
├── scripts/
│   ├── doctor-github-issues.sh
│   └── run-github-issues.sh
├── .env.opencode.example
└── .gitignore.opencode-issues
```

Do not replace an existing `.gitignore`. Copy the lines from `.gitignore.opencode-issues` into your project's `.gitignore`.

## 2. Create local configuration

```bash
cp .env.opencode.example .env.opencode
chmod +x scripts/doctor-github-issues.sh scripts/run-github-issues.sh
```

`.env.opencode` is intentionally ignored and should not be committed.

`GITHUB_REPO` may be left empty when the local Git repository points at the correct GitHub repository. The runner auto-detects `OWNER/REPO` through GitHub CLI.

## 3. Authenticate prerequisites

```bash
gh auth login
opencode auth login
```

Confirm:

```bash
gh auth status
opencode models | grep 'opencode-go/deepseek-v4.1-flash'
```

## 4. Run the doctor

```bash
./scripts/doctor-github-issues.sh
```

The runner can automatically create these labels:

- `ready-for-agent`
- `agent-running`
- `agent-done`
- `agent-blocked`

## 5. Queue issues

Add `ready-for-agent` to any open GitHub Issue you want the agent to implement.

Queue flow:

```text
ready-for-agent
    ↓
agent-running
    ↓
agent-done
```

On failure:

```text
agent-running
    ↓
agent-blocked
```

To retry a blocked issue, remove `agent-blocked` and add `ready-for-agent` again.

## 6. Dry run

```bash
DRY_RUN=1 ./scripts/run-github-issues.sh
```

This resolves the repository and queue without changing labels or code.

## 7. Execute

All queued issues, sequentially:

```bash
./scripts/run-github-issues.sh
```

One explicit issue:

```bash
./scripts/run-github-issues.sh 123
```

Several explicit issues in a fixed order:

```bash
./scripts/run-github-issues.sh 123 128 131
```

Explicit issue numbers do not need the `ready-for-agent` label, but the issue must be open. `agent-done` issues are skipped unless `FORCE=1`.

Retry explicitly:

```bash
FORCE=1 ./scripts/run-github-issues.sh 123
```

## Safe mode vs full automation

The default `.env.opencode.example` uses:

```bash
AUTO_COMMIT=1
AUTO_PUSH=0
AUTO_CLOSE_ISSUE=0
AUTO_COMMENT=1
```

This creates one deterministic local commit per successful issue and writes the result back to GitHub, but it does not push or close the issue.

For end-to-end automation:

```bash
AUTO_PUSH=1
AUTO_CLOSE_ISSUE=1
```

The runner intentionally refuses `AUTO_CLOSE_ISSUE=1` with `AUTO_PUSH=0`, because closing a GitHub Issue before its implementation reaches the remote repository produces a false completed state.

## What success means

The agent must return an explicit `AUTOMATION_RESULT: DONE` contract. The runner then verifies:

1. OpenCode exited successfully.
2. A DONE contract exists.
3. The agent did not switch branches.
4. The agent did not create commits itself.
5. Repository changes actually exist.
6. `git diff --check` passes.
7. The runner creates the issue commit.
8. Optional push succeeds.
9. GitHub status/comment is updated.
10. Optional issue closing happens only after the previous steps.

Missing final text is treated as a failure, not success. This matters for DeepSeek V4.1 Flash because intermittent reasoning-only/empty final responses have been reported in recent OpenCode builds.

## Logs

Local logs:

```text
.scratch/opencode-auto-logs/
```

Issue snapshots passed to OpenCode:

```text
.scratch/opencode-issue-context/
```

Both should remain ignored by Git.

## Manual OpenCode command

For debugging inside the OpenCode TUI:

```text
/issue-auto 123
```

This is intentionally not the full queue automation. It does not manage GitHub labels, commits, pushes, or issue closing. Use `scripts/run-github-issues.sh` for the automated workflow.
