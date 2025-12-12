from logging import Logger, getLogger
from pathlib import Path


def sync_in(
    repo_path: str | Path,
    in_fields: set[str] = None,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    logger.info(f"Syncing in fields: {in_fields} of {repo_path}")
    pass


def sync_out(
    repo_path: str | Path,
    out_field: str,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    logger.info(f"Syncing out field: {out_field} to {repo_path}")
    pass
