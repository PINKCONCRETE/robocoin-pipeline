"""测试文件同步功能"""

from pathlib import Path

from robocoin_pipeline.utils.file_sync import pull_files, push_files

# 数据集路径
DATASET_PATH = (
    "/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_basket_storage_peach"
)
FEATURES = ["scenec_annotation", "subtask_annotation"]


def test_pull() -> None:
    """测试从云端拉取数据"""
    print("=" * 60)
    print("测试: Pull数据从云端NAS")
    print("=" * 60)
    pull_files(repo_path=DATASET_PATH, feature_keys=FEATURES)

    # 验证本地文件
    sync_dir = Path(__file__).parent.parent / "sync_files"
    dataset_name = Path(DATASET_PATH).name
    local_path = sync_dir / dataset_name

    print(f"\n本地同步目录: {local_path}")
    print(f"元数据文件: {local_path / '.sync_metadata.json'}")


def test_push() -> None:
    """测试推送数据到云端（使用测试目录）"""
    print("\n" + "=" * 60)
    print("测试: Push数据到测试目录")
    print("=" * 60)

    # 推送到临时测试目录避免影响真实数据
    test_path = "/tmp/test_nas_dataset/unitree_g1_basket_storage_peach"
    push_files(repo_path=test_path, feature_keys=FEATURES)

    print(f"\n测试目录: {test_path}")
    print(f"元数据文件: {test_path}/.sync_metadata.json")


if __name__ == "__main__":
    test_pull()
    test_push()
