from pathlib import Path

import av
import pyarrow.parquet as pq

from robocoin_pipeline.constants.meta_constant import (
    FRAME_NUM,
    VIDEO_CODEC,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)

from .checker_result import CheckerResult


# 该方法由qc-pipeline调用，不需要注册器装饰器
def qc_data_file_corruption(parquet_file_path: str | Path) -> tuple[bool, dict]:
    """
    检查视频文件是否损坏的示例检查器
    """
    parquet_file_path = Path(parquet_file_path).expanduser().absolute()
    result = CheckerResult()
    flag = True
    if not parquet_file_path.exists():
        result.set_errors("File not found")
        return False, result

    try:
        import pyarrow.parquet as pq

        # 尝试读取 Parquet 文件以检查其完整性
        pq.read_table(parquet_file_path)
    except Exception:
        result.set_errors("File corruption detected")
        flag = False

    return flag, result


def get_parquet_meta(file_path: str | Path) -> dict:
    pf = pq.ParquetFile(file_path)
    meta = pf.metadata
    results = {}
    results[FRAME_NUM] = meta.num_rows
    # other metas


def qc_data_meta_consistency(
    parquet_file_path: str | Path, frame_num: int, task_index: int, episode_index: int
) -> CheckerResult:
    """
    检查数据文件元信息一致性
    """
    result = CheckerResult()
    parquet_meta = get_parquet_meta(parquet_file_path)
    errors = []
    if parquet_meta[FRAME_NUM] != frame_num:
        errors.append(
            f"Frame number {frame_num} does not match expected {parquet_meta[FRAME_NUM]}"
        )
    # other metas
    result.set_errors("\n".join(errors))


def qc_video_file_corruption(video_file_path: str | Path) -> tuple[bool, dict]:
    """
    检查视频文件是否损坏的示例检查器
    """
    video_file_path = Path(video_file_path).expanduser().absolute()
    result = CheckerResult()
    if not video_file_path.exists():
        result.set_errors("File not found")
        return False, result
    flag = True
    try:
        import av

        # 尝试打开视频文件以检查其完整性
        container = av.open(str(video_file_path))
        # 读取第一帧以确保视频文件未损坏
        for _ in container.decode(video=0):
            break
        container.close()
    except Exception as e:
        result.set_errors(f"Video file corruption detected: {str(e)}")
        flag = False

    return flag, result


def get_video_meta(
    video_file_path: str | Path,
) -> dict:
    # todo: 实现视频文件元信息一致性检查逻辑，填写result.error
    with av.open(video_file_path) as container:
        video_stream: av.VideoStream = next(
            s for s in container.streams if s.type == "video"
        )
        return {
            VIDEO_CODEC: video_stream.codec.name,
            VIDEO_WIDTH: video_stream.width,
            VIDEO_HEIGHT: video_stream.height,
            VIDEO_FPS: video_stream.rate.numerator / video_stream.rate.denominator,
        }
    pass


def qc_video_meta_consistency(
    video_file_path: str | Path,
    video_codec: str,
    video_width: int,
    video_height: int,
    video_fps: float,
) -> CheckerResult:
    """
    检查视频文件元信息一致性
    """
    result = CheckerResult()
    video_meta = get_video_meta(video_file_path)
    errors = []
    if video_codec != video_meta[VIDEO_CODEC]:
        errors.append(
            f"Video codec {video_codec} does not match expected {video_meta[VIDEO_CODEC]}"
        )

    if video_width != video_meta[VIDEO_WIDTH]:
        errors.append(
            f"Video width {video_width} does not match expected {video_meta[VIDEO_WIDTH]}"
        )

    if video_height != video_meta[VIDEO_HEIGHT]:
        errors.append(
            f"Video height {video_height} does not match expected {video_meta[VIDEO_HEIGHT]}"
        )

    if video_fps != video_meta[VIDEO_FPS]:
        errors.append(
            f"Video fps {video_fps} does not match expected {video_meta[VIDEO_FPS]}"
        )

    result.set_errors("\n".join(errors))
    return result
