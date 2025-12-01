from prefect import task

# 全局注册表
TASK_REGISTRY = {}


def register_task(name=None, ncpu=1, nmem=4, ngpu=0):
    """
    自定义装饰器：将 task 自动注册到 TASK_REGISTRY，并应用 @task
    """

    def decorator(fn):
        # 获取注册名
        task_name = name or fn.__name__

        # 先应用 Prefect 的 @task
        prefect_task = task(fn)

        # 将带 @task 的 callable 注册到全局字典
        if task_name in TASK_REGISTRY:
            raise ValueError(f"Task name '{task_name}' is already registered.")
        TASK_REGISTRY[task_name] = {
            "fn": prefect_task,
            "resources": {"CPU": ncpu, "MEMORY_GB": nmem, "GPU": ngpu},
        }

        return prefect_task

    return decorator
