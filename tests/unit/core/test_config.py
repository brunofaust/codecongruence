from __future__ import annotations

from typing import TYPE_CHECKING

from codecongruence.core.config import discover_config_path, load_config

if TYPE_CHECKING:
    from pathlib import Path


def test_default_when_file_missing(tmp_path: Path) -> None:
    cfg = load_config(repo_root=tmp_path)
    assert cfg.model == "BAAI/bge-small-en-v1.5"
    assert cfg.parallel is True
    assert cfg.rules == {}
    assert cfg.rule("anything").enabled is True


def test_loads_thresholds(tmp_path: Path) -> None:
    (tmp_path / "codecongruence.toml").write_text(
        """
[codecongruence]
model = "BAAI/bge-small-en-v1.5"
parallel = false

[rules.docstring_vs_body]
enabled = true
threshold = 0.42
min_body_statement_count = 5

[rules.docs_on_change]
enabled = false
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.parallel is False
    assert cfg.rule("docstring_vs_body").threshold == 0.42
    assert cfg.rule("docstring_vs_body").enabled is True
    assert cfg.rule("docs_on_change").enabled is False
    assert cfg.enabled_rules() == ["docstring_vs_body"]


def test_loads_cache_ttl_days(tmp_path: Path) -> None:
    (tmp_path / "codecongruence.toml").write_text(
        """
[codecongruence]
cache_ttl_days = 7
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.cache_ttl_days == 7


def test_cache_ttl_days_defaults_to_30(tmp_path: Path) -> None:
    (tmp_path / "codecongruence.toml").write_text("[codecongruence]\nparallel = false\n")
    cfg = load_config(repo_root=tmp_path)
    assert cfg.cache_ttl_days == 30


def test_extras_preserved(tmp_path: Path) -> None:
    (tmp_path / "codecongruence.toml").write_text(
        """
[rules.docstring_vs_body]
enabled = true
threshold = 0.30
exclude = ["tests/**"]
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    rc = cfg.rule("docstring_vs_body")
    assert rc.exclude == ["tests/**"]


def test_loads_from_pyproject(tmp_path: Path) -> None:
    """``pyproject.toml`` with ``[tool.codecongruence]`` is a first-class config source."""
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.0.1"

[tool.codecongruence]
model = "BAAI/bge-small-en-v1.5"
parallel = false

[tool.codecongruence.rules.docstring_vs_body]
enabled = true
threshold = 0.42
min_body_statement_count = 5

[tool.codecongruence.rules.docs_on_change]
enabled = false
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.parallel is False
    assert cfg.rule("docstring_vs_body").threshold == 0.42
    assert cfg.rule("docs_on_change").enabled is False
    assert cfg.source is not None
    assert cfg.source.name == "pyproject.toml"


def test_pyproject_takes_priority_over_legacy(tmp_path: Path) -> None:
    """When both files exist, ``pyproject.toml`` wins per documented priority."""
    (tmp_path / "codecongruence.toml").write_text(
        """
[rules.docstring_vs_body]
enabled = true
threshold = 0.10
        """.strip()
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.codecongruence.rules.docstring_vs_body]
enabled = true
threshold = 0.55
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.rule("docstring_vs_body").threshold == 0.55
    assert cfg.source is not None
    assert cfg.source.name == "pyproject.toml"


def test_pyproject_without_section_falls_back_to_legacy(tmp_path: Path) -> None:
    """A pyproject.toml without ``[tool.codecongruence]`` is ignored."""
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
        """.strip()
    )
    (tmp_path / "codecongruence.toml").write_text(
        """
[rules.docstring_vs_body]
enabled = true
threshold = 0.33
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.rule("docstring_vs_body").threshold == 0.33
    assert cfg.source is not None
    assert cfg.source.name == "codecongruence.toml"


def test_explicit_pyproject_path(tmp_path: Path) -> None:
    """Explicit --config=path/to/pyproject.toml works even outside the repo root."""
    nested = tmp_path / "nested"
    nested.mkdir()
    py = nested / "pyproject.toml"
    py.write_text(
        """
[tool.codecongruence.rules.name_vs_body]
enabled = true
threshold = 0.77
        """.strip()
    )
    cfg = load_config(path=py, repo_root=tmp_path)
    assert cfg.rule("name_vs_body").threshold == 0.77


def test_discover_returns_none_when_nothing_present(tmp_path: Path) -> None:
    assert discover_config_path(tmp_path) is None


def test_rule_config_default_threshold_is_none(tmp_path: Path) -> None:
    """RuleConfig() with no threshold key must default to None, not 0.25."""
    cfg = load_config(repo_root=tmp_path)
    rc = cfg.rule("anything")
    assert rc.threshold is None


def test_section_without_threshold_key_gives_none(tmp_path: Path) -> None:
    """A rule section that sets enabled=true but omits threshold must not shadow
    the rule's own default_threshold (previously silently overrode to 0.25)."""
    (tmp_path / "codecongruence.toml").write_text(
        """
[rules.docstring_vs_body]
enabled = true
        """.strip()
    )
    cfg = load_config(repo_root=tmp_path)
    rc = cfg.rule("docstring_vs_body")
    assert rc.threshold is None
