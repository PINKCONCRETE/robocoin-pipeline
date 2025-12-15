import time
from logging import Logger, getLogger
from pathlib import Path

from robocoin_pipeline.pipeline.tasks.task_registry import (
    register_multi_input_fields_task,
)


@register_multi_input_fields_task()
def data_merge(
    repo_path: str | Path,
    in_fields: set[str],
    out_field: str,
    logger: Logger | None = None,
) -> str:
    if logger is None:
        logger = getLogger(__name__)
    """模拟Data Merge任务"""
    logger.info("Begin running data_merge")
    time.sleep(2)
