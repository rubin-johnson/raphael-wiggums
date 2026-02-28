import json
from pathlib import Path
from typing import Optional
from execute.cost import parse_escalation, ModelTier
from understand.repomap import build_repo_map
from understand.mapper import map_module
from understand.coherence import run_coherence_gate

_SKIP_DIRS = {".venv", "__pycache__", ".git", "tests", ".raphael", "node_modules"}
_OUTPUT_DIR = ".raphael"


def run_understand(
    repo_path: Path,
    output_dir: Optional[Path] = None,
    map_model: str = "sonnet",
    escalation: Optional[list] = None,
) -> Path:
    """
    Full understand pipeline. Returns path to understanding.md.

    Stage 1: Build static repo map (ast, no LLM)
    Stage 2: Map each module (LLM, sequential)
    Stage 3+2.5: Reduce + coherence gate with retry/escalation
    """
    if escalation is None:
        escalation = parse_escalation("sonnet:2,opus:1")

    out = output_dir or (repo_path / _OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    map_dir = out / "map"
    map_dir.mkdir(exist_ok=True)

    # Stage 1: static repo map
    repo_map = build_repo_map(repo_path)
    (out / "repo_map.md").write_text(repo_map)

    # Stage 2: per-module LLM analysis
    py_files = [
        f for f in sorted(repo_path.rglob("*.py"))
        if not any(part in _SKIP_DIRS for part in f.relative_to(repo_path).parts)
    ]

    module_summaries = []
    for py_file in py_files:
        result = map_module(py_file, repo_path, repo_map=repo_map, model=map_model)
        safe_name = str(py_file.relative_to(repo_path)).replace("/", "_").replace(".py", "")
        (map_dir / f"{safe_name}.json").write_text(json.dumps(result, indent=2))
        module_summaries.append(result)

    # Stage 3 + 2.5: reduce with coherence gate
    understanding = run_coherence_gate(module_summaries, repo_map, escalation)
    understanding_path = out / "understanding.md"
    understanding_path.write_text(understanding)

    return understanding_path
