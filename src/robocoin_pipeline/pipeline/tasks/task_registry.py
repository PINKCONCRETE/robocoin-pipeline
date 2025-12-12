import functools
from collections.abc import Callable
from pathlib import Path

from prefect import get_run_logger
from prefect import task as prefect_task  # 避免命名冲突

from robocoin_pipeline.constants.config_constant import MEMORY_GB, NCPU, NGPU
from robocoin_pipeline.pipeline.tasks.resource_config import get_task_resource_config
from robocoin_pipeline.utils.dataset_info import (
    get_device_model,
    get_device_model_version,
)
from robocoin_pipeline.utils.file_sync import sync_in, sync_out

_TASK_REGISTRY: dict[str, dict[str, any]] = {}


def register_multi_input_fields_task(
    name: str | None = None,
) -> Callable:
    """
    装饰器：注册 RoboCoin Pipeline 任务

    运行时自动：
    - 从 repo_path/pipeline_config.yaml 读取 device_model/version
    - 加载对应资源配置
    - 执行 sync_from → user task → sync_back
    """

    def decorator(func: Callable) -> Callable:
        registered_name = name if name is not None else func.__name__

        @prefect_task(name=registered_name)
        @functools.wraps(func)
        def wrapped_task(
            repo_path: str | Path,
            input_fields: dict[str, str],
            output_field: str,
        ) -> None:
            logger = get_run_logger()
            repo_path = Path(repo_path)

            # 🔍 Step 0: 从 repo 动态加载 device_model 和 version
            device_model = get_device_model(repo_path)
            version = get_device_model_version(repo_path)
            logger.info(
                f"Loaded config: device_model={device_model}, version={version}"
            )

            # 📦 Step 1: 获取资源配置（可用于日志/校验/扩展）
            resource = get_task_resource_config(
                task_name=registered_name,
                device_model=device_model,
                version=version,
            )
            ncpu = resource[NCPU]
            nmem = resource[MEMORY_GB]
            ngpu = resource[NGPU]
            logger.info(
                f"Task resource requirement: CPU={ncpu}, MEM={nmem}GB, GPU={ngpu}"
            )

            # 🔄 Step 2: 同步输入
            sync_in(repo_path, input_fields)

            # ▶️ Step 3: 执行用户逻辑
            try:
                func(
                    repo_path=repo_path,
                    input_fields=input_fields,
                    output_field=output_field,
                )
            except Exception as e:
                logger.error(f"Task {registered_name} failed: {e}")
                raise

            # 🔄 Step 4: 同步输出
            sync_out(repo_path, output_field)

        # 注册（此时不加载资源，只存函数）
        _TASK_REGISTRY[registered_name] = {
            "func": wrapped_task,
            # 注意：不再存 ncpu/nmem/ngpu，因为它们是 per-repo 动态的
        }

        return wrapped_task

    return decorator


def register_single_input_field_task(
    name: str | None = None,
) -> Callable:
    """
    装饰器：注册 RoboCoin Pipeline 任务

    运行时自动：
    - 从 repo_path/pipeline_config.yaml 读取 device_model/version
    - 加载对应资源配置
    - 执行 sync_from → user task → sync_back
    """

    def decorator(func: Callable) -> Callable:
        registered_name = name if name is not None else func.__name__

        @prefect_task(name=registered_name)
        @functools.wraps(func)
        def wrapped_task(
            repo_path: str | Path,
            input_field: str,
            output_field: str,
        ) -> None:
            logger = get_run_logger()
            repo_path = Path(repo_path)

            # 🔍 Step 0: 从 repo 动态加载 device_model 和 version
            device_model = get_device_model(repo_path)
            version = get_device_model_version(repo_path)
            logger.info(
                f"Loaded config: device_model={device_model}, version={version}"
            )

            # 📦 Step 1: 获取资源配置（可用于日志/校验/扩展）
            resource = get_task_resource_config(
                task_name=registered_name,
                device_model=device_model,
                version=version,
            )
            ncpu = resource[NCPU]
            nmem = resource[MEMORY_GB]
            ngpu = resource[NGPU]
            logger.info(
                f"Task resource requirement: CPU={ncpu}, MEM={nmem}GB, GPU={ngpu}"
            )

            # 🔄 Step 2: 同步输入
            sync_in(repo_path, {input_field})

            # ▶️ Step 3: 执行用户逻辑
            try:
                func(
                    repo_path=repo_path,
                    input_field=input_field,
                    output_field=output_field,
                )
            except Exception as e:
                logger.error(f"Task {registered_name} failed: {e}")
                raise

            # 🔄 Step 4: 同步输出
            sync_out(repo_path, output_field)

        # 注册（此时不加载资源，只存函数）
        _TASK_REGISTRY[registered_name] = {
            "func": wrapped_task,
            # 注意：不再存 ncpu/nmem/ngpu，因为它们是 per-repo 动态的
        }

        return wrapped_task

    return decorator


def get_registered_task(task_name: str) -> Callable:
    """从注册表获取 Prefect task 函数"""
    if task_name not in _TASK_REGISTRY:
        raise ValueError(
            f"Task '{task_name}' not registered. Available: {list(_TASK_REGISTRY.keys())}"
        )
    return _TASK_REGISTRY[task_name]["func"]  # 已被 @task 装饰
