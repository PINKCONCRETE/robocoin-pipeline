import os

ROBOCOIN_PIPELINE_DISTRIBUTION_MODE = 1  # 0: 本地开发模式, 1: 集群分布式模式


def get_dask_scheduler_address() -> str:
    """
    获取 Dask 调度器地址。

    优先级（从高到低）：
    1. 环境变量 DASK_SCHEDULER
    2. 默认值 tcp://127.0.0.1:8786
    """
    return os.getenv("DASK_SCHEDULER", "tcp://127.0.0.1:8786")


def get_default_resources() -> dict:
    """
    获取本地回退资源（仅用于开发提示，实际调度由 worker 资源标签决定）。
    """
    return {
        "CPU": int(os.getenv("DATAFORGE_LOCAL_CPU", "14")),
        "MEMORY_GB": int(os.getenv("DATAFORGE_LOCAL_MEMORY_GB", "8")),
    }
