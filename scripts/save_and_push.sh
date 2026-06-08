#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

message="${1:-Auto-save workspace}"

git add -A

if git diff --cached --quiet; then
  echo "No changes to save."
else
  git commit -m "${message}"
fi

branch="$(git branch --show-current)"
git push origin "${branch}"

echo "Saved and pushed ${branch}."
