"""check-secrets.sh must catch leaks and stay quiet on a clean tree.

Release-plan R5: the guard is the net that catches a real identifier
before it is committed. A guard that always passes is worse than none,
so both directions are pinned: red on a leak, green on clean.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "check-secrets.sh"


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, cwd=REPO)


def test_guard_passes_on_clean_tree():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sauber" in result.stdout


def test_guard_catches_a_planted_leak(tmp_path):
    # plant a leak in a tracked file, expect exit 1, then restore
    marker = REPO / "tests" / "_leak_probe.txt"
    pattern = next(
        line.strip()
        for line in (REPO / ".secret-patterns").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    )
    marker.write_text(f"probe {pattern}\n")
    try:
        # the probe is untracked -> git grep needs --no-index... but the
        # guard runs git grep over tracked content, so add it first
        subprocess.run(["git", "add", str(marker)], cwd=REPO, check=True)
        result = _run()
        assert result.returncode == 1
        assert "LECK" in result.stdout
    finally:
        subprocess.run(["git", "rm", "--cached", "-q", str(marker)], cwd=REPO, check=False)
        marker.unlink(missing_ok=True)
