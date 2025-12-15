from pathlib import Path

from robocoin_pipeline.utils.paths import get_meta_info_file

from .checker_registry import register_repo_format_checker
from .checker_result import CheckerResult


@register_repo_format_checker()
def qc_repo_structure(
    repo_path: str | Path, checker_config: dict | None = None
) -> dict:
    repo_path = Path(repo_path).expanduser().absolute()
    result = CheckerResult()
    # todo: 实现文件结构检查逻辑，填写result.error
    result.set_errors("File structure error example.")
    return result


@register_repo_format_checker()
def qc_info_file(repo_path: str | Path, checker_config: dict | None = None) -> dict:
    get_meta_info_file(repo_path, None)
    results = CheckerResult()
    results.set_warnings("Meta info file warning example.")


@register_repo_format_checker()
def qc_episodes_file(repo_path: str | Path, checker_config: dict | None = None) -> dict:
    pass


@register_repo_format_checker()
def qc_tasks_file(repo_path: str | Path, checker_config: dict | None = None) -> dict:
    pass


@register_repo_format_checker()
def qc_episodes_stats_file(
    repo_path: str | Path, checker_config: dict | None = None
) -> dict:
    pass


@register_repo_format_checker()
def qc_repo_meta(repo_path: str | Path, checker_config: dict | None = None) -> dict:
    pass


@register_repo_format_checker()
def qc_feature_names(repo_path: str | Path, checker_config: dict | None = None) -> dict:
    pass


@register_repo_format_checker()
def qc_data_file_paths(
    repo_path: str | Path, checker_config: dict | None = None
) -> dict:
    pass


@register_repo_format_checker()
def qc_video_file_paths(
    repo_path: str | Path, checker_config: dict | None = None
) -> dict:
    pass
