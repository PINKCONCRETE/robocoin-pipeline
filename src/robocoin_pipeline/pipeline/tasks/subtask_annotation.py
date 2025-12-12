import time
from logging import Logger, getLogger
from pathlib import Path

from robocoin_pipeline.pipeline.tasks.task_registry import (
    register_single_input_field_task,
)


@register_single_input_field_task
def subtask_annotation(
    repo_path: str | Path,
    input_field: str,
    output_field: str,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    """模拟Subtask Annotation任务"""
    logger.info("Begin running subtask_annotation")
    time.sleep(2)
    logger.info("Finished running subtask_annotation")
