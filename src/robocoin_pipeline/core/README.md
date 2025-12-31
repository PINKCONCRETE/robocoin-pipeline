# Core Module

该模块包含了 `robocoin-pipeline` 的核心数据处理逻辑。

## Data Processor (`data_processor.py`)

`data_processor.py` 提供了一个通用的数据处理框架，用于定义和执行数据转换任务。它由配置类 `DataProcessorConfig` 和基类 `DataProcessorBase` 组成。

### 1. DataProcessorConfig

`DataProcessorConfig` 是一个数据类（dataclass），用于定义数据处理任务的输入和输出规范。

**主要参数:**

*   `input_fields` (`set[str]`): 需要读取的输入字段列表（例如 `['camera', 'arm_state']`）。
*   `input_fields_features` (`dict[str, set[str]]`): 每个输入字段下需要读取的具体特征（例如 `{'camera': {'image', 'depth'}, 'arm_state': {'qpos'}}`）。
*   `input_fields_features_names` (`dict[str, dict[str, list[str] | None] | None]`): （可选）输入特征的具体维度名称定义。
*   `output_field` (`str`): 处理结果将要写入的输出字段名称。
*   `output_field_features` (`set[str]`): 输出数据包含的特征列表。
*   `output_field_features_names` (`dict[str, list[str] | None]`): 输出特征的具体维度名称定义。

**功能:**
*   **校验**: 在初始化 (`__post_init__`) 时会自动检查配置的合法性，例如确保 features 属于对应的 fields。
*   **加载**: 提供 `from_yaml(path)` 类方法，支持从 YAML 文件直接加载配置。

### 2. DataProcessorBase

`DataProcessorBase` 是所有数据处理器的基类。开发者需要继承该类并实现 `process_data` 方法。

**核心流程 (`process` 方法):**

1.  **准备**: 调用 `prepare_processing()`（可重写）进行预处理准备。
2.  **遍历**: 遍历 **输出文件列表** (`self.output_field_data_files`) 对应的索引。
    *   *注意*: 目前的逻辑依赖于输出文件路径列表来确定循环次数。这意味着在运行处理之前，目标路径可能需要预先存在或通过某种方式被识别。
3.  **读取**: 调用 `get_input_fields_episode_data(episode_idx)` 读取指定 episode 的所有输入字段数据。
    *   该方法会自动对齐不同输入字段的数据。
4.  **处理**: 调用 `process_data(ori_data)` 处理数据。
    *   **这是用户必须实现的核心逻辑**。
    *   输入: `dict[str, dict[str, np.ndarray]]` (输入字段 -> 特征 -> 数组)。
    *   输出: `dict[str, np.ndarray]` (输出特征 -> 数组)。
5.  **校验**: 检查输出数据的 keys 是否与配置的 `output_field_features` 一致。
6.  **写入**: 调用 `write_output_field_episode_data` 将结果写入 Parquet 文件。
    *   自动处理 numpy 到 pyarrow 的类型转换。
    *   支持 1D 数组和 2D 数组（转换为 ListArray）。
7.  **统计**: 计算每个 episode 的统计信息（均值、方差、极值等）。
8.  **收尾**:
    *   将统计信息写入 JSONL 文件 (`_write_output_field_episodes_stats_file`)。
    *   更新元数据文件 (`write_output_field_info_file`)。

**关键方法:**

*   `process_data(self, input_field_datas)`: **[抽象方法]** 接收原始数据字典，返回处理后的数据字典。
*   `get_input_fields_episode_data(self, ep_idx)`: 根据配置从磁盘读取输入数据。
*   `write_output_field_episode_data(self, output_data, ep_idx)`: 将处理后的数据写入磁盘。

### 使用示例

```python
from robocoin_pipeline.core.data_processor import DataProcessorBase, DataProcessorConfig
import numpy as np

class MyProcessor(DataProcessorBase):
    def process_data(self, input_field_datas: dict[str, dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
        # 假设我们从 'camera' 字段读取 'image'
        image_data = input_field_datas['camera']['image']
        
        # 执行一些处理，例如计算平均值
        processed_result = np.mean(image_data, axis=-1)
        
        # 返回结果，key 必须对应配置中的 output_field_features
        return {
            "image_mean": processed_result
        }

# 加载配置
config = DataProcessorConfig.from_yaml("config.yaml")
# 初始化处理器
processor = MyProcessor(repo_path="/path/to/repo", config=config)
# 执行处理
processor.process()
```
