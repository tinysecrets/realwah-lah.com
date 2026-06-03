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

# Print a test result line and update counters.
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
# Provides a temporary directory with a fake flyctl that succeeds silently,
# and exports the minimum required secrets so require_secret() calls pass.

setup_fixture() {
  local tmpdir
  tmpdir="$(mktemp -d)"

  # Fake flyctl — accepts any arguments, exits 0.
  cat > "$tmpdir/flyctl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$tmpdir/flyctl"

  echo "$tmpdir"
}

# Base env vars that satisfy all require_secret() calls.
# Values are long enough and contain no placeholder patterns.
BASE_ENV=(
  "PATH=$(setup_fixture):$PATH"
  "GENIE_JWT_SECRET=this-is-a-sufficiently-long-jwt-secret-value-32chars"
  "GENIE_ADMIN_EMAIL=admin@example.com"
  "GENIE_ADMIN_PASSWORD=securepassword123456"
  "MONGO_URL=mongodb://localhost:27017/db"
)

# ── Tests ────────────────────────────────────────────────────────────────────

echo ""
echo "=== deploy-genie-secrets.sh tests ==="
echo ""

echo "--- FLY_API_TOKEN validation removed ---"

# Previously the script would exit 1 when FLY_API_TOKEN was unset.
# After the PR, it should proceed past that point without error.
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is unset" \
  "${BASE_ENV[@]}"

# Explicitly unset FLY_API_TOKEN — should not trigger any error.
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is explicitly empty string" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN="

# Verify the old error message is never emitted.
assert_output_not_contains \
  "no 'FLY_API_TOKEN is not set' error when token absent" \
  "FLY_API_TOKEN is not set" \
  "${BASE_ENV[@]}"

# Confirm the script still works when FLY_API_TOKEN IS provided (regression guard).
assert_exits_ok \
  "script succeeds when FLY_API_TOKEN is set to a valid value" \
  "${BASE_ENV[@]}" \
  "FLY_API_TOKEN=tok_test_abc123"

echo ""
echo "--- ADMIN_EMAIL length validation removed ---"

# Previously the script exited if ADMIN_EMAIL (old variable) was < 5 chars.
# After the PR the check is gone; the old ADMIN_EMAIL variable is irrelevant.

# 1-char ADMIN_EMAIL — old code would have exited 1.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is 1 character" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=a"

# 4-char ADMIN_EMAIL — right at the old boundary (< 5 → was blocked).
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is 4 characters" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=user"

# Empty ADMIN_EMAIL — was always ignored by old code if it happened to be empty
# and still ignored now.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is empty" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL="

# Verify the old error message is never emitted.
assert_output_not_contains \
  "no 'ADMIN_EMAIL is too short' error for short value" \
  "ADMIN_EMAIL is too short" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=hi"

# Old boundary regression: 5-char value (was the minimum that passed the old check).
# Script should also succeed for this.
assert_exits_ok \
  "script succeeds when ADMIN_EMAIL (old var) is exactly 5 characters" \
  "${BASE_ENV[@]}" \
  "ADMIN_EMAIL=admin"

echo ""
echo "--- CEREBRAS_API_KEY optional block (context lines adjacent to removed code) ---"

# When CEREBRAS_API_KEY is provided the block immediately after the removed
# checks should add it to the secrets list.
CEREBRAS_OUTPUT=$(env "${BASE_ENV[@]}" \
  CEREBRAS_API_KEY=test-cerebras-key \
  CEREBRAS_MODEL=qwen-3-235b \
  bash "$SCRIPT_UNDER_TEST" 2>&1 || true)

if echo "$CEREBRAS_OUTPUT" | grep -q "Setting [0-9]* secrets"; then
  pass "script reports setting secrets when CEREBRAS_API_KEY provided"
else
  fail "script did not report setting secrets when CEREBRAS_API_KEY provided"
fi

# When CEREBRAS_API_KEY is absent the block should be skipped (no error).
assert_exits_ok \
  "script succeeds when CEREBRAS_API_KEY is absent" \
  "${BASE_ENV[@]}"

echo ""
echo "--- require_secret() pre-existing validations still enforced ---"

# Sanity check: existing validations (not removed by this PR) still work,
# ensuring the surrounding logic was not accidentally broken.
assert_exits_error \
  "script fails when GENIE_JWT_SECRET is missing" \
  "${BASE_ENV[@]/GENIE_JWT_SECRET=*/GENIE_JWT_SECRET=}"  # clear via env override
# ↑ env array substitution won't work cleanly; use a direct approach below.

# Clear GENIE_JWT_SECRET explicitly to confirm require_secret still fires.
JWT_FAIL_EXIT=0
env "${BASE_ENV[@]}" GENIE_JWT_SECRET="" bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1 || JWT_FAIL_EXIT=$?
if [[ $JWT_FAIL_EXIT -ne 0 ]]; then
  pass "require_secret still rejects empty GENIE_JWT_SECRET"
else
  fail "require_secret did NOT reject empty GENIE_JWT_SECRET"
fi

# Placeholder value should also be rejected by require_secret.
JWT_PLACEHOLDER_EXIT=0
env "${BASE_ENV[@]}" GENIE_JWT_SECRET="REPLACE_ME" bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1 || JWT_PLACEHOLDER_EXIT=$?
if [[ $JWT_PLACEHOLDER_EXIT -ne 0 ]]; then
  pass "require_secret still rejects placeholder GENIE_JWT_SECRET"
else
  fail "require_secret did NOT reject placeholder GENIE_JWT_SECRET"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo ""

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
