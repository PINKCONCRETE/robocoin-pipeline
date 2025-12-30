"""
Quality Check: Video Data Desynchronization
检测视频和数据是否同步
"""

import gc
import logging
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import rerun as rr
import torch
import torch.utils.data
import tqdm
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):
    def __init__(self, dataset: LeRobotDataset, episode_index: int) -> None:
        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        self.frame_ids = range(from_idx, to_idx)

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


def to_hwc_uint8_numpy(chw_float32_torch: torch.Tensor) -> np.ndarray:
    assert chw_float32_torch.dtype == torch.float32
    assert chw_float32_torch.ndim == 3
    c, h, w = chw_float32_torch.shape
    assert (
        c < h and c < w
    ), f"expect channel first images, but instead {chw_float32_torch.shape}"
    return (chw_float32_torch * 255).type(torch.uint8).permute(1, 2, 0).numpy()


def get_annotation_text(batch: dict, idx: int) -> str:
    """生成注释文本，包括动作数据"""
    annotation_text = ""

    # 任务信息
    if "task" in batch:
        annotation_text += f"Task:\n{batch['task'][idx]}\n"

    # 子任务信息
    if "subtasks" in batch:
        annotation_text += f"Subtasks:\n{batch['subtasks'][idx]}\n"

    annotation_text += "\n"

    # 动作数据 - 左臂
    annotation_text += "Left Arm Actions:\n"
    if "left_eef_acc_mag_action" in batch:
        annotation_text += (
            f"  EEF Acc Magnitude: {batch['left_eef_acc_mag_action'][idx]}\n"
        )
    if "left_eef_direction_action" in batch:
        annotation_text += (
            f"  EEF Direction: {batch['left_eef_direction_action'][idx]}\n"
        )
    if "left_eef_velocity_action" in batch:
        annotation_text += f"  EEF Velocity: {batch['left_eef_velocity_action'][idx]}\n"
    if "left_gripper_mode_action" in batch:
        annotation_text += f"  Gripper Mode: {batch['left_gripper_mode_action'][idx]}\n"

    annotation_text += "\n"

    # 动作数据 - 右臂
    annotation_text += "Right Arm Actions:\n"
    if "right_eef_acc_mag_action" in batch:
        annotation_text += (
            f"  EEF Acc Magnitude: {batch['right_eef_acc_mag_action'][idx]}\n"
        )
    if "right_eef_direction_action" in batch:
        annotation_text += (
            f"  EEF Direction: {batch['right_eef_direction_action'][idx]}\n"
        )
    if "right_eef_velocity_action" in batch:
        annotation_text += (
            f"  EEF Velocity: {batch['right_eef_velocity_action'][idx]}\n"
        )
    if "right_gripper_mode_action" in batch:
        annotation_text += (
            f"  Gripper Mode: {batch['right_gripper_mode_action'][idx]}\n"
        )

    return annotation_text


def check_video_data_desynchronization(
    repo_path: str | Path,
    episode_index: int | None = None,
    batch_size: int = 32,
    num_workers: int = 4,
) -> None:
    """
    检测视频和数据是否同步

    Args:
        repo_path: 数据集路径
        episode_index: episode索引，默认为None则随机选择
        batch_size: 批大小
        num_workers: 工作进程数
    """
    import random

    repo_path = Path(repo_path).expanduser().absolute()

    # 使用更大的tolerance_s来允许加载有时间戳问题的数据集
    # 这样我们可以检查和诊断这些问题
    try:
        dataset = LeRobotDataset(
            "test/visualize_dataset",
            repo_path,
            tolerance_s=100.0,  # 大幅提高容差，允许加载有问题的数据
        )
        logging.info("Dataset loaded successfully")
    except Exception as e:
        logging.error(f"Failed to load dataset: {e}")
        raise

    # 如果没有指定episode，则随机选择
    if episode_index is None:
        episode_index = random.randint(0, len(dataset.episode_data_index["from"]) - 1)

    # 验证episode索引有效性
    if episode_index >= len(dataset.episode_data_index["from"]):
        raise ValueError(f"Episode index {episode_index} out of range")

    logging.info(f"Selected episode index: {episode_index}")

    episode_sampler = EpisodeSampler(dataset, episode_index)
    dataloader = torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
    )

    logging.info("Starting Rerun - Video Data Desynchronization Check")
    rr.init(f"{str(repo_path)}_qc_video_data_desync", spawn=True)
    gc.collect()

    logging.info("Checking Video Data Synchronization")

    # 收集视频的时间戳
    video_timestamps = []
    frame_count = 0

    for batch in tqdm.tqdm(
        dataloader, total=len(dataloader), desc="Analyzing synchronization"
    ):
        for i in range(len(batch["index"])):
            video_timestamps.append(batch["timestamp"][i].item())
            frame_count += 1

    logging.info(f"Total frames: {frame_count}")
    logging.info(
        f"Video timestamp range: {min(video_timestamps):.6f} - {max(video_timestamps):.6f}"
    )

    # 检查视频数据的帧间隔一致性
    if len(video_timestamps) > 1:
        timestamp_diffs = np.diff(video_timestamps)
        mean_diff = np.mean(timestamp_diffs)
        std_diff = np.std(timestamp_diffs)

        logging.info(f"Frame interval - Mean: {mean_diff:.6f}s, Std: {std_diff:.6f}s")

        # 检测异常的帧间隔
        deviation_threshold = mean_diff * 0.5  # 偏差超过50%视为异常
        anomalies = np.where(np.abs(timestamp_diffs - mean_diff) > deviation_threshold)[
            0
        ]

        if len(anomalies) > 0:
            logging.warning(f"Found {len(anomalies)} frames with abnormal timing")
            for anomaly_idx in anomalies[:10]:  # 仅显示前10个
                logging.warning(
                    f"  Frame {anomaly_idx}: interval={timestamp_diffs[anomaly_idx]:.6f}s "
                    f"(expected ~{mean_diff:.6f}s)"
                )

    # 在Rerun中可视化
    for batch in tqdm.tqdm(dataloader, total=len(dataloader), desc="Visualizing"):
        for i in range(len(batch["index"])):
            rr.set_time_sequence("frame_index", batch["frame_index"][i].item())
            rr.set_time_seconds("timestamp", batch["timestamp"][i].item())

            # 显示相机图像
            for camera_key in dataset.meta.camera_keys:
                if camera_key in batch:
                    rr.log(
                        camera_key, rr.Image(to_hwc_uint8_numpy(batch[camera_key][i]))
                    )

            # 记录数据同步状态
            annotation_text = get_annotation_text(batch, i)
            if annotation_text:
                rr.log("data_sync", rr.TextLog(annotation_text))

    logging.info("Video Data Desynchronization Check Complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python qc_video_data_desynchronization.py <repo_path> [episode_index]"
        )
        print("If episode_index is not provided, a random episode will be selected")
        sys.exit(1)

    repo_path = sys.argv[1]
    episode_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    check_video_data_desynchronization(repo_path, episode_index)
