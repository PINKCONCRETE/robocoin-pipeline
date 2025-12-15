import numpy as np

from .checker_registry import register_data_quality_checker


@register_data_quality_checker()
def qc_data_static_frames(data: np.ndarray, checker_config: dict | None = None) -> dict:
    pass


@register_data_quality_checker()
def qc_data_static_features(
    data: np.ndarray, checker_config: dict | None = None
) -> dict:

    pass
