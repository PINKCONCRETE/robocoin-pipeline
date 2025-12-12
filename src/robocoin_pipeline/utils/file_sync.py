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
logger.setLevel(logging.DEBUG)

# 常量配置
TAR_SIZE_THRESHOLD = 50 * 1024 * 1024  # 50MB
BUFFER_SIZE_ENV = "ROBOCOIN_BUFFER_SIZE"  # 环境变量：缓存大小（字节）
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


def get_buffer_size() -> Optional[int]:
    """
    从环境变量获取缓存大小限制（字节）。

    Returns:
        缓存大小（字节），如果未设置返回 None
    """
    buffer_size_str = os.getenv(BUFFER_SIZE_ENV)
    if buffer_size_str:
        try:
            return int(buffer_size_str)
        except ValueError:
            logger.warning(f"无效的缓存大小设置: {buffer_size_str}")
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

    buffer_size = get_buffer_size()
    if buffer_size is None:
        logger.info("未设置缓存大小限制，跳过内存管理")
        return

    available_space = get_available_space(local_root)

    # 检查总空间是否足够
    if available_space + buffer_size < required_space:
        raise InsufficientSpaceError(
            f"总空间不足：需要 {required_space / 1024**3:.2f}GB，"
            f"但总可用空间仅 {(available_space + buffer_size) / 1024**3:.2f}GB"
        ) from None

    # 如果当前可用空间足够，直接返回
    if available_space >= required_space:
        logger.info(f"可用空间充足: {available_space / 1024**3:.2f}GB")
        return

    # 收集所有数据集及其时间戳
    datasets = []
    for dataset_dir in local_root.iterdir():
        if not dataset_dir.is_dir():
            continue
        if dataset_dir.name == dataset_name:
            continue  # 不删除当前数据集

        timestamp_file = dataset_dir / UPDATE_TIME_NAME
        if timestamp_file.exists():
            timestamp_data = load_json_file(timestamp_file)
            last_update = timestamp_data.get("last_update", 0)
        else:
            last_update = dataset_dir.stat().st_mtime

        dataset_size = get_directory_size(dataset_dir)
        datasets.append((last_update, dataset_dir, dataset_size))

    # 按时间戳排序（最老的在前）
    datasets.sort(key=lambda x: x[0])

    # 删除最老的数据集直到空间足够
    for _, dataset_dir, dataset_size in datasets:
        if available_space >= required_space:
            break

        logger.info(
            f"删除旧数据集以释放空间: {dataset_dir.name} "
            f"({dataset_size / 1024**3:.2f}GB)"
        )

        try:
            shutil.rmtree(dataset_dir)
            available_space += dataset_size
        except Exception as e:
            logger.error(f"删除数据集失败 {dataset_dir.name}: {e}")

    # 最终检查
    if available_space < required_space:
        raise InsufficientSpaceError(
            f"即使删除最老的数据集后仍然空间不足：需要 {required_space / 1024**3:.2f}GB，"
            f"但仅有 {available_space / 1024**3:.2f}GB"
        ) from None

    logger.info(f"内存管理完成，可用空间: {available_space / 1024**3:.2f}GB")


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

    # 1. 拉取 file_tar.json
    tar_json_nas = dataset_nas / TAR_FILE_NAME
    tar_json_local = dataset_local / TAR_FILE_NAME

    if not tar_json_nas.exists():
        raise FileSyncError(f"NAS 上不存在 {TAR_FILE_NAME}: {tar_json_nas}") from None

    shutil.copy2(tar_json_nas, tar_json_local)
    tar_mapping = load_json_file(tar_json_local)

    # 2. 计算需要下载的 tar 包和所需空间
    required_tars = set()
    episode_idx_set = set(episode_idx_list)

    for field in field_list:
        for file_path, tar_name in tar_mapping.get(field, {}).items():
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


def file_push(
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

    # # 上传 file_tar.json
    # tar_json_local = dataset_local / TAR_FILE_NAME
    # tar_json_nas = dataset_nas / TAR_FILE_NAME
    # shutil.copy2(tar_json_local, tar_json_nas)

    # # 上传 file_hash.json
    # for field in field_list:
    #     hash_local = dataset_local / field / HASH_FILE_NAME
    #     hash_nas = dataset_nas / field / HASH_FILE_NAME
    #     if hash_local.exists():
    #         shutil.copy2(hash_local, hash_nas)

    # 上传

    # 更新时间戳
    update_timestamp(dataset_local)
    update_timestamp(dataset_nas)

    logger.info(f"file_push 完成: {dataset_name}")


def pull_files(
    nas_path: Path,
    local_path: Path,
    dataset_name: str,
    field_list: list[str],
    episode_idx_list: list[int],
) -> None:
    """
    拉取原始文件（增量更新）。

    Args:
        nas_path: NAS 根目录
        local_path: 本地根目录
        dataset_name: 数据集名称
        field_list: 字段列表
        episode_idx_list: episode 索引列表
    """
    dataset_nas = nas_path / dataset_name
    dataset_local = local_path / dataset_name
    dataset_local.mkdir(parents=True, exist_ok=True)

    episode_idx_set = set(episode_idx_list)

    for field in field_list:
        logger.info(f"处理字段: {field}")

        field_nas = dataset_nas / field
        field_local = dataset_local / field
        field_local.mkdir(parents=True, exist_ok=True)

        # 1. 拉取 hardlink_mappings.json
        hardlink_nas = field_nas / HARDLINK_MAPPING_NAME
        hardlink_local = field_local / HARDLINK_MAPPING_NAME

        if hardlink_nas.exists():
            shutil.copy2(hardlink_nas, hardlink_local)
            hardlink_mappings = load_json_file(hardlink_local)

            # 2. 递归拉取依赖的字段（沿着 hardlink 链）
            _pull_hardlink_dependencies(
                nas_path,
                local_path,
                dataset_name,
                field,
                hardlink_mappings,
                episode_idx_set,
            )

        # 3. 备份本地 file_hash.json
        hash_local = field_local / HASH_FILE_NAME
        hash_local_backup = field_local / f"local_{HASH_FILE_NAME}"

        if hash_local.exists():
            shutil.copy2(hash_local, hash_local_backup)
            local_hashes = load_json_file(hash_local_backup)
        else:
            local_hashes = {}

        # 4. 拉取 NAS 上的 file_hash.json
        hash_nas = field_nas / HASH_FILE_NAME
        if hash_nas.exists():
            shutil.copy2(hash_nas, hash_local)
            remote_hashes = load_json_file(hash_local)
        else:
            logger.warning(f"NAS 上不存在 {HASH_FILE_NAME}: {hash_nas}")
            remote_hashes = {}

        # 5. 对比并删除差集
        local_files = set(local_hashes.keys())
        remote_files = set(remote_hashes.keys())
        files_to_delete = local_files - remote_files

        for file_rel_path in files_to_delete:
            file_local = field_local / file_rel_path
            if file_local.exists():
                logger.info(f"删除多余文件: {file_rel_path}")
                file_local.unlink()

        # 6. 拉取本地不存在或哈希不匹配的文件
        for file_rel_path, remote_hash in remote_hashes.items():
            episode_idx = _extract_episode_idx(file_rel_path)
            if episode_idx is not None and episode_idx not in episode_idx_set:
                continue

            file_local = field_local / file_rel_path
            file_nas = field_nas / file_rel_path

            # 检查是否需要下载
            need_download = False
            if not file_local.exists():
                need_download = True
            else:
                local_hash = local_hashes.get(file_rel_path)
                if local_hash != remote_hash:
                    need_download = True

            if need_download:
                if not file_nas.exists():
                    logger.warning(f"NAS 上文件不存在: {file_nas}")
                    continue

                logger.info(f"下载文件: {file_rel_path}")
                file_local.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_nas, file_local)

        # 清理备份
        if hash_local_backup.exists():
            hash_local_backup.unlink()

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
    file_push(
        local_path=Path("sync_files"),
        nas_path=Path("/mnt/nas/synnas/docker2/robocoin-pipeline"),
        dataset_name="RMC-AIDA-L_box_up_down",
        field_list=["merged", "format_convert", "motion_annotation"],
        episode_idx_list=list(range(0, 200)),
    )
    pass
