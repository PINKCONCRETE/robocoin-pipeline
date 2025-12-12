from robocoin_pipeline.pipeline.tasks.resource_config import (
    get_task_resource_config,
    set_task_resource_config_root,
)

set_task_resource_config_root("test/configs/tasks/resources")


task_name = "format_convert"
device_model = "RMC-AIDA-L"
version = "gpu"

print(
    "------------------------------------------------------------------------------------------"
)
print(
    f"Resource config for task '{task_name}', device_model '{device_model}', version '{version}':"
)
config = get_task_resource_config(task_name, device_model, version)
print(config)


task_name = "format_convert"
device_model = "RMC-AIDA-L"
version = "version_not_exist"

print(
    "------------------------------------------------------------------------------------------"
)
print(
    f"Resource config for task '{task_name}', device_model '{device_model}', version '{version}':"
)
config = get_task_resource_config(task_name, device_model, version)
print(config)


task_name = "format_convert"
device_model = "device_model_not_exist"
print(
    "------------------------------------------------------------------------------------------"
)
print(
    f"Resource config for task '{task_name}', device_model '{device_model}', version '{version}':"
)
config = get_task_resource_config(task_name, device_model, version)
print(config)


task_name = "task_not_exist"
device_model = "RMC-AIDA-L"
version = "gpu"

print(
    "------------------------------------------------------------------------------------------"
)
print(
    f"Resource config for task '{task_name}', device_model '{device_model}', version '{version}':"
)
config = get_task_resource_config(task_name, device_model, version)
print(config)
