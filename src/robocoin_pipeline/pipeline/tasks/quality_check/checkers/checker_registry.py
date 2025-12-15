import functools
from collections import defaultdict
from collections.abc import Callable

from robocoin_pipeline.constants.config_constant import (
    LEROBOT_VERSION_V21,
)


# ====== 通用注册表工厂 ======
def create_checker_registry() -> dict[str, Callable]:
    return defaultdict(dict)


# ====== 通用装饰器工厂 ======
def make_register_decorator(
    registry: dict[str, dict],
    decorator_name: str = "register_checker",
) -> Callable:
    """
    生成一个注册装饰器。

    Args:
        registry: 要注册到的目标字典（如 _FORMAT_CHECKER_REGISTRY）
        decorator_name: 用于报错信息的装饰器名称
    """

    def register_checker(
        name: str | None = None, lerobot_format_version: str = LEROBOT_VERSION_V21
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            nonlocal name
            if name is None:
                name = func.__name__

            versioned_reg = registry[lerobot_format_version]
            if name in versioned_reg:
                raise ValueError(
                    f"{decorator_name}: Checker '{name}' already registered "
                    f"for version '{lerobot_format_version}'!"
                )
            versioned_reg[name] = func

            @functools.wraps(func)
            def wrapper(*args: any, **kwargs: any) -> any:
                return func(*args, **kwargs)

            return wrapper

        return decorator

    return register_checker


# ====== 具体注册器实例 ======
# 数据集元信息检查器
_REPO_FORMAT_CHECKER_REGISTRY = create_checker_registry()
register_repo_format_checker = make_register_decorator(
    _REPO_FORMAT_CHECKER_REGISTRY, "register_repo_format_checker"
)

# 异常Episode长度检查器
_ABNORMAL_EPISODE_LENGTH_CHECKER_REGISTRY = create_checker_registry()
register_abnormal_episode_length_checker = make_register_decorator(
    _ABNORMAL_EPISODE_LENGTH_CHECKER_REGISTRY,
    "register_abnormal_episode_length_checker",
)

# 数据文件Meta信息检查器
_DATA_META_CHECKER_REGISTRY = create_checker_registry()
register_data_meta_checker = make_register_decorator(
    _DATA_META_CHECKER_REGISTRY, "register_data_meta_checker"
)

# 数据质量检查器
_DATA_QUALITY_CHECKER_REGISTRY = create_checker_registry()
register_data_quality_checker = make_register_decorator(
    _DATA_QUALITY_CHECKER_REGISTRY, "register_data_quality_checker"
)

# 视频文件Meta信息检查器
_VIDEO_META_CHECKER_REGISTRY = create_checker_registry()
register_video_meta_checker = make_register_decorator(
    _VIDEO_META_CHECKER_REGISTRY, "register_video_meta_checker"
)

# 视频质量检查器
_VIDEO_QUALITY_CHECKER_REGISTRY = create_checker_registry()
register_video_quality_checker = make_register_decorator(
    _VIDEO_QUALITY_CHECKER_REGISTRY, "register_video_quality_checker"
)


# ====== 辅助查询函数 ======
def get_repo_meta_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str, Callable]:
    return dict(_REPO_FORMAT_CHECKER_REGISTRY.get(lerobot_format_version, {}))


def get_repo_meta_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(_REPO_FORMAT_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys())


def get_abnormal_episode_length_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(
        _ABNORMAL_EPISODE_LENGTH_CHECKER_REGISTRY.get(lerobot_format_version, {})
    )


def get_abnormal_episode_length_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(
        _ABNORMAL_EPISODE_LENGTH_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys()
    )


def get_data_meta_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return dict(_DATA_META_CHECKER_REGISTRY.get(lerobot_format_version, {}))


def get_data_meta_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(_DATA_META_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys())


def get_data_quality_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return dict(_DATA_QUALITY_CHECKER_REGISTRY.get(lerobot_format_version, {}))


def get_data_quality_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(_DATA_QUALITY_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys())


def get_video_meta_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return dict(_VIDEO_META_CHECKER_REGISTRY.get(lerobot_format_version, {}))


def get_video_meta_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(_VIDEO_META_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys())


def get_video_quality_checkers(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return dict(_VIDEO_QUALITY_CHECKER_REGISTRY.get(lerobot_format_version, {}))


def get_video_quality_checker_names(
    lerobot_format_version: str = LEROBOT_VERSION_V21,
) -> dict[str]:
    return list(_VIDEO_QUALITY_CHECKER_REGISTRY.get(lerobot_format_version, {}).keys())
