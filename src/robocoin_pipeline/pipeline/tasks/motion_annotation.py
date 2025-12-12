import time
from logging import Logger, getLogger
from pathlib import Path

from .task_registry import register_single_input_field_task


@register_single_input_field_task()
def motion_annotation(
    repo_path: str | Path,
    in_field: set[str],
    out_field: str,
    config: dict,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    """模拟Motion Annotation任务"""
    logger.info("Begin running motion_annotation")
    time.sleep(2)
    logger.info("Finished running motion_annotation")
