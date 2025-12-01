from prefect import task

# 全局注册表
TASK_REGISTRY = {}


def register_task(name=None):
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
        TASK_REGISTRY[task_name] = prefect_task

        # # 可选：保留原始函数的一些属性（非必须）
        # @wraps(fn)
        # def wrapper(*args, **kwargs):
        #     return prefect_task(*args, **kwargs)

        # 注意：我们返回的是 Prefect Task 对象本身（它是可调用的）
        # 所以通常直接返回 prefect_task 即可
        return prefect_task

    return decorator
