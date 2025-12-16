#!/usr/bin/env python3
"""
视频帧跳变检测脚本

检测视频中是否存在由于关键帧遗漏、画面过度等导致的帧跳变

使用方法:
    python qc_drop_frame.py <video_file_path> --phash_dist_threshold 15
"""

import argparse
import logging
from pathlib import Path

import av
import cv2
import numpy as np
from qc_logger import setup_logger


def compute_phash(image: np.ndarray, hash_size: int = 8) -> str:
    """
    计算图像的感知哈希 (pHash)

    Args:
        image: 输入图像 (BGR格式)
        hash_size: 哈希大小 (默认 8x8)

    Returns:
        哈希字符串
    """
    # 转换为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 调整大小
    resized = cv2.resize(gray, (hash_size, hash_size))

    # 计算DCT
    dct = cv2.dct(np.float32(resized))

    # 取左上角8x8区域的平均值
    dct_left = dct[:8, :8]
    avg = np.mean(dct_left)

    # 生成二进制哈希
    return "".join(["1" if x > avg else "0" for x in dct_left.flatten()])


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个哈希的汉明距离"""
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def check_frame_drops(
    video_path: Path,
    phash_dist_threshold: float = 15,
    logger: logging.Logger | None = None,
) -> dict:
    """
    检测视频中的帧跳变（使用pHash计算相邻帧的相似度变化）

    Args:
        video_path: 视频文件路径
        phash_dist_threshold: pHash距离阈值，超过此值表示可能存在帧跳变
        logger: 日志对象

    Returns:
        检查结果字典
    """
    result = {
        "total_frames": 0,
        "drop_frame_locations": [],  # [(frame_idx, distance), ...]
        "max_distance": 0,
        "avg_distance": 0,
        "drop_frame_count": 0,
        "has_drop_frames": False,
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
        logger.info(f"Drop frame detection threshold: {phash_dist_threshold}")

    prev_hash = None
    distances = []
    frame_idx = 0

    try:
        for frame in container.decode(video_stream):
            frame_idx += 1

            # 转换为 numpy 数组并转换为 BGR
            image = frame.to_ndarray(format="bgr24")

            # 计算 pHash
            current_hash = compute_phash(image)

            if prev_hash is None:
                prev_hash = current_hash
                continue

            # 计算汉明距离
            distance = hamming_distance(prev_hash, current_hash)
            distances.append(distance)

            if distance > phash_dist_threshold:
                # 可能存在帧跳变
                result["drop_frame_locations"].append((frame_idx, distance))

                if logger:
                    logger.warning(
                        f"⚠️ Large frame difference at frame {frame_idx}: distance={distance}"
                    )

            result["max_distance"] = max(result["max_distance"], distance)
            prev_hash = current_hash

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
    result["drop_frame_count"] = len(result["drop_frame_locations"])

    # 计算平均距离
    if distances:
        result["avg_distance"] = np.mean(distances)

        # 计算评分：基于drop frames 的比例
        proportion = result["drop_frame_count"] / len(distances)
        result["score"] = max(0, 1.0 - proportion)

        if result["drop_frame_count"] > 0:
            result["has_drop_frames"] = True
            if logger:
                logger.error(
                    f"❌ Detected {result['drop_frame_count']} potential frame drops"
                )
        else:
            if logger:
                logger.info("✅ No frame drops detected")

    container.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检测视频中的帧跳变",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认阈值
  python qc_drop_frame.py /path/to/video.mp4

  # 自定义阈值（更严格的检测）
  python qc_drop_frame.py /path/to/video.mp4 --phash_dist_threshold 10

  # 自定义阈值（更宽松的检测）
  python qc_drop_frame.py /path/to/video.mp4 --phash_dist_threshold 20
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--phash_dist_threshold",
        type=float,
        default=15,
        help="pHash汉明距离阈值，超过此值表示可能存在帧跳变 (0-64, 默认: 15)",
    )

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(name="QC_DROP_FRAME", log_dir=log_dir, level=logging.INFO)

    logger.info(f"Checking frame drops: {video_path}")

    result = check_frame_drops(video_path, args.phash_dist_threshold, logger)

    print("\n" + "=" * 80)
    print("FRAME DROP CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Total Frames: {result['total_frames']}")
    print(f"Potential Frame Drops: {result['drop_frame_count']}")
    print(f"Max Frame Distance: {result['max_distance']}")
    print(f"Average Frame Distance: {result['avg_distance']:.2f}")
    print(f"Score (0-1): {result['score']:.3f}")
    print(
        f"Status: {'✅ OK' if not result['has_drop_frames'] else '❌ PROBLEM DETECTED'}"
    )

    if result["drop_frame_locations"]:
        print("\nPotential Frame Drop Locations (first 10):")
        for frame_idx, distance in result["drop_frame_locations"][:10]:
            print(f"  Frame {frame_idx}: distance={distance}")

        if len(result["drop_frame_locations"]) > 10:
            print(f"  ... and {len(result['drop_frame_locations']) - 10} more")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    print("=" * 80)

    return 1 if result["has_drop_frames"] or result["errors"] else 0


if __name__ == "__main__":
    exit(main())
