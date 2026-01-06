import json
from pathlib import Path

import yaml

from robocoin_pipeline.constants.path_constant import (
    DATASET_INFO_YAML_FILE,
    DEFAULT_FIELD,
    META_EPISODES_JSONL_FILE,
)
from robocoin_pipeline.utils.paths import (
    get_field_root_path,
    get_meta_info_file,
)

# 用于获得dataset的各种元信息
DATASET_META_INFO = {}
# 用于获得dataset episode的各种元信息
DATASET_EPISODE_META_INFO = {}


def get_dataset_info(repo_path: str | Path, field: str = DEFAULT_FIELD) -> dict:
    if (repo_path, field) in DATASET_META_INFO:
        return DATASET_META_INFO[(repo_path, field)]

    meta_info_file = get_meta_info_file(repo_path, field)
    if not meta_info_file.exists():
        raise ValueError(f"{repo_path} does not exist")

    if meta_info_file.is_dir():
        raise ValueError(f"{repo_path} is not a file")

    dataset_info_yaml_file = repo_path / DATASET_INFO_YAML_FILE
    if not dataset_info_yaml_file.exists():
        raise ValueError(f"{dataset_info_yaml_file} does not exist")

    with open(meta_info_file) as f:
        meta_info = json.load(f)
        DATASET_META_INFO[(repo_path, field)] = meta_info

    with open(dataset_info_yaml_file) as f:
        yaml_obj = yaml.safe_load(f)
        DATASET_META_INFO[(repo_path, field)].update(yaml_obj)

        return meta_info


def get_dataset_episode_info(repo_path: str | Path, field: str = DEFAULT_FIELD) -> dict:
    if (repo_path, field) in DATASET_EPISODE_META_INFO:
        return DATASET_EPISODE_META_INFO[(repo_path, field)]

    field_root_path = get_field_root_path(repo_path, field)
    if not field_root_path.exists():
        raise ValueError(f"{field_root_path} does not exist")

    if not field_root_path.is_dir():
        raise ValueError(f"{field_root_path} is not a directory")

    episodes_jsonl_file = field_root_path / META_EPISODES_JSONL_FILE
    if not episodes_jsonl_file.exists():
        raise ValueError(f"{episodes_jsonl_file} does not exist")

    ep_lengths = {}
    ep_tasks = {}
    with open(episodes_jsonl_file) as f:
        while True:
            line = f.readline()
            if not line:
                break
            json_obj = json.loads(line)
            ep_idx = json_obj["episode_index"]
            tasks = json_obj["tasks"]
            length = json_obj["length"]
            ep_lengths[ep_idx] = length
            ep_tasks[ep_idx] = tasks
    frame_start_idx = 0
    ep_frame_start_idx = {}
    ep_frame_end_idx = {}

    for ep_idx in sorted(ep_tasks.keys()):
        ep_frame_start_idx[ep_idx] = frame_start_idx
        ep_frame_end_idx[ep_idx] = frame_start_idx + ep_lengths[ep_idx]
        frame_start_idx += ep_lengths[ep_idx]

    DATASET_EPISODE_META_INFO[(repo_path, field)] = {
        "ep_lengths": ep_lengths,
        "ep_tasks": ep_tasks,
        "ep_frame_start_idx": ep_frame_start_idx,
        "ep_frame_end_idx": ep_frame_end_idx,
    }


def get_lerobot_version(repo_path: str | Path, field: str = DEFAULT_FIELD) -> str:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["codebase_version"]


def get_robot_type(repo_path: str | Path, field: str = DEFAULT_FIELD) -> str:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["robot_type"]


def get_fps(repo_path: str | Path, field: str = DEFAULT_FIELD) -> int:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["fps"]


def get_total_episodes(repo_path: str | Path, field: str = DEFAULT_FIELD) -> int:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["total_episodes"]


def get_chunk_size(repo_path: str | Path, field: str = DEFAULT_FIELD) -> int:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["chunks_size"]


def get_total_frames(repo_path: str | Path, field: str = DEFAULT_FIELD) -> int:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["total_frames"]


def get_total_tasks(repo_path: str | Path, field: str = DEFAULT_FIELD) -> int:
    meta_info = get_dataset_info(repo_path, field)
    return meta_info["total_tasks"]


def get_device_model(repo_path: str | Path, field: str = DEFAULT_FIELD) -> str:
    return get_dataset_info(repo_path, field)["device_model"]


def get_device_model_version(repo_path: str | Path, field: str = DEFAULT_FIELD) -> str:
    return get_dataset_info(repo_path, field)["device_model_version"]


def get_episode_frames_num(
    repo_path: str | Path, episode_id: int, field: str = DEFAULT_FIELD
) -> int:
    return get_dataset_episode_info(repo_path, field)["ep_lengths"][episode_id]


def get_episode_tasks(repo_path: str | Path, episode_id: int) -> list[str]:
    return get_dataset_episode_info(repo_path)["ep_tasks"][episode_id]


def get_episode_frame_start_idx(
    repo_path: str | Path, episode_id: int, field: str = DEFAULT_FIELD
) -> int:
    return get_dataset_episode_info(repo_path, field)["ep_frame_start_idx"][episode_id]


def get_episode_frame_end_idx(
    repo_path: str | Path, episode_id: int, field: str = DEFAULT_FIELD
) -> int:
    return get_dataset_episode_info(repo_path, field)["ep_frame_end_idx"][episode_id]


def get_episode_timestamp_from(
    repo_path: str | Path, episode_id: int, field: str = DEFAULT_FIELD
) -> float:
    return get_episode_frame_start_idx(repo_path, episode_id, field) / get_fps(
        repo_path
    )


def get_episode_timestamp_to(
    repo_path: str | Path, episode_id: int, field: str = DEFAULT_FIELD
) -> float:
    return get_episode_frame_end_idx(repo_path, episode_id, field) / get_fps(repo_path)


def get_video_features(repo_path: str | Path, field: str = DEFAULT_FIELD) -> set[str]:
    info_json_obj = get_dataset_info(repo_path, field)
    results = set()
    for feature_name, feature_info in info_json_obj["features"].items():
        if feature_info["dtype"] == "video":
            results.add(feature_name)

    return results


def get_dataset_basic_infos(repo_path: str | Path, field: str = DEFAULT_FIELD) -> dict:
    meta_info = get_dataset_info(repo_path, field)
    basic_info = {}
    basic_info["codebase_version"] = meta_info["codebase_version"]
    basic_info["robot_type"] = meta_info["robot_type"]
    basic_info["total_tasks"] = meta_info["total_tasks"]
    basic_info["fps"] = meta_info["fps"]
    basic_info["data_path"] = meta_info["data_path"]
    basic_info["video_path"] = meta_info["video_path"]
    basic_info["chunk_size"] = meta_info["chunk_size"]
    basic_info["features"] = {}

    return basic_info
