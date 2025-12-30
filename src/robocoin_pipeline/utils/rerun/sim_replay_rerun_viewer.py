#!/usr/bin/env python3
"""
Sim Replay Rerun Viewer

使用 Rerun 可视化 MuJoCo 仿真回放的图像。
接收 sim_replay 的仿真图像，逐帧在 Rerun 中展示。

使用方法:
    python sim_replay_rerun_viewer.py --config_path <config.yaml> --repo_path <dataset_path> \\
        --robot_version default_version --episode_idx 0

依赖:
    - rerun-sdk
    - mujoco
    - pandas
    - numpy
    - pyyaml
"""

import argparse
import os
import sys
from pathlib import Path

import rerun as rr

# 在导入 mujoco 之前设置 headless 模式
os.environ["MUJOCO_GL"] = "egl"


from ..sim_replay.sim_replay import LerobotSimReplayer


def visualize_sim_replay(
    config_path: str,
    repo_path: str,
    robot_version: str,
    episode_idx: int = 0,
    action: bool = False,
    render_width: int = 640,
    render_height: int = 480,
    fps: float = 30.0,
    show_joint_data: bool = True,
) -> None:
    """
    使用 Rerun 可视化 MuJoCo 仿真回放

    Args:
        config_path: 配置文件路径
        repo_path: 数据集路径
        robot_version: 机器人版本（配置文件中的key）
        episode_idx: Episode 索引
        action: 是否使用 action 数据（否则使用 observation.state）
        render_width: 渲染宽度
        render_height: 渲染高度
        fps: 回放帧率
        show_joint_data: 是否在 Rerun 中显示关节数据曲线
    """
    # 初始化 Rerun
    rr.init(f"sim_replay_episode_{episode_idx}", spawn=True)

    # 设置时间线
    rr.log(
        "description",
        rr.TextDocument(
            f"""
# Sim Replay Viewer

- **Config**: {config_path}
- **Dataset**: {repo_path}
- **Robot Version**: {robot_version}
- **Episode**: {episode_idx}
- **Data Type**: {"action" if action else "observation.state"}
- **Resolution**: {render_width}x{render_height}
""",
            media_type=rr.MediaType.MARKDOWN,
        ),
    )

    print("初始化 Sim Replayer...")
    print(f"  Config: {config_path}")
    print(f"  Repo: {repo_path}")
    print(f"  Robot Version: {robot_version}")
    print(f"  Episode: {episode_idx}")

    # 创建 replayer（headless 模式）
    replayer = LerobotSimReplayer(
        config_path=config_path,
        robot_version=robot_version,
        repo_path=repo_path,
        episode_idx=episode_idx,
        action=action,
        headless=True,  # 始终使用 headless 模式，通过 Rerun 显示
        render_width=render_width,
        render_height=render_height,
    )

    print(f"开始回放 Episode {episode_idx}...")

    frame_idx = 0
    joint_history = {}  # 存储关节数据历史用于绘图

    frame_interval = 1.0 / fps

    try:
        while replayer.step():
            # 设置 Rerun 时间
            rr.set_time_sequence("frame", frame_idx)
            rr.set_time_seconds("time", frame_idx * frame_interval)

            # 获取渲染图像 (RGB)
            img_rgb = replayer.get_img()

            # 记录图像到 Rerun
            rr.log("sim/image", rr.Image(img_rgb))

            # 记录关节数据（如果有）
            if (
                show_joint_data
                and hasattr(replayer, "data_frame")
                and replayer.data_frame
            ):
                for key, value in replayer.data_frame.items():
                    if isinstance(value, (int, float)):
                        # 记录标量值
                        rr.log(f"joints/{key}", rr.Scalar(value))

                        # 存储历史用于调试
                        if key not in joint_history:
                            joint_history[key] = []
                        joint_history[key].append(value)

            # 记录帧信息
            rr.log("info/frame_idx", rr.Scalar(frame_idx))

            frame_idx += 1

            # 控制回放速度（可选）
            # time.sleep(frame_interval)

            # 进度输出
            if frame_idx % 100 == 0:
                print(f"  已处理 {frame_idx} 帧...")

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"错误: {e}")
        raise
    finally:
        replayer.close_viewer()

    print(f"\n✅ 回放完成！共 {frame_idx} 帧")
    print("Rerun 可视化窗口应该已经打开，可以使用时间滑块浏览。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="使用 Rerun 可视化 MuJoCo 仿真回放",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python sim_replay_rerun_viewer.py \\
    --config_path configs/task_params/sim_replay/default.yaml \\
    --repo_path /path/to/dataset \\
    --robot_version default_version \\
    --episode_idx 0

  # 使用 action 数据回放
  python sim_replay_rerun_viewer.py \\
    --config_path configs/task_params/sim_replay/default.yaml \\
    --repo_path /path/to/dataset \\
    --robot_version default_version \\
    --episode_idx 5 \\
    --action

  # 自定义分辨率和帧率
  python sim_replay_rerun_viewer.py \\
    --config_path configs/task_params/sim_replay/default.yaml \\
    --repo_path /path/to/dataset \\
    --robot_version default_version \\
    --render_width 1280 --render_height 720 \\
    --fps 60
        """,
    )

    parser.add_argument(
        "--config_path", type=str, required=True, help="仿真配置文件路径 (YAML)"
    )

    parser.add_argument(
        "--repo_path", type=str, required=True, help="LeRobot 格式数据集路径"
    )

    parser.add_argument(
        "--robot_version",
        type=str,
        required=True,
        help="机器人版本（配置文件中的 key，如 default_version）",
    )

    parser.add_argument(
        "--episode_idx", type=int, default=0, help="Episode 索引 (默认: 0)"
    )

    parser.add_argument(
        "--action",
        action="store_true",
        help="使用 action 数据回放（否则使用 observation.state）",
    )

    parser.add_argument(
        "--render_width", type=int, default=640, help="渲染宽度 (默认: 640)"
    )

    parser.add_argument(
        "--render_height", type=int, default=480, help="渲染高度 (默认: 480)"
    )

    parser.add_argument("--fps", type=float, default=30.0, help="回放帧率 (默认: 30.0)")

    parser.add_argument("--no_joints", action="store_true", help="不显示关节数据曲线")

    args = parser.parse_args()

    # 检查文件存在
    config_path = Path(args.config_path)
    repo_path = Path(args.repo_path)

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return 1

    if not repo_path.exists():
        print(f"❌ 数据集路径不存在: {repo_path}")
        return 1

    # 运行可视化
    visualize_sim_replay(
        config_path=str(config_path),
        repo_path=str(repo_path),
        robot_version=args.robot_version,
        episode_idx=args.episode_idx,
        action=args.action,
        render_width=args.render_width,
        render_height=args.render_height,
        fps=args.fps,
        show_joint_data=not args.no_joints,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
