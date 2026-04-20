from __future__ import annotations

import logging

from app.bootstrap import run_migrations_with_advisory_lock


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    _configure_logging()
    run_migrations_with_advisory_lock()


if __name__ == "__main__":
    main()
