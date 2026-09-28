import shutil
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _pytest(cwd, *targets):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets],
                          cwd=cwd, capture_output=True, text=True, env={"PYTHONPATH": str(cwd), "PATH": ""}).returncode


def _copy(tmp_path, variant=None):
    shutil.copytree(FIXTURES / "fix_repo", tmp_path / "repo")
    if variant:
        shutil.copytree(FIXTURES / "fix_repo_variants" / variant, tmp_path / "repo", dirs_exist_ok=True)
    return tmp_path / "repo"


def test_fixture_tests_pass_but_hidden_test_catches_the_bug(tmp_path):
    repo = _copy(tmp_path)
    assert _pytest(repo) == 0
    assert _pytest(repo, str(FIXTURES / "fix_repo_hidden_test.py")) != 0


def test_tests_fail_variant_adds_a_failing_test_and_keeps_the_rest(tmp_path):
    repo = _copy(tmp_path, "tests_fail")
    assert (repo / "tests" / "test_referral.py").exists()
    assert _pytest(repo, "tests/test_referral.py", "tests/test_money.py") == 0
    assert _pytest(repo) != 0


def test_fixing_the_bug_makes_the_hidden_test_pass(tmp_path):
    repo = _copy(tmp_path)
    source = repo / "rewards" / "referral.py"
    source.write_text(source.read_text().replace(
        "    return round(order.price * REFERRAL_RATE)",
        "    if order.is_gift:\n        return 0\n    return round(order.price * REFERRAL_RATE)"))
    assert _pytest(repo, str(FIXTURES / "fix_repo_hidden_test.py")) == 0
