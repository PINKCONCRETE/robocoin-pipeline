#!/usr/bin/env python3
"""
视频画面色差检测脚本

检测相邻帧的颜色是否存在过大的差异（可能表示编码问题或画面抖动）

使用方法:
    python qc_color_shift_artifacts.py <video_file_path> --color_diff_threshold 30
"""

import argparse
import logging
from pathlib import Path

import av
import cv2
import numpy as np
from qc_logger import setup_logger


def compute_color_histogram(image: np.ndarray, bins: int = 32) -> np.ndarray:
    """
    计算图像的颜色直方图

    Args:
        image: 输入图像 (BGR格式)
        bins: 直方图的bin数量

    Returns:
        颜色直方图向量
    """
    # 对每个通道计算直方图
    hist = []
    for i in range(3):
        h = cv2.calcHist([image], [i], None, [bins], [0, 256])
        hist.append(h.flatten())

    # 归一化并合并
    hist = np.concatenate(hist)
    hist = hist / (np.sum(hist) + 1e-6)

    return hist


def histogram_distance(hist1: np.ndarray, hist2: np.ndarray) -> float:
    """
    计算两个直方图的距离（使用L2距离）

    Args:
        hist1: 第一个直方图
        hist2: 第二个直方图

    Returns:
        直方图距离
    """
    return np.linalg.norm(hist1 - hist2)


def compute_mean_colors(image: np.ndarray) -> dict:
    """
    计算图像各通道的平均颜色

    Args:
        image: 输入图像 (BGR格式)

    Returns:
        各通道平均颜色字典
    """
    return {
        "B": np.mean(image[:, :, 0]),
        "G": np.mean(image[:, :, 1]),
        "R": np.mean(image[:, :, 2]),
    }


def check_color_artifacts(
    video_path: Path,
    color_diff_threshold: float = 30,
    logger: logging.Logger | None = None,
) -> dict:
    """
    检测视频中的色差问题

    Args:
        video_path: 视频文件路径
        color_diff_threshold: 颜色差异阈值 (0-255)
        logger: 日志对象

    Returns:
        检查结果字典
    """
    result = {
        "total_frames": 0,
        "color_shift_locations": [],  # [(frame_idx, diff), ...]
        "max_color_diff": 0,
        "avg_color_diff": 0,
        "color_shift_count": 0,
        "has_color_artifacts": False,
        "score": 1.0,  # 评分 0-1，1 为最好
        "errors": [],
        "warnings": [],
        "file_path": str(video_path),
    }

    if not video_path.exists():
        result["errors"].append(f"File does not exist: {video_path}")
        if logger:
            logger.error(f"❌ File does not exist: {video_path}")
        return result

    try:
        container = av.open(str(video_path))
    except Exception as e:
        result["errors"].append(f"Failed to open video: {type(e).__name__}: {str(e)}")
        if logger:
            logger.error(f"❌ Failed to open video: {str(e)}")
        return result

    # 获取视频流
    video_stream = None
    for stream in container.streams.video:
        video_stream = stream
        break

    if video_stream is None:
        result["errors"].append("No video stream found")
        if logger:
            logger.error("❌ No video stream found")
        container.close()
        return result

    if logger:
        logger.info(f"Processing video: {video_path}")
        logger.info(f"Color difference threshold: {color_diff_threshold}")

    prev_mean_colors = None
    color_diffs = []
    frame_idx = 0

    try:
        for frame in container.decode(video_stream):
            frame_idx += 1

            # 转换为 numpy 数组并转换为 BGR
            image = frame.to_ndarray(format="bgr24")

            # 计算平均颜色
            current_mean_colors = compute_mean_colors(image)

            if prev_mean_colors is None:
                prev_mean_colors = current_mean_colors
                continue

            # 计算颜色差异（各通道差异的最大值）
            color_diff = max(
                abs(current_mean_colors["B"] - prev_mean_colors["B"]),
                abs(current_mean_colors["G"] - prev_mean_colors["G"]),
                abs(current_mean_colors["R"] - prev_mean_colors["R"]),
            )

            color_diffs.append(color_diff)

            if color_diff > color_diff_threshold:
                # 检测到色差
                result["color_shift_locations"].append((frame_idx, color_diff))

                if logger:
                    logger.warning(
                        f"⚠️ Color shift at frame {frame_idx}: diff={color_diff:.1f}"
                    )

            result["max_color_diff"] = max(result["max_color_diff"], color_diff)
            prev_mean_colors = current_mean_colors

            # 进度输出
            if frame_idx % 100 == 0 and logger:
                logger.debug(f"Processed {frame_idx} frames...")

    except Exception as e:
        result["errors"].append(
            f"Error processing frames: {type(e).__name__}: {str(e)}"
        )
        if logger:
            logger.error(f"❌ Error processing frames: {str(e)}")

    result["total_frames"] = frame_idx
    result["color_shift_count"] = len(result["color_shift_locations"])

    # 计算平均颜色差异
    if color_diffs:
        result["avg_color_diff"] = np.mean(color_diffs)

        # 计算评分：基于color shift 的比例
        proportion = result["color_shift_count"] / len(color_diffs)
        result["score"] = max(0, 1.0 - proportion * 0.5)  # 影响相对较小

        if result["color_shift_count"] > 0:
            result["has_color_artifacts"] = True
            if logger:
                logger.error(f"❌ Detected {result['color_shift_count']} color shifts")
        else:
            if logger:
                logger.info("✅ No significant color shifts detected")

    container.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检测视频中的画面色差",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认阈值
  python qc_color_shift_artifacts.py /path/to/video.mp4

  # 自定义阈值（更严格的检测）
  python qc_color_shift_artifacts.py /path/to/video.mp4 --color_diff_threshold 20

  # 自定义阈值（更宽松的检测）
  python qc_color_shift_artifacts.py /path/to/video.mp4 --color_diff_threshold 50
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--color_diff_threshold",
        type=float,
        default=30,
        help="颜色差异阈值，超过此值表示存在色差 (0-255, 默认: 30)",
    )

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(name="QC_COLOR_SHIFT", log_dir=log_dir, level=logging.INFO)

    logger.info(f"Checking color artifacts: {video_path}")

    result = check_color_artifacts(video_path, args.color_diff_threshold, logger)

    print("\n" + "=" * 80)
    print("COLOR SHIFT ARTIFACTS CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Total Frames: {result['total_frames']}")
    print(f"Color Shifts Detected: {result['color_shift_count']}")
    print(f"Max Color Difference: {result['max_color_diff']:.1f}")
    print(f"Average Color Difference: {result['avg_color_diff']:.1f}")
    print(f"Score (0-1): {result['score']:.3f}")
    print(
        f"Status: {'✅ OK' if not result['has_color_artifacts'] else '⚠️ PROBLEM DETECTED'}"
    )

    if result["color_shift_locations"]:
        print("\nColor Shift Locations (first 10):")
        for frame_idx, diff in result["color_shift_locations"][:10]:
            print(f"  Frame {frame_idx}: diff={diff:.1f}")

        if len(result["color_shift_locations"]) > 10:
            print(f"  ... and {len(result['color_shift_locations']) - 10} more")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    print("=" * 80)

    return 1 if result["errors"] else 0


if __name__ == "__main__":
    exit(main())
