"""
Quality Check: Image Fidelity
检测相机视频是否存在显著噪声、模糊等问题
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


def estimate_noise_level(image_tensor: torch.Tensor) -> float:
    """
    估计图像噪声水平（使用Laplacian算子）

    Args:
        image_tensor: CHW格式的torch张量

    Returns:
        噪声估计值（方差）
    """
    # 转换为灰度
    if image_tensor.shape[0] == 3:  # RGB
        gray = (
            0.299 * image_tensor[0] + 0.587 * image_tensor[1] + 0.114 * image_tensor[2]
        )
    else:  # 单通道
        gray = image_tensor[0]

    # 应用Laplacian算子检测边缘（高频分量）
    # 简单的Laplacian核
    kernel = torch.tensor(
        [
            [-1.0, -1.0, -1.0],
            [-1.0, 8.0, -1.0],
            [-1.0, -1.0, -1.0],
        ],
        dtype=torch.float32,
    )

    # 添加批次和通道维度
    gray_expanded = gray.unsqueeze(0).unsqueeze(0)
    kernel_expanded = kernel.unsqueeze(0).unsqueeze(0)

    # 计算卷积
    try:
        laplacian = torch.nn.functional.conv2d(
            gray_expanded, kernel_expanded, padding=1
        )
        # 计算方差作为噪声估计
        noise_level = laplacian.var().item()
    except Exception as e:
        logging.warning(f"Failed to compute Laplacian: {e}")
        noise_level = 0.0

    return noise_level


def estimate_blur_level(image_tensor: torch.Tensor) -> float:
    """
    估计图像模糊水平（使用Sobel算子的梯度能量）

    Args:
        image_tensor: CHW格式的torch张量

    Returns:
        梯度能量（越高越清晰）
    """
    # 转换为灰度
    if image_tensor.shape[0] == 3:  # RGB
        gray = (
            0.299 * image_tensor[0] + 0.587 * image_tensor[1] + 0.114 * image_tensor[2]
        )
    else:  # 单通道
        gray = image_tensor[0]

    # Sobel X和Y核
    sobel_x = torch.tensor(
        [
            [-1.0, 0.0, 1.0],
            [-2.0, 0.0, 2.0],
            [-1.0, 0.0, 1.0],
        ],
        dtype=torch.float32,
    )

    sobel_y = torch.tensor(
        [
            [-1.0, -2.0, -1.0],
            [0.0, 0.0, 0.0],
            [1.0, 2.0, 1.0],
        ],
        dtype=torch.float32,
    )

    gray_expanded = gray.unsqueeze(0).unsqueeze(0)

    try:
        # 计算梯度
        gx = torch.nn.functional.conv2d(
            gray_expanded, sobel_x.unsqueeze(0).unsqueeze(0), padding=1
        )
        gy = torch.nn.functional.conv2d(
            gray_expanded, sobel_y.unsqueeze(0).unsqueeze(0), padding=1
        )

        # 计算梯度幅度
        gradient_magnitude = torch.sqrt(gx**2 + gy**2)
        # 梯度能量（越高越清晰）
        clarity_score = gradient_magnitude.mean().item()
    except Exception as e:
        logging.warning(f"Failed to compute Sobel: {e}")
        clarity_score = 0.0

    return clarity_score


def calculate_contrast(image_tensor: torch.Tensor) -> float:
    """
    计算图像对比度

    Args:
        image_tensor: CHW格式的torch张量

    Returns:
        对比度（标准差）
    """
    # 转换为灰度
    if image_tensor.shape[0] == 3:  # RGB
        gray = (
            0.299 * image_tensor[0] + 0.587 * image_tensor[1] + 0.114 * image_tensor[2]
        )
    else:  # 单通道
        gray = image_tensor[0]

    return gray.std().item()


def check_image_fidelity(
    repo_path: str | Path,
    episode_index: int | None = None,
    batch_size: int = 32,
    num_workers: int = 4,
) -> None:
    """
    检测相机视频是否存在显著噪声、模糊等问题

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

    logging.info("Starting Rerun - Image Fidelity Check")
    rr.init(f"{str(repo_path)}_qc_image_fidelity", spawn=True)
    gc.collect()

    logging.info("Checking Image Fidelity")

    # 统计每个相机的图像质量
    camera_keys = dataset.meta.camera_keys
    fidelity_stats = {
        camera: {
            "noise_levels": [],
            "blur_levels": [],
            "contrast_levels": [],
            "frame_indices": [],
        }
        for camera in camera_keys
    }

    # 第一遍：收集统计数据
    for batch in tqdm.tqdm(
        dataloader, total=len(dataloader), desc="Analyzing image quality"
    ):
        for i in range(len(batch["index"])):
            for camera_key in camera_keys:
                if camera_key in batch:
                    image = batch[camera_key][i]

                    # 计算图像质量指标
                    noise = estimate_noise_level(image)
                    blur = estimate_blur_level(image)
                    contrast = calculate_contrast(image)

                    fidelity_stats[camera_key]["noise_levels"].append(noise)
                    fidelity_stats[camera_key]["blur_levels"].append(blur)
                    fidelity_stats[camera_key]["contrast_levels"].append(contrast)
                    fidelity_stats[camera_key]["frame_indices"].append(
                        batch["frame_index"][i].item()
                    )

    # 分析图像质量统计
    for camera_key, stats in fidelity_stats.items():
        noise_levels = np.array(stats["noise_levels"])
        blur_levels = np.array(stats["blur_levels"])
        contrast_levels = np.array(stats["contrast_levels"])

        logging.info(f"\n{camera_key} Image Quality Analysis:")
        logging.info("  Noise Level:")
        logging.info(f"    Mean: {np.mean(noise_levels):.6f}")
        logging.info(f"    Std: {np.std(noise_levels):.6f}")
        logging.info(f"    Max: {np.max(noise_levels):.6f}")

        logging.info("  Clarity (blur level - higher is better):")
        logging.info(f"    Mean: {np.mean(blur_levels):.6f}")
        logging.info(f"    Std: {np.std(blur_levels):.6f}")
        logging.info(f"    Min: {np.min(blur_levels):.6f}")

        logging.info("  Contrast:")
        logging.info(f"    Mean: {np.mean(contrast_levels):.6f}")
        logging.info(f"    Std: {np.std(contrast_levels):.6f}")
        logging.info(f"    Min: {np.min(contrast_levels):.6f}")

        # 检测低质量帧
        low_clarity_frames = np.where(blur_levels < np.percentile(blur_levels, 10))[0]
        if len(low_clarity_frames) > 0:
            logging.warning(
                f"  Low clarity frames (bottom 10%): {[stats['frame_indices'][idx] for idx in low_clarity_frames[:5]]}..."
            )

        high_noise_frames = np.where(noise_levels > np.percentile(noise_levels, 90))[0]
        if len(high_noise_frames) > 0:
            logging.warning(
                f"  High noise frames (top 10%): {[stats['frame_indices'][idx] for idx in high_noise_frames[:5]]}..."
            )

        low_contrast_frames = np.where(
            contrast_levels < np.percentile(contrast_levels, 10)
        )[0]
        if len(low_contrast_frames) > 0:
            logging.warning(
                f"  Low contrast frames (bottom 10%): {[stats['frame_indices'][idx] for idx in low_contrast_frames[:5]]}..."
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

                    # 计算质量指标
                    noise = estimate_noise_level(image)
                    blur = estimate_blur_level(image)
                    contrast = calculate_contrast(image)

                    # 生成质量报告
                    quality_text = f"{camera_key} Quality Metrics:\n"
                    quality_text += f"Noise Level: {noise:.6f}\n"
                    quality_text += f"Clarity Score: {blur:.6f}\n"
                    quality_text += f"Contrast: {contrast:.6f}\n"
                    quality_text += "\nQuality Assessment:\n"

                    # 质量评估
                    if blur < 0.001:
                        quality_text += "  Clarity: POOR (blurry)\n"
                    elif blur < 0.005:
                        quality_text += "  Clarity: FAIR\n"
                    else:
                        quality_text += "  Clarity: GOOD\n"

                    if noise > 0.01:
                        quality_text += "  Noise: HIGH\n"
                    elif noise > 0.005:
                        quality_text += "  Noise: MODERATE\n"
                    else:
                        quality_text += "  Noise: LOW\n"

                    if contrast < 0.1:
                        quality_text += "  Contrast: LOW\n"
                    elif contrast < 0.2:
                        quality_text += "  Contrast: FAIR\n"
                    else:
                        quality_text += "  Contrast: GOOD\n"

                    rr.log(f"{camera_key}/quality", rr.TextLog(quality_text))

    logging.info("\nImage Fidelity Check Complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python qc_image_fidelity.py <repo_path> [episode_index]")
        print("If episode_index is not provided, a random episode will be selected")
        sys.exit(1)

    repo_path = sys.argv[1]
    episode_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    check_image_fidelity(repo_path, episode_index)
