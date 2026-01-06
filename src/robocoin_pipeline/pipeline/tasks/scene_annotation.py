from pathlib import Path

import numpy as np

from robocoin_pipeline.core.data_processor import DataProcessorBase, DataProcessorConfig

# from robocoin_pipeline.pipeline.tasks.task_registry import (
#     register_single_input_field_task,
# )


# @register_single_input_field_task()
# def scene_annotation(
#     repo_path: str | Path,
#     input_field: str,
#     output_field: str,
#     config: dict,
#     logger: Logger | None = None,
# ) -> None:
#     if logger is None:
#         logger = getLogger(__name__)
#     """模拟Scene Annotation任务"""
#     logger.info("Begin running scene_annotation")
#     time.sleep(2)
#     logger.info("Finished running scene_annotation")


class SceneAnnotationProcessor(DataProcessorBase):
    def __init__(self, repo_path: str | Path, config: DataProcessorConfig) -> None:
        super().__init__(repo_path, config)

    def data_process(
        self, input_field_datas: dict[str, dict[str, np.ndarray]]
    ) -> dict[str, np.ndarray]:
        return {}

    def link_data_file(self, episode_index: int) -> bool:
        return True


if __name__ == "__main__":
    scene_annotation_processor = SceneAnnotationProcessor(
        repo_path="sync_files/test_memory/RMC-AIDA-L_box_up_down1",
        config=DataProcessorConfig(
            input_fields=["format_convert"],
            input_fields_features={"format_convert": {}},
            input_fields_features_names={"format_convert": {}},
            output_field="scene_annotation",
            output_field_features={"scene_annotation"},
            output_field_features_names={"scene_annotation": None},
        ),
    )
    scene_annotation_processor.process()
