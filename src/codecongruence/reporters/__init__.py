"""Output reporters: human-readable terminal + machine-readable JSON."""

from codecongruence.reporters.json import JsonReporter
from codecongruence.reporters.text import TextReporter

__all__ = ["JsonReporter", "TextReporter"]
