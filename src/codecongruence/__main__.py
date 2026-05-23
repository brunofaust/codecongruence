"""Entry point for `python -m codecongruence`."""

from codecongruence.cli import app

__all__ = ["app"]


if __name__ == "__main__":  # pragma: no cover
    app()
