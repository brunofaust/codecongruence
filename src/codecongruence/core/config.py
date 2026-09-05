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

import fnmatch
import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DEFAULT_CACHE_TTL_DAYS",
    "DEFAULT_EMBED_BATCH_SIZE",
    "DEFAULT_MODEL",
    "STRIP_PATTERN_FLAGS",
    "CodeCongruenceConfig",
    "RuleConfig",
    "StripRules",
    "compile_path_globs",
    "compile_strip_patterns",
    "compile_strip_rules",
    "default_config_path",
    "discover_config_path",
    "load_config",
    "scope_path",
]

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

# Texts per ONNX inference call. Peak RSS scales with the largest single batch
# (padded to the longest sequence), and ONNX Runtime's memory arena keeps that
# high-water mark for the life of the process: fastembed's default of 256 peaks
# at ~5.7 GB on realistic function bodies, 16 peaks at ~0.9 GB with no
# measurable throughput cost.
DEFAULT_EMBED_BATCH_SIZE = 16

DEFAULT_CACHE_TTL_DAYS = 30

# ``^``/``$`` anchor per line, which is what a line-oriented boilerplate pattern
# expects. Multi-line frames opt in with an inline ``(?s)``.
STRIP_PATTERN_FLAGS = re.MULTILINE


@cache
def compile_strip_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile ``strip_before_compare`` patterns once per distinct pattern set.

    Config owns the compile so the same call both validates at load time and
    serves the runtime, and a rule pays the compile cost once per run rather
    than once per compared pair.

    Args:
        patterns: Regular expression sources, as a hashable tuple.

    Returns:
        The compiled patterns, in the given order.

    Raises:
        ValueError: If a pattern is not a valid regular expression. The message
            names the offending pattern.
    """
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, STRIP_PATTERN_FLAGS))
        except re.error as exc:
            msg = f"invalid strip_before_compare regular expression {pattern!r}: {exc}"
            raise ValueError(msg) from exc
    return tuple(compiled)


@cache
def compile_path_globs(globs: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile file globs to anchored regexes, once per distinct glob set.

    Globs use :mod:`fnmatch` semantics — the same dialect the runner already
    applies to ``exclude`` and ``exclude_functions``, so this project has one
    notion of a glob rather than two. ``*`` crosses ``/``, which is why both
    ``tests/**/a*.py`` and ``tests/*/a*.py`` match a nested ``tests/x/ab.py``.
    Matching is case-sensitive and always against a repo-relative POSIX path.

    Args:
        globs: File glob sources, as a hashable tuple.

    Returns:
        The compiled globs, in the given order.

    Raises:
        ValueError: If a glob is blank, absolute, or does not translate to a
            valid pattern. The message names the offending glob.
    """
    compiled: list[re.Pattern[str]] = []
    for glob in globs:
        if not glob.strip():
            msg = f"invalid strip scope file glob {glob!r}: the glob is empty"
            raise ValueError(msg)
        if glob.startswith("/") or (len(glob) > 1 and glob[1] == ":"):
            msg = (
                f"invalid strip scope file glob {glob!r}: globs match repo-relative "
                "paths, so an absolute glob can never match"
            )
            raise ValueError(msg)
        try:
            compiled.append(re.compile(fnmatch.translate(glob)))
        except re.error as exc:
            msg = f"invalid strip scope file glob {glob!r}: {exc}"
            raise ValueError(msg) from exc
    return tuple(compiled)


def scope_path(path: Path, repo_root: Path) -> str:
    """Return the repo-relative POSIX path that strip scopes match against.

    Anchoring on the repo root rather than the process working directory is
    what makes a glob behave the same whether the CLI runs from the root or a
    subdirectory. A file outside the repo root keeps its own POSIX path.

    Args:
        path: The file path as the rule knows it (repo-relative, per
            :class:`~codecongruence.core.git.ChangedFile`, or absolute).
        repo_root: The repository root the path is relative to.

    Returns:
        The path scopes match, using ``/`` separators.
    """
    try:
        return (repo_root / path).resolve().relative_to(repo_root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


@dataclass(frozen=True, slots=True)
class StripRules:
    """Compiled ``strip_before_compare`` patterns and the scopes they apply to."""

    everywhere: tuple[re.Pattern[str], ...]
    by_path: tuple[tuple[re.Pattern[str], tuple[re.Pattern[str], ...]], ...]
    by_symbol: tuple[tuple[re.Pattern[str], tuple[re.Pattern[str], ...]], ...]

    def __bool__(self) -> bool:
        """True when any pattern is configured.

        Returns:
            ``False`` for the default, empty configuration.
        """
        return bool(self.everywhere or self.by_path or self.by_symbol)

    def patterns_for(self, path: str, symbol: str) -> tuple[re.Pattern[str], ...]:
        """Return every pattern that applies to one function.

        Scopes compose: the result is the union of the global patterns and
        every matching path and symbol scope, in configuration order.

        Args:
            path: Repo-relative POSIX path from :func:`scope_path`.
            symbol: The function's simple name.

        Returns:
            The patterns to strip from that function's body.
        """
        patterns = list(self.everywhere)
        patterns.extend(
            pattern for glob, scoped in self.by_path if glob.match(path) for pattern in scoped
        )
        patterns.extend(
            pattern for name, scoped in self.by_symbol if name.search(symbol) for pattern in scoped
        )
        return tuple(patterns)


@cache
def compile_strip_rules(
    everywhere: tuple[str, ...],
    by_path: tuple[tuple[str, tuple[str, ...]], ...],
    by_symbol: tuple[tuple[str, tuple[str, ...]], ...],
) -> StripRules:
    """Compile every strip pattern and scope key once per distinct configuration.

    Propagates the :class:`ValueError` raised by :func:`compile_strip_patterns`
    or :func:`compile_path_globs` for an invalid value, which is what makes a
    bad pattern or glob fail at config load rather than mid-run.

    Args:
        everywhere: Unscoped patterns.
        by_path: ``(file glob, patterns)`` pairs, in configuration order.
        by_symbol: ``(symbol-name regex, patterns)`` pairs, in configuration order.

    Returns:
        The compiled rules, ready to resolve per function.
    """
    return StripRules(
        everywhere=compile_strip_patterns(everywhere),
        by_path=tuple(
            (compile_path_globs((glob,))[0], compile_strip_patterns(patterns))
            for glob, patterns in by_path
        ),
        by_symbol=tuple(
            (compile_strip_patterns((name,))[0], compile_strip_patterns(patterns))
            for name, patterns in by_symbol
        ),
    )


class RuleConfig(BaseModel):
    """Per-rule configuration. Unknown keys are preserved as ``extras``."""

    model_config = ConfigDict(extra="allow", frozen=True)

    enabled: bool = True
    threshold: float | None = None
    exclude: list[str] = Field(default_factory=list)
    exclude_functions: list[str] = Field(default_factory=list)
    # Regular expressions removed from both sides before similarity is computed.
    # Declared fields rather than config extras so an invalid pattern or glob
    # fails at config load with the offending value in the message. They are
    # general options for the similarity rules; only C003 reads them today.
    # The scoped forms are keyed tables so a reader can always tell a path glob
    # from a symbol regex by the table it sits in, never by guessing the key.
    strip_before_compare: list[str] = Field(default_factory=list)
    strip_before_compare_by_path: dict[str, list[str]] = Field(default_factory=dict)
    strip_before_compare_by_symbol: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_strip_before_compare(self) -> RuleConfig:
        """Reject an unparsable pattern or glob at config load rather than mid-run.

        Returns:
            The unchanged config once every pattern and glob compiles.
        """
        self.strip_rules()
        return self

    def strip_rules(self) -> StripRules:
        """Return the compiled strip patterns for this rule.

        Backed by an :func:`~functools.cache`d compile, so repeated calls
        within a run — validation, then execution — share one compilation.

        Returns:
            The compiled global and scoped patterns.
        """
        return compile_strip_rules(
            tuple(self.strip_before_compare),
            tuple((glob, tuple(pats)) for glob, pats in self.strip_before_compare_by_path.items()),
            tuple(
                (name, tuple(pats)) for name, pats in self.strip_before_compare_by_symbol.items()
            ),
        )

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

    model: str = DEFAULT_MODEL
    parallel: bool = True
    threads: int | None = None
    embed_batch_size: int = Field(
        default=DEFAULT_EMBED_BATCH_SIZE,
        ge=1,
        description="Max texts per ONNX inference call; caps peak activation memory",
    )
    cache_ttl_days: int = Field(
        default=DEFAULT_CACHE_TTL_DAYS,
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

    # Absent keys fall back to the model's field defaults — the single source of
    # truth — instead of restating each default literal here.
    payload = {key: value for key, value in section.items() if key != "rules"}
    payload["rules"] = rules
    payload["repo_root"] = root
    payload["source"] = cfg_path
    return CodeCongruenceConfig.model_validate(payload)
