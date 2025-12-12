import time
from logging import Logger, getLogger
from pathlib import Path

from robocoin_pipeline.pipeline.tasks.task_registry import (
    register_single_input_field_task,
)


@register_single_input_field_task()
def format_convert(
    repo_path: str | Path,
    in_field: set[str],
    out_field: str,
    logger: Logger | None = None,
) -> str:
    # """模拟format convert任务"""

    if logger is None:
        logger = getLogger(__name__)
    logger.info("Begin running format_convert")
    time.sleep(2)
    logger.info("Finished running format_convert")
