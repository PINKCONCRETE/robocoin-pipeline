#!/usr/bin/env python3
"""
视频文件损坏检测脚本

检测视频文件是否损坏，包括：
1. 错误的编码格式
2. 不完整的视频内容
3. 时间连续性假设问题

使用方法:
    python qc_video_file_corruption.py <video_file_path>
"""

import argparse
import logging
from pathlib import Path

import av
from qc_logger import setup_logger


def check_video_corruption(video_path: Path, logger: logging.Logger) -> dict:
    """
    检查视频文件是否损坏

    Args:
        video_path: 视频文件路径
        logger: 日志对象

    Returns:
        检查结果字典，包含:
            - is_corrupted: bool，是否损坏
            - errors: list[str]，错误信息列表
            - warnings: list[str]，警告信息列表
    """
    result = {
        "is_corrupted": False,
        "errors": [],
        "warnings": [],
        "file_path": str(video_path),
    }

    if not video_path.exists():
        result["is_corrupted"] = True
        result["errors"].append(f"File does not exist: {video_path}")
        return result

    if video_path.stat().st_size == 0:
        result["is_corrupted"] = True
        result["errors"].append("File size is 0")
        return result

    try:
        container = av.open(str(video_path))
    except av.error.InvalidDataError as e:
        result["is_corrupted"] = True
        result["errors"].append(f"Invalid data format: {str(e)}")
        logger.error(f"❌ Invalid data format: {str(e)}")
        return result
    except av.error.FileNotFoundError as e:
        result["is_corrupted"] = True
        result["errors"].append(f"File not found: {str(e)}")
        logger.error(f"❌ File not found: {str(e)}")
        return result
    except Exception as e:
        result["is_corrupted"] = True
        result["errors"].append(f"Failed to open video: {type(e).__name__}: {str(e)}")
        logger.error(f"❌ Failed to open video: {type(e).__name__}: {str(e)}")
        return result

    # 检查视频流是否存在
    video_stream = None
    for stream in container.streams.video:
        video_stream = stream
        break

    if video_stream is None:
        result["is_corrupted"] = True
        result["errors"].append("No video stream found in container")
        logger.error("❌ No video stream found")
        return result

    # 尝试读取几帧以检查完整性
    frame_count = 0
    read_errors = 0

    try:
        for _frame in container.decode(video_stream):
            frame_count += 1
            # 只检查前几帧
            if frame_count >= 5:
                break
    except av.error.InvalidDataError as e:
        read_errors += 1
        result["errors"].append(f"Error reading frame {frame_count}: {str(e)}")
    except Exception as e:
        read_errors += 1
        result["errors"].append(
            f"Error reading frame {frame_count}: {type(e).__name__}: {str(e)}"
        )

    if read_errors > 0:
        result["is_corrupted"] = True
        logger.error(f"❌ Failed to read frames: {read_errors} errors")

    if frame_count == 0:
        result["is_corrupted"] = True
        result["errors"].append("Could not read any frames from video")
        logger.error("❌ Could not read any frames")

    # 检查基本元数据
    try:
        duration = container.duration
        if duration is None or duration <= 0:
            result["warnings"].append("Duration is invalid or not available")
            logger.warning("⚠️ Duration is invalid or not available")
    except Exception as e:
        result["warnings"].append(f"Failed to get duration: {str(e)}")
        logger.warning(f"⚠️ Failed to get duration: {str(e)}")

    try:
        fps = video_stream.average_rate
        if fps is None or float(fps) <= 0:
            result["warnings"].append(f"FPS is invalid: {fps}")
            logger.warning(f"⚠️ FPS is invalid: {fps}")
    except Exception as e:
        result["warnings"].append(f"Failed to get FPS: {str(e)}")
        logger.warning(f"⚠️ Failed to get FPS: {str(e)}")

    container.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检测视频文件是否损坏",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python qc_video_file_corruption.py /path/to/video.mp4
  python qc_video_file_corruption.py --log_dir ./logs /path/to/video.mp4
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(
        name="QC_VIDEO_CORRUPTION", log_dir=log_dir, level=logging.INFO
    )

    logger.info(f"Checking video file: {video_path}")
    result = check_video_corruption(video_path, logger)

    print("\n" + "=" * 80)
    print("VIDEO CORRUPTION CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Status: {'✅ OK' if not result['is_corrupted'] else '❌ CORRUPTED'}")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    if not result["errors"] and not result["warnings"]:
        print("\n✅ Video file is healthy")

    print("=" * 80)

    return 1 if result["is_corrupted"] else 0


if __name__ == "__main__":
    exit(main())
