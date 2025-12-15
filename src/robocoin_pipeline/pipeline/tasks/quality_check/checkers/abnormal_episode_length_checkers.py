from .checker_registry import register_abnormal_episode_length_checker
from .checker_result import CheckerResult


@register_abnormal_episode_length_checker()
def qc_short_episodes(
    episodes_frame_num: list[int], checker_config: dict | None = None
) -> dict:
    result = CheckerResult()
    # todo: 实现异常片段长度检查逻辑，填写result.error
    result.set_warnings("Short episode length error example.")
    return result


@register_abnormal_episode_length_checker()
def qc_episode_frame_count_anomalies(
    episodes_frame_num: list[int], checker_config: dict | None = None
) -> dict:
    result = CheckerResult()
    result.set_warnings("Episode length zscore warning example.")
