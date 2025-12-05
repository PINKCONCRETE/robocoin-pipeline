"""
src.robocoin_pipeline.utils.file_sync

文件同步工具：支持在云端NAS和本地sync_files之间双向同步数据
使用UUID追踪机制确保数据一致性和增量更新
"""

import json
import os
import shutil
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from robocoin_pipeline.config import ROBOCOIN_PIPELINE_DISTRIBUTION_MODE

# Constants
METADATA_FILE = ".sync_metadata.json"
HARDLINK_MAPPINGS_FILE = "hardlink_mappings.json"
FEATURE_CONFIG_FILE = "feature_key.yaml"
SYNC_BASE_DIR = Path(__file__).parent.parent.parent.parent / "sync_files"


@contextmanager
def safe_write(file_path: Path) -> Generator[Path, None, None]:
    """安全写入文件的上下文管理器，先写临时文件再重命名"""
    temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
    try:
        yield temp_path
        temp_path.replace(file_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def load_metadata(metadata_path: Path) -> dict[str, dict]:
    """加载或初始化metadata文件"""
    if not metadata_path.exists():
        return {}

    with open(metadata_path, encoding="utf-8") as f:
        return json.load(f)


def save_metadata(metadata_path: Path, metadata: dict[str, dict]) -> None:
    """安全保存metadata文件"""
    with (
        safe_write(metadata_path) as temp_path,
        open(temp_path, "w", encoding="utf-8") as f,
    ):
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def ensure_feature_uuid(metadata: dict[str, dict], feature_key: str) -> str:
    """确保feature_key有UUID，如果没有则创建"""
    if feature_key not in metadata:
        metadata[feature_key] = {
            "uuid": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
        }
    return metadata[feature_key]["uuid"]


def get_dataset_name(repo_path: Path) -> str:
    """从repo路径提取dataset名称"""
    return repo_path.name


def load_feature_config() -> dict[str, list[str]]:
    """加载feature_key配置"""
    config_path = Path(__file__).parent / FEATURE_CONFIG_FILE
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def initialize_metadata(
    metadata: dict[str, dict], feature_config: dict[str, list[str]]
) -> None:
    """为所有feature_key初始化UUID"""
    for feature_key in feature_config:
        ensure_feature_uuid(metadata, feature_key)


def load_hardlink_mappings(base_dir: Path, feature_key: str) -> dict[str, str] | None:
    """加载hardlink映射文件

    :param base_dir: 数据集基础目录
    :param feature_key: feature_key名称
    :return: hardlink映射字典，如果文件不存在则返回None
    """
    mapping_file = base_dir / feature_key / HARDLINK_MAPPINGS_FILE
    if not mapping_file.exists():
        return None

    with open(mapping_file, encoding="utf-8") as f:
        return json.load(f)


def is_hardlink(file_path: Path, reference_path: Path) -> bool:
    """检查两个文件是否为硬链接（指向同一个inode）

    :param file_path: 要检查的文件路径
    :param reference_path: 参考文件路径
    :return: 如果是硬链接返回True
    """
    try:
        if not (file_path.exists() and reference_path.exists()):
            return False
        if file_path.is_dir() or reference_path.is_dir():
            return False
        return file_path.stat().st_ino == reference_path.stat().st_ino
    except OSError:
        return False


def pull_missing_file(repo_path: Path, sync_dir: Path, file_path: str) -> bool:
    """从云端NAS递归拉取缺失的文件

    :param repo_path: 云端NAS数据集路径
    :param sync_dir: 本地sync目录
    :param file_path: 相对文件路径
    :return: 成功返回True
    """
    src = repo_path / file_path
    if not src.exists():
        print(f"    错误: 云端也不存在: {file_path}")
        return False

    dst = sync_dir / file_path
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"    拉取目录: {file_path}")
        else:
            shutil.copy2(src, dst)
            print(f"    拉取文件: {file_path}")
        return True
    except Exception as e:
        print(f"    拉取失败: {e}")
        return False


def _create_directory_symlink(
    target: Path, source: Path, target_path: str, source_path: str
) -> None:
    """创建目录符号链接（使用相对路径）"""
    try:
        relative_source = os.path.relpath(source, target.parent)
        target.symlink_to(relative_source)
        print(f"    ✓ 目录符号链接: {target_path} -> {source_path}")
    except OSError as e:
        print(f"    警告: 无法创建符号链接: {e}")


def _create_file_hardlink(
    target: Path, source: Path, target_path: str, source_path: str
) -> None:
    """创建文件硬链接，失败时降级为复制"""
    try:
        target.hardlink_to(source)
        print(f"    ✓ 文件硬链接: {target_path} -> {source_path}")
    except OSError as e:
        print(f"    警告: 无法创建硬链接，使用复制: {e}")
        shutil.copy2(source, target)


def rebuild_hardlinks(
    base_dir: Path, feature_key: str, repo_path: Path | None = None
) -> None:
    """根据hardlink_mappings.json重建hard links和符号链接

    :param base_dir: 数据集基础目录
    :param feature_key: feature_key名称
    :param repo_path: 云端NAS路径（用于拉取缺失文件，None则跳过拉取）

    支持：
    - 文件级hardlink: 多个文件名指向同一个inode
    - 目录级symlink: 使用符号链接共享整个目录
    - 自动拉取缺失的源文件
    """
    mappings = load_hardlink_mappings(base_dir, feature_key)
    if not mappings:
        return

    print(f"  重建链接: {len(mappings)}个映射")

    for target_path, source_path in mappings.items():
        target = base_dir / target_path
        source = base_dir / source_path

        # 如果源不存在，尝试从云端拉取
        if not source.exists():
            if not repo_path:
                print(f"    警告: 源不存在且无法拉取: {source_path}")
                continue
            print(f"    源不存在，尝试从云端拉取: {source_path}")
            if not pull_missing_file(repo_path, base_dir, source_path):
                continue

        # 确保目标父目录存在
        target.parent.mkdir(parents=True, exist_ok=True)

        # 如果目标已存在，先删除
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()

        # 根据源类型选择链接方式
        if source.is_dir():
            _create_directory_symlink(target, source, target_path, source_path)
        else:
            _create_file_hardlink(target, source, target_path, source_path)


def pull_files(
    repo_path: str | Path,
    feature_keys: list[str] | None = None,
) -> None:
    """
    从云端NAS拉取文件到本地sync_files
    :param repo_path: 云端NAS数据集路径
    :param feature_keys: 要同步的特征列表
    """
    if ROBOCOIN_PIPELINE_DISTRIBUTION_MODE == 0:
        return

    repo_path = Path(repo_path)
    dataset_name = get_dataset_name(repo_path)
    sync_dir = SYNC_BASE_DIR / dataset_name
    sync_dir.mkdir(parents=True, exist_ok=True)

    feature_config = load_feature_config()

    # 加载云端和本地metadata
    nas_metadata_path = repo_path / METADATA_FILE
    local_metadata_path = sync_dir / METADATA_FILE

    nas_metadata = (
        load_metadata(nas_metadata_path) if nas_metadata_path.exists() else {}
    )
    local_metadata = load_metadata(local_metadata_path)

    # 为云端metadata中不存在的feature_key初始化UUID
    metadata_updated = False
    for feature_key in feature_config:
        if feature_key not in nas_metadata:
            ensure_feature_uuid(nas_metadata, feature_key)
            metadata_updated = True
            print(f"为新feature_key初始化UUID: {feature_key}")

    # 如果有更新，保存到本地和云端
    if metadata_updated:
        save_metadata(local_metadata_path, nas_metadata)
        nas_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        save_metadata(nas_metadata_path, nas_metadata)
        print("元数据已更新并同步到云端")
    elif nas_metadata_path.exists():
        # 如果云端有metadata且无更新，只拉取到本地
        shutil.copy2(nas_metadata_path, local_metadata_path)
        print(f"拉取元数据: {METADATA_FILE}")

    # 重新加载本地metadata
    local_metadata = load_metadata(local_metadata_path)

    for feature_key in feature_keys or []:
        if feature_key not in feature_config:
            print(f"未知的feature_key: {feature_key}")
            continue

        # 检查本地是否有实际数据文件
        file_paths = feature_config[feature_key]
        has_local_data = any((sync_dir / path).exists() for path in file_paths)

        # 检查UUID是否匹配
        nas_uuid = nas_metadata.get(feature_key, {}).get("uuid")
        local_uuid = local_metadata.get(feature_key, {}).get("uuid")

        if has_local_data and nas_uuid and local_uuid and nas_uuid == local_uuid:
            print(f"跳过 {feature_key}: UUID匹配且本地有数据，无需拉取")
            continue

        print(f"拉取 {feature_key} (UUID不匹配或本地无数据)")

        for file_path in feature_config[feature_key]:
            src = repo_path / file_path
            dst = sync_dir / file_path

            if not src.exists():
                print(f"  源文件不存在: {src}")
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"  拉取目录: {file_path}")
            else:
                shutil.copy2(src, dst)
                print(f"  拉取文件: {file_path}")

        # 拉取完成后重建hard links（传入repo_path以便拉取缺失文件）
        rebuild_hardlinks(sync_dir, feature_key, repo_path)


def push_files(
    repo_path: str | Path,
    feature_keys: list[str] | None = None,
) -> None:
    """
    从本地sync_files推送文件到云端NAS
    :param repo_path: 云端NAS数据集路径
    :param feature_keys: 要同步的特征列表
    """
    if ROBOCOIN_PIPELINE_DISTRIBUTION_MODE == 0:
        return

    repo_path = Path(repo_path)
    dataset_name = get_dataset_name(repo_path)
    sync_dir = SYNC_BASE_DIR / dataset_name

    if not sync_dir.exists():
        print(f"同步目录不存在: {sync_dir}")
        return

    feature_config = load_feature_config()
    local_metadata_path = sync_dir / METADATA_FILE
    local_metadata = load_metadata(local_metadata_path)

    # 加载云端metadata
    nas_metadata_path = repo_path / METADATA_FILE
    nas_metadata = (
        load_metadata(nas_metadata_path) if nas_metadata_path.exists() else {}
    )

    # 为云端metadata中不存在的新feature_key初始化UUID
    for feature_key in feature_config:
        if feature_key not in nas_metadata:
            ensure_feature_uuid(nas_metadata, feature_key)
            print(f"为新feature_key初始化UUID: {feature_key}")

    for feature_key in feature_keys or []:
        if feature_key not in feature_config:
            print(f"未知的feature_key: {feature_key}")
            continue

        # 检查本地是否有这个feature_key的数据
        if feature_key not in local_metadata:
            print(f"跳过 {feature_key}: 本地无此feature_key数据")
            continue

        # 检查UUID是否匹配
        nas_uuid = nas_metadata.get(feature_key, {}).get("uuid")
        local_uuid = local_metadata.get(feature_key, {}).get("uuid")

        if nas_uuid and local_uuid and nas_uuid == local_uuid:
            print(f"跳过 {feature_key}: UUID匹配，无需推送")
            continue

        print(f"推送 {feature_key} (UUID不匹配或本地有更新)")

        # 更新本地metadata的UUID到云端（保持本地的UUID）
        nas_metadata[feature_key] = local_metadata[feature_key]

        # 收集已推送文件用于检查硬链接
        pushed_files = set()

        for file_path in feature_config[feature_key]:
            src = sync_dir / file_path
            dst = repo_path / file_path

            if not src.exists():
                print(f"  源文件不存在: {src}")
                continue

            # 如果是文件且是硬链接，检查是否已推送过源文件
            if src.is_file() and any(
                is_hardlink(src, sync_dir / pushed) for pushed in pushed_files
            ):
                print(f"  跳过硬链接: {file_path} (已推送源文件)")
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"  推送目录: {file_path}")
            else:
                shutil.copy2(src, dst)
                print(f"  推送文件: {file_path}")
                pushed_files.add(file_path)

        # 推送完成后重建hard links（不需要repo_path参数）
        rebuild_hardlinks(repo_path, feature_key, None)

    # 推送合并后的metadata到云端
    nas_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    save_metadata(nas_metadata_path, nas_metadata)
    print(f"元数据已保存并推送: {nas_metadata_path}")


def sync_files(
    repo_path: str | Path,
    feature_keys: list[str] | None = None,
    direction: Literal["pull", "push"] = "pull",
) -> None:
    """
    同步文件(pull或push)
    :param repo_path: 云端NAS数据集路径
    :param feature_keys: 要同步的特征列表
    :param direction: 同步方向 'pull'(从云端NAS到本地sync_files) 或 'push'(从本地sync_files到云端NAS)
    """
    if direction == "pull":
        pull_files(repo_path, feature_keys)
    elif direction == "push":
        push_files(repo_path, feature_keys)
    else:
        raise ValueError(f"不支持的同步方向: {direction}")
