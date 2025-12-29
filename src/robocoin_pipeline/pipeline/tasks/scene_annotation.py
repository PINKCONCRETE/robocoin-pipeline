import time
from logging import Logger, getLogger
from pathlib import Path

from robocoin_pipeline.pipeline.tasks.task_registry import (
    register_single_input_field_task,
)


@register_single_input_field_task()
def scene_annotation(
    repo_path: str | Path,
    input_field: str,
    output_field: str,
    config: dict,
    logger: Logger | None = None,
) -> None:
    if logger is None:
        logger = getLogger(__name__)
    """模拟Scene Annotation任务"""
    logger.info("Begin running scene_annotation")
    time.sleep(2)
    logger.info("Finished running scene_annotation")
