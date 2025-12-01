# prefect_dask_cluster/tasks.py


from .task_registry import register_task

# @register_task
# def cpu_intensive_task(n: int) -> int:
#     """模拟 CPU 密集型任务"""
#     total = 0
#     for i in range(n):
#         total += i * i
#     time.sleep(20)
#     return total


# @task
# def gpu_simulated_task(data: list) -> list:
#     """模拟 GPU 任务（实际使用时替换为 CUDA/PyTorch 代码）"""
#     time.sleep(20)  # 模拟计算延迟
#     return [x * 2 for x in data]


# @task
# def io_bound_task(url: str) -> str:
#     """模拟 I/O 密集型任务（如下载）"""
#     time.sleep(20)
#     return f"Downloaded mock data from {url}"


@register_task
def motion_annotation(
    repo_path: str, input_features: list[str], output_features: list[str]
):
    """模拟Motion Annotation任务"""
    pass
