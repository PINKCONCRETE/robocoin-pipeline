import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from dacite import from_dict
from pandas import DataFrame as pd
from tqdm import tqdm

from robocoin_pipeline.utils.dataset_info import (
    get_dataset_basic_infos,
)
from robocoin_pipeline.utils.paths import (
    get_data_files,
    get_episodes_stats_jsonl_file,
    get_meta_info_file,
)


@dataclass
class DataProcessorConfig:
    input_fields: set[str]
    input_fields_features: dict[str, set[str]]
    input_fields_features_names: dict[str, dict[str, list[str] | None] | None]
    output_field: str
    output_field_features: set[str]
    output_field_features_names: dict[str, list[str] | None]

    def __post_init__(self) -> None:
        # 确保 input_fields_features 的 key 是 input_fields 的子集
        if not set(self.input_fields_features.keys()).issubset(self.input_fields):
            raise ValueError("Keys in input_fields_features must be in input_fields")
        # 其他校验...
        if not set(self.input_fields_features_names.keys()).issubset(
            self.input_fields_features.keys()
        ):
            raise ValueError(
                "Keys in input_fields_features_names must be in input_fields_features"
            )

        for field, features_nmes in self.input_fields_features_names.items():
            features = self.input_fields_features[field]
            if not set(features_nmes.keys()).issubset(features):
                raise ValueError(
                    f"Keys in input_fields_features_names[{field}] must be in input_fields_features[{field}]"
                )

        if not set(self.output_field_features_names.keys).issubset(
            self.output_field_features
        ):
            raise ValueError(
                "Keys in output_field_features_names must be in output_field_features"
            )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DataProcessorConfig":
        """从 YAML 文件加载配置并返回 DataProcessorConfig 实例"""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return from_dict(data_class=cls, data=data)


class DataProcessorBase:
    def __init__(
        self,
        repo_path: str | Path,
        config: DataProcessorConfig,
    ) -> None:
        self.repo_path: Path = Path(repo_path).expanduser().absolute()

        self.input_fields = config.input_fields
        self.input_field_features = config.input_fields_features
        self.input_field_features_names = config.input_fields_features_names

        self.output_field = config.output_field
        self.output_field_features = config.output_field_features
        self.output_field_features_names = config.output_field_features_names

        self.output_field_data_files: list[Path] = get_data_files(
            self.repo_path, self.output_field
        )

        self.input_fields_data_files: dict[str, list[Path]] = {}
        for feature in self.input_field_features.keys:
            self.input_fields_data_files[feature] = get_data_files(
                self.repo_path, feature
            )

        self.output_meta_info_json_file = get_meta_info_file(
            self.repo_path, self.output_field
        )

        self.output_episodes_stats_jsonl_file = get_episodes_stats_jsonl_file(
            self.repo_path, self.output_field
        )

        self._ep_idx: int | None = None

        # self._validate_inputs()

    # def _validate_inputs(self) -> None:
    #     if not self.input_field_features:
    #         raise ValueError("input_field_features is empty")

    #     if not self.output_features:
    #         raise ValueError("output_features is empty")

    #     input_fields = self.input_field_features.keys()
    #     ep_num = get_total_episodes(self.repo_path, input_fields[0])
    #     for field in input_fields[1:]:
    #         if ep_num != get_total_episodes(self.repo_path, field):
    #             raise ValueError(
    #                 f"Number of episodes mismatch: {ep_num} vs {get_total_episodes(self.repo_path, field)} for '{field}'"
    #             )
    #     return None

    # 将处理episode数据的准备工作放在这里
    def prepare_processing(self) -> None:
        return None

    # 该方法将ori_data进行后处理，返回结果为后处理后的数据
    def process_data(
        self, input_field_datas: dict[str, dict[str, np.ndarray]]
    ) -> dict[str, np.ndarray]:
        return {}

    @property
    def episode_idx(self) -> int | None:
        return self._ep_idx

    def get_input_fields_episode_data(
        self, ep_idx: int
    ) -> dict[str, dict[str, np.ndarray | None]]:
        for field in self.input_field_features:
            if ep_idx >= len(self.input_fields_data_files[field]):
                raise ValueError(
                    f"episode_idx {ep_idx} out of range of input field {field} episodes",
                )
        results = defaultdict(dict)

        for feature, data_keys in self.input_field_features.items():
            df = pd.read_parquet(self.input_fields_data_files[feature][ep_idx])
            for data_key in data_keys:
                if data_key not in df:
                    results[feature][data_key] = None
                else:
                    results[feature][data_key] = np.array(df[data_key].tolist())

        return results

    def _get_pa_type(self, np_dtype: np.dtype) -> pa.lib.DataType:
        mapping = {
            np.int32: pa.int32(),
            np.int64: pa.int32(),
            np.float32: pa.float32(),
            np.float64: pa.float32(),
            np.bool_: pa.bool_(),
        }
        return mapping.get(np.dtype(np_dtype).type, pa.from_numpy_dtype(np_dtype))

    def write_output_field_episode_data(
        self, output_data: dict[str, np.ndarray], ep_idx: int
    ) -> None:
        if ep_idx >= len(self.output_field_data_files):
            raise ValueError(f"episode_idx {ep_idx} out of range")

        file_path = self.output_field_data_files[ep_idx]

        lengths = {key: arr.shape[0] for key, arr in output_data.items()}
        if len(set(lengths.values())) > 1:
            raise ValueError(f"Array length mismatch: {lengths}")

        try:
            arrays = []
            fields = []

            for col_name, arr in output_data.items():
                if arr.ndim == 1:
                    pa_type = self._get_pa_type(arr.dtype)
                    pa_array = pa.array(arr, type=pa_type)
                    arrays.append(pa_array)
                    fields.append(pa.field(col_name, pa_type))
                elif arr.ndim == 2:
                    # 使用 ListArray: 每个元素是一个 list
                    value_type = self._get_pa_type(arr.dtype)
                    list_type = pa.list_(value_type)
                    # 转换为 ListArray
                    pa_array = pa.array([row.tolist() for row in arr], type=list_type)
                    arrays.append(pa_array)
                    fields.append(pa.field(col_name, list_type))
                else:
                    raise ValueError(
                        f"Unsupported array dimension: {arr.ndim} for '{col_name}'"
                    )

            schema = pa.schema(fields)
            table = pa.Table.from_arrays(arrays, schema=schema)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, file_path)

        except Exception as e:
            raise OSError(f"Failed to write episode {ep_idx} to {file_path}") from e

    def write_output_field_info_file(self) -> None:
        json_dict = get_dataset_basic_infos(self.repo_path)
        json_dict["features"] = defaultdict(dict)
        for feature, names in self.output_field_features_names().items():
            if names is not None:
                # 确保 names 是一个列表
                if not isinstance(names, list):
                    raise ValueError(
                        f"Feature names must be a list, got {type(names)} for '{feature}'"
                    )

                # 扁平化处理：如果列表中有嵌套列表，展开它们
                flattened_names = []
                for item in names:
                    if isinstance(item, list):
                        # 如果是列表，展开它
                        flattened_names.extend(item)
                    elif isinstance(item, str):
                        # 如果是字符串，直接添加
                        flattened_names.append(item)
                    else:
                        raise ValueError(
                            f"Feature name in '{feature}' must be a string or list, "
                            f"got {type(item)}: {item}"
                        )

                # 使用扁平化后的列表
                names = flattened_names

                # 检查是否有重复的名称
                if len(names) != len(set(names)):
                    duplicates = [name for name in names if names.count(name) > 1]
                    raise ValueError(
                        f"Feature '{feature}' contains duplicated names: {set(duplicates)}"
                    )

            json_dict["features"][feature]["names"] = names

        with open(self.output_meta_info_json_file, "w") as f:
            json.dump(json_dict, f)

    def process(self) -> None:
        self.prepare_processing()
        self.episodes_stats = []
        for episode_idx in tqdm(
            range(len(self.output_field_data_files)),
            desc="Processing episodes",
            unit="episode",
        ):
            ori_data = self.get_input_fields_episode_data(episode_idx)
            self._ep_idx = episode_idx
            output_datas: dict[str, np.ndarray] = self.process_data(ori_data)

            if set(output_datas.keys()) != self.output_field_features:
                raise ValueError(
                    f"new_datas features {output_datas.keys()} != self.output_field_features {self.output_field_features}"
                )

            self.write_output_field_episode_data(output_datas, episode_idx)
            self.episodes_stats.append(self._compute_episode_stat(output_datas))
        self._write_output_field_episodes_stats_file()
        self.write_output_field_info_file()
        self._ep_idx = None

    def _compute_episode_stat(
        self, episode_data: dict[str, np.ndarray]
    ) -> dict[str, dict[str, list[float]]]:
        ep_stats = {}
        ep_stats["episode_index"] = self.episode_idx
        ep_stats["stats"] = {}
        for feature_key, data in episode_data.items():
            if data is None:
                raise ValueError(f"ori_data {feature_key} is None")
            ep_stats["stats"][feature_key] = {}
            ep_stats["stats"][feature_key]["mean"] = np.mean(data, axis=0).tolist()
            ep_stats["stats"][feature_key]["std"] = np.std(data, axis=0).tolist()
            ep_stats["stats"][feature_key]["min"] = np.min(data, axis=0).tolist()
            ep_stats["stats"][feature_key]["max"] = np.max(data, axis=0).tolist()
            ep_stats["stats"][feature_key]["count"] = [data.shape[0]]
        return ep_stats

    def _write_output_field_episodes_stats_file(self) -> None:
        with open(self.output_episodes_stats_jsonl_file, "w") as f:
            for stat in self.episodes_stats:
                json.dump(stat, f)
                f.write("\n")
