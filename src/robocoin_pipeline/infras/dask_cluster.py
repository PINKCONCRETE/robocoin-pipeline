# src/dataforge/infrastructure/dask_cluster.py
import socket

from prefect_dask import DaskTaskRunner

from ..config import get_dask_scheduler_address


def get_dask_task_runner() -> DaskTaskRunner:
    scheduler_address = get_dask_scheduler_address()
    try:
        host, port = scheduler_address.replace("tcp://", "").split(":")
        with socket.create_connection((host, int(port)), timeout=3):
            pass
        print(f"✅ 连接到 Dask 调度器: {scheduler_address}")
        return DaskTaskRunner(address=scheduler_address)
    except (OSError, ValueError, TimeoutError) as e:
        raise RuntimeError(
            f"❌ 无法连接 Dask 调度器 ({scheduler_address})。请确保已运行 dask-scheduler。\n"
            "可通过环境变量指定地址：export DASK_SCHEDULER=tcp://your-ip:8786"
        ) from e
