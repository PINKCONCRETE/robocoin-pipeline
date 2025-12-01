from pathlib import Path

from prefect import flow

from ..infras.dask_cluster import get_dask_task_runner


def parse_yaml_config(yaml_config_path: str | Path):
    pass


@flow(task_runner=get_dask_task_runner())
def pipeline_flow(yaml_config_path: str | Path):
    """演示混合资源任务的工作流"""
    futures = []

    results = [f.result() for f in futures]
    return results

    # # 提交 CPU 任务
    # with dask.annotate(resources={"CPU": 2, "MEMORY_GB": 2}):
    #     cpu_fut = cpu_intensive_task.submit(500_000)
    #     futures.append(cpu_fut)
    # print("✅ 提交CPU 任务:", cpu_fut)

    # # 提交“GPU”任务
    # with dask.annotate(resources={"GPU": 1, "CPU": 2}):
    #     gpu_fut = gpu_simulated_task.submit([1, 2, 3, 4, 5])
    #     futures.append(gpu_fut)

    # print("✅ 提交GPU 模拟任务:", gpu_fut)

    # # 提交 I/O 任务
    # with dask.annotate(resources={"CPU": 1, "MEMORY_GB": 1}):
    #     io_fut = io_bound_task.submit("http://example.com/data")
    #     futures.append(io_fut)

    # print("✅ 提交I/O 任务:", io_fut)

    # # 等待所有结果
    # results = [f.result() for f in futures]
    # print("✅ 所有任务完成:", results)
    # return results
