from pathlib import Path
import subprocess

import pytest


def test_showcase_fixture_files_are_git_visible():
    repo = Path(__file__).resolve().parents[3]
    if not (repo / ".git").exists():
        pytest.skip("git visibility check only applies inside a repository checkout")
    paths = [
        "comps/provider-pipeline/provider_pipeline/sources/board.py",
        "comps/provider-pipeline/provider_pipeline/review_queue.py",
        "comps/provider-pipeline/scripts/make_review_queue.py",
        "comps/provider-pipeline/data/fixtures/board/SHOW-MOVE.json",
        "comps/provider-pipeline/data/fixtures/npi/4444444444.json",
        "comps/provider-pipeline/data/fixtures/snippets/SHOW-MOVE.json",
        "comps/provider-pipeline/data/fixtures/websites/SHOW-MOVE.html",
        "comps/provider-pipeline/tests/test_sponsor_contract.py",
        "comps/provider-pipeline/tests/test_review_queue.py",
    ]

    missing = []
    for path in paths:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=repo,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            missing.append(path)

    assert missing == []
