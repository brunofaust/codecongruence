"""Installed distribution version resolution."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

__all__ = ["__version__", "resolve_version"]


def resolve_version() -> str:
    """Return the installed distribution version or an honest fallback.

    Returns:
        The installed ``codecongruence`` distribution version, or ``"unavailable"``
        when package metadata cannot supply one.
    """
    try:
        return distribution_version("codecongruence") or "unavailable"
    except PackageNotFoundError:
        return "unavailable"


__version__ = resolve_version()
