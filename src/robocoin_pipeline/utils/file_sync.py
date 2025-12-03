"""
src.robocoin_pipeline.utils.file_sync

文件同步工具：支持在云端NAS和本地sync_files之间双向同步数据
使用UUID追踪机制确保数据一致性和增量更新
"""

import json
import shutil
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from robocoin_pipeline.config import ROBOCOIN_PIPELINE_DISTRIBUTION_MODE

METADATA_FILE = ".sync_metadata.json"
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
    config_path = Path(__file__).parent / "feature_key.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def initialize_metadata(
    metadata: dict[str, dict], feature_config: dict[str, list[str]]
) -> None:
    """为所有feature_key初始化UUID"""
    for feature_key in feature_config:
        ensure_feature_uuid(metadata, feature_key)


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
        has_local_data = False
        for file_path in feature_config[feature_key]:
            if (sync_dir / file_path).exists():
                has_local_data = True
                break

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

        for file_path in feature_config[feature_key]:
            src = sync_dir / file_path
            dst = repo_path / file_path

            if not src.exists():
                print(f"  源文件不存在: {src}")
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
