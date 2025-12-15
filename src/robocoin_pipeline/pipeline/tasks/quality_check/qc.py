from pathlib import Path

from robocoin_pipeline.pipeline.tasks.task_registry import (
    register_single_input_fields_task,
)
from robocoin_pipeline.utils.paths import get_field_root_path


@register_single_input_fields_task()
def quality_check(dataset_path: str | Path, in_field: str, out_field: str) -> None:
    """
    Perform a quality check on the dataset located at dataset_path.
    The check verifies the presence of required input fields.

    Args:
        dataset_path (str | Path): The path to the dataset.
        input_fields (set[str]): A set of required input field names.

    Returns:
        dict[str, bool]: A dictionary indicating the presence of each input field.
    """
    from pathlib import Path

    dataset_path = Path(dataset_path)
    in_repo_path = get_field_root_path(in_field)
    out_repo_path = get_field_root_path(out_field)
    if not in_repo_path.exists():
        raise FileNotFoundError(f"The repo path {in_repo_path} does not exist.")
    if not out_repo_path.exists():
        raise FileNotFoundError(f"The repo path {out_repo_path} does not exist.")
