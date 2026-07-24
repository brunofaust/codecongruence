"""Config loading from ``codecongruence.toml`` or ``pyproject.toml``.

Single source of truth for rule thresholds, model selection and path globs.
Uses Pydantic for validation; ``tomllib`` for parsing (stdlib).

Resolution order (highest priority wins):

1. Explicit path via ``--config FILE`` — auto-detects whether the file is a
   ``codecongruence.toml`` (top-level ``[codecongruence]`` section + flat
   ``[rules.*]`` sections) or a ``pyproject.toml`` (PEP 518 file with a
   ``[tool.codecongruence]`` section + ``[tool.codecongruence.rules.*]``
   sections).
2. ``pyproject.toml`` at the repo root with a ``[tool.codecongruence]``
   section — the uv/poetry-friendly modern location.
3. ``codecongruence.toml`` at the repo root — the legacy stand-alone file.
4. Built-in defaults.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CodeCongruenceConfig",
    "RuleConfig",
    "default_config_path",
    "discover_config_path",
    "load_config",
]


class RuleConfig(BaseModel):
    """Per-rule configuration. Unknown keys are preserved as ``extras``."""

    model_config = ConfigDict(extra="allow", frozen=True)

    enabled: bool = True
    threshold: float | None = None
    exclude: list[str] = Field(default_factory=list)
    exclude_functions: list[str] = Field(default_factory=list)

    def extra(self, key: str, default: Any = None) -> Any:
        """Return an unknown-but-allowed extra option from the rule config.

        Args:
            key: Attribute name to look up.
            default: Value to return when the key is absent.
        """
        return (
            getattr(self, key, default)
            if hasattr(self, key)
            else (self.__pydantic_extra__.get(key, default) if self.__pydantic_extra__ else default)
        )


class CodeCongruenceConfig(BaseModel):
    """Top-level configuration loaded from a TOML source."""

    model_config = ConfigDict(frozen=True)

    model: str = "BAAI/bge-small-en-v1.5"
    parallel: bool = True
    threads: int | None = None
    embed_batch_size: int = Field(
        default=16,
        ge=1,
        description="Max texts per ONNX inference call; caps peak activation memory",
    )
    cache_ttl_days: int = Field(
        default=30,
        description="TTL for embedding cache entries in days; 0 disables TTL eviction",
    )
    exclude: list[str] = Field(default_factory=list)
    exclude_functions: list[str] = Field(default_factory=list)
    rules: dict[str, RuleConfig] = Field(default_factory=dict)
    repo_root: Path = Field(default_factory=Path.cwd)
    source: Path | None = None

    def rule(self, rule_id: str) -> RuleConfig:
        """Return per-rule config with global excludes merged in.

        Args:
            rule_id: The rule identifier (e.g. ``"docstring_vs_body"``).

        Returns:
            A :class:`RuleConfig` combining global and per-rule exclude lists.
        """
        rc = self.rules.get(rule_id, RuleConfig())
        if not self.exclude and not self.exclude_functions:
            return rc
        merged_exclude = list(self.exclude) + list(rc.exclude)
        merged_fns = list(self.exclude_functions) + list(rc.exclude_functions)
        return rc.model_copy(update={"exclude": merged_exclude, "exclude_functions": merged_fns})

    def enabled_rules(self) -> list[str]:
        """Return IDs of enabled rules in deterministic order."""
        return sorted([name for name, rc in self.rules.items() if rc.enabled])


def default_config_path(repo_root: Path | None = None) -> Path:
    """Return the canonical stand-alone config path at the repo root.

    Args:
        repo_root: Repository root directory. Defaults to current working directory.
    """
    return (repo_root or Path.cwd()) / "codecongruence.toml"


def _pyproject_path(repo_root: Path) -> Path:
    return repo_root / "pyproject.toml"


def discover_config_path(repo_root: Path | None = None) -> Path | None:
    """Find the active config file using the documented priority order.

    Args:
        repo_root: Repository root to search. Defaults to current working directory.

    Returns:
        The config file path, or ``None`` if neither ``pyproject.toml
        [tool.codecongruence]`` nor ``codecongruence.toml`` is present.
    """
    root = (repo_root or Path.cwd()).resolve()
    pyproject = _pyproject_path(root)
    if pyproject.exists() and _has_pyproject_section(pyproject):
        return pyproject
    legacy = default_config_path(root)
    if legacy.exists():
        return legacy
    return None


def _has_pyproject_section(pyproject: Path) -> bool:
    try:
        with pyproject.open("rb") as handle:
            raw: dict[str, Any] = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = raw.get("tool", {})
    return isinstance(tool, dict) and "codecongruence" in tool


def _extract_codecongruence_section(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the ``[codecongruence]`` payload from either layout.

    - Stand-alone ``codecongruence.toml`` → ``raw["codecongruence"]`` plus
      ``raw["rules"]`` merged in under ``"rules"``.
    - ``pyproject.toml`` → ``raw["tool"]["codecongruence"]`` which already
      nests ``rules`` underneath via ``[tool.codecongruence.rules.*]``.
    """
    tool = raw.get("tool", {})
    if isinstance(tool, dict) and "codecongruence" in tool:
        # pyproject.toml layout
        section = dict(tool["codecongruence"])
        return section

    # Stand-alone layout: top-level [codecongruence] + [rules.*]
    section = dict(raw.get("codecongruence", {}))
    rules = raw.get("rules", {})
    if rules:
        existing = section.get("rules", {})
        section["rules"] = {**existing, **rules}
    return section


def load_config(path: Path | None = None, repo_root: Path | None = None) -> CodeCongruenceConfig:
    """Load configuration from a TOML file (or auto-discover) and return defaults if absent.

    Args:
        path: Explicit TOML path. Auto-detects ``codecongruence.toml`` vs
            ``pyproject.toml`` layout based on which section is present.
        repo_root: Repository root. Defaults to current working directory.

    Returns:
        A frozen :class:`CodeCongruenceConfig` ready to feed into the runner.
    """
    root = (repo_root or Path.cwd()).resolve()
    cfg_path = path if path is not None else discover_config_path(root)

    if cfg_path is None or not cfg_path.exists():
        return CodeCongruenceConfig(repo_root=root)

    with cfg_path.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    section = _extract_codecongruence_section(raw)

    rules_payload = section.get("rules", {})
    rules: dict[str, RuleConfig] = {
        name: RuleConfig.model_validate(payload) for name, payload in rules_payload.items()
    }

    return CodeCongruenceConfig(
        model=section.get("model", "BAAI/bge-small-en-v1.5"),
        parallel=section.get("parallel", True),
        threads=section.get("threads", None),
        embed_batch_size=section.get("embed_batch_size", 16),
        cache_ttl_days=section.get("cache_ttl_days", 30),
        exclude=section.get("exclude", []),
        exclude_functions=section.get("exclude_functions", []),
        rules=rules,
        repo_root=root,
        source=cfg_path,
    )
