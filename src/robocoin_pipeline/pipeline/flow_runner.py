from collections import defaultdict, deque
from pathlib import Path

from prefect import flow

from robocoin_pipeline.constants.config_constant import (
    DEPENDS_ON,
    INPUT_FROM,
    TASK_NAME,
    TASKS,
)
from robocoin_pipeline.pipeline.tasks.task_registry import _TASK_REGISTRY


def _validate_task_names_in_flow(
    tasks: list[dict[str, any]],
) -> None:
    task_depends_on = {}
    task_input_from = {}
    task_names = []
    all_depends = []
    all_input = []
    for task in tasks:
        task_name = task[TASK_NAME]
        depends = task.get(DEPENDS_ON, [])
        input = task.get(INPUT_FROM, [])
        task_depends_on[task_name] = set(depends)
        task_input_from[task_name] = set(input)
        task_names.append(task_name)

        all_depends.extend(depends)
        all_input.extend(input)

    if len(set(task_names)) != len(task_names):
        raise ValueError(f"存在重复的 {TASK_NAME}，请检查配置！")

    if not set(all_depends).issubset(set(task_names)):
        missing = set(all_depends) - set(task_names)
        raise ValueError(f"部分 {DEPENDS_ON} 引用的 {TASK_NAME} 不存在：{missing}")

    if not set(all_input).issubset(set(task_names)):
        missing = set(all_input) - set(task_names)
        raise ValueError(f"部分 {INPUT_FROM} 引用的 {TASK_NAME} 不存在：{missing}")


def _get_flow_from_config(
    tasks: list[dict[str, any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    task_depends_on = {}
    task_input_from = {}
    for task in tasks:
        task_name = task[TASK_NAME]
        depends_on = set(task.get(DEPENDS_ON, []))
        input_from = set(task.get(INPUT_FROM, []))
        task_depends_on[task_name] = depends_on
        task_input_from[task_name] = input_from

    return task_depends_on, task_input_from


def _is_flow_dag(flow: dict[str, set[str]]) -> bool:
    # Kahn's algorithm for cycle detection
    in_degree = dict.fromkeys(flow, 0)
    for node, deps in flow.items():
        in_degree[node] = len(deps)

    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    visited_count = 0

    while queue:
        node = queue.popleft()
        visited_count += 1
        for child, deps in flow.items():
            if node in deps:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

    return visited_count == len(flow)


def _topological_sort(dag: dict[str, set[str]]) -> list[str]:
    """
    对 DAG 进行拓扑排序。
    dag: {task_id: {dependency_task_ids}}
    返回执行顺序列表。
    """
    # 收集所有节点
    all_tasks = set(dag.keys())
    for deps in dag.values():
        all_tasks.update(deps)

    # 构建反向图（依赖 → 被依赖者）并计算入度
    graph = defaultdict(set)  # dep -> [tasks that depend on dep]
    in_degree = dict.fromkeys(all_tasks, 0)

    for task, deps in dag.items():
        for dep in deps:
            graph[dep].add(task)
            in_degree[task] += 1  # task 依赖 dep，所以 task 入度 +1

    # 初始化队列：无依赖的任务
    queue = deque([t for t in all_tasks if in_degree[t] == 0])
    order = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(all_tasks):
        raise RuntimeError("Cycle detected in task DAG!")

    return order


def _get_all_tasks(flow_task_dag: dict[str, set[str]]) -> set[str]:
    """获取所有任务"""
    all_tasks = set(flow_task_dag.keys())
    for deps in flow_task_dag.values():
        all_tasks.update(deps)
    return all_tasks


def _validate_tasks_registered(tasks: set[str]) -> None:
    """
    检查所有任务是否已注册
    """
    for task_id in tasks:
        if task_id not in _TASK_REGISTRY:
            raise ValueError(f"任务 {task_id} 未注册！")


def get_flow_from_config_file(
    config_path: str | Path,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    import yaml

    config_path = Path(config_path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Flow 配置文件不存在：{config_path}")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    tasks = config.get(TASKS, [])
    task_depends_on, task_input_from = _get_flow_from_config(tasks)
    _validate_task_names_in_flow(tasks)
    if not _is_flow_dag(task_depends_on):
        raise ValueError("Flow 配置文件格式错误：任务依赖关系有环")
    if not _is_flow_dag(task_input_from):
        raise ValueError("Flow 配置文件格式错误：数据依赖关系有环")
    return task_depends_on, task_input_from


@flow
async def run_dag_flow(
    repo_path: str | Path,
    task_flow_dag: dict[str, set[str]],
    data_flow_dag: dict[str, set[str]],
) -> None:
    repo_path = Path(repo_path)
    all_tasks = _get_all_tasks(task_flow_dag)

    _validate_tasks_registered(all_tasks)

    # 拓扑排序
    order = _topological_sort(task_flow_dag)
    futures = {}
    for task_id in order:
        # 等待依赖完成（同步阻塞）
        dep_futures = [futures[dep] for dep in task_flow_dag.get(task_id, set())]
        if dep_futures:
            # .result() 是同步等待
            [f.result() for f in dep_futures]

        # ✅ 提交到 Dask 集群
        task_func = _TASK_REGISTRY[task_id]["func"]
        future = task_func.submit(
            repo_path=repo_path,
            input_fields=data_flow_dag.get(task_id, set()),
            output_field=task_id,
        )
        futures[task_id] = future

    [f.result() for f in futures.values()]
