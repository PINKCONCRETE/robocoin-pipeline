"""
Quality Check: View Obstruction or Blind Spots
检测相机视野是否存在遮挡和盲区
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


def detect_potential_occlusion(
    image_tensor: torch.Tensor, threshold: float = 0.1
) -> tuple[bool, float]:
    """
    检测图像中潜在的遮挡和暗区

    Args:
        image_tensor: CHW格式的torch张量
        threshold: 黑色像素比例阈值

    Returns:
        (是否检测到遮挡, 黑色像素比例)
    """
    # 转换为灰度
    if image_tensor.shape[0] == 3:  # RGB
        gray = (
            0.299 * image_tensor[0] + 0.587 * image_tensor[1] + 0.114 * image_tensor[2]
        )
    else:  # 单通道
        gray = image_tensor[0]

    # 计算黑色像素比例 (值 < 0.05)
    black_pixel_ratio = (gray < 0.05).float().mean().item()

    # 检测是否存在显著的黑色区域
    has_occlusion = black_pixel_ratio > threshold

    return has_occlusion, black_pixel_ratio


def detect_edge_coverage(image_tensor: torch.Tensor) -> dict:
    """
    检测图像边缘的覆盖情况

    Args:
        image_tensor: CHW格式的torch张量

    Returns:
        边缘覆盖信息字典
    """
    # 转换为灰度
    if image_tensor.shape[0] == 3:  # RGB
        gray = (
            0.299 * image_tensor[0] + 0.587 * image_tensor[1] + 0.114 * image_tensor[2]
        )
    else:  # 单通道
        gray = image_tensor[0]

    h, w = gray.shape
    edge_width = w // 20  # 边缘宽度为图像宽度的5%
    edge_height = h // 20  # 边缘高度为图像高度的5%

    # 检查四个角
    return {
        "top_left": gray[:edge_height, :edge_width].mean().item(),
        "top_right": gray[:edge_height, -edge_width:].mean().item(),
        "bottom_left": gray[-edge_height:, :edge_width].mean().item(),
        "bottom_right": gray[-edge_height:, -edge_width:].mean().item(),
    }


def check_view_obstruction_or_blind_spots(
    repo_path: str | Path,
    episode_index: int | None = None,
    batch_size: int = 32,
    num_workers: int = 4,
) -> None:
    """
    检测相机视野是否存在遮挡和盲区

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

    logging.info("Starting Rerun - View Obstruction or Blind Spots Check")
    rr.init(f"{str(repo_path)}_qc_view_obstruction", spawn=True)
    gc.collect()

    logging.info("Checking View Obstruction and Blind Spots")

    # 统计每个相机的遮挡情况
    camera_keys = dataset.meta.camera_keys
    occlusion_stats = {camera: [] for camera in camera_keys}
    corner_coverage_stats = {
        camera: {
            corner: []
            for corner in ["top_left", "top_right", "bottom_left", "bottom_right"]
        }
        for camera in camera_keys
    }

    # 第一遍：收集统计数据
    for batch in tqdm.tqdm(
        dataloader, total=len(dataloader), desc="Analyzing obstruction"
    ):
        for i in range(len(batch["index"])):
            for camera_key in camera_keys:
                if camera_key in batch:
                    image = batch[camera_key][i]

                    # 检测遮挡
                    has_occlusion, black_ratio = detect_potential_occlusion(image)
                    occlusion_stats[camera_key].append(
                        {
                            "frame": batch["frame_index"][i].item(),
                            "has_occlusion": has_occlusion,
                            "black_ratio": black_ratio,
                        }
                    )

                    # 检测边缘覆盖
                    corners = detect_edge_coverage(image)
                    for corner_name, value in corners.items():
                        corner_coverage_stats[camera_key][corner_name].append(value)

    # 分析遮挡统计
    for camera_key, stats in occlusion_stats.items():
        occlusion_frames = [s for s in stats if s["has_occlusion"]]
        black_ratios = [s["black_ratio"] for s in stats]

        logging.info(f"\n{camera_key}:")
        logging.info(
            f"  Total frames with occlusion: {len(occlusion_frames)}/{len(stats)}"
        )
        logging.info(f"  Average black pixel ratio: {np.mean(black_ratios):.4f}")
        logging.info(f"  Max black pixel ratio: {np.max(black_ratios):.4f}")

        if len(occlusion_frames) > 0:
            logging.warning(
                f"  Occlusion detected in frames: {[s['frame'] for s in occlusion_frames[:5]]}..."
            )

    # 分析边缘覆盖
    for camera_key, corners in corner_coverage_stats.items():
        logging.info(f"\n{camera_key} edge coverage (brightness):")
        for corner_name, values in corners.items():
            logging.info(
                f"  {corner_name}: mean={np.mean(values):.4f}, std={np.std(values):.4f}"
            )

    # 第二遍：可视化
    for batch in tqdm.tqdm(dataloader, total=len(dataloader), desc="Visualizing"):
        for i in range(len(batch["index"])):
            rr.set_time_sequence("frame_index", batch["frame_index"][i].item())
            rr.set_time_seconds("timestamp", batch["timestamp"][i].item())

            # 显示相机图像
            for camera_key in camera_keys:
                if camera_key in batch:
                    image = batch[camera_key][i]
                    rr.log(camera_key, rr.Image(to_hwc_uint8_numpy(image)))

                    # 检测遮挡
                    has_occlusion, black_ratio = detect_potential_occlusion(image)
                    corners = detect_edge_coverage(image)

                    # 生成分析文本
                    analysis_text = f"{camera_key} Analysis:\n"
                    analysis_text += (
                        f"Occlusion detected: {'YES' if has_occlusion else 'NO'}\n"
                    )
                    analysis_text += f"Black pixel ratio: {black_ratio:.4f}\n"
                    analysis_text += "\nEdge Coverage (brightness):\n"
                    for corner_name, value in corners.items():
                        analysis_text += f"  {corner_name}: {value:.4f}\n"

                    rr.log(f"{camera_key}/analysis", rr.TextLog(analysis_text))

    logging.info("\nView Obstruction and Blind Spots Check Complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python qc_view_obstruction_or_blind_spots.py <repo_path> [episode_index]"
        )
        print("If episode_index is not provided, a random episode will be selected")
        sys.exit(1)

    repo_path = sys.argv[1]
    episode_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    check_view_obstruction_or_blind_spots(repo_path, episode_index)
