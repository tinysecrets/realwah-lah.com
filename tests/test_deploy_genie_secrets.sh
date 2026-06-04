#!/usr/bin/env bash
# Tests for deploy-genie-secrets.sh
#
# Scope: Covers the two validation checks removed in the PR:
#   1. FLY_API_TOKEN presence check  (was: exit 1 if unset/empty)
#   2. ADMIN_EMAIL length check       (was: exit 1 if < 5 chars)
#
# No external testing framework required — runs as a standalone bash script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/deploy-genie-secrets.sh"

PASS=0
FAIL=0

# ── Helpers ─────────────────────────────────────────────────────────────────

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; (( FAIL++ )) || true; }

assert_exits_ok() {
  local label="$1"; shift
  if env "$@" bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1; then
    pass "$label"
  else
    fail "$label (expected exit 0, got non-zero)"
  fi
}

assert_exits_error() {
  local label="$1"; shift
  if ! env "$@" bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1; then
    pass "$label"
  else
    fail "$label (expected non-zero exit, got 0)"
  fi
}

assert_output_contains() {
  local label="$1"
  local pattern="$2"
  shift 2
  local output
  output=$(env "$@" bash "$SCRIPT_UNDER_TEST" 2>&1 || true)
  if echo "$output" | grep -qF "$pattern"; then
    pass "$label"
  else
    fail "$label (pattern '$pattern' not found in output)"
  fi
}

assert_output_not_contains() {
  local label="$1"
  local pattern="$2"
  shift 2
  local output
  output=$(env "$@" bash "$SCRIPT_UNDER_TEST" 2>&1 || true)
  if echo "$output" | grep -qF "$pattern"; then
    fail "$label (unexpected pattern '$pattern' found in output)"
  else
    pass "$label"
  fi
}

# ── Test fixture ─────────────────────────────────────────────────────────────
# Provides a temporary directory with a fake flyctl that succeeds silently.

FAKE_FLYCTL_DIR="$(mktemp -d)"
trap 'rm -rf "$FAKE_FLYCTL_DIR"' EXIT

cat > "$FAKE_FLYCTL_DIR/flyctl" <<'FLYCTL_EOF'
#!/usr/bin/env bash
# Fake flyctl: accepts any subcommand, prints minimal output, exits 0.
case "${1:-}" in
  secrets)
    case "${2:-}" in
      set)  echo "Setting secrets on app" ;;
      list) echo "NAME  DIGEST  CREATED_AT" ;;
    esac
    ;;
esac
exit 0
FLYCTL_EOF
chmod +x "$FAKE_FLYCTL_DIR/flyctl"

# Base environment variables satisfying all require_secret() calls in the script.
# Values are non-placeholder and meet minimum length requirements.
BASE_ENV=(
  "PATH=$FAKE_FLYCTL_DIR:$PATH"
  "GENIE_JWT_SECRET=this-is-a-sufficiently-long-jwt-secret-value-32ch"
  "GENIE_ADMIN_EMAIL=admin@example.com"
  "GENIE_ADMIN_PASSWORD=securepassword123456"
  "MONGO_URL=mongodb://localhost:27017/db"
)

# ── Tests: FLY_API_TOKEN validation removed ──────────────────────────────────

echo ""
echo "=== deploy-genie-secrets.sh tests ==="
echo ""
echo "--- FLY_API_TOKEN validation removed ---"

# The old check exited 1 when FLY_API_TOKEN was unset. After the PR removal it
# must not cause any failure.
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is unset" \
  "${BASE_ENV[@]}"

# Explicitly empty FLY_API_TOKEN must also be accepted.
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is explicitly empty" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN="

# The old error message must never appear when the token is absent.
assert_output_not_contains \
  "no 'FLY_API_TOKEN is not set' error when token absent" \
  "FLY_API_TOKEN is not set" \
  "${BASE_ENV[@]}"

# Regression: a valid token must still be accepted (no inadvertent inversion).
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is set to a valid value" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN=tok_test_abc123"

# Boundary: token with only whitespace — previously would have triggered error;
# now must also pass through without complaint.
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is whitespace-only" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN=   "

assert_output_not_contains \
  "no FLY_API_TOKEN error message when token is whitespace" \
  "FLY_API_TOKEN" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN=   "

# ── Tests: ADMIN_EMAIL length validation removed ─────────────────────────────

echo ""
echo "--- ADMIN_EMAIL length validation removed ---"

# The removed check tested the legacy ADMIN_EMAIL variable (not GENIE_ADMIN_EMAIL).
# After removal, any value of ADMIN_EMAIL must be accepted.

# Single character — was blocked by the old >= 5 length requirement.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is 1 character" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=a"

# 4 characters — right at the old boundary (< 5 was blocked).
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is 4 characters" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=user"

# Empty string — was previously allowed only when unset; now explicitly empty.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is empty" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL="

# Exactly 5 characters — was the old minimum passing length; must still pass.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is exactly 5 characters" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=admin"

# Verify the old error message is never emitted.
assert_output_not_contains \
  "no 'ADMIN_EMAIL is too short' error for 2-char value" \
  "ADMIN_EMAIL is too short" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=hi"

assert_output_not_contains \
  "no 'ADMIN_EMAIL is too short' error for empty value" \
  "ADMIN_EMAIL is too short" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL="

# Boundary regression: 3-char value — old check would have rejected this.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is 3 characters" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=foo"

# ── Tests: CEREBRAS optional block (adjacent to removed code) ────────────────

echo ""
echo "--- CEREBRAS_API_KEY optional block (adjacent to removed code) ---"

# When CEREBRAS_API_KEY is set the block should add it to SECRET_ARGS.
CEREBRAS_OUTPUT=$(env "${BASE_ENV[@]}" \
  CEREBRAS_API_KEY=test-cerebras-key \
  CEREBRAS_MODEL=qwen-3-235b \
  bash "$SCRIPT_UNDER_TEST" 2>&1 || true)

if echo "$CEREBRAS_OUTPUT" | grep -qi "Setting"; then
  pass "script reports setting secrets when CEREBRAS_API_KEY provided"
else
  fail "script did not report setting secrets when CEREBRAS_API_KEY provided"
fi

# When CEREBRAS_API_KEY is absent the optional block should be skipped silently.
assert_exits_ok \
  "script succeeds when CEREBRAS_API_KEY is absent" \
  "${BASE_ENV[@]}"

# CEREBRAS block should work regardless of FLY_API_TOKEN presence.
assert_exits_ok \
  "script succeeds with CEREBRAS_API_KEY set and FLY_API_TOKEN unset" \
  "${BASE_ENV[@]}" \
  "CEREBRAS_API_KEY=cerebras-key-value" \
  "CEREBRAS_MODEL=qwen-3-235b"

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo ""

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
