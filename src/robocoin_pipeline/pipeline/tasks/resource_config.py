import os
from pathlib import Path

import yaml
from prefect import get_run_logger

from robocoin_pipeline.constants.config_constant import (
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_MODEL_VERSION,
    DEFAULT_YAML_FILE,
    MEMORY_GB,
    NCPU,
    NGPU,
)

_TASK_RESOURCES: dict[str, dict[str, int]] = {}

DEFAULT_NCPU = 4
DEFAULT_MEMERY_GB = 8
DEFAULT_NGPU = 0

TASK_RESOURCE_CONFIG_ROOT_PATH = None


def set_task_resource_config_root(path: str | Path) -> None:
    """显式设置资源配置根目录（最高优先级）"""
    global TASK_RESOURCE_CONFIG_ROOT_PATH
    TASK_RESOURCE_CONFIG_ROOT_PATH = Path(path).expanduser().absolute()


def get_task_resource_config_root() -> Path:
    """获取资源配置根目录，按优先级查找"""
    global TASK_RESOURCE_CONFIG_ROOT_PATH

    # 1. 显式设置
    if TASK_RESOURCE_CONFIG_ROOT_PATH is not None:
        return TASK_RESOURCE_CONFIG_ROOT_PATH

    # 2. 环境变量
    env_path = os.getenv("ROBOCOIN_PIPELINE_TASK_RESOURCE_CONFIG_ROOT")
    if env_path:
        return Path(env_path).expanduser().absolute()

    # 3. 默认路径 (~/.config/robocoin-pipeline/resource_configs)
    default_path = Path.home() / ".config" / "robocoin-pipeline" / "task_resources"
    return default_path


def _is_valid_config_dir(dir_path: Path, with_default_config: bool = False) -> bool:
    if not dir_path.is_dir():
        return False
    if dir_path.name.startswith("."):
        return False
    if with_default_config:
        default_config_file = dir_path / DEFAULT_YAML_FILE
        if not default_config_file.exists() or not default_config_file.is_file():
            return False
    return True


def _load_task_resource_config() -> None:
    """从 YAML 加载任务资源配置到全局变量"""
    global _TASK_RESOURCES
    _TASK_RESOURCES.clear()
    config_root_path = get_task_resource_config_root()
    if not config_root_path.exists() or not config_root_path.is_dir():
        raise ValueError(
            f"Config root path '{config_root_path}' is not a valid directory"
        )

    for dir_entry in config_root_path.iterdir():
        if not _is_valid_config_dir(dir_entry):
            continue
        task_name = dir_entry.name
        task_configs = {}
        default_config_file = dir_entry / DEFAULT_YAML_FILE

        if default_config_file.exists() and default_config_file.is_file():
            with open(default_config_file) as f:
                config_data = yaml.safe_load(f)
                task_configs[DEFAULT_DEVICE_MODEL] = config_data

        for device_model_dir in dir_entry.iterdir():
            device_model_config = {}
            if not _is_valid_config_dir(device_model_dir, with_default_config=True):
                continue

            default_config_file = device_model_dir / DEFAULT_YAML_FILE

            if default_config_file.exists() and default_config_file.is_file():
                with open(default_config_file) as f:
                    config_data = yaml.safe_load(f)
                    device_model_config[DEFAULT_DEVICE_MODEL_VERSION] = config_data

            device_model = device_model_dir.name
            for config_version_file in device_model_dir.iterdir():
                if (
                    config_version_file.is_file()
                    and config_version_file.suffix == ".yaml"
                ):
                    version = config_version_file.stem
                    with open(config_version_file) as f:
                        config_data = yaml.safe_load(f)
                        device_model_config[version] = config_data
            if device_model_config:
                task_configs[device_model] = device_model_config
        if task_configs:
            _TASK_RESOURCES[task_name] = task_configs


def get_task_resource_config(
    task_name: str,
    device_model: str | None = None,
    version: str | None = None,
) -> dict[str, int]:
    """根据任务名获取资源配置，fallback 到默认值"""
    if not _TASK_RESOURCES:
        _load_task_resource_config()

    resource_config = {}

    logger = get_run_logger()
    while True:
        task_resource_config = _TASK_RESOURCES.get(task_name, {})
        if not task_resource_config:
            raise ValueError(
                f"No resource config found for task '{task_name}', please check your resource config path {get_task_resource_config_root()}."
            )
        if not device_model or device_model not in task_resource_config:
            resource_config = task_resource_config.get(DEFAULT_DEVICE_MODEL, {})
            break

        version_configs = task_resource_config.get(device_model, {})

        if version not in version_configs:
            resource_config = version_configs[DEFAULT_DEVICE_MODEL_VERSION]
            break
        else:
            resource_config = version_configs[version]
            break

    ncpu = resource_config.get(NCPU, DEFAULT_NCPU)
    nmem = resource_config.get(MEMORY_GB, DEFAULT_MEMERY_GB)
    ngpu = resource_config.get(NGPU, DEFAULT_NGPU)
    logger.info(
        f"Task '{task_name}' using resource config: {NCPU}={ncpu}, {MEMORY_GB}={nmem}, {NGPU}={ngpu}"
    )

    return {NCPU: ncpu, MEMORY_GB: nmem, NGPU: ngpu}
