import os
from pathlib import Path

import yaml
from prefect import get_run_logger

from robocoin_pipeline.constants.config_constant import (
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_MODEL_VERSION,
    DEFAULT_YAML_FILE,
)

_CHECKER_CONFIG: dict[str, dict[str, int]] = {}


CHECKER_CONFIG_ROOT_PATH = None


def set_checker_config_root(path: str | Path) -> None:
    """显式设置资源配置根目录（最高优先级）"""
    global CHECKER_CONFIG_ROOT_PATH
    CHECKER_CONFIG_ROOT_PATH = Path(path).expanduser().absolute()


def get_checker_config_root_path() -> Path:
    """获取资源配置根目录，按优先级查找"""
    global CHECKER_CONFIG_ROOT_PATH

    # 1. 显式设置
    if CHECKER_CONFIG_ROOT_PATH is not None:
        return CHECKER_CONFIG_ROOT_PATH

    # 2. 环境变量
    env_path = os.getenv("ROBOCOIN_PIPELINE_CHECKER_CONFIG_ROOT_PATH")
    if env_path:
        return Path(env_path).expanduser().absolute()

    # 3. 默认路径 (~/.config/robocoin-pipeline/checker_configs)
    default_path = Path.home() / ".config" / "robocoin-pipeline" / "checker_configs"
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


def _load_checker_config() -> None:
    """从 YAML 加载任务资源配置到全局变量"""
    global _CHECKER_CONFIG
    _CHECKER_CONFIG.clear()
    config_root_path = get_checker_config_root_path()
    if not config_root_path.exists() or not config_root_path.is_dir():
        raise ValueError(
            f"Config root path '{config_root_path}' is not a valid directory"
        )

    for dir_entry in config_root_path.iterdir():
        if not _is_valid_config_dir(dir_entry):
            continue
        checker_name = dir_entry.name
        checker_configs = {}
        default_config_file = dir_entry / DEFAULT_YAML_FILE

        if default_config_file.exists() and default_config_file.is_file():
            with open(default_config_file) as f:
                config_data = yaml.safe_load(f)
                checker_configs[DEFAULT_DEVICE_MODEL] = config_data

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
                checker_configs[device_model] = device_model_config
        if checker_configs:
            _CHECKER_CONFIG[checker_name] = checker_configs


def get_checker_config(
    checker_name: str,
    device_model: str | None = None,
    version: str | None = None,
) -> dict[str, int]:
    """根据任务名获取资源配置，fallback 到默认值"""
    if not _CHECKER_CONFIG:
        _load_checker_config()

    checker_config = {}

    logger = get_run_logger()
    while True:
        checker_config = _CHECKER_CONFIG.get(checker_name, {})
        if not checker_config:
            raise ValueError(
                f"No resource config found for task '{checker_name}', please check your resource config path {get_checker_config_root_path()}."
            )
        if not device_model or device_model not in checker_config:
            checker_config = checker_config.get(DEFAULT_DEVICE_MODEL, {})
            break

        version_configs = checker_config.get(device_model, {})

        if version not in version_configs:
            checker_config = version_configs[DEFAULT_DEVICE_MODEL_VERSION]
            break
        else:
            checker_config = version_configs[version]
            break

    logger.info(f"Checker'{checker_name}' using config: {checker_config}")

    return checker_config
