#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env.opencode" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.opencode"
  set +a
fi

OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/deepseek-v4.1-flash}"
MIN_OPENCODE_VERSION="${MIN_OPENCODE_VERSION:-2.0.23}"
GITHUB_REPO="${GITHUB_REPO:-}"
READY_LABEL="${READY_LABEL:-ready-for-agent}"
RUNNING_LABEL="${RUNNING_LABEL:-agent-running}"
DONE_LABEL="${DONE_LABEL:-agent-done}"
BLOCKED_LABEL="${BLOCKED_LABEL:-agent-blocked}"

pass() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || fail "git not found"
command -v gh >/dev/null || fail "GitHub CLI (gh) not found"
command -v opencode >/dev/null || fail "opencode not found"
pass "required commands found"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not inside a Git repository"
pass "Git repository: $ROOT"

gh auth status >/dev/null 2>&1 || fail "gh is not authenticated. Run: gh auth login"
pass "GitHub CLI authenticated"

if [[ -z "$GITHUB_REPO" ]]; then
  GITHUB_REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)" || fail "unable to auto-detect GitHub repository"
fi
[[ -n "$GITHUB_REPO" ]] || fail "GITHUB_REPO is empty"
pass "GitHub repository: $GITHUB_REPO"

version_raw="$(opencode --version 2>/dev/null || true)"
version="$(printf '%s' "$version_raw" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
[[ -n "$version" ]] || fail "could not detect OpenCode version from: $version_raw"
first="$(printf '%s\n%s\n' "$MIN_OPENCODE_VERSION" "$version" | sort -V | head -n1)"
[[ "$first" == "$MIN_OPENCODE_VERSION" ]] || fail "OpenCode $version is older than required $MIN_OPENCODE_VERSION"
pass "OpenCode version: $version"

if opencode models 2>/dev/null | grep -Fxq "$OPENCODE_MODEL"; then
  pass "model available: $OPENCODE_MODEL"
else
  fail "model not listed by 'opencode models': $OPENCODE_MODEL"
fi

branch="$(git branch --show-current)"
[[ -n "$branch" ]] || fail "detached HEAD is not supported"
pass "current branch: $branch"

if [[ -n "$(git status --porcelain)" ]]; then
  warn "working tree is not clean; the runner will refuse to start"
  git status --short
else
  pass "working tree clean"
fi

labels="$(gh label list -R "$GITHUB_REPO" --limit 1000 --json name --jq '.[].name')"
for label in "$READY_LABEL" "$RUNNING_LABEL" "$DONE_LABEL" "$BLOCKED_LABEL"; do
  if grep -Fxq "$label" <<<"$labels"; then
    pass "label exists: $label"
  else
    warn "label missing: $label (runner can create it when AUTO_CREATE_LABELS=1)"
  fi
done

count="$(gh issue list -R "$GITHUB_REPO" --state open --label "$READY_LABEL" --limit 1000 --json number --jq 'length' 2>/dev/null || printf '0')"
pass "open issues queued with '$READY_LABEL': $count"

printf '\nDoctor completed.\n'
