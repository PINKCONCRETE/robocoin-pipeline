from pathlib import Path

from prefect import flow

from ..infras.dask_cluster import get_dask_task_runner


@flow(task_runner=get_dask_task_runner())
def pipeline_flow(flow_config_path: str | Path, task_config_path: str | Path = None):
    """演示混合资源任务的工作流"""

    flow_config_path = Path(flow_config_path).expanduser().absolute()
    # task_config: dict | None = None
    if task_config_path:
        task_config_path = Path(task_config_path).expanduser().absolute()
        if not task_config_path.exists():
            raise FileNotFoundError(f"配置文件 {task_config_path} 不存在")

        # with open(task_config_path) as f:
        #     task_config = yaml.load(f, Loader=yaml.FullLoader)
    # else:
    #     for task_name, task_config in TASK_REGISTRY.items():
    #         task_config["name"] = task_config

    # task_config = TASK_REGISTRY
    # if not config_path.exists():
    #     raise FileNotFoundError(f"配置文件 {config_path} 不存在")
    # with open(config_path) as f:
    #     pipeline_config = yaml.load(f, Loader=yaml.FullLoader)

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
