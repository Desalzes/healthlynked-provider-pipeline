from pathlib import Path
import subprocess

import pytest


def test_showcase_fixture_files_are_git_visible():
    pp_root = Path(__file__).resolve().parents[1]
    # Works whether this project sits inside the monorepo (prefix
    # "comps/provider-pipeline/") or is published as a standalone repo (no prefix):
    # find the enclosing git checkout and compute the path prefix from it.
    repo = next((p for p in (pp_root, *pp_root.parents) if (p / ".git").exists()), None)
    if repo is None:
        pytest.skip("git visibility check only applies inside a repository checkout")
    rel = pp_root.relative_to(repo).as_posix()
    prefix = "" if rel == "." else rel + "/"
    paths = [prefix + p for p in (
        "provider_pipeline/sources/board.py",
        "provider_pipeline/review_queue.py",
        "scripts/make_review_queue.py",
        "data/fixtures/board/SHOW-MOVE.json",
        "data/fixtures/npi/4444444444.json",
        "data/fixtures/snippets/SHOW-MOVE.json",
        "data/fixtures/websites/SHOW-MOVE.html",
        "tests/test_sponsor_contract.py",
        "tests/test_review_queue.py",
    )]

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
