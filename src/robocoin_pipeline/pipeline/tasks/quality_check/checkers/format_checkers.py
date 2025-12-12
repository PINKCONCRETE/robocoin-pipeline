from pathlib import Path

from robocoin_pipeline.utils.paths import get_meta_info_file

from .checker_registry import register_format_checker
from .checker_result import CheckerResult


@register_format_checker()
def qc_file_structure(repo_path: str | Path) -> dict:
    repo_path = Path(repo_path).expanduser().absolute()
    result = CheckerResult()
    # todo: 实现文件结构检查逻辑，填写result.error
    result.set_errors("File structure error example.")
    return result


@register_format_checker()
def qc_info_file(repo_path: str | Path) -> dict:
    get_meta_info_file(repo_path, None)
    results = CheckerResult()
    results.set_warnings("Meta info file warning example.")


@register_format_checker()
def qc_episodes_file(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_tasks_file(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_episodes_stats_file(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_meta(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_feature_names(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_data_file_paths(repo_path: str | Path) -> dict:
    pass


@register_format_checker()
def qc_vidoe_file_paths(repo_path: str | Path) -> dict:
    pass


# 该方法由qc-pipeline调用，不需要注册器装饰器
def qc_data_file_corruption(parquet_file_path: str | Path) -> tuple[bool, dict]:
    """
    检查视频文件是否损坏的示例检查器
    """
    parquet_file_path = Path(parquet_file_path).expanduser().absolute()
    result = CheckerResult()
    flag = True
    if not parquet_file_path.exists():
        result.set_errors("File not found")
        return False, result

    try:
        import pyarrow.parquet as pq

        # 尝试读取 Parquet 文件以检查其完整性
        pq.read_table(parquet_file_path)
    except Exception:
        result.set_errors("File corruption detected")
        flag = False

    return flag, result


def qc_data_meta_consistency(repo_path: str | Path) -> dict:
    # todo: 实现数据文件元信息一致性检查逻辑，填写result.error
    pass


def qc_video_file_corruption(video_file_path: str | Path) -> tuple[bool, dict]:
    """
    检查视频文件是否损坏的示例检查器
    """
    video_file_path = Path(video_file_path).expanduser().absolute()
    result = CheckerResult()
    if not video_file_path.exists():
        result.set_errors("File not found")
        return False, result
    flag = True
    try:
        import av

        # 尝试打开视频文件以检查其完整性
        container = av.open(str(video_file_path))
        # 读取第一帧以确保视频文件未损坏
        for _ in container.decode(video=0):
            break
        container.close()
    except Exception as e:
        result.set_errors(f"Video file corruption detected: {str(e)}")
        flag = False

    return flag, result
