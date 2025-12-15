# ignore: UP006 UP035

"""
用于文件同步的实用程序模块。
包含内存管理，文件传输和路径处理功能。
"""

import hashlib
import json
import logging
import os
import shutil
import tarfile
from pathlib import Path
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

# 常量配置
TAR_SIZE_THRESHOLD = 50 * 1024 * 1024  # 50MB
STORAGE_LIMIT_ENV = "ROBOCOIN_STORAGE_LIMIT"  # 环境变量：存储总限制（字节）
AUTO_CLEANUP_ENV = "ROBOCOIN_AUTO_CLEANUP"  # 环境变量：是否自动清理
HASH_FILE_NAME = "file_hash.json"
TAR_FILE_NAME = "file_tar.json"
HARDLINK_MAPPING_NAME = "hardlink_mappings.json"
UPDATE_TIME_NAME = "update_time.json"


class FileSyncError(Exception):
    """文件同步相关的异常"""

    pass


class InsufficientSpaceError(FileSyncError):
    """存储空间不足异常"""

    pass


# ============================================================================
# 工具函数
# ============================================================================


def calculate_file_hash(file_path: Path, algorithm: str = "md5") -> str:
    """
    计算文件的哈希值。

    Args:
        file_path: 文件路径
        algorithm: 哈希算法（默认 md5）

    Returns:
        文件的哈希值（十六进制字符串）
    """
    hash_func = hashlib.new(algorithm)

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        logger.error(f"计算文件哈希失败 {file_path}: {e}")
        raise FileSyncError(f"计算文件哈希失败: {e}") from e


def get_directory_size(path: Path) -> int:
    """
    递归计算目录大小（字节）。

    Args:
        path: 目录路径

    Returns:
        目录总大小（字节）
    """
    total_size = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total_size += entry.stat().st_size
    except Exception as e:
        logger.error(f"计算目录大小失败 {path}: {e}")
        raise FileSyncError(f"计算目录大小失败: {e}") from e

    return total_size


def get_available_space(path: Path) -> int:
    """
    获取路径所在磁盘的可用空间（字节）。

    Args:
        path: 文件或目录路径

    Returns:
        可用空间（字节）
    """
    try:
        stat = shutil.disk_usage(path)
        return stat.free
    except Exception as e:
        logger.error(f"获取可用空间失败 {path}: {e}")
        raise FileSyncError(f"获取可用空间失败: {e}") from e


def load_json_file(file_path: Path) -> dict:
    """
    加载 JSON 文件。

    Args:
        file_path: JSON 文件路径

    Returns:
        解析后的字典
    """
    try:
        if not file_path.exists():
            return {}

        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载 JSON 文件失败 {file_path}: {e}")
        raise FileSyncError(f"加载 JSON 文件失败: {e}") from e


def save_json_file(data: dict, file_path: Path) -> None:
    """
    保存字典到 JSON 文件。

    Args:
        data: 要保存的字典
        file_path: JSON 文件路径
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存 JSON 文件失败 {file_path}: {e}")
        raise FileSyncError(f"保存 JSON 文件失败: {e}") from e


def update_timestamp(dataset_path: Path) -> None:
    """
    更新数据集的时间戳。

    Args:
        dataset_path: 数据集路径
    """
    import time

    timestamp_file = dataset_path / UPDATE_TIME_NAME
    timestamp_data = {"last_update": time.time()}
    save_json_file(timestamp_data, timestamp_file)
    logger.info(f"更新时间戳: {dataset_path.name}")


def get_storage_limit() -> Optional[int]:
    """
    从环境变量获取存储总限制（字节）。

    Returns:
        存储总限制（字节），如果未设置返回 None
    """
    storage_limit_str = os.getenv(STORAGE_LIMIT_ENV)
    if storage_limit_str:
        try:
            return int(storage_limit_str)
        except ValueError:
            logger.warning(f"无效的存储限制设置: {storage_limit_str}")
    return None


def is_auto_cleanup_enabled() -> bool:
    """
    检查是否启用自动清理。

    Returns:
        是否启用自动清理
    """
    return os.getenv(AUTO_CLEANUP_ENV, "1").lower() in ("1", "true", "yes")


# ============================================================================
# 核心功能函数
# ============================================================================


def memory_manage(local_root: Path, dataset_name: str, required_space: int) -> None:
    """
    内存管理：确保有足够空间，必要时删除最老的数据集。

    Args:
        local_root: 本地根目录
        dataset_name: 当前数据集名称
        required_space: 所需空间（字节）

    Raises:
        InsufficientSpaceError: 空间不足
    """
    if not is_auto_cleanup_enabled():
        logger.info("自动清理未启用，跳过内存管理")
        return

    storage_limit = get_storage_limit()
    if storage_limit is None:
        logger.info("未设置存储限制，跳过内存管理")
        return

    # 计算当前已使用的存储空间
    current_used_space = 0
    datasets = []
    for dataset_dir in local_root.iterdir():
        if not dataset_dir.is_dir():
            continue

        dataset_size = get_directory_size(dataset_dir)
        current_used_space += dataset_size

        if dataset_dir.name == dataset_name:
            continue  # 不删除当前数据集

        # 获取时间戳
        timestamp_file = dataset_dir / UPDATE_TIME_NAME
        if timestamp_file.exists():
            timestamp_data = load_json_file(timestamp_file)
            last_update = timestamp_data.get("last_update", 0)
        else:
            last_update = dataset_dir.stat().st_mtime

        datasets.append((last_update, dataset_dir, dataset_size))

    logger.info(
        f"当前存储使用: {current_used_space / 1024**3:.2f} GB / "
        f"{storage_limit / 1024**3:.2f} GB"
    )

    # 计算新增后的总空间
    space_after_add = current_used_space + required_space

    # 检查总空间是否足够
    if space_after_add > storage_limit:
        logger.info(
            f"存储空间不足，需要清理。"
            f"新增后将占用 {space_after_add / 1024**3:.2f} GB"
        )

        # 按时间戳排序（最老的在前）
        datasets.sort(key=lambda x: x[0])

        # 删除最老的数据集直到空间足够
        freed_space = 0
        for _, dataset_dir, dataset_size in datasets:
            if space_after_add - freed_space <= storage_limit:
                break

            logger.info(
                f"删除旧数据集以释放空间: {dataset_dir.name} "
                f"({dataset_size / 1024**3:.2f} GB)"
            )

            try:
                shutil.rmtree(dataset_dir)
                freed_space += dataset_size
            except Exception as e:
                logger.error(f"删除数据集失败 {dataset_dir.name}: {e}")

        # 最终检查
        final_space = space_after_add - freed_space
        if final_space > storage_limit:
            raise InsufficientSpaceError(
                f"即使删除最老的数据集后仍然空间不足：需要 {final_space / 1024**3:.2f} GB，"
                f"但存储限制为 {storage_limit / 1024**3:.2f} GB"
            ) from None

        logger.info(
            f"清理完成，释放了 {freed_space / 1024**3:.2f} GB，"
            f"新增后将占用 {final_space / 1024**3:.2f} GB"
        )
    else:
        logger.info(f"存储空间充足，新增后将占用 {space_after_add / 1024**3:.2f} GB")


def tar_pull(
    nas_path: Path,
    local_path: Path,
    dataset_name: str,
    field_list: list[str],
    episode_idx_list: list[int],
) -> None:
    """
    拉取并解压 tar 包。

    Args:
        nas_path: NAS 根目录
        local_path: 本地根目录
        dataset_name: 数据集名称
        field_list: 字段列表（如 ['meta', 'data', 'videos']）
        episode_idx_list: episode 索引列表
    """
    dataset_nas = nas_path / dataset_name
    dataset_local = local_path / dataset_name
    dataset_local.mkdir(parents=True, exist_ok=True)

    # 1. 拉取各个 field 的 file_tar.json 并计算需要下载的 tar 包
    required_tars = set()
    episode_idx_set = set(episode_idx_list)

    for field in field_list:
        field_nas = dataset_nas / field
        field_local = dataset_local / field
        field_local.mkdir(parents=True, exist_ok=True)

        tar_json_nas = field_nas / TAR_FILE_NAME
        tar_json_local = field_local / TAR_FILE_NAME

        if not tar_json_nas.exists():
            logger.warning(f"NAS 上不存在 {TAR_FILE_NAME}: {tar_json_nas}")
            continue

        shutil.copy2(tar_json_nas, tar_json_local)
        tar_mapping = load_json_file(tar_json_local)

        for file_path, tar_name in tar_mapping.items():
            # 解析 episode 索引
            episode_idx = _extract_episode_idx(file_path)
            if episode_idx is not None and episode_idx in episode_idx_set:
                required_tars.add((field, tar_name))

    # 计算所需空间
    total_required_space = 0
    for field, tar_name in required_tars:
        tar_path_nas = dataset_nas / field / tar_name
        if tar_path_nas.exists():
            total_required_space += tar_path_nas.stat().st_size

    logger.info(
        f"需要下载 {len(required_tars)} 个 tar 包，"
        f"共 {total_required_space / 1024**3:.2f}GB"
    )

    # 3. 空间检查
    memory_manage(
        local_path, dataset_name, total_required_space * 2
    )  # 解压需要额外空间

    # 4. 下载并解压 tar 包
    for field, tar_name in required_tars:
        tar_path_nas = dataset_nas / field / tar_name
        tar_path_local = dataset_local / field / tar_name

        if not tar_path_nas.exists():
            logger.warning(f"tar 包不存在: {tar_path_nas}")
            continue

        # 下载
        tar_path_local.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"下载 tar 包: {tar_name}")
        shutil.copy2(tar_path_nas, tar_path_local)

        # 解压
        logger.info(f"解压 tar 包: {tar_name}")
        try:
            with tarfile.open(tar_path_local, "r") as tar:
                tar.extractall(path=tar_path_local.parent)
        except Exception as e:
            logger.error(f"解压失败 {tar_name}: {e}")
            raise FileSyncError(f"解压失败: {e}") from e

        # 删除 tar 包
        tar_path_local.unlink()

    # 5. 删除不需要的文件
    _cleanup_unnecessary_files(dataset_local, field_list, episode_idx_set, tar_mapping)

    # 更新时间戳
    update_timestamp(dataset_local)
    logger.info(f"tar_pull 完成: {dataset_name}")


def tar_build(
    local_path: Path,
    dataset_name: str,
    field_list: list[str],
    episode_idx_list: list[int],
) -> None:
    """
    构建 tar 包。

    Args:
        local_path: 本地根目录
        dataset_name: 数据集名称
        field_list: 字段列表
        episode_idx_list: episode 索引列表

    Returns:
        tar 映射字典 {field: {file_path: tar_name}}

    只打包指定 episode_idx_list 中的文件，跳过已在 hardlink 中的文件。
    """
    dataset_local = local_path / dataset_name

    if not dataset_local.exists():
        raise FileSyncError(f"数据集不存在: {dataset_local}") from None

    episode_idx_set = set(episode_idx_list)

    for field in field_list:
        field_path: Path = dataset_local / field
        tar_mapping = {}
        if not field_path.exists():
            logger.warning(f"字段目录不存在: {field_path}")
            continue
        # 获取所有已在 hardlink 中的文件（这些文件不应重复打包）
        hardlinked_files = set()
        if (field_path / HARDLINK_MAPPING_NAME).exists():
            # 加载 hardlink_mappings.json
            hardlink_file = field_path / HARDLINK_MAPPING_NAME
            hardlink_mappings = load_json_file(hardlink_file)

            for field_mappings in hardlink_mappings:
                hardlinked_files.add(field_mappings)

        # tar_mapping[field] = {}

        # 收集需要打包的文件
        files_to_pack = []
        for file_path in field_path.rglob("*"):
            if not file_path.is_file():
                continue

            episode_idx = _extract_episode_idx(str(file_path))
            if episode_idx is None or episode_idx not in episode_idx_set:
                continue

            # 跳过已在 hardlink 中的文件
            relative_path = file_path.relative_to(dataset_local)
            if str(relative_path) in hardlinked_files:
                logger.debug(f"跳过 hardlink 文件: {relative_path}")
                continue

            file_size = file_path.stat().st_size
            files_to_pack.append((file_path, file_size))

        # 按文件大小排序（大文件优先）
        files_to_pack.sort(key=lambda x: x[1], reverse=True)

        # 打包文件
        tar_id = 0
        current_tar_files = []
        current_tar_size = 0

        for file_path, file_size in files_to_pack:
            current_tar_files.append(file_path)
            current_tar_size += file_size

            # 如果达到阈值，创建 tar 包
            if current_tar_size >= TAR_SIZE_THRESHOLD:
                tar_name = f"tar_{tar_id:03d}.tar"
                _create_tar_archive(
                    dataset_local, field_path, tar_name, current_tar_files, tar_mapping
                )

                tar_id += 1
                current_tar_files = []
                current_tar_size = 0

        # 处理剩余文件
        if current_tar_files:
            tar_name = f"tar_{tar_id:03d}.tar"
            _create_tar_archive(
                dataset_local, field_path, tar_name, current_tar_files, tar_mapping
            )

        # 保存 tar 映射
        tar_json_path = dataset_local / field / TAR_FILE_NAME
        save_json_file(tar_mapping, tar_json_path)

    logger.info(f"tar_build 完成: {dataset_name}")


def file_hash_build(
    local_path: Path,
    dataset_name: str,
    field_list: list[str],
) -> None:
    """
    为所有非tar文件计算哈希值并保存
    """
    dataset_local = local_path / dataset_name
    for field in field_list:
        field_path: Path = dataset_local / field
        hash_mapping = {}

        if not field_path.exists():
            logger.warning(f"字段目录不存在: {field_path}")
            continue

        for file_path in field_path.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(dataset_local)
            file_hash = calculate_file_hash(file_path)
            hash_mapping[str(relative_path)] = file_hash

        # 保存哈希映射
        hash_json_path = dataset_local / field / HASH_FILE_NAME
        save_json_file(hash_mapping, hash_json_path)


def push_files(
    local_path: Path,
    nas_path: Path,
    dataset_name: str,
    field_list: list[str],
    episode_idx_list: list[int],
) -> None:
    """
    构建并上传 tar 包到 NAS。

    Args:
        local_path: 本地根目录
        nas_path: NAS 根目录
        dataset_name: 数据集名称
        field_list: 字段列表
        episode_idx_list: episode 索引列表
    """
    dataset_local = local_path / dataset_name
    dataset_nas = nas_path / dataset_name
    dataset_nas.mkdir(parents=True, exist_ok=True)

    # 构建 tar 包
    logger.info(f"开始构建 tar 包: {dataset_name}")
    tar_build(local_path, dataset_name, field_list, episode_idx_list)

    # 上传 tar 包
    for field in field_list:
        field_local = dataset_local / field
        field_nas = dataset_nas / field
        field_nas.mkdir(parents=True, exist_ok=True)
        tar_mapping = load_json_file(field_local / TAR_FILE_NAME)
        for tar_name in set(tar_mapping.values()):
            tar_local = field_local / tar_name
            tar_nas = field_nas / tar_name

            if not tar_local.exists():
                logger.warning(f"tar 包不存在: {tar_local}")
                continue

            logger.info(f"上传 tar 包: {tar_name}")
            shutil.copy2(tar_local, tar_nas)
    # 计算文件哈希并保存
    logger.info(f"开始计算文件哈希: {dataset_name}")
    file_hash_build(local_path, dataset_name, field_list)

    # 上传不在file_tar.json和hardlink_mappings.json中的所有文件
    for field in field_list:
        field_local = dataset_local / field
        field_nas = dataset_nas / field
        field_nas.mkdir(parents=True, exist_ok=True)

        # 加载 tar 映射
        tar_json_path = field_local / TAR_FILE_NAME
        tar_mapping_field = load_json_file(tar_json_path)
        tar_files = set(tar_mapping_field.keys())

        # 加载 hardlink 映射
        hardlink_file = field_local / HARDLINK_MAPPING_NAME
        if hardlink_file.exists():
            hardlink_mappings = load_json_file(hardlink_file)
            hardlinked_files = set(hardlink_mappings.keys())
        else:
            hardlinked_files = set()

        for file_path in field_local.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(dataset_local)

            # 跳过在hardlink_mapping.json中的文件 和 在file_tar.json 中的不在videos下的非tar文件
            if (
                str(relative_path) in hardlinked_files
                or (
                    str(relative_path) in tar_files
                    and "/videos/" not in str(relative_path)
                )
                or file_path.suffix == ".tar"
            ):
                continue

            file_nas = field_nas / file_path.relative_to(field_local)
            file_nas.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"上传文件: {relative_path}")
            shutil.copy2(file_path, file_nas)

    # 上传 dataset 根目录下的文件（不在任何 field 文件夹下的文件）
    logger.info(f"开始上传根目录文件: {dataset_name}")
    root_files_uploaded = 0
    for file_path in dataset_local.iterdir():
        # 只处理文件，不处理文件夹
        if file_path.is_file():
            file_nas = dataset_nas / file_path.name
            logger.info(f"  上传根目录文件: {file_path.name}")
            shutil.copy2(file_path, file_nas)
            root_files_uploaded += 1

    if root_files_uploaded > 0:
        logger.info(f"上传了 {root_files_uploaded} 个根目录文件")

    # 清理 NAS 上多余的文件（不在 file_hash.json 中的文件）
    logger.info(f"开始清理 NAS 上的多余文件: {dataset_name}")
    for field in field_list:
        field_local = dataset_local / field
        field_nas = dataset_nas / field

        if not field_nas.exists():
            continue

        # 加载 file_hash.json
        hash_local = field_local / HASH_FILE_NAME
        if not hash_local.exists():
            logger.warning(f"本地 file_hash.json 不存在: {hash_local}")
            continue

        hash_mapping = load_json_file(hash_local)
        # file_hash.json 的 key 包含 field 前缀，需要去掉前缀得到相对路径
        valid_files = set()
        for file_path in hash_mapping:
            if file_path.startswith(field + "/"):
                rel_path = file_path[len(field) + 1 :]
                valid_files.add(rel_path)

        # 遍历 NAS 上的所有文件
        files_deleted = 0
        for file_path in field_nas.rglob("*"):
            if not file_path.is_file():
                continue

            # 跳过元数据文件
            if file_path.name in [
                HARDLINK_MAPPING_NAME,
                TAR_FILE_NAME,
                HASH_FILE_NAME,
            ]:
                continue

            file_rel_path = str(file_path.relative_to(field_nas))

            # 如果文件不在 file_hash.json 中，删除
            if file_rel_path not in valid_files:
                logger.info(f"  删除多余文件: {field}/{file_rel_path}")
                file_path.unlink()
                files_deleted += 1

        if files_deleted > 0:
            logger.info(f"  字段 {field} 删除了 {files_deleted} 个多余文件")

    # 更新时间戳
    update_timestamp(dataset_local)
    update_timestamp(dataset_nas)

    logger.info(f"file_push 完成: {dataset_name}")


def pull_files(
    nas_path: Path,
    local_path: Path,
    dataset_name: str,
    field_list: list[str],
    data_episode_list: list[int],
    video_episode_list: list[int],
) -> None:
    """
    拉取原始文件（增量更新）。

    Args:
        nas_path: NAS 根目录
        local_path: 本地根目录
        dataset_name: 数据集名称
        field_list: 字段列表
        data_episode_list: data 的 episode 索引列表
        video_episode_list: video 的 episode 索引列表
    """
    dataset_nas = nas_path / dataset_name
    dataset_local = local_path / dataset_name
    dataset_local.mkdir(parents=True, exist_ok=True)

    data_episode_set = set(data_episode_list)
    video_episode_set = set(video_episode_list)

    # 1. 拉取 dataset 根目录下的文件（不在任何 field 文件夹下的文件）
    logger.info(f"开始拉取根目录文件: {dataset_name}")
    root_files_pulled = 0
    for file_path in dataset_nas.iterdir():
        # 只处理文件，不处理文件夹
        if file_path.is_file():
            file_local = dataset_local / file_path.name
            logger.info(f"  拉取根目录文件: {file_path.name}")
            shutil.copy2(file_path, file_local)
            root_files_pulled += 1

    if root_files_pulled > 0:
        logger.info(f"拉取了 {root_files_pulled} 个根目录文件")

    # 2. 收集所有需要拉取的字段（包括依赖字段）
    all_fields_to_pull = _collect_dependent_fields(
        dataset_nas, field_list, data_episode_set, video_episode_set
    )

    logger.info(f"总共需要拉取 {len(all_fields_to_pull)} 个字段: {all_fields_to_pull}")

    # 存储所有字段的 hardlink_mappings，用于最后统一重建
    all_hardlink_mappings = {}

    # 存储每个字段需要拉取的文件（用于依赖字段，只拉取被引用的文件）
    field_required_files = {}

    # 存储所有字段中已存在的文件（用于保护，避免删除）
    # 格式: {field: set(file_paths)}
    field_existing_files = {}

    # 3. 预先扫描所有字段，收集已存在的文件
    for field_to_scan in all_fields_to_pull:
        field_local_scan = dataset_local / field_to_scan
        if field_local_scan.exists():
            existing_files = set()
            for file_path in field_local_scan.rglob("*"):
                if file_path.is_file():
                    # 跳过元数据文件
                    if file_path.name in [
                        HARDLINK_MAPPING_NAME,
                        TAR_FILE_NAME,
                        HASH_FILE_NAME,
                        "local_file_hash.json",
                    ]:
                        continue
                    file_rel_path = str(file_path.relative_to(field_local_scan))
                    existing_files.add(file_rel_path)
            if existing_files:
                field_existing_files[field_to_scan] = existing_files
                logger.info(
                    f"  字段 {field_to_scan} 已有 {len(existing_files)} 个文件，将保护不删除"
                )

    # 3.5. 预先收集依赖字段需要的文件（通过 hardlink_mappings）
    for field in field_list:
        field_nas = dataset_nas / field
        hardlink_nas = field_nas / HARDLINK_MAPPING_NAME

        if hardlink_nas.exists():
            hardlink_mappings = load_json_file(hardlink_nas)

            for link_path, target_path in hardlink_mappings.items():
                # 只处理属于当前 field 的链接
                if not link_path.startswith(field + "/"):
                    continue

                # 检查 episode 过滤
                episode_idx = _extract_episode_idx(target_path)
                is_video = "videos/" in target_path or "/videos/" in target_path
                episode_set = video_episode_set if is_video else data_episode_set

                if episode_idx is not None and episode_idx not in episode_set:
                    continue

                # target_path 格式: "field_name/path/to/file"
                target_parts = Path(target_path).parts
                if target_parts:
                    target_field = target_parts[0]
                    if target_field != field:
                        # 这是跨字段的硬链接，记录需要拉取的文件
                        if target_field not in field_required_files:
                            field_required_files[target_field] = set()
                        # 去掉 field 前缀，只保留相对路径
                        target_rel_path = "/".join(target_parts[1:])
                        field_required_files[target_field].add(target_rel_path)

    # 3.6. 预先计算所有需要下载的 tar 包总大小（用于内存管理）
    logger.info("开始计算需要下载的文件总大小...")
    total_download_size = 0
    all_required_tars = {}  # {field: set(tar_names)}

    for field in all_fields_to_pull:
        field_nas = dataset_nas / field
        field_local = dataset_local / field

        # 加载远程的 tar 映射
        tar_json_nas = field_nas / TAR_FILE_NAME
        if not tar_json_nas.exists():
            continue

        tar_mapping = load_json_file(tar_json_nas)

        # 加载远程和本地的 hash
        hash_nas = field_nas / HASH_FILE_NAME
        hash_local = field_local / HASH_FILE_NAME

        remote_hashes = {}
        local_hashes = {}

        if hash_nas.exists():
            remote_hashes_raw = load_json_file(hash_nas)
            for file_path, file_hash in remote_hashes_raw.items():
                if file_path.startswith(field + "/"):
                    rel_path = file_path[len(field) + 1 :]
                    remote_hashes[rel_path] = file_hash

        if hash_local.exists():
            local_hashes_raw = load_json_file(hash_local)
            for file_path, file_hash in local_hashes_raw.items():
                if file_path.startswith(field + "/"):
                    rel_path = file_path[len(field) + 1 :]
                    local_hashes[rel_path] = file_hash

        # 判断是主字段还是依赖字段
        is_primary_field = field in field_list
        required_tars_for_field = set()

        if not is_primary_field and field in field_required_files:
            # 依赖字段，只检查被引用的文件
            for file_rel_path in field_required_files[field]:
                file_local_path = field_local / file_rel_path
                remote_hash = remote_hashes.get(file_rel_path)
                local_hash = local_hashes.get(file_rel_path)

                if not file_local_path.exists() or local_hash != remote_hash:
                    file_path_with_field = field + "/" + file_rel_path
                    if file_path_with_field in tar_mapping:
                        required_tars_for_field.add(tar_mapping[file_path_with_field])
        else:
            # 主字段，检查所有需要的文件
            for file_path_with_field, tar_name in tar_mapping.items():
                if not file_path_with_field.startswith(field + "/"):
                    continue

                file_rel_path = file_path_with_field[len(field) + 1 :]

                # 检查 episode 过滤
                episode_idx = _extract_episode_idx(file_rel_path)
                is_video = "videos/" in file_rel_path or "/videos/" in file_rel_path
                episode_set = video_episode_set if is_video else data_episode_set

                if episode_idx is not None and episode_idx not in episode_set:
                    continue

                # 检查是否需要更新
                file_local_path = field_local / file_rel_path
                remote_hash = remote_hashes.get(file_rel_path)
                local_hash = local_hashes.get(file_rel_path)

                if not file_local_path.exists() or local_hash != remote_hash:
                    required_tars_for_field.add(tar_name)

        # 计算该字段需要下载的 tar 包大小
        if required_tars_for_field:
            all_required_tars[field] = required_tars_for_field
            for tar_name in required_tars_for_field:
                tar_nas_path = field_nas / tar_name
                if tar_nas_path.exists():
                    total_download_size += tar_nas_path.stat().st_size

    # 计算最大的 tar 包大小（用于滚动解压时的峰值空间需求）
    max_tar_size = 0
    for field, tar_set in all_required_tars.items():
        field_nas = dataset_nas / field
        for tar_name in tar_set:
            tar_nas_path = field_nas / tar_name
            if tar_nas_path.exists():
                tar_size = tar_nas_path.stat().st_size
                if tar_size > max_tar_size:
                    max_tar_size = tar_size

    logger.info(
        f"预计需要下载 {sum(len(tars) for tars in all_required_tars.values())} 个 tar 包，"
        f"总大小: {total_download_size / 1024**3:.2f} GB，"
        f"最大单个 tar: {max_tar_size / 1024**2:.2f} MB"
    )

    # 执行内存管理检查
    # 所需空间 = 所有解压后的文件 + 最大 tar 包（滚动下载解压删除）
    if total_download_size > 0:
        required_space = total_download_size + max_tar_size
        logger.info(
            f"预计需要空间: {required_space / 1024**3:.2f} GB（解压后文件 + 临时 tar）"
        )
        memory_manage(local_path, dataset_name, required_space)

    # 4. 拉取所有字段的文件
    for field in all_fields_to_pull:
        logger.info(f"处理字段: {field}")

        field_nas = dataset_nas / field
        field_local = dataset_local / field
        field_local.mkdir(parents=True, exist_ok=True)

        # 检查这是否是用户直接请求的字段还是依赖字段
        is_primary_field = field in field_list

        # 1. 拉取 hardlink_mappings.json
        hardlink_nas = field_nas / HARDLINK_MAPPING_NAME
        hardlink_local = field_local / HARDLINK_MAPPING_NAME
        hardlink_mappings = {}

        if hardlink_nas.exists():
            shutil.copy2(hardlink_nas, hardlink_local)
            hardlink_mappings = load_json_file(hardlink_local)
            all_hardlink_mappings[field] = hardlink_mappings
            logger.info("  拉取 hardlink_mappings.json")

            # 如果这是主字段，收集它依赖的其他字段的文件
            if is_primary_field:
                for link_path, target_path in hardlink_mappings.items():
                    # 只处理属于当前 field 的链接
                    if not link_path.startswith(field + "/"):
                        continue

                    # 检查 episode 过滤
                    episode_idx = _extract_episode_idx(target_path)
                    is_video = "videos/" in target_path or "/videos/" in target_path
                    episode_set = video_episode_set if is_video else data_episode_set

                    if episode_idx is not None and episode_idx not in episode_set:
                        continue

                    # target_path 格式: "field_name/path/to/file"
                    target_parts = Path(target_path).parts
                    if target_parts:
                        target_field = target_parts[0]
                        if target_field != field:
                            # 这是跨字段的硬链接，记录需要拉取的文件
                            if target_field not in field_required_files:
                                field_required_files[target_field] = set()
                            # 去掉 field 前缀，只保留相对路径
                            target_rel_path = "/".join(target_parts[1:])
                            field_required_files[target_field].add(target_rel_path)

        # 2. 拉取 file_tar.json
        tar_json_nas = field_nas / TAR_FILE_NAME
        tar_json_local = field_local / TAR_FILE_NAME
        tar_mapping = {}

        if tar_json_nas.exists():
            shutil.copy2(tar_json_nas, tar_json_local)
            tar_mapping = load_json_file(tar_json_local)
            logger.info("  拉取 file_tar.json")

        # 3. 拉取 file_hash.json
        hash_nas = field_nas / HASH_FILE_NAME
        hash_local = field_local / HASH_FILE_NAME
        hash_local_backup = field_local / "local_file_hash.json"

        # 备份本地 file_hash.json
        local_hashes = {}
        if hash_local.exists():
            shutil.copy2(hash_local, hash_local_backup)
            local_hashes_raw = load_json_file(hash_local_backup)
            # file_hash.json 的 key 包含 field 前缀，需要去掉
            for file_path, file_hash in local_hashes_raw.items():
                if file_path.startswith(field + "/"):
                    rel_path = file_path[len(field) + 1 :]
                    local_hashes[rel_path] = file_hash

        # 下载云端 file_hash.json
        remote_hashes = {}
        if hash_nas.exists():
            shutil.copy2(hash_nas, hash_local)
            remote_hashes_raw = load_json_file(hash_local)
            # file_hash.json 的 key 包含 field 前缀，需要去掉
            for file_path, file_hash in remote_hashes_raw.items():
                if file_path.startswith(field + "/"):
                    rel_path = file_path[len(field) + 1 :]
                    remote_hashes[rel_path] = file_hash
            logger.info("  拉取 file_hash.json")

        # 获取所有 hardlink 的链接文件路径（相对于 field）
        # hardlink_mappings 格式: {link_path: target_path}，路径都是完整路径（field/...）
        hardlinked_links = set()
        hardlinked_targets = set()
        for link_path, target_path in hardlink_mappings.items():
            # link_path 和 target_path 是完整路径（field/...）
            # 转换为相对于 field 的路径
            if link_path.startswith(field + "/"):
                hardlinked_links.add(link_path[len(field) + 1 :])
            if target_path.startswith(field + "/"):
                hardlinked_targets.add(target_path[len(field) + 1 :])

        # 4. 计算需要下载的 tar 包（基于 hash 检查）
        required_tars = set()
        needed_files = set()
        files_need_update = set()  # 需要更新的文件（本地不存在或 hash 不匹配）

        # 如果是依赖字段，只处理被引用的文件
        if not is_primary_field and field in field_required_files:
            logger.info(
                f"  依赖字段，只拉取被引用的 {len(field_required_files[field])} 个文件"
            )

            for file_rel_path in field_required_files[field]:
                needed_files.add(file_rel_path)

                # 检查文件是否需要更新（基于 hash）
                file_local_path = field_local / file_rel_path
                remote_hash = remote_hashes.get(file_rel_path)
                local_hash = local_hashes.get(file_rel_path)

                # 如果本地文件不存在，或者 hash 不匹配，需要更新
                if not file_local_path.exists() or local_hash != remote_hash:
                    files_need_update.add(file_rel_path)
                    # 查找该文件对应的 tar 包
                    file_path_with_field = field + "/" + file_rel_path
                    if file_path_with_field in tar_mapping:
                        required_tars.add(tar_mapping[file_path_with_field])
        else:
            # 主字段，拉取所有需要的文件
            for file_path_with_field, tar_name in tar_mapping.items():
                # file_path_with_field 格式: "field/path/to/file"
                # 去掉 field 前缀
                if not file_path_with_field.startswith(field + "/"):
                    continue

                file_rel_path = file_path_with_field[len(field) + 1 :]

                # 检查是否需要这个文件
                episode_idx = _extract_episode_idx(file_rel_path)
                is_video = "videos/" in file_rel_path or "/videos/" in file_rel_path
                episode_set = video_episode_set if is_video else data_episode_set

                # 过滤 episode
                if episode_idx is not None and episode_idx not in episode_set:
                    continue

                # 如果是 hardlink 的 link 文件，跳过（不需要下载，后面会重建）
                if file_rel_path in hardlinked_links:
                    continue

                # 记录需要的文件
                needed_files.add(file_rel_path)

                # 检查文件是否需要更新（基于 hash）
                file_local_path = field_local / file_rel_path
                remote_hash = remote_hashes.get(file_rel_path)
                local_hash = local_hashes.get(file_rel_path)

                # 如果本地文件不存在，或者 hash 不匹配，需要更新
                if not file_local_path.exists() or local_hash != remote_hash:
                    files_need_update.add(file_rel_path)
                    required_tars.add(tar_name)

            # 添加所有 hardlink 的 target 文件（仅主字段）
            for target_rel_path in hardlinked_targets:
                episode_idx = _extract_episode_idx(target_rel_path)
                is_video = "videos/" in target_rel_path or "/videos/" in target_rel_path
                episode_set = video_episode_set if is_video else data_episode_set

                if episode_idx is not None and episode_idx not in episode_set:
                    continue

                needed_files.add(target_rel_path)

                # 检查 target 文件是否需要更新
                file_local_path = field_local / target_rel_path
                remote_hash = remote_hashes.get(target_rel_path)
                local_hash = local_hashes.get(target_rel_path)

                if not file_local_path.exists() or local_hash != remote_hash:
                    files_need_update.add(target_rel_path)
                    # 查找该文件对应的 tar 包
                    file_path_with_field = field + "/" + target_rel_path
                    if file_path_with_field in tar_mapping:
                        required_tars.add(tar_mapping[file_path_with_field])

        # 计算需要下载的 tar 包总大小
        total_tar_size = 0
        for tar_name in required_tars:
            tar_nas_path = field_nas / tar_name
            if tar_nas_path.exists():
                total_tar_size += tar_nas_path.stat().st_size

        logger.info(
            f"  需要更新 {len(files_need_update)} 个文件，下载 {len(required_tars)} 个 tar 包 "
            f"({total_tar_size / 1024**2:.2f} MB)"
        )

        # 5. 下载并解压 tar 包
        for tar_name in required_tars:
            tar_nas_path = field_nas / tar_name
            tar_local_path = field_local / tar_name

            if not tar_nas_path.exists():
                logger.warning(f"  tar 包不存在: {tar_name}")
                continue

            # 下载 tar 包
            logger.info(f"  下载 tar 包: {tar_name}")
            shutil.copy2(tar_nas_path, tar_local_path)

            # 解压 tar 包
            logger.info(f"  解压 tar 包: {tar_name}")
            try:
                with tarfile.open(tar_local_path, "r") as tar:
                    tar.extractall(path=field_local)
            except Exception as e:
                logger.error(f"  解压失败 {tar_name}: {e}")
                raise FileSyncError(f"解压失败: {e}") from e

            # 删除 tar 包
            tar_local_path.unlink()

        # 6. 删除不需要的文件
        # 对所有字段（主字段和依赖字段）都保护已存在的文件，实现增量更新
        # 只删除本次新下载但不需要的文件
        for file_path in field_local.rglob("*"):
            if not file_path.is_file():
                continue

            # 跳过元数据文件
            if file_path.name in [
                HARDLINK_MAPPING_NAME,
                TAR_FILE_NAME,
                HASH_FILE_NAME,
                "local_file_hash.json",
            ]:
                continue

            file_rel_path = file_path.relative_to(field_local)
            file_rel_path_str = str(file_rel_path)

            # 检查是否应该删除
            should_delete = False

            # 检查是否是已存在的文件
            is_existing = (
                field in field_existing_files
                and file_rel_path_str in field_existing_files[field]
            )

            if is_existing:
                # 已存在的文件，保护不删除（增量更新）
                should_delete = False
            elif file_rel_path_str in hardlinked_links:
                # link 文件可以删除并重建
                if file_rel_path_str not in needed_files:
                    should_delete = True
                    reason = "不需要的 link 文件"
            else:
                # 新下载的文件，如果不需要则删除
                if file_rel_path_str not in needed_files:
                    should_delete = True
                    reason = "不需要的文件"

            if should_delete:
                logger.debug(f"  删除{reason}: {file_rel_path}")
                file_path.unlink()

        # 清理备份
        if hash_local_backup.exists():
            hash_local_backup.unlink()

    # 5. 统一重建所有硬链接
    logger.info("开始重建硬链接...")
    total_hardlinks_created = 0

    for field, hardlink_mappings in all_hardlink_mappings.items():
        if not hardlink_mappings:
            continue

        logger.info(f"  处理字段 {field} 的硬链接...")
        hardlinks_created = 0

        for link_path, target_path in hardlink_mappings.items():
            # link_path 和 target_path 都是完整路径（field/...）
            link_full_path = dataset_local / link_path
            target_full_path = dataset_local / target_path

            # 只重建属于当前 field 的链接
            if not link_path.startswith(field + "/"):
                continue

            # 过滤 episode
            episode_idx = _extract_episode_idx(target_path)
            is_video = "videos/" in target_path or "/videos/" in target_path
            episode_set = video_episode_set if is_video else data_episode_set

            if episode_idx is not None and episode_idx not in episode_set:
                continue

            if not target_full_path.exists():
                logger.warning(f"    目标文件不存在，跳过: {target_path}")
                continue

            # 删除已存在的链接
            if link_full_path.exists():
                link_full_path.unlink()

            # 创建硬链接
            link_full_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(target_full_path, link_full_path)
                logger.debug(f"    创建硬链接: {link_path} -> {target_path}")
                hardlinks_created += 1
            except Exception as e:
                logger.error(f"    创建硬链接失败 {link_path}: {e}")

        if hardlinks_created > 0:
            logger.info(f"  字段 {field} 创建了 {hardlinks_created} 个硬链接")
            total_hardlinks_created += hardlinks_created

    if total_hardlinks_created > 0:
        logger.info(f"总共创建了 {total_hardlinks_created} 个硬链接")

    # 更新时间戳
    update_timestamp(dataset_local)
    logger.info(f"pull_files 完成: {dataset_name}")


def rebuild_hardlink(
    dataset_path: Path, field_list: Optional[list[str]] = None
) -> None:
    """
    根据 hardlink_mappings.json 重建硬链接。

    Args:
        dataset_path: 数据集路径
        field_list: 字段列表（如果为 None，则处理所有字段）
    """
    hardlink_file = dataset_path / HARDLINK_MAPPING_NAME

    if not hardlink_file.exists():
        logger.warning(f"hardlink_mappings.json 不存在: {hardlink_file}")
        return

    hardlink_mappings = load_json_file(hardlink_file)

    if field_list is None:
        field_list = list(hardlink_mappings.keys())

    for field in field_list:
        field_mappings = hardlink_mappings.get(field, {})

        for link_path_str, target_path_str in field_mappings.items():
            link_path = dataset_path / link_path_str
            target_path = dataset_path / target_path_str

            if not target_path.exists():
                logger.warning(f"目标文件不存在: {target_path}")
                continue

            # 删除已存在的链接
            if link_path.exists():
                link_path.unlink()

            # 创建硬链接
            link_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(target_path, link_path)
                logger.debug(f"创建硬链接: {link_path_str} -> {target_path_str}")
            except Exception as e:
                logger.error(f"创建硬链接失败 {link_path_str}: {e}")

    logger.info(f"rebuild_hardlink 完成: {dataset_path.name}")


# ============================================================================
# 辅助函数
# ============================================================================


def _collect_dependent_fields(
    dataset_nas: Path,
    initial_fields: list[str],
    data_episode_set: set[int],
    video_episode_set: set[int],
) -> list[str]:
    """
    递归收集所有需要拉取的字段（包括硬链接依赖的字段）。

    Args:
        dataset_nas: NAS 数据集路径
        initial_fields: 初始字段列表
        data_episode_set: data 的 episode 集合
        video_episode_set: video 的 episode 集合

    Returns:
        所有需要拉取的字段列表（去重后）
    """
    visited_fields = set()
    fields_to_process = list(initial_fields)
    result_fields = []

    while fields_to_process:
        field = fields_to_process.pop(0)

        if field in visited_fields:
            continue

        visited_fields.add(field)
        result_fields.append(field)

        # 检查该字段是否有 hardlink_mappings.json
        hardlink_nas = dataset_nas / field / HARDLINK_MAPPING_NAME
        if not hardlink_nas.exists():
            continue

        # 加载 hardlink 映射
        hardlink_mappings = load_json_file(hardlink_nas)

        # 找出该字段依赖的其他字段
        dependent_fields = set()
        for link_path, target_path in hardlink_mappings.items():
            # 只处理属于当前 field 的链接
            if not link_path.startswith(field + "/"):
                continue

            # 检查 episode 过滤
            episode_idx = _extract_episode_idx(target_path)
            is_video = "videos/" in target_path or "/videos/" in target_path
            episode_set = video_episode_set if is_video else data_episode_set

            if episode_idx is not None and episode_idx not in episode_set:
                continue

            # target_path 格式: "field_name/path/to/file"
            # 提取字段名
            target_parts = Path(target_path).parts
            if target_parts and target_parts[0] != field:
                dependent_field = target_parts[0]
                if dependent_field not in visited_fields:
                    dependent_fields.add(dependent_field)

        # 将依赖字段加入处理队列
        for dep_field in dependent_fields:
            if dep_field not in visited_fields:
                fields_to_process.append(dep_field)
                logger.info(f"  发现依赖字段: {field} -> {dep_field}")

    return result_fields


def _extract_episode_idx(file_path: str) -> Optional[int]:
    """
    从文件路径中提取 episode 索引。

    Args:
        file_path: 文件路径

    Returns:
        episode 索引，如果无法提取则返回 None
    """
    import re

    # 匹配 episode_000123 这样的模式
    match = re.search(r"episode_(\d+)", file_path)
    if match:
        return int(match.group(1))
    return None


def _create_tar_archive(
    dataset_path: Path,
    field_path: Path,
    tar_name: str,
    files: list[Path],
    tar_mapping: dict[str, str],
) -> None:
    """
    创建 tar 归档文件。

    Args:
        dataset_path: 数据集路径
        field_path: 字段路径
        tar_name: tar 文件名
        files: 要打包的文件列表
        tar_mapping: tar 映射字典（字段级）
    """
    tar_path = field_path / tar_name

    try:
        with tarfile.open(tar_path, "w") as tar:
            for file_path in files:
                arcname = file_path.relative_to(field_path)
                tar.add(file_path, arcname=arcname)

                # 更新映射
                relative_path = file_path.relative_to(dataset_path)
                tar_mapping[str(relative_path)] = tar_name

        logger.info(f"创建 tar 包: {tar_name} ({len(files)} 个文件)")
    except Exception as e:
        logger.error(f"创建 tar 包失败 {tar_name}: {e}")
        raise FileSyncError(f"创建 tar 包失败: {e}") from e


def _cleanup_unnecessary_files(
    dataset_path: Path,
    field_list: list[str],
    episode_idx_set: set[int],
) -> None:
    """
    删除不需要的文件。

    Args:
        dataset_path: 数据集路径
        field_list: 字段列表
        episode_idx_set: episode 索引集合
        tar_mapping: tar 映射
    """
    for field in field_list:
        field_path = dataset_path / field
        if not field_path.exists():
            continue

        for file_path in field_path.rglob("*"):
            if not file_path.is_file():
                continue

            episode_idx = _extract_episode_idx(str(file_path))
            if episode_idx is not None and episode_idx not in episode_idx_set:
                logger.info(f"删除不需要的文件: {file_path.relative_to(dataset_path)}")
                file_path.unlink()


def _pull_hardlink_dependencies(
    nas_path: Path,
    local_path: Path,
    dataset_name: str,
    field: str,
    hardlink_mappings: dict[str, str],
    episode_idx_set: set[int],
    visited: Optional[set[str]] = None,
) -> None:
    """
    递归拉取 hardlink 依赖的字段。

    Args:
        nas_path: NAS 根目录
        local_path: 本地根目录
        dataset_name: 数据集名称
        field: 当前字段
        hardlink_mappings: hardlink 映射
        episode_idx_set: episode 索引集合
        visited: 已访问的字段集合（用于防止循环依赖）
    """
    if visited is None:
        visited = set()

    if field in visited:
        return

    visited.add(field)

    # 找出依赖的字段
    dependent_fields = set()
    for target_path in hardlink_mappings.values():
        # target_path 格式如 "field_name/subdir/file.ext"
        parts = Path(target_path).parts
        if parts:
            dependent_field = parts[0]
            dependent_fields.add(dependent_field)

    # 递归拉取依赖字段
    for dep_field in dependent_fields:
        if dep_field == field:
            continue

        logger.info(f"拉取依赖字段: {dep_field}")

        # 简化版：直接拉取整个字段（实际应该只拉取需要的文件）
        dep_field_nas = nas_path / dataset_name / dep_field
        dep_field_local = local_path / dataset_name / dep_field

        if dep_field_nas.exists():
            dep_field_local.mkdir(parents=True, exist_ok=True)

            # 拉取该字段的 hardlink_mappings.json
            dep_hardlink_nas = dep_field_nas / HARDLINK_MAPPING_NAME
            dep_hardlink_local = dep_field_local / HARDLINK_MAPPING_NAME

            if dep_hardlink_nas.exists():
                shutil.copy2(dep_hardlink_nas, dep_hardlink_local)
                dep_hardlink_mappings = load_json_file(dep_hardlink_local)

                # 递归
                _pull_hardlink_dependencies(
                    nas_path,
                    local_path,
                    dataset_name,
                    dep_field,
                    dep_hardlink_mappings,
                    episode_idx_set,
                    visited,
                )

            # 拉取文件（简化版：拉取所有文件）
            for file_nas in dep_field_nas.rglob("*"):
                if not file_nas.is_file():
                    continue

                if file_nas.name in [
                    HARDLINK_MAPPING_NAME,
                    HASH_FILE_NAME,
                    TAR_FILE_NAME,
                ]:
                    continue

                episode_idx = _extract_episode_idx(str(file_nas))
                if episode_idx is not None and episode_idx not in episode_idx_set:
                    continue

                file_local = dep_field_local / file_nas.relative_to(dep_field_nas)
                if not file_local.exists():
                    file_local.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_nas, file_local)


if __name__ == "__main__":
    # 测试内存管理功能
    # 设置环境变量：启用自动清理，存储总限制为 1.2GB（可容纳约2个数据集）
    os.environ["ROBOCOIN_AUTO_CLEANUP"] = "1"
    os.environ["ROBOCOIN_STORAGE_LIMIT"] = str(int(1.2 * 1024**3))  # 1.2GB

    logger.info("=" * 80)
    logger.info("开始测试内存管理功能")
    logger.info(f"存储总限制: {get_storage_limit() / 1024**3:.2f} GB")
    logger.info(f"自动清理启用: {is_auto_cleanup_enabled()}")
    logger.info("=" * 80)

    # 测试场景：
    # 1. 先拉取 RMC-AIDA-L_box_up_down1（约 1.1GB）
    # 2. 再拉取 RMC-AIDA-L_box_up_down2（会触发内存管理）
    # 3. 再拉取 RMC-AIDA-L_box_up_down3（会触发内存管理，删除最老的数据集）

    nas_path = Path("/mnt/nas/synnas/docker2/robocoin-pipeline/robocoin-datasets")
    local_path = Path("sync_files/test_memory")

    # 清空测试目录
    if local_path.exists():
        logger.info(f"清空测试目录: {local_path}")
        shutil.rmtree(local_path)
    local_path.mkdir(parents=True, exist_ok=True)

    logger.info("\n" + "=" * 80)
    logger.info("第 1 步：拉取 RMC-AIDA-L_box_up_down1（所有 episode）")
    logger.info("=" * 80)
    pull_files(
        nas_path=nas_path,
        local_path=local_path,
        dataset_name="RMC-AIDA-L_box_up_down1",
        field_list=["merged"],
        data_episode_list=list(range(200)),
        video_episode_list=list(range(200)),
    )

    # 查看当前磁盘使用情况
    logger.info("\n当前数据集:")
    import subprocess

    result = subprocess.run(
        ["du", "-sh"] + [str(p) for p in local_path.iterdir() if p.is_dir()],
        capture_output=True,
        text=True,
    )
    logger.info(result.stdout)

    logger.info("\n" + "=" * 80)
    logger.info("第 2 步：拉取 RMC-AIDA-L_box_up_down2（所有 episode）")
    logger.info("=" * 80)
    pull_files(
        nas_path=nas_path,
        local_path=local_path,
        dataset_name="RMC-AIDA-L_box_up_down2",
        field_list=["merged"],
        data_episode_list=list(range(200)),
        video_episode_list=list(range(200)),
    )

    # 查看当前磁盘使用情况
    logger.info("\n当前数据集:")
    result = subprocess.run(
        ["du", "-sh"] + [str(p) for p in local_path.iterdir() if p.is_dir()],
        capture_output=True,
        text=True,
    )
    logger.info(result.stdout)

    logger.info("\n" + "=" * 80)
    logger.info("第 3 步：拉取 RMC-AIDA-L_box_up_down3（所有 episode，应触发删除）")
    logger.info("=" * 80)
    pull_files(
        nas_path=nas_path,
        local_path=local_path,
        dataset_name="RMC-AIDA-L_box_up_down3",
        field_list=["merged"],
        data_episode_list=list(range(200)),
        video_episode_list=list(range(200)),
    )

    # 查看最终磁盘使用情况
    logger.info("\n最终数据集:")
    result = subprocess.run(
        ["du", "-sh"] + [str(p) for p in local_path.iterdir() if p.is_dir()],
        capture_output=True,
        text=True,
    )
    logger.info(result.stdout)

    logger.info("\n" + "=" * 80)
    logger.info("内存管理测试完成")
    logger.info("=" * 80)
