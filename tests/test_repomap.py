from pathlib import Path
from understand.repomap import build_repo_map


def test_build_repo_map_lists_functions(tmp_path):
    (tmp_path / "foo.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n"
    )
    result = build_repo_map(tmp_path)
    assert "foo.py" in result
    assert "greet" in result


def test_build_repo_map_lists_classes(tmp_path):
    (tmp_path / "bar.py").write_text(
        "class Supervisor:\n    def run(self): pass\n"
    )
    result = build_repo_map(tmp_path)
    assert "Supervisor" in result
    assert "run" in result


def test_build_repo_map_skips_venv(tmp_path):
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "hidden.py").write_text("def secret(): pass\n")
    (tmp_path / "real.py").write_text("def visible(): pass\n")
    result = build_repo_map(tmp_path)
    assert "secret" not in result
    assert "visible" in result


def test_build_repo_map_skips_test_files(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_foo.py").write_text("def test_something(): pass\n")
    (tmp_path / "src.py").write_text("def real_fn(): pass\n")
    result = build_repo_map(tmp_path)
    assert "test_something" not in result
    assert "real_fn" in result


def test_build_repo_map_handles_syntax_error(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n")
    (tmp_path / "ok.py").write_text("def fine(): pass\n")
    result = build_repo_map(tmp_path)
    assert "fine" in result


def test_build_repo_map_empty_repo(tmp_path):
    result = build_repo_map(tmp_path)
    assert result == "" or isinstance(result, str)
