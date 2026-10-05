#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# Values explicitly supplied by the caller (for example
# DRY_RUN=1 ./scripts/run-github-issues.sh) must win over .env.opencode.
# Capture supported overrides before sourcing the file, then restore them.
CONFIG_VARS=(
  OPENCODE_MODEL OPENCODE_AGENT MIN_OPENCODE_VERSION GITHUB_REPO
  READY_LABEL RUNNING_LABEL DONE_LABEL BLOCKED_LABEL AUTO_CREATE_LABELS
  ISSUE_LIMIT MAX_ISSUES STOP_ON_BLOCKED FORCE
  AUTO_COMMIT COMMIT_PREFIX ALLOWED_BRANCH ROLLBACK_ON_FAILURE
  AUTO_PUSH AUTO_CLOSE_ISSUE AUTO_COMMENT ALLOW_CLOSE_WITHOUT_PUSH
  DRY_RUN LOG_DIR CONTEXT_DIR
)
declare -A CALLER_OVERRIDES=()
for _name in "${CONFIG_VARS[@]}"; do
  if [[ -v "$_name" ]]; then
    CALLER_OVERRIDES["$_name"]="${!_name}"
  fi
done

if [[ -f "$ROOT/.env.opencode" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.opencode"
  set +a
fi

for _name in "${!CALLER_OVERRIDES[@]}"; do
  printf -v "$_name" '%s' "${CALLER_OVERRIDES[$_name]}"
  export "$_name"
done
unset _name

OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/deepseek-v4.1-flash}"
OPENCODE_AGENT="${OPENCODE_AGENT:-issue-runner}"
MIN_OPENCODE_VERSION="${MIN_OPENCODE_VERSION:-2.0.23}"
GITHUB_REPO="${GITHUB_REPO:-}"

READY_LABEL="${READY_LABEL:-ready-for-agent}"
RUNNING_LABEL="${RUNNING_LABEL:-agent-running}"
DONE_LABEL="${DONE_LABEL:-agent-done}"
BLOCKED_LABEL="${BLOCKED_LABEL:-agent-blocked}"
AUTO_CREATE_LABELS="${AUTO_CREATE_LABELS:-1}"

ISSUE_LIMIT="${ISSUE_LIMIT:-100}"
MAX_ISSUES="${MAX_ISSUES:-0}"
STOP_ON_BLOCKED="${STOP_ON_BLOCKED:-1}"
FORCE="${FORCE:-0}"

AUTO_COMMIT="${AUTO_COMMIT:-1}"
COMMIT_PREFIX="${COMMIT_PREFIX:-issue}"
ALLOWED_BRANCH="${ALLOWED_BRANCH:-}"
ROLLBACK_ON_FAILURE="${ROLLBACK_ON_FAILURE:-1}"
AUTO_PUSH="${AUTO_PUSH:-0}"
AUTO_CLOSE_ISSUE="${AUTO_CLOSE_ISSUE:-0}"
AUTO_COMMENT="${AUTO_COMMENT:-1}"
ALLOW_CLOSE_WITHOUT_PUSH="${ALLOW_CLOSE_WITHOUT_PUSH:-0}"

DRY_RUN="${DRY_RUN:-0}"
LOG_DIR="${LOG_DIR:-.scratch/opencode-auto-logs}"
CONTEXT_DIR="${CONTEXT_DIR:-.scratch/opencode-issue-context}"

CURRENT_ACTIVE=0
CURRENT_ISSUE=""
CURRENT_BASE=""
CURRENT_BRANCH=""
CURRENT_CONTEXT=""

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

is_true() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

rollback_repo() {
  local base="$1"
  local branch="$2"

  if ! is_true "$ROLLBACK_ON_FAILURE"; then
    warn "ROLLBACK_ON_FAILURE=0; repository changes were not reverted"
    return 0
  fi

  info "Rolling repository back to $base"
  local now_branch
  now_branch="$(git branch --show-current || true)"
  if [[ "$now_branch" != "$branch" && -n "$branch" ]]; then
    git switch "$branch" >/dev/null 2>&1 || true
  fi
  git reset --hard "$base" >/dev/null 2>&1 || true

  # Initial preflight requires a clean tree, so any non-ignored untracked file
  # now present was created during this issue run. Ignored logs/context are kept.
  while IFS= read -r -d '' path; do
    rm -rf -- "$path"
  done < <(git ls-files --others --exclude-standard -z)
}

remove_label_if_present() {
  local issue="$1"
  local label="$2"
  gh issue edit "$issue" -R "$GITHUB_REPO" --remove-label "$label" >/dev/null 2>&1 || true
}

add_label() {
  local issue="$1"
  local label="$2"
  gh issue edit "$issue" -R "$GITHUB_REPO" --add-label "$label" >/dev/null
}

mark_running() {
  local issue="$1"
  add_label "$issue" "$RUNNING_LABEL"
  remove_label_if_present "$issue" "$READY_LABEL"
  remove_label_if_present "$issue" "$DONE_LABEL"
  remove_label_if_present "$issue" "$BLOCKED_LABEL"
}

mark_done() {
  local issue="$1"
  add_label "$issue" "$DONE_LABEL"
  remove_label_if_present "$issue" "$RUNNING_LABEL"
  remove_label_if_present "$issue" "$READY_LABEL"
  remove_label_if_present "$issue" "$BLOCKED_LABEL"
}

mark_blocked() {
  local issue="$1"
  add_label "$issue" "$BLOCKED_LABEL" || true
  remove_label_if_present "$issue" "$RUNNING_LABEL"
  remove_label_if_present "$issue" "$READY_LABEL"
}

comment_file() {
  local issue="$1"
  local file="$2"
  if is_true "$AUTO_COMMENT"; then
    gh issue comment "$issue" -R "$GITHUB_REPO" --body-file "$file" >/dev/null
  fi
}

on_exit() {
  local status=$?
  if [[ "$CURRENT_ACTIVE" == "1" && -n "$CURRENT_ISSUE" ]]; then
    warn "Runner interrupted or exited unexpectedly while processing issue #$CURRENT_ISSUE"
    rollback_repo "$CURRENT_BASE" "$CURRENT_BRANCH"
    mark_blocked "$CURRENT_ISSUE" || true
    if is_true "$AUTO_COMMENT"; then
      local tmp
      tmp="$(mktemp)"
      cat > "$tmp" <<MSG
## OpenCode automation

**Status:** BLOCKED
**Model:** \`$OPENCODE_MODEL\`

The local runner exited unexpectedly while processing this issue. Repository changes from this run were rolled back when rollback was enabled.

Re-apply \`$READY_LABEL\` after investigating the runner/logs to retry.
MSG
      gh issue comment "$CURRENT_ISSUE" -R "$GITHUB_REPO" --body-file "$tmp" >/dev/null 2>&1 || true
      rm -f "$tmp"
    fi
  fi
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

preflight() {
  require_cmd git
  require_cmd gh
  require_cmd opencode
  require_cmd sort
  require_cmd grep
  require_cmd awk
  require_cmd sed

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Not inside a Git repository"
  gh auth status >/dev/null 2>&1 || die "GitHub CLI is not authenticated. Run: gh auth login"

  if [[ -z "$GITHUB_REPO" ]]; then
    GITHUB_REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)" || die "Unable to auto-detect GitHub repository. Set GITHUB_REPO in .env.opencode"
  fi
  [[ -n "$GITHUB_REPO" ]] || die "GITHUB_REPO is empty"

  local version_raw version first
  version_raw="$(opencode --version 2>/dev/null || true)"
  version="$(printf '%s' "$version_raw" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
  [[ -n "$version" ]] || die "Could not detect OpenCode version from: $version_raw"
  first="$(printf '%s\n%s\n' "$MIN_OPENCODE_VERSION" "$version" | sort -V | head -n1)"
  [[ "$first" == "$MIN_OPENCODE_VERSION" ]] || die "OpenCode $version is older than required $MIN_OPENCODE_VERSION"

  opencode models 2>/dev/null | grep -Fxq "$OPENCODE_MODEL" || die "Model not listed by 'opencode models': $OPENCODE_MODEL"

  local branch
  branch="$(git branch --show-current)"
  [[ -n "$branch" ]] || die "Detached HEAD is not supported"
  if [[ -n "$ALLOWED_BRANCH" && "$branch" != "$ALLOWED_BRANCH" ]]; then
    die "Current branch '$branch' does not match ALLOWED_BRANCH='$ALLOWED_BRANCH'"
  fi

  [[ -z "$(git status --porcelain)" ]] || {
    git status --short >&2
    die "Working tree must be clean before starting the issue runner"
  }

  if ! is_true "$AUTO_COMMIT"; then
    die "AUTO_COMMIT must remain enabled. The runner uses one deterministic commit per successful issue to prevent changes from different issues being mixed."
  fi

  if is_true "$AUTO_CLOSE_ISSUE" && ! is_true "$AUTO_PUSH" && ! is_true "$ALLOW_CLOSE_WITHOUT_PUSH"; then
    die "AUTO_CLOSE_ISSUE=1 requires AUTO_PUSH=1. Set ALLOW_CLOSE_WITHOUT_PUSH=1 only if you intentionally want to close issues before code reaches GitHub."
  fi

  mkdir -p "$LOG_DIR" "$CONTEXT_DIR"

  info "Repository: $GITHUB_REPO"
  info "OpenCode: $version"
  info "Model: $OPENCODE_MODEL"
  info "Agent: $OPENCODE_AGENT"
  info "Branch: $branch"
}

ensure_label() {
  local name="$1"
  local color="$2"
  local description="$3"

  if gh label list -R "$GITHUB_REPO" --limit 1000 --json name --jq '.[].name' | grep -Fxq "$name"; then
    return 0
  fi

  if is_true "$AUTO_CREATE_LABELS"; then
    if is_true "$DRY_RUN"; then
      info "DRY_RUN: would create label: $name"
      return 0
    fi
    info "Creating label: $name"
    gh label create "$name" -R "$GITHUB_REPO" --color "$color" --description "$description" >/dev/null
  else
    die "Required label does not exist: $name"
  fi
}

ensure_labels() {
  ensure_label "$READY_LABEL" "0E8A16" "Issue is approved for autonomous implementation"
  ensure_label "$RUNNING_LABEL" "1D76DB" "Issue is currently being processed by the OpenCode runner"
  ensure_label "$DONE_LABEL" "5319E7" "Issue implementation completed by the OpenCode runner"
  ensure_label "$BLOCKED_LABEL" "D93F0B" "Issue automation stopped and requires intervention"
}

issue_state() {
  gh issue view "$1" -R "$GITHUB_REPO" --json state --jq '.state'
}

issue_title() {
  gh issue view "$1" -R "$GITHUB_REPO" --json title --jq '.title'
}

issue_has_label() {
  local issue="$1"
  local label="$2"
  gh issue view "$issue" -R "$GITHUB_REPO" --json labels --jq '.["labels"][]?.name' 2>/dev/null | grep -Fxq "$label"
}

write_issue_context() {
  local issue="$1"
  local context_file="$2"

  {
    printf '# GitHub Issue Context\n\n'
    printf 'Repository: %s\n' "$GITHUB_REPO"
    printf 'Issue: #%s\n\n' "$issue"
    GH_PAGER=cat NO_COLOR=1 gh issue view "$issue" -R "$GITHUB_REPO" \
      --json title,body,url,author,labels,comments \
      --jq '. as $i |
        "Title: \($i.title)\nURL: \($i.url)\nAuthor: \($i.author.login)\nLabels: \([$i.labels[].name] | join(", "))\n\n## Description\n\n\($i.body // "")\n\n## Comments\n\n" +
        ([$i.comments[] | "### Comment by \(.author.login)\n\n\(.body)\n"] | join("\n"))'
  } > "$context_file"
}

extract_contract() {
  local log="$1"
  awk '
    /AUTOMATION_RESULT:/ { block=$0 ORS; capture=1; next }
    capture { block=block $0 ORS }
    END { printf "%s", block }
  ' "$log"
}

make_blocked_comment() {
  local issue="$1"
  local reason="$2"
  local contract="$3"
  local file="$4"

  cat > "$file" <<EOF_COMMENT
## OpenCode automation

**Status:** BLOCKED  
**Model:** \`$OPENCODE_MODEL\`  
**Runner reason:** $reason

### Agent report

\`\`\`text
${contract:-No valid automation contract was produced.}
\`\`\`

The runner rolled back repository changes from this issue when rollback was enabled. Re-apply \`$READY_LABEL\` after resolving the blocker to retry.
EOF_COMMENT
}

make_done_comment() {
  local issue="$1"
  local commit="$2"
  local pushed="$3"
  local contract="$4"
  local file="$5"

  cat > "$file" <<EOF_COMMENT
## OpenCode automation

**Status:** DONE  
**Model:** \`$OPENCODE_MODEL\`  
**Commit:** \`$commit\`  
**Pushed:** $pushed

### Agent report

\`\`\`text
$contract
\`\`\`
EOF_COMMENT
}

block_issue() {
  local issue="$1"
  local base="$2"
  local branch="$3"
  local reason="$4"
  local contract="${5:-}"

  warn "Issue #$issue BLOCKED: $reason"
  rollback_repo "$base" "$branch"
  mark_blocked "$issue"

  local comment
  comment="$(mktemp)"
  make_blocked_comment "$issue" "$reason" "$contract" "$comment"
  comment_file "$issue" "$comment" || warn "Failed to comment on issue #$issue"
  rm -f "$comment"

  CURRENT_ACTIVE=0

  if is_true "$STOP_ON_BLOCKED"; then
    die "Stopping because STOP_ON_BLOCKED=1"
  fi
  return 1
}

run_issue() {
  local issue="$1"

  [[ "$issue" =~ ^[0-9]+$ ]] || die "Invalid issue number: $issue"

  local state
  state="$(issue_state "$issue" 2>/dev/null || true)"
  [[ "$state" == "OPEN" ]] || {
    warn "Skipping issue #$issue because state is '${state:-unknown}'"
    return 0
  }

  if ! is_true "$FORCE" && issue_has_label "$issue" "$DONE_LABEL"; then
    warn "Skipping issue #$issue because it already has '$DONE_LABEL'. Use FORCE=1 to override."
    return 0
  fi

  local title safe_title base branch context_file log_file prompt exit_code contract
  title="$(issue_title "$issue")"
  safe_title="$(printf '%s' "$title" | tr '\n\r/' '   ' | cut -c1-100)"
  base="$(git rev-parse HEAD)"
  branch="$(git branch --show-current)"
  context_file="$CONTEXT_DIR/issue-${issue}.md"
  log_file="$LOG_DIR/issue-${issue}-$(date +%Y%m%d-%H%M%S).log"

  CURRENT_ACTIVE=1
  CURRENT_ISSUE="$issue"
  CURRENT_BASE="$base"
  CURRENT_BRANCH="$branch"
  CURRENT_CONTEXT="$context_file"

  info "============================================================"
  info "Issue #$issue: $title"
  info "Base commit: $base"

  write_issue_context "$issue" "$context_file"

  if is_true "$DRY_RUN"; then
    info "DRY_RUN=1; would process issue #$issue"
    CURRENT_ACTIVE=0
    return 0
  fi

  mark_running "$issue"

  prompt="Implement exactly GitHub Issue #$issue from the attached issue context file. Investigate the repository, load relevant project skills/instructions, make the smallest complete implementation, validate it, and finish with the required AUTOMATION_RESULT contract. Do not commit, push, switch branches, close the issue, or mutate GitHub labels."

  set +e
  # The runner already cd's to the repository root. OpenCode 2.0.23 does
  # not expose --dir on `opencode run`, so the process working directory is
  # the project context.
  NO_COLOR=1 opencode run \
    --auto \
    --agent "$OPENCODE_AGENT" \
    --model "$OPENCODE_MODEL" \
    --title "github-issue-$issue" \
    --file "$context_file" \
    "$prompt" 2>&1 | tee "$log_file"
  exit_code=${PIPESTATUS[0]}
  set -e

  contract="$(extract_contract "$log_file")"

  if [[ "$exit_code" -ne 0 ]]; then
    block_issue "$issue" "$base" "$branch" "OpenCode exited with status $exit_code" "$contract" || return 1
    return 1
  fi

  if grep -Eq 'AUTOMATION_RESULT:[[:space:]]*BLOCKED' <<<"$contract"; then
    block_issue "$issue" "$base" "$branch" "Agent reported BLOCKED" "$contract" || return 1
    return 1
  fi

  if ! grep -Eq 'AUTOMATION_RESULT:[[:space:]]*DONE' <<<"$contract"; then
    block_issue "$issue" "$base" "$branch" "No valid DONE/BLOCKED final contract was found. DeepSeek V4.1 Flash can occasionally finish without a text response, so missing output is never treated as success." "$contract" || return 1
    return 1
  fi

  local after_branch after_head
  after_branch="$(git branch --show-current || true)"
  after_head="$(git rev-parse HEAD)"

  if [[ "$after_branch" != "$branch" ]]; then
    block_issue "$issue" "$base" "$branch" "Agent changed branches from '$branch' to '${after_branch:-detached}'" "$contract" || return 1
    return 1
  fi

  if [[ "$after_head" != "$base" ]]; then
    block_issue "$issue" "$base" "$branch" "Agent created or rewrote commits. The runner owns commits for deterministic issue boundaries." "$contract" || return 1
    return 1
  fi

  if [[ -z "$(git status --porcelain)" ]]; then
    block_issue "$issue" "$base" "$branch" "Agent reported DONE but produced no repository changes" "$contract" || return 1
    return 1
  fi

  if ! git diff --check; then
    block_issue "$issue" "$base" "$branch" "git diff --check failed" "$contract" || return 1
    return 1
  fi

  local commit_hash
  git add -A
  git commit -m "$COMMIT_PREFIX #$issue: $safe_title"
  commit_hash="$(git rev-parse --short HEAD)"

  local pushed="no"
  if is_true "$AUTO_PUSH"; then
    git push
    pushed="yes"
  fi

  # From this point onward the implementation is committed, and may already be
  # on the remote. GitHub metadata failures must never roll the code back.
  CURRENT_ACTIVE=0

  if ! mark_done "$issue"; then
    die "Issue #$issue was implemented at commit $commit_hash, but GitHub labels could not be updated. Code was preserved."
  fi

  local comment
  comment="$(mktemp)"
  make_done_comment "$issue" "$commit_hash" "$pushed" "$contract" "$comment"
  if ! comment_file "$issue" "$comment"; then
    rm -f "$comment"
    die "Issue #$issue was implemented at commit $commit_hash, but the GitHub completion comment failed. Code was preserved and the issue was not auto-closed."
  fi
  rm -f "$comment"

  if is_true "$AUTO_CLOSE_ISSUE"; then
    if ! gh issue close "$issue" -R "$GITHUB_REPO" --reason completed >/dev/null; then
      die "Issue #$issue was implemented at commit $commit_hash, but GitHub could not close it. Code was preserved."
    fi
  fi

  info "Issue #$issue DONE at commit $commit_hash (pushed: $pushed)"
}

collect_issues() {
  local -n out_ref=$1
  shift

  if [[ "$#" -gt 0 ]]; then
    out_ref=("$@")
    return 0
  fi

  mapfile -t out_ref < <(
    gh issue list \
      -R "$GITHUB_REPO" \
      --state open \
      --label "$READY_LABEL" \
      --limit "$ISSUE_LIMIT" \
      --json number \
      --jq '.[].number'
  )
}

main() {
  preflight
  ensure_labels

  local issues=()
  collect_issues issues "$@"

  if [[ "${#issues[@]}" -eq 0 ]]; then
    info "No issues to process. Add '$READY_LABEL' to an open GitHub Issue or pass issue numbers explicitly."
    return 0
  fi

  info "Issues selected: ${issues[*]}"
  if is_true "$DRY_RUN"; then
    info "DRY_RUN=1; GitHub labels, repository files, commits, pushes, and issue states will not be changed."
  fi

  local processed=0 issue
  for issue in "${issues[@]}"; do
    if [[ "$MAX_ISSUES" =~ ^[0-9]+$ ]] && [[ "$MAX_ISSUES" -gt 0 ]] && [[ "$processed" -ge "$MAX_ISSUES" ]]; then
      info "MAX_ISSUES=$MAX_ISSUES reached"
      break
    fi

    if run_issue "$issue"; then
      processed=$((processed + 1))
    else
      processed=$((processed + 1))
      if is_true "$STOP_ON_BLOCKED"; then
        break
      fi
    fi
  done

  info "Finished. Processed: $processed"
}

main "$@"
