from pathlib import Path

from robocoin_pipeline.pipeline.tasks.quality_check.checkers.checker_registry import (
    get_abnormal_episode_length_checkers,
    get_format_checkers,
)
from robocoin_pipeline.utils.dataset_info import (
    get_episode_frames_num,
    get_total_episodes,
)
from robocoin_pipeline.utils.paths import (
    get_data_files,
    get_field_root_path,
)

from .checkers.format_checkers import (
    qc_data_file_corruption,
    qc_data_meta_consistency,
    qc_video_file_corruption,
)


def quality_check_core(
    dataset_path: str | Path, qc_config_dir: str | Path, field: str | None = None
) -> dict[str, dict]:
    dataset_path = Path(dataset_path).expanduser().absolute()
    dataset_path = get_field_root_path(dataset_path, field)
    format_checker_results = {}
    if not dataset_path.exists():
        raise FileNotFoundError(f"{dataset_path} does not exist")

    qc_config_dir = Path(qc_config_dir).expanduser().absolute()
    if not qc_config_dir.exists():
        raise FileNotFoundError(f"{qc_config_dir} does not exist")

    checker_results = {}
    format_checkers = get_format_checkers()
    for checker_name, checker_func in format_checkers.items():
        format_checker_results[checker_name] = checker_func(dataset_path, field)

    checker_results["format_checkers"] = format_checker_results

    abnormal_episode_length_checkers = get_abnormal_episode_length_checkers()
    episodes_frames_num = [
        get_episode_frames_num(dataset_path, ep_idx, field)
        for ep_idx in range(get_total_episodes(dataset_path, field))
    ]
    for checker_name, checker_func in abnormal_episode_length_checkers.items():
        format_checker_results[checker_name] = checker_func(
            dataset_path, field, episodes_frames_num
        )

    checker_results["abnormal_episode_length_checkers"] = format_checker_results

    data_files = get_data_files(dataset_path, None)
    data_file_corruption_checker_results = {}
    data_meta_consistency_checker_results = {}
    for file in data_files:
        flag, qc_result = qc_data_file_corruption(file)
        if not flag:
            data_file_corruption_checker_results[str(file)] = qc_result
            continue
        data_meta_consistency_checker_results[file.name] = qc_data_meta_consistency(
            file
        )

    checker_results["data_file_corruption_checkers"] = (
        data_file_corruption_checker_results
    )
    checker_results["data_meta_consistency_checkers"] = (
        data_meta_consistency_checker_results
    )

    video_file_corruption_checker_results = {}
    for video_file in get_data_files(dataset_path, field):
        flag, qc_result = qc_video_file_corruption(video_file)
        if not flag:
            video_file_corruption_checker_results[str(file)] = qc_result
            continue
