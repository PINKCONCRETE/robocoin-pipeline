import time
from logging import Logger, getLogger
from pathlib import Path

from .task_registry import register_single_input_field_task


@register_single_input_field_task()
def upload_ms(
    repo_path: str | Path,
    in_field: str,
    out_field: str,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    """模拟Upload ModelScope任务"""
    logger.info("Begin running upload_ms")
    time.sleep(2)
    logger.info("Finished running upload_ms")
