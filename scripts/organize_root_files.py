#!/usr/bin/env python3
"""Move loose root files into their architectural folders.

The rules are intentionally name-based and conservative: deployment/runtime
entrypoints stay at the repository root, while loose docs, diagnostics, and
manual tests move into existing project areas.
"""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]

MOVE_RULES = {
    "render.yaml": Path("infra/render.yaml"),
    "run_new.sh": Path("scripts/run_local.sh"),
    "DEPLOY.md": Path("docs/deployment/DEPLOY.md"),
    "DEPLOYMENT_STATUS.md": Path("docs/deployment/DEPLOYMENT_STATUS.md"),
    "FINAL-SETUP.md": Path("docs/setup/FINAL-SETUP.md"),
    "PERSONA-SETUP.md": Path("docs/setup/PERSONA-SETUP.md"),
    "FEATURES_IMPLEMENTED.md": Path("docs/features/FEATURES_IMPLEMENTED.md"),
    "FULL_SYSTEM_AUDIT.md": Path("docs/audits/FULL_SYSTEM_AUDIT.md"),
    "design_guidelines.md": Path("docs/design/design_guidelines.md"),
    "design_guidelines.json": Path("docs/design/design_guidelines.json"),
    "firtrequirements.txt": Path("docs/requirements/firtrequirements.txt"),
    "test_result.md": Path("test_reports/manual/test_result.md"),
    "backend_test.py": Path("tests/manual/backend_test.py"),
    "simple_backend_test.py": Path("tests/manual/simple_backend_test.py"),
    "debug_admin_auth.py": Path("tests/manual/debug_admin_auth.py"),
}


def move_file(source_name: str, destination: Path) -> str:
    source = ROOT / source_name
    target = ROOT / destination

    if target.exists():
        return f"already organized: {destination}"

    if not source.exists():
        return f"skip missing: {source_name}"

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return f"moved: {source_name} -> {destination}"


def main() -> int:
    for source_name, destination in MOVE_RULES.items():
        print(move_file(source_name, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
