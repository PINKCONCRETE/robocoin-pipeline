#!/usr/bin/env python3
"""
视频连续静止帧检测脚本

检测视频中是否存在过多连续的几乎完全相同的帧（表示视频可能卡住或损坏）

使用方法:
    python qc_consecutive_static_frames.py <video_file_path> --phash_dist_threshold 5
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
    phash = "".join(["1" if x > avg else "0" for x in dct_left.flatten()])

    return phash


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个哈希的汉明距离"""
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def check_consecutive_static_frames(
    video_path: Path,
    phash_dist_threshold: float = 5,
    static_frames_threshold: int = 10,
    logger: logging.Logger | None = None,
) -> dict:
    """
    检测视频中的连续静止帧

    Args:
        video_path: 视频文件路径
        phash_dist_threshold: pHash距离阈值 (0-64, 越小表示帧越相似)
        static_frames_threshold: 被视为"连续静止"的帧数阈值
        logger: 日志对象

    Returns:
        检查结果字典
    """
    result = {
        "total_frames": 0,
        "static_frame_groups": [],  # [(start_idx, end_idx, count), ...]
        "max_static_frames": 0,
        "has_excessive_static": False,
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
        logger.info(
            f"pHash threshold: {phash_dist_threshold}, Static threshold: {static_frames_threshold} frames"
        )

    prev_hash = None
    static_group_start = None
    static_count = 0
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
                static_count = 1
                static_group_start = frame_idx
                continue

            # 计算汉明距离
            distance = hamming_distance(prev_hash, current_hash)

            if distance <= phash_dist_threshold:
                # 相似帧
                static_count += 1
            else:
                # 不相似帧，结束之前的静止组
                if static_count >= static_frames_threshold:
                    group = (static_group_start, frame_idx - 1, static_count)
                    result["static_frame_groups"].append(group)

                    if logger:
                        logger.warning(
                            f"⚠️ Found consecutive static frames: "
                            f"frames {static_group_start}-{frame_idx-1} ({static_count} frames)"
                        )

                if static_count > result["max_static_frames"]:
                    result["max_static_frames"] = static_count

                # 开始新的静止组
                prev_hash = current_hash
                static_count = 1
                static_group_start = frame_idx

            # 进度输出（每100帧）
            if frame_idx % 100 == 0 and logger:
                logger.debug(f"Processed {frame_idx} frames...")

    except Exception as e:
        result["errors"].append(
            f"Error processing frames: {type(e).__name__}: {str(e)}"
        )
        if logger:
            logger.error(f"❌ Error processing frames: {str(e)}")

    # 处理最后一组
    if static_count >= static_frames_threshold:
        group = (static_group_start, frame_idx, static_count)
        result["static_frame_groups"].append(group)

        if logger:
            logger.warning(
                f"⚠️ Found consecutive static frames at end: "
                f"frames {static_group_start}-{frame_idx} ({static_count} frames)"
            )

    if static_count > result["max_static_frames"]:
        result["max_static_frames"] = static_count

    result["total_frames"] = frame_idx

    # 计算评分
    if result["static_frame_groups"]:
        result["has_excessive_static"] = True
        # 评分基于最长的静止帧组占总帧数的比例
        proportion = result["max_static_frames"] / frame_idx
        result["score"] = max(0, 1.0 - proportion)

        if logger:
            logger.error("❌ Video has excessive static frames")
    else:
        result["score"] = 1.0
        if logger:
            logger.info("✅ No excessive consecutive static frames detected")

    container.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检测视频中的连续静止帧",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认阈值
  python qc_consecutive_static_frames.py /path/to/video.mp4

  # 自定义阈值
  python qc_consecutive_static_frames.py /path/to/video.mp4 \\
    --phash_dist_threshold 3 --static_frames_threshold 20
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--phash_dist_threshold",
        type=float,
        default=5,
        help="pHash汉明距离阈值，低于此值的帧被认为相同 (0-64, 默认: 5)",
    )

    parser.add_argument(
        "--static_frames_threshold",
        type=int,
        default=10,
        help="连续相同帧数的阈值 (默认: 10)",
    )

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(
        name="QC_CONSECUTIVE_STATIC", log_dir=log_dir, level=logging.INFO
    )

    logger.info(f"Checking consecutive static frames: {video_path}")

    result = check_consecutive_static_frames(
        video_path, args.phash_dist_threshold, args.static_frames_threshold, logger
    )

    print("\n" + "=" * 80)
    print("CONSECUTIVE STATIC FRAMES CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Total Frames: {result['total_frames']}")
    print(f"Max Consecutive Static Frames: {result['max_static_frames']}")
    print(f"Score (0-1): {result['score']:.3f}")
    print(
        f"Status: {'✅ OK' if not result['has_excessive_static'] else '❌ PROBLEM DETECTED'}"
    )

    if result["static_frame_groups"]:
        print(f"\nStatic Frame Groups ({len(result['static_frame_groups'])}):")
        for start, end, count in result["static_frame_groups"]:
            print(f"  Frames {start}-{end}: {count} consecutive static frames")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    print("=" * 80)

    return 1 if result["has_excessive_static"] or result["errors"] else 0


if __name__ == "__main__":
    exit(main())
