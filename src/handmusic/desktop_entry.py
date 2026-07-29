from __future__ import annotations

import sys

from handmusic.app import main as application_main
from handmusic.ui.desktop import launch_ui


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        return application_main(arguments)
    return launch_ui()


if __name__ == "__main__":
    raise SystemExit(main())
