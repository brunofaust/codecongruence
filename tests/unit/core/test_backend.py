"""Backend resolution matrix, explicit-mlx errors, and config/CLI precedence."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from codecongruence.cli import app, make_embedder
from codecongruence.core import backend as backend_module
from codecongruence.core.backend import (
    MLX_MODEL_MAP,
    BackendUnavailableError,
    resolve_backend,
)
from codecongruence.core.config import BackendRequest, CodeCongruenceConfig, load_config
from tests.conftest import base_git_env

if TYPE_CHECKING:
    from pathlib import Path

MAPPED_MODEL = "BAAI/bge-small-en-v1.5"
UNMAPPED_MODEL = "some-org/unmapped-model"


def pretend(monkeypatch: pytest.MonkeyPatch, *, apple: bool, installed: bool) -> None:
    monkeypatch.setattr(backend_module, "is_apple_silicon", lambda: apple)
    monkeypatch.setattr(backend_module, "mlx_installed", lambda: installed)


@pytest.mark.parametrize(
    ("requested", "apple", "installed", "mapped"),
    list(itertools.product(["auto", "mlx", "onnx"], [True, False], [True, False], [True, False])),
)
def test_resolution_matrix(
    monkeypatch: pytest.MonkeyPatch,
    requested: BackendRequest,
    apple: bool,
    installed: bool,
    mapped: bool,
) -> None:
    pretend(monkeypatch, apple=apple, installed=installed)
    model = MAPPED_MODEL if mapped else UNMAPPED_MODEL
    mlx_possible = apple and installed and mapped

    if requested == "mlx" and not mlx_possible:
        with pytest.raises(BackendUnavailableError):
            resolve_backend(requested, model)
        return

    resolved = resolve_backend(requested, model)
    if requested == "onnx":
        assert (resolved.kind, resolved.reason) == ("onnx", None)
    elif mlx_possible:
        assert resolved.kind == "mlx"
        assert resolved.mlx_repo == MLX_MODEL_MAP[MAPPED_MODEL]
        assert resolved.reason is None
    else:
        assert resolved.kind == "onnx"
        assert resolved.reason is not None
        assert resolved.reason.startswith("auto: ")


@pytest.mark.parametrize(
    ("apple", "installed", "model", "needle"),
    [
        (False, True, MAPPED_MODEL, "Apple Silicon"),
        (True, False, MAPPED_MODEL, "codecongruence[mlx]"),
        (True, True, UNMAPPED_MODEL, "MLX_MODEL_MAP"),
    ],
)
def test_explicit_mlx_error_names_the_unmet_requirement(
    monkeypatch: pytest.MonkeyPatch, apple: bool, installed: bool, model: str, needle: str
) -> None:
    pretend(monkeypatch, apple=apple, installed=installed)
    with pytest.raises(BackendUnavailableError, match="unavailable") as excinfo:
        resolve_backend("mlx", model)
    assert needle in str(excinfo.value)


def test_unmapped_model_error_names_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    pretend(monkeypatch, apple=True, installed=True)
    with pytest.raises(BackendUnavailableError) as excinfo:
        resolve_backend("mlx", UNMAPPED_MODEL)
    assert UNMAPPED_MODEL in str(excinfo.value)


def test_auto_fallback_lists_every_unmet_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    pretend(monkeypatch, apple=False, installed=False)
    resolved = resolve_backend("auto", UNMAPPED_MODEL)
    assert resolved.reason is not None
    assert resolved.reason.count(";") == 2
    assert resolved.describe().startswith("onnx (auto: ")


def test_config_defaults_to_auto_and_parses_backend(tmp_path: Path) -> None:
    assert load_config(repo_root=tmp_path).backend == "auto"
    (tmp_path / "codecongruence.toml").write_text('[codecongruence]\nbackend = "onnx"\n')
    assert load_config(repo_root=tmp_path).backend == "onnx"


def test_config_rejects_unknown_backend(tmp_path: Path) -> None:
    (tmp_path / "codecongruence.toml").write_text('[codecongruence]\nbackend = "cuda"\n')
    with pytest.raises(ValueError, match="backend"):
        load_config(repo_root=tmp_path)


def test_pyproject_section_carries_backend(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.codecongruence]\nbackend = "mlx"\n')
    assert load_config(repo_root=tmp_path).backend == "mlx"


async def test_flag_overrides_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pretend(monkeypatch, apple=True, installed=True)
    config = CodeCongruenceConfig(backend="onnx", repo_root=tmp_path)
    assert (await make_embedder(config, tmp_path)).resolved.kind == "onnx"
    assert (await make_embedder(config, tmp_path, "mlx")).resolved.kind == "mlx"


async def test_flag_cannot_hide_an_unsatisfiable_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pretend(monkeypatch, apple=False, installed=False)
    config = CodeCongruenceConfig(backend="mlx", repo_root=tmp_path)
    with pytest.raises(BackendUnavailableError):
        await make_embedder(config, tmp_path)
    assert (await make_embedder(config, tmp_path, "onnx")).resolved.kind == "onnx"


def init_repo(path: Path) -> None:
    env = {
        **base_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True, env=env)


def test_cli_explicit_mlx_unavailable_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pretend(monkeypatch, apple=False, installed=False)
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["--backend", "mlx"])
    assert result.exit_code == 2
    assert "unavailable" in result.stderr


def test_cli_prints_backend_once_and_json_records_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pretend(monkeypatch, apple=False, installed=False)
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", os.fspath(tmp_path))
    result = CliRunner().invoke(app, ["--backend", "auto", "--format", "json"])
    assert result.exit_code == 0
    assert result.stderr.count("embedding backend: onnx (auto:") == 1
    payload = json.loads(result.stdout)
    assert payload["backend"] == "onnx"
    assert payload["backend_reason"].startswith("auto: ")
