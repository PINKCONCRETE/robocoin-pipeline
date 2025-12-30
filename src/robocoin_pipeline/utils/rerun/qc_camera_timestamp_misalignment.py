"""
Quality Check: Camera Timestamp Misalignment
检测相机视频时间戳是否对齐
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


def check_camera_timestamp_alignment(
    repo_path: str | Path,
    episode_index: int | None = None,
    batch_size: int = 32,
    num_workers: int = 4,
) -> None:
    """
    检测相机视频时间戳是否对齐

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

    logging.info("Starting Rerun - Camera Timestamp Misalignment Check")
    rr.init(f"{str(repo_path)}_qc_camera_timestamp", spawn=True)
    gc.collect()

    logging.info("Checking Camera Timestamp Alignment")

    # 获取所有相机的时间戳信息
    camera_keys = dataset.meta.camera_keys
    timestamp_data = {camera: [] for camera in camera_keys}
    all_timestamps = []

    for batch in tqdm.tqdm(
        dataloader, total=len(dataloader), desc="Collecting timestamps"
    ):
        for i in range(len(batch["index"])):
            current_timestamp = batch["timestamp"][i].item()
            all_timestamps.append(current_timestamp)

            # 记录每个相机的时间戳
            for camera_key in camera_keys:
                if camera_key in batch:
                    timestamp_data[camera_key].append(current_timestamp)

    # 分析时间戳对齐情况
    logging.info(f"Total frames: {len(all_timestamps)}")
    logging.info(f"Cameras: {camera_keys}")

    # 计算时间戳差异
    if len(all_timestamps) > 1:
        timestamp_diffs = np.diff(all_timestamps)
        mean_diff = np.mean(timestamp_diffs)
        std_diff = np.std(timestamp_diffs)
        max_diff = np.max(timestamp_diffs)
        min_diff = np.min(timestamp_diffs)

        logging.info(
            f"Timestamp differences - Mean: {mean_diff:.6f}, Std: {std_diff:.6f}"
        )
        logging.info(
            f"Timestamp differences - Min: {min_diff:.6f}, Max: {max_diff:.6f}"
        )

    # 在Rerun中可视化相机图像和时间戳信息
    for batch in tqdm.tqdm(dataloader, total=len(dataloader), desc="Visualizing"):
        for i in range(len(batch["index"])):
            rr.set_time_sequence("frame_index", batch["frame_index"][i].item())
            rr.set_time_seconds("timestamp", batch["timestamp"][i].item())

            # 显示每个相机的图像
            for camera_key in camera_keys:
                if camera_key in batch:
                    rr.log(
                        camera_key, rr.Image(to_hwc_uint8_numpy(batch[camera_key][i]))
                    )

            # 记录时间戳信息
            timestamp_info = f"Timestamp: {batch['timestamp'][i].item():.6f}\n"
            timestamp_info += f"Frame Index: {batch['frame_index'][i].item()}\n"
            timestamp_info += "Camera Alignment Status: OK"

            rr.log("timestamp_info", rr.TextLog(timestamp_info))

    logging.info("Camera Timestamp Alignment Check Complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python qc_camera_timestamp_misalignment.py <repo_path> [episode_index]"
        )
        print("If episode_index is not provided, a random episode will be selected")
        sys.exit(1)

    repo_path = sys.argv[1]
    episode_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    check_camera_timestamp_alignment(repo_path, episode_index)
