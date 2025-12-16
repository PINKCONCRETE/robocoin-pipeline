#!/usr/bin/env python3
"""
视频帧数校验脚本

检测视频帧数是否与episode信息中的长度一致

使用方法:
    python qc_video_frame_count.py <video_file_path> <expected_frame_count>
"""

import argparse
import logging
from pathlib import Path

import av
from qc_logger import setup_logger


def check_frame_count(
    video_path: Path,
    expected_count: int | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """
    检查视频帧数是否与预期一致

    Args:
        video_path: 视频文件路径
        expected_count: 预期的帧数，为None时仅统计
        logger: 日志对象

    Returns:
        检查结果字典，包含:
            - actual_frame_count: int，实际帧数
            - expected_frame_count: int | None，预期帧数
            - is_match: bool，是否匹配
            - errors: list[str]，错误信息列表
            - warnings: list[str]，警告信息列表
    """
    result = {
        "actual_frame_count": 0,
        "expected_frame_count": expected_count,
        "is_match": expected_count is None,  # 如果没有预期值，默认为True
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

    # 方法1: 尝试从流信息中获取帧数
    frame_count = 0
    try:
        if video_stream.nb_frames is not None and video_stream.nb_frames > 0:
            frame_count = video_stream.nb_frames
            if logger:
                logger.info(f"📊 Got frame count from stream metadata: {frame_count}")
        else:
            # 方法2: 逐帧计数（较慢，但准确）
            for _frame in container.decode(video_stream):
                frame_count += 1

            if logger:
                logger.info(f"📊 Counted frames by decoding: {frame_count}")
    except Exception as e:
        result["errors"].append(f"Error counting frames: {type(e).__name__}: {str(e)}")
        if logger:
            logger.error(f"❌ Error counting frames: {str(e)}")
        container.close()
        return result

    result["actual_frame_count"] = frame_count

    if expected_count is not None:
        if frame_count == expected_count:
            result["is_match"] = True
            if logger:
                logger.info(
                    f"✅ Frame count matches: {frame_count} == {expected_count}"
                )
        else:
            result["is_match"] = False
            diff = frame_count - expected_count
            result["errors"].append(
                f"Frame count mismatch: actual={frame_count}, expected={expected_count}, diff={diff:+d}"
            )
            if logger:
                logger.error(
                    f"❌ Frame count mismatch: actual={frame_count}, expected={expected_count}, diff={diff:+d}"
                )

    # 获取其他元数据
    try:
        fps = video_stream.average_rate
        duration = container.duration

        if fps and duration:
            fps_value = float(fps)
            duration_seconds = float(duration) / av.time_base.denominator
            expected_from_fps = int(fps_value * duration_seconds)

            if logger:
                logger.info(
                    f"📊 FPS: {fps_value:.2f}, Duration: {duration_seconds:.2f}s, Expected from FPS: {expected_from_fps}"
                )

            if abs(frame_count - expected_from_fps) > 2:
                result["warnings"].append(
                    f"Frame count differs from FPS calculation: actual={frame_count}, calculated={expected_from_fps}"
                )
                if logger:
                    logger.warning("⚠️ Frame count differs from FPS calculation")
    except Exception as e:
        result["warnings"].append(f"Failed to validate FPS/duration: {str(e)}")

    container.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查视频帧数是否与预期一致",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 仅计数帧数
  python qc_video_frame_count.py /path/to/video.mp4

  # 校验帧数是否为1000
  python qc_video_frame_count.py /path/to/video.mp4 --expected_frames 1000

  # 指定日志目录
  python qc_video_frame_count.py /path/to/video.mp4 --expected_frames 1000 --log_dir ./logs
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--expected_frames", type=int, default=None, help="预期的帧数（可选）"
    )

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(
        name="QC_VIDEO_FRAME_COUNT", log_dir=log_dir, level=logging.INFO
    )

    logger.info(f"Checking video frame count: {video_path}")
    if args.expected_frames:
        logger.info(f"Expected frame count: {args.expected_frames}")

    result = check_frame_count(video_path, args.expected_frames, logger)

    print("\n" + "=" * 80)
    print("VIDEO FRAME COUNT CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Actual Frame Count: {result['actual_frame_count']}")

    if result["expected_frame_count"] is not None:
        print(f"Expected Frame Count: {result['expected_frame_count']}")
        print(f"Status: {'✅ MATCH' if result['is_match'] else '❌ MISMATCH'}")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    if not result["errors"] and not result["warnings"]:
        print("\n✅ Video frame count is valid")

    print("=" * 80)

    return 1 if not result["is_match"] or result["errors"] else 0


if __name__ == "__main__":
    exit(main())
