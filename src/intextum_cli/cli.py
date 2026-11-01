"""Command-line entry point and error reporting."""

from __future__ import annotations

import logging
import os
import sys
import warnings

from .cli_parser import build_parser
from .commands import CommandError
from .commands.extract import cmd_extract
from .commands.schemas import cmd_check_schemas
from .commands.workspace import cmd_convert, cmd_export, cmd_verify, cmd_view
from .review_state import ReviewConflict
from .store import StorageError


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        # Docling, OCR engines and model loaders log, warn and draw progress bars
        # through their own handlers; problems that matter end up in the results.
        logging.disable(logging.WARNING)
        warnings.filterwarnings("ignore")
        os.environ.setdefault("TQDM_DISABLE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    handlers = {
        "extract": cmd_extract,
        "view": cmd_view,
        "convert": cmd_convert,
        "export": cmd_export,
        "verify": cmd_verify,
        "check-schemas": cmd_check_schemas,
    }
    try:
        return handlers[args.command](args)
    except (CommandError, StorageError, OSError, ReviewConflict) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
