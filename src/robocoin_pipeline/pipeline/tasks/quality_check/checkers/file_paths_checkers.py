from pathlib import Path

from .checker_registry import register_repo_format_checker


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
