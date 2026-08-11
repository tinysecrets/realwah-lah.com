import os
import subprocess
import tempfile
from pathlib import Path
import requests
import logging

logger = logging.getLogger(__name__)

OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip()
OPENROUTER_URL = os.environ.get('OPENROUTER_API_URL', 'https://api.openrouter.ai/v1/chat/completions')
REPO_ROOT = Path(__file__).resolve().parents[2]


def call_openrouter_system(prompt: str) -> str:
    """Call OpenRouter (simple chat completion). Returns text response or raises."""
    if not OPENROUTER_KEY:
        raise RuntimeError('OPENROUTER_API_KEY not configured')
    headers = {
        'Authorization': f'Bearer {OPENROUTER_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': os.environ.get('OPENROUTER_MODEL', 'gpt-4o-mini'),
        'messages': [
            {'role': 'system', 'content': 'You are a secure code assistant. Given a precise edit request and repository context, produce a unified diff (git patch) that makes the requested change without destabilizing the app. Respond ONLY with the patch wrapped in ```diff\n...``` or plain unified diff.'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 2000
    }
    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    j = resp.json()
    # OpenRouter's response shape may vary; try common paths
    try:
        text = j['choices'][0]['message']['content']
    except Exception:
        # fallback: stringify entire json
        text = str(j)
    return text


def run_shell(cmd: str, cwd: Path | str = REPO_ROOT) -> tuple[int, str]:
    logger.info(f"Running: {cmd}")
    p = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True)
    out = (p.stdout or '') + (p.stderr or '')
    return p.returncode, out


def apply_patch_and_create_pr(patch_text: str, pr_title: str, pr_body: str = "Automated change from Telegram bridge") -> dict:
    """Apply a unified diff patch in a safe branch, run builds/tests, then create a PR with gh CLI.
    Returns details dict with keys: success(bool), branch, commit, build_ok(bool), tests_ok(bool), pr_url(optional)
    """
    result = {"success": False, "branch": None, "commit": None, "build_ok": False, "tests_ok": False, "pr_url": None}

    # sanitize and create branch
    safe_suffix = ''.join(c for c in pr_title if c.isalnum() or c in ('-', '_')).lower()[:40]
    branch = f'tg-edit/{safe_suffix}-{os.getpid()}'
    result['branch'] = branch

    # create temp file for patch
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tf:
        tf.write(patch_text)
        tf.flush()
        patch_file = tf.name

    # create branch
    code, out = run_shell(f'git checkout -b {branch} --quiet')
    if code != 0:
        # try to create branch via git switch
        code, out = run_shell(f'git switch -c {branch}')
    if code != 0:
        result['error'] = f'Failed to create branch: {out}'
        logger.error(result['error'])
        return result

    # apply patch
    code, out = run_shell(f'git apply --index "{patch_file}"')
    if code != 0:
        # attempt git apply without index
        code2, out2 = run_shell(f'git apply "{patch_file}"')
        if code2 != 0:
            result['error'] = f'Patch apply failed: {out} | {out2}'
            logger.error(result['error'])
            # abort branch
            run_shell(f'git switch -')
            run_shell(f'git branch -D {branch}')
            return result
    # commit
    code, out = run_shell(f'git add -A && git commit -m "{pr_title}" --quiet')
    if code != 0:
        # maybe no changes
        result['error'] = f'Commit failed: {out}'
        logger.error(result['error'])
        run_shell(f'git switch -')
        run_shell(f'git branch -D {branch}')
        return result

    # record commit id
    code, out = run_shell('git rev-parse --short HEAD')
    commit = out.strip()
    result['commit'] = commit

    # run frontend build (if present)
    build_cmd = os.environ.get('BRIDGE_BUILD_CMD', 'yarn build --silent')
    code, out = run_shell(build_cmd)
    result['build_ok'] = (code == 0)
    result['build_output'] = out
    if not result['build_ok']:
        logger.warning('Build failed on branch; preserving branch for review')
        # push branch for review anyway
    # run backend tests (optional)
    test_cmd = os.environ.get('BRIDGE_TEST_CMD', 'pytest -q')
    code, out = run_shell(test_cmd)
    result['tests_ok'] = (code == 0)
    result['tests_output'] = out

    # push branch
    push_cmd = f'git push --set-upstream origin {branch} --quiet'
    code, out = run_shell(push_cmd)
    if code != 0:
        # still continue; user may run pushes manually
        logger.warning(f'Push failed: {out}')

    # create PR via gh
    pr_url = None
    gh_cmd = f'gh pr create --title "{pr_title}" --body "{pr_body}\n\nAutomated bridge edit." --base main --head {branch} --repo {os.environ.get("GITHUB_REPO") or ""} '
    code, out = run_shell(gh_cmd)
    if code == 0:
        # try to parse URL (gh prints it)
        pr_url = out.strip().splitlines()[-1]
        result['pr_url'] = pr_url
    else:
        logger.warning(f'gh pr create failed: {out}')

    result['success'] = True
    return result


if __name__ == '__main__':
    print('agent_bridge module - intended to be imported by scripts or the server')    headers = {
        'Authorization': f'Bearer {OPENROUTER_KEY}',
        'Content-Type': 'application/json'
    }import os
import subprocess
import tempfile
from pathlib import Path
import requests
import logging

logger = logging.getLogger(__name__)

OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip()
OPENROUTER_URL = os.environ.get('OPENROUTER_API_URL', 'https://api.openrouter.ai/v1/chat/completions')
REPO_ROOT = Path(__file__).resolve().parents[2]


def call_openrouter_system(prompt: str) -> str:
    """Call OpenRouter (simple chat completion). Returns text response or raises."""
    if not OPENROUTER_KEY:
        raise RuntimeError('OPENROUTER_API_KEY not configured')
    headers = {
        'Authorization': f'Bearer {OPENROUTER_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': os.environ.get('OPENROUTER_MODEL', 'gpt-4o-mini'),
        'messages': [
            {'role': 'system', 'content': 'You are a secure code assistant. Given a precise edit request and repository context, produce a unified diff (git patch) that makes the requested change without destabilizing the app. Respond ONLY with the patch wrapped in ```diff\n...``` or plain unified diff.'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 2000
    }
    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    j = resp.json()
    # OpenRouter's response shape may vary; try common paths
    try:
        text = j['choices'][0]['message']['content']
    except Exception:
        # fallback: stringify entire json
        text = str(j)
    return text


def run_shell(cmd: str, cwd: Path | str = REPO_ROOT) -> tuple[int, str]:
    logger.info(f"Running: {cmd}")
    p = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True)
    out = (p.stdout or '') + (p.stderr or '')
    return p.returncode, out


def apply_patch_and_create_pr(patch_text: str, pr_title: str, pr_body: str = "Automated change from Telegram bridge") -> dict:
    """Apply a unified diff patch in a safe branch, run builds/tests, then create a PR with gh CLI.
    Returns details dict with keys: success(bool), branch, commit, build_ok(bool), tests_ok(bool), pr_url(optional)
    """
    result = {"success": False, "branch": None, "commit": None, "build_ok": False, "tests_ok": False, "pr_url": None}

    # sanitize and create branch
    safe_suffix = ''.join(c for c in pr_title if c.isalnum() or c in ('-', '_')).lower()[:40]
    branch = f'tg-edit/{safe_suffix}-{os.getpid()}'
    result['branch'] = branch

    # create temp file for patch
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tf:
        tf.write(patch_text)
        tf.flush()
        patch_file = tf.name

    # create branch
    code, out = run_shell(f'git checkout -b {branch} --quiet')
    if code != 0:
        # try to create branch via git switch
        code, out = run_shell(f'git switch -c {branch}')
    if code != 0:
        result['error'] = f'Failed to create branch: {out}'
        logger.error(result['error'])
        return result

    # apply patch
    code, out = run_shell(f'git apply --index "{patch_file}"')
    if code != 0:
        # attempt git apply without index
        code2, out2 = run_shell(f'git apply "{patch_file}"')
        if code2 != 0:
            result['error'] = f'Patch apply failed: {out} | {out2}'
            logger.error(result['error'])
            # abort branch
            run_shell(f'git switch -')
            run_shell(f'git branch -D {branch}')
            return result
    # commit
    code, out = run_shell(f'git add -A && git commit -m "{pr_title}" --quiet')
    if code != 0:
        # maybe no changes
        result['error'] = f'Commit failed: {out}'
        logger.error(result['error'])
        run_shell(f'git switch -')
        run_shell(f'git branch -D {branch}')
        return result

    # record commit id
    code, out = run_shell('git rev-parse --short HEAD')
    commit = out.strip()
    result['commit'] = commit

    # run frontend build (if present)
    build_cmd = os.environ.get('BRIDGE_BUILD_CMD', 'yarn build --silent')
    code, out = run_shell(build_cmd)
    result['build_ok'] = (code == 0)
    result['build_output'] = out
    if not result['build_ok']:
        logger.warning('Build failed on branch; preserving branch for review')
        # push branch for review anyway
    # run backend tests (optional)
    test_cmd = os.environ.get('BRIDGE_TEST_CMD', 'pytest -q')
    code, out = run_shell(test_cmd)
    result['tests_ok'] = (code == 0)
    result['tests_output'] = out

    # push branch
    push_cmd = f'git push --set-upstream origin {branch} --quiet'
    code, out = run_shell(push_cmd)
    if code != 0:
        # still continue; user may run pushes manually
        logger.warning(f'Push failed: {out}')

    # create PR via gh
    pr_url = None
    gh_cmd = f'gh pr create --title "{pr_title}" --body "{pr_body}\n\nAutomated bridge edit." --base main --head {branch} --repo {os.environ.get("GITHUB_REPO") or ""} '
    code, out = run_shell(gh_cmd)
    if code == 0:
        # try to parse URL (gh prints it)
        pr_url = out.strip().splitlines()[-1]
        result['pr_url'] = pr_url
    else:
        logger.warning(f'gh pr create failed: {out}')

    result['success'] = True
    return result


if __name__ == '__main__':
    print('agent_bridge module - intended to be imported by scripts or the server')
