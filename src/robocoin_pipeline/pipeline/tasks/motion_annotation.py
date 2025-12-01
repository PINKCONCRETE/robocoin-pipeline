from .task_registry import register_task


@register_task(ncpu=1, nmem=4, ngpu=0)
def motion_annotation(
    repo_path: str, input_features: list[str], output_features: list[str]
):
    """模拟Motion Annotation任务"""
    pass
