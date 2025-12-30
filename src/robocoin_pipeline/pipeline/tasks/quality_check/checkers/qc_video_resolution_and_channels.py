#!/usr/bin/env python3
"""
视频分辨率和通道检查脚本

检测视频分辨率、通道数是否与预期一致

使用方法:
    python qc_video_resolution_and_channels.py <video_file_path> --expected_width 640 --expected_height 480
"""

import argparse
import logging
from pathlib import Path

import av
from qc_logger import setup_logger


def check_resolution_and_channels(
    video_path: Path,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_channels: int | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """
    检查视频分辨率和通道数

    Args:
        video_path: 视频文件路径
        expected_width: 预期宽度
        expected_height: 预期高度
        expected_channels: 预期通道数 (3=RGB, 4=RGBA, etc.)
        logger: 日志对象

    Returns:
        检查结果字典
    """
    result = {
        "width": None,
        "height": None,
        "channels": None,
        "pixel_format": None,
        "expected_width": expected_width,
        "expected_height": expected_height,
        "expected_channels": expected_channels,
        "resolution_match": expected_width is None or expected_height is None,
        "channels_match": expected_channels is None,
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

    # 获取分辨率
    try:
        result["width"] = video_stream.width
        result["height"] = video_stream.height
        result["pixel_format"] = str(video_stream.pix_fmt)

        if logger:
            logger.info(
                f"📊 Resolution: {result['width']}x{result['height']}, Format: {result['pixel_format']}"
            )

        # 检查分辨率是否匹配
        if expected_width is not None and expected_height is not None:
            if (
                result["width"] == expected_width
                and result["height"] == expected_height
            ):
                result["resolution_match"] = True
                if logger:
                    logger.info(
                        f"✅ Resolution matches: {result['width']}x{result['height']}"
                    )
            else:
                result["resolution_match"] = False
                result["errors"].append(
                    f"Resolution mismatch: actual={result['width']}x{result['height']}, "
                    f"expected={expected_width}x{expected_height}"
                )
                if logger:
                    logger.error("❌ Resolution mismatch")
    except Exception as e:
        result["errors"].append(
            f"Error getting resolution: {type(e).__name__}: {str(e)}"
        )
        if logger:
            logger.error(f"❌ Error getting resolution: {str(e)}")

    # 尝试读取一帧以获取通道信息
    try:
        for frame in container.decode(video_stream):
            # 获取帧的格式信息
            if frame.format.name:
                result["pixel_format"] = frame.format.name

                # 从像素格式推断通道数
                pix_fmt = frame.format.name.lower()
                if "rgb" in pix_fmt or "bgr" in pix_fmt:
                    if "a" in pix_fmt or "rgba" in pix_fmt:
                        result["channels"] = 4
                    else:
                        result["channels"] = 3
                elif "yuv" in pix_fmt or "yuvj" in pix_fmt:
                    # YUV 格式通常包含Y和UV分量
                    # 但在整体上被视为3通道（需要转换为RGB）
                    result["channels"] = 3
                elif "gray" in pix_fmt or "mono" in pix_fmt:
                    result["channels"] = 1
                else:
                    # 默认尝试 3 通道
                    result["channels"] = 3

            if logger:
                logger.info(
                    f"📊 Detected channels: {result['channels']}, Pixel format: {result['pixel_format']}"
                )

            # 检查通道数是否匹配
            if expected_channels is not None and result["channels"] is not None:
                if result["channels"] == expected_channels:
                    result["channels_match"] = True
                    if logger:
                        logger.info(f"✅ Channels match: {result['channels']}")
                else:
                    result["channels_match"] = False
                    result["errors"].append(
                        f"Channel count mismatch: actual={result['channels']}, expected={expected_channels}"
                    )
                    if logger:
                        logger.error("❌ Channel count mismatch")

            # 只需要第一帧
            break
    except Exception as e:
        result["warnings"].append(
            f"Could not verify channels from frame: {type(e).__name__}: {str(e)}"
        )
        if logger:
            logger.warning(f"⚠️ Could not verify channels: {str(e)}")

    container.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查视频分辨率和通道数",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查分辨率
  python qc_video_resolution_and_channels.py /path/to/video.mp4 --expected_width 1920 --expected_height 1080

  # 检查通道数
  python qc_video_resolution_and_channels.py /path/to/video.mp4 --expected_channels 3

  # 检查所有项
  python qc_video_resolution_and_channels.py /path/to/video.mp4 \\
    --expected_width 1920 --expected_height 1080 --expected_channels 3
        """,
    )

    parser.add_argument("video_path", type=str, help="视频文件路径")

    parser.add_argument(
        "--expected_width", type=int, default=None, help="预期宽度（像素）"
    )

    parser.add_argument(
        "--expected_height", type=int, default=None, help="预期高度（像素）"
    )

    parser.add_argument(
        "--expected_channels",
        type=int,
        default=None,
        help="预期通道数 (1=Gray, 3=RGB, 4=RGBA)",
    )

    parser.add_argument(
        "--log_dir", type=str, default="./logs", help="日志目录 (默认: ./logs)"
    )

    args = parser.parse_args()

    video_path = Path(args.video_path)
    log_dir = Path(args.log_dir)

    logger = setup_logger(
        name="QC_VIDEO_RESOLUTION", log_dir=log_dir, level=logging.INFO
    )

    logger.info(f"Checking video resolution and channels: {video_path}")

    result = check_resolution_and_channels(
        video_path,
        args.expected_width,
        args.expected_height,
        args.expected_channels,
        logger,
    )

    print("\n" + "=" * 80)
    print("VIDEO RESOLUTION AND CHANNELS CHECK RESULT")
    print("=" * 80)
    print(f"File: {result['file_path']}")
    print(f"Resolution: {result['width']}x{result['height']}")
    print(f"Channels: {result['channels']}")
    print(f"Pixel Format: {result['pixel_format']}")

    if args.expected_width and args.expected_height:
        print(
            f"Resolution Status: {'✅ MATCH' if result['resolution_match'] else '❌ MISMATCH'}"
        )

    if args.expected_channels:
        print(
            f"Channels Status: {'✅ MATCH' if result['channels_match'] else '❌ MISMATCH'}"
        )

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"  ❌ {error}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"  ⚠️ {warning}")

    if not result["errors"]:
        print("\n✅ Video resolution and channels are valid")

    print("=" * 80)

    return (
        1
        if result["errors"]
        or not result["resolution_match"]
        or not result["channels_match"]
        else 0
    )


if __name__ == "__main__":
    exit(main())
