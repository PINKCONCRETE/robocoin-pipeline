import json
from pathlib import Path

from robocoin_pipeline.constants.path_constant import (
    DEFAULT_FIELD,
    HARDLINK_MAPPINGS_JSON_FILE,
    META_EPISODES_JSONL_FILE,
    META_EPISODES_STATS_JSONL_FILE,
    META_INFO_JSON_FILE,
    META_TASKS_JSONL_FILE,
)


def get_field_root_path(
    dataset_path: str | Path, field: str | None = DEFAULT_FIELD
) -> Path:
    dataset_path = Path(dataset_path).expanduser().absolute()
    if field is None:
        return dataset_path
    return dataset_path / field


def get_meta_info_file(
    dataset_path: str | Path, field: str | None = DEFAULT_FIELD
) -> Path:
    return get_field_root_path(dataset_path, field) / META_INFO_JSON_FILE


def get_tasks_jsonl_file(
    dataset_path: str | Path, field: str | None = DEFAULT_FIELD
) -> Path:
    return get_field_root_path(dataset_path, field) / META_TASKS_JSONL_FILE


def get_episodes_jsonl_file(
    dataset_path: str | Path, field: str | None = DEFAULT_FIELD
) -> Path:
    return get_field_root_path(dataset_path, field) / META_EPISODES_JSONL_FILE


def get_hardlinks(
    dataset_path: str, field: str | None = DEFAULT_FIELD
) -> dict[str | Path, str | Path]:
    hl_map_json_file = (
        get_field_root_path(dataset_path, field) / HARDLINK_MAPPINGS_JSON_FILE
    )
    if not hl_map_json_file.exists():
        return {}

    with hl_map_json_file.open("r") as f:
        return json.load(f)


def get_episodes_stats_jsonl_file(
    root_dir: str | Path, field: str | None = DEFAULT_FIELD
) -> Path:
    return get_field_root_path(root_dir, field) / META_EPISODES_STATS_JSONL_FILE


def get_relative_data_file(ep_idx: int, chunk_size: int) -> Path:
    return f"chunk-{ep_idx // chunk_size:03d}/episode_{ep_idx:06d}.parquet"


def get_relative_video_file(ep_idx: int, image_key: str, chunk_size: int) -> Path:
    return f"chunk-{ep_idx // chunk_size:03d}/{image_key}/episode_{ep_idx:06d}.mp4"


def get_video_files(
    dataset_path: str | Path, field: str | None = DEFAULT_FIELD
) -> list[list[Path]]:
    from robocoin_pipeline.utils.dataset_info import (
        get_chunk_size,
        get_total_episodes,
        get_video_features,
    )

    dataset_path = Path(dataset_path).expanduser().absolute()
    episodes_num = get_total_episodes(dataset_path, field)
    chunk_size = get_chunk_size(dataset_path, field)
    video_keys = get_video_features(dataset_path, field)

    results = []
    for ep_idx in range(episodes_num):
        key_video_paths = [
            get_field_root_path(dataset_path, field)
            / "videos"
            / get_relative_video_file(ep_idx, video_key, chunk_size)
            for video_key in video_keys
        ]
        results.append(dataset_path / key_video_paths)


def get_data_files(
    dataset_path: str | Path,
    field: str | None = DEFAULT_FIELD,
) -> list[Path]:
    from robocoin_pipeline.utils.dataset_info import (
        get_chunk_size,
        get_total_episodes,
    )

    total_episodes = get_total_episodes(dataset_path, field)
    chunk_size = get_chunk_size(dataset_path, field)

    return [
        get_field_root_path(dataset_path, field)
        / get_relative_data_file(ep_idx, chunk_size)
        for ep_idx in range(total_episodes)
    ]
