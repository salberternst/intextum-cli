"""Command implementations, separate from argument parsing and dispatch."""


class CommandError(Exception):
    """An actionable command failure reported without a traceback."""
