import json
from collections import defaultdict
from pathlib import Path

import yaml

from robocoin_pipeline.constants.config_constant import (
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_MODEL_VERSION,
    DEFAULT_YAML_FILE,
)
from robocoin_pipeline.pipeline.tasks.quality_check.checkers.checker_registry import (
    get_abnormal_episode_length_checkers,
    get_data_quality_checker_names,
    get_data_quality_checkers,
    get_repo_meta_checkers,
    get_video_quality_checker_names,
)
from robocoin_pipeline.utils.dataset_info import (
    get_episode_frames_num,
    get_total_episodes,
)
from robocoin_pipeline.utils.paths import (
    get_data_files,
    get_field_root_path,
)

from .checkers.checker_result import CheckerResult
from .checkers.utils import (
    qc_data_file_corruption,
    qc_data_meta_consistency,
    qc_video_file_corruption,
    qc_video_meta_consistency,
)


def get_checker_configs(
    config_dir: str | Path,
    checker_name: str,
    device_model: str = DEFAULT_DEVICE_MODEL,
    device_model_version: str = DEFAULT_DEVICE_MODEL_VERSION,
) -> dict[str, dict]:
    config_dir = Path(config_dir).expanduser().absolute()
    checker_config_path = config_dir / checker_name
    if not checker_config_path.exists() or not checker_config_path.is_dir():
        return {}

    device_model_configs = checker_config_path / device_model
    if not device_model_configs.exists() or not device_model_configs.is_dir():
        return {}

    if not device_model_version:
        return yaml.safe_load(device_model_configs / DEFAULT_YAML_FILE)

    version_config_file = device_model_configs / f"{device_model_version}.yaml"
    if not version_config_file.exists():
        return {}

    return yaml.safe_load(version_config_file)


def quality_check_core(
    dataset_path: str | Path, qc_config_dir: str | Path, field: str | None = None
) -> dict[str, dict]:
    dataset_path = Path(dataset_path).expanduser().absolute()
    dataset_path = get_field_root_path(dataset_path, field)
    checker_results = {}

    repo_meta_checker_results = {}
    if not dataset_path.exists():
        raise FileNotFoundError(f"{dataset_path} does not exist")

    qc_config_dir = Path(qc_config_dir).expanduser().absolute()
    if not qc_config_dir.exists():
        raise FileNotFoundError(f"{qc_config_dir} does not exist")

    repo_meta_checkers = get_repo_meta_checkers()
    for checker_name, checker_func in repo_meta_checkers.items():
        checker_config = get_checker_configs(qc_config_dir, checker_name)
        repo_meta_checker_results[checker_name] = checker_func(
            dataset_path, field, checker_config
        )

    checker_results["repo_meta_checkers"] = repo_meta_checker_results

    abnormal_episode_length_checkers = get_abnormal_episode_length_checkers()
    episodes_frames_num = [
        get_episode_frames_num(dataset_path, ep_idx, field)
        for ep_idx in range(get_total_episodes(dataset_path, field))
    ]
    for checker_name, checker_func in abnormal_episode_length_checkers.items():
        checker_config = get_checker_configs(qc_config_dir, checker_name)
        repo_meta_checker_results[checker_name] = checker_func(
            dataset_path, field, episodes_frames_num, checker_config=checker_config
        )

    checker_results["abnormal_episode_length_checkers"] = repo_meta_checker_results

    data_files = get_data_files(dataset_path, None)
    data_file_corruption_checker_results = {}
    data_meta_consistency_checker_results = {}
    data_meta_consistency_checker_config = get_checker_configs(
        qc_config_dir, "data_meta_consistency_checker"
    )
    data_quality_checker_configs = {}
    data_quality_checker_results = defaultdict(dict)
    for checker_name in get_data_quality_checker_names():
        data_quality_checker_configs[checker_name] = get_checker_configs(
            qc_config_dir, checker_name
        )
    for file in data_files:
        flag, qc_result = qc_data_file_corruption(file)
        if not flag:
            data_file_corruption_checker_results[str(file)] = qc_result
            continue
        data_meta_consistency_checker_results[file.name] = qc_data_meta_consistency(
            file, checker_config=data_meta_consistency_checker_config
        )
        for checker_name, checker_func in get_data_quality_checkers():
            checker_config = data_quality_checker_configs.get(checker_name, {})
            data_quality_checker_results[file.name] = checker_func(
                file, data_meta_consistency_checker_config
            )

    checker_results["data_file_corruption_checkers"] = (
        data_file_corruption_checker_results
    )
    checker_results["data_meta_consistency_checkers"] = (
        data_meta_consistency_checker_results
    )

    video_file_corruption_checker_results = {}
    video_quality_checker_results = defaultdict(dict)
    video_quality_checker_configs = {}
    for checker_name in get_video_quality_checker_names():
        video_quality_checker_configs[checker_name] = get_checker_configs(
            qc_config_dir, checker_name
        )
    for video_file in get_data_files(dataset_path, field):
        flag, qc_result = qc_video_file_corruption(video_file)
        if not flag:
            video_file_corruption_checker_results[str(file)] = qc_result
            continue

        meta_consistency_result = qc_video_meta_consistency(
            video_file, checker_config=data_meta_consistency_checker_config
        )
        video_file_corruption_checker_results[video_file] = meta_consistency_result
        for checker_name, checker_func in video_quality_checker_configs.items():
            checker_config = video_quality_checker_configs.get(checker_name, {})
            video_quality_checker_results[checker_name] = checker_func(
                video_file, checker_config
            )

    checker_results["video_file_corruption_checkers"] = (
        video_file_corruption_checker_results
    )
    checker_results["video_quality_checkers"] = video_quality_checker_results


def _filter_checker_dict(d: dict[str, any]) -> dict[str, any] | None:
    """
    递归过滤嵌套字典：
    - 如果值是 CheckerResult：仅当非空时返回其 to_dict()
    - 如果值是 dict：递归处理，若子 dict 过滤后非空则保留
    - 其他类型：忽略（或可抛错）

    返回：
      - 过滤后的 dict（可能为空）
      - 或 None（表示整棵子树应被丢弃）
    """
    if not isinstance(d, dict):
        return None  # 非法结构，安全忽略

    filtered = {}
    for key, value in d.items():
        if isinstance(value, CheckerResult):
            if not value.is_empty():
                filtered[key] = value.to_dict()
        elif isinstance(value, dict):
            sub_filtered = _filter_checker_dict(value)
            if sub_filtered is not None and sub_filtered:  # 非空才保留
                filtered[key] = sub_filtered
        else:
            # 可选：跳过未知类型，或 raise ValueError
            continue

    return filtered if filtered else None


def gen_qc_report(
    checker_results: dict[str, dict],
    md_file_path: str | Path,
    json_file_path: str | Path,
) -> dict[str, any]:
    """
    支持任意深度嵌套的 checker_results。
    只保留包含非空 CheckerResult 的路径。
    """
    # Step 1: 递归过滤
    cleaned_results = _filter_checker_dict(checker_results) or {}

    # Step 2: 写入 JSON
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_results, f, indent=2, ensure_ascii=False)

    # Step 3: 生成 Markdown（需要递归遍历 cleaned_results）
    def _dict_to_md(d: dict[str, any], depth: int = 1) -> list[str]:
        lines = []
        for key, value in d.items():
            if isinstance(value, dict):
                # 检查是否是叶子节点（即 value 是 CheckerResult 转成的 dict）
                if any(k in value for k in ("errors", "warnings", "score")) and all(
                    isinstance(v, (str, float, int)) for v in value.values()
                ):
                    # 这是一个结果叶子节点
                    lines.append(f"{'#' * depth} {key}\n")
                    if "score" in value:
                        lines.append(f"- **Score**: {value['score']}\n")
                    if "errors" in value:
                        lines.append(f"- **Errors**: {value['errors']}\n")
                    if "warnings" in value:
                        lines.append(f"- **Warnings**: {value['warnings']}\n")
                    lines.append("")
                else:
                    # 中间节点
                    lines.append(f"{'#' * depth} {key}\n")
                    lines.extend(_dict_to_md(value, depth + 1))
        return lines

    md_lines = ["# Checker Report\n"]
    if cleaned_results:
        md_lines.extend(_dict_to_md(cleaned_results))
    else:
        md_lines.append("No issues found. All checks passed.")

    with open(md_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return cleaned_results
