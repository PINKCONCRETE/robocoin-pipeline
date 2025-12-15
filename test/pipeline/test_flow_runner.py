# submit_flow.py
import asyncio
import os
from pathlib import Path

from robocoin_pipeline.pipeline.flow_runner import (
    get_flow_from_config_file,
    run_dag_flow,
)
from robocoin_pipeline.pipeline.tasks.resource_config import (
    set_task_resource_config_root,
)

repo_name = "robocoin-datasets/RMC-AIDA-L_box_up_down"

repo_path_root = (
    Path(os.environ["ROBOCOIN_PIPELINE_CACHE_ROOT_PATH"]).expanduser().resolve()
)
set_task_resource_config_root("./configs/task_resources")
repo_path = repo_path_root / repo_name
data_flow_dag, task_flow_dag = get_flow_from_config_file(
    "test/configs/flows/test_flow.yaml"
)

asyncio.run(
    run_dag_flow(
        repo_path=repo_path,
        task_flow_dag=task_flow_dag,
        data_flow_dag=data_flow_dag,
    )
)
