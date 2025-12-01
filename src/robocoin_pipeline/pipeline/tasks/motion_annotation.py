from pathlib import Path

from robocoin_pipeline.utils.file_sync import sync_files

from .task_registry import register_task


@register_task(ncpu=1, nmem=4, ngpu=0)
def motion_annotation(
    repo_path: str | Path,
    need_ori_data: bool,
    input_features: list[str],
    output_features: list[str] | None = None,
):
    """模拟Motion Annotation任务"""
    sync_files(repo_path, need_ori_data)

    pass
