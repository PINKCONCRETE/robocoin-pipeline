import argparse
import importlib
import json
import os
import sys
from pathlib import Path

# 必须在导入 mujoco 之前设置环境变量
# 注意：如果作为模块导入使用，调用方需要在导入前设置 os.environ['MUJOCO_GL'] = 'egl'
if '--headless' in sys.argv:
    os.environ['MUJOCO_GL'] = 'egl'

import mujoco
import mujoco.viewer
import numpy as np
import pandas as pd
import yaml


def set_mujoco_rendering_backend(backend='egl'):
    """
    设置 MuJoCo 渲染后端。
    
    警告：此函数必须在导入 mujoco 之前调用才有效！
    如果 mujoco 已经被导入，此函数将不起作用。
    
    Args:
        backend: 渲染后端，可选 'egl', 'osmesa', 'glfw'
    """
    if 'mujoco' in sys.modules:
        print(f"[Warning] mujoco already imported, setting MUJOCO_GL may not work")
    os.environ['MUJOCO_GL'] = backend

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class LerobotSimReplayer:
    def __init__(
        self,
        config_path: str,
        robot_version: str,
        repo_path: str,
        episode_idx: int = 0,
        action: bool = False,
        headless: bool = False,
        render_width: int = 640,
        render_height: int = 480,
    ):
        # 1. 加载配置
        with open(config_path, "r", encoding="utf-8") as f:
            self.full_config = yaml.safe_load(f)
        self.sim_cfg = self.full_config["sim"]
        self.xml_path = self.sim_cfg["xml_path"]
        self.robot_cfg = self.full_config[robot_version]
        self.gripper_config = self.sim_cfg["gripper_config"]
        # Normalize camera config: allow either a dict or a list of single-key dicts (YAML style)
        raw_camera = self.sim_cfg.get("camera", {})
        if isinstance(raw_camera, list):
            merged = {}
            for entry in raw_camera:
                if isinstance(entry, dict):
                    merged.update(entry)
            self.camera_config = merged
        elif isinstance(raw_camera, dict):
            self.camera_config = raw_camera
        else:
            self.camera_config = {}

        self.gripper_names = self.gripper_config["gripper_name"]

        # 2. 初始化 MuJoCo
        if not os.path.exists(self.xml_path):
            raise RuntimeError(f"Module xml file {self.xml_path} not found.")
        self.mjcf_model = mujoco.MjModel.from_xml_path(self.xml_path)
        self.mjcf_data = mujoco.MjData(self.mjcf_model)

        # 3. 初始化状态
        self.action = action
        self.repo_path = Path(repo_path)
        self.episode_idx = episode_idx
        self.headless = headless
        self.mjcf_viewer = None  # 延迟初始化
        self.mappings = []
        self._build_mappings()

        # 4. 【优化】预加载 Fix 函数，避免在 step 中重复 import
        self._init_fix_function()

        # 5. 初始化生成器
        self.frame_generator = self.get_frame_data()

        self.render_width = render_width
        self.render_height = render_height

        # 初始化 Renderer (离屏渲染，不需要显示窗口)
        self.renderer = mujoco.Renderer(
            self.mjcf_model, height=render_height, width=render_width
        )

        # 初始化 Camera 并设置参数
        self.camera = mujoco.MjvCamera()

        # Use .get with defaults and coerce to float to avoid KeyError/TypeError
        lookat_x = float(self.camera_config.get("lookat_x", 0.0))
        lookat_y = float(self.camera_config.get("lookat_y", 0.0))
        lookat_z = float(self.camera_config.get("lookat_z", 0.0))
        self.camera.lookat = np.array([lookat_x, lookat_y, lookat_z])

        self.camera.distance = float(self.camera_config.get("distance", 1.0))
        self.camera.azimuth = float(self.camera_config.get("azimuth", 0.0))
        self.camera.elevation = float(self.camera_config.get("elevation", 0.0))
        
        # UI Viewer 状态 (仅在非 headless 模式下使用)
        self.mjcf_viewer = None

    def _init_fix_function(self):
        """预先加载并实例化修正函数，提高运行效率"""
        try:
            func_name = self.sim_cfg.get("function")
            module_path = self.sim_cfg.get("module_file")

            if func_name and module_path:
                # 假设 module_file 格式为 "config.xxx"
                module_name = module_path.replace("config.", "configs.", 1)
                print(f"Loading fix function from: {module_name}.CustomFix.{func_name}")

                module = importlib.import_module(module_name)
                cls = getattr(module, "CustomFix")
                self.fix_instance = cls()  # 实例化
                self.fix_method = getattr(self.fix_instance, func_name)  # 获取方法引用
            else:
                self.fix_method = lambda x: x  # 空函数
        except Exception as e:
            # print(f"[Warning] Failed to load fix function: {e}")
            raise RuntimeError(f"[Warning] Failed to load fix function: {e}")

    def _build_mappings(self):
        """解析 YAML，建立 DataField -> QposIndex 的映射表"""
        print("-" * 30)
        print("正在构建数据映射...")
        for mj_name, data_field in self.sim_cfg["joints"].items():
            joint_id = mujoco.mj_name2id(
                self.mjcf_model, mujoco.mjtObj.mjOBJ_JOINT, mj_name
            )
            if joint_id == -1:
                print(f"[警告] XML中找不到关节: {mj_name}")
                continue
            qpos_adr = self.mjcf_model.jnt_qposadr[joint_id]
            self.mappings.append(
                {"data_key": data_field, "qpos_adr": qpos_adr, "name": mj_name}
            )
        # print("数据映射构建完成:")
        # for item in self.mappings:
        #     print(
        #         f"  数据 '{item['data_key']}' -> 关节 '{item['name']}' (qpos地址: {item['qpos_adr']})"
        #     )
        # print("-" * 30)

    def map_gripper_val(self):
        """将数据的值映射到关节"""
        self.gripper_value_open = self.robot_cfg["gripper_config"]["gripper_value_open"]
        self.gripper_value_close = self.robot_cfg["gripper_config"][
            "gripper_value_close"
        ]
        self.gripper_joint_max = self.gripper_config["gripper_joint_max"]
        self.gripper_joint_min = self.gripper_config["gripper_joint_min"]

        for name in self.gripper_names:
            if name in self.data_frame:
                val = self.data_frame[name]
                if abs(self.gripper_value_open - self.gripper_value_close) < 1e-6:
                    self.data_frame[name] = self.gripper_joint_min
                    continue

                ratio = (val - self.gripper_value_close) / (
                    self.gripper_value_open - self.gripper_value_close
                )
                # 检查范围，超出则报错
                if ratio < 0.0 or ratio > 1.0:
                    raise RuntimeError(
                        f"夹爪值 {name}={val} 超出范围 [{self.gripper_value_close}, {self.gripper_value_open}]，归一化比例={ratio}"
                    )

                sim_val = self.gripper_joint_min + ratio * (
                    self.gripper_joint_max - self.gripper_joint_min
                )
                self.data_frame[name] = sim_val

    def get_frame_data(self):
        """读取文件并建立生成器"""
        parquet_file_path = (
            self.repo_path
            / "state_action_data"
            / f"chunk-{self.episode_idx // 1000:03d}"
            / f"episode_{self.episode_idx:06d}.parquet"
        )

        if not parquet_file_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_file_path}")

        print(f"正在加载数据: {parquet_file_path}")
        # print(f"state or action?: {'action' if self.action else 'observation.state'}")
        df = pd.read_parquet(str(parquet_file_path))

        info_file_path = self.repo_path / "meta" / "info.json"
        with open(info_file_path, "r") as f:
            info = json.load(f)

        data_key = "observation.state" if not self.action else "action"
        names = info["features"][data_key]["names"]
        data_list = df[data_key].to_list()

        for frame_data in data_list:
            yield dict(zip(names, frame_data))

    def get_img(self):
        # 1. 将当前的物理状态(data) 更新到 渲染器场景中
        self.renderer.update_scene(self.mjcf_data, camera=self.camera)

        # 2. 渲染像素
        pixels = self.renderer.render()

        return pixels  # 返回 numpy array (H, W, 3) RGB格式

    def step(self) -> bool:
        try:
            self.data_frame = next(self.frame_generator)
        except StopIteration:
            print(">>> 数据回放结束")
            return False

        # 1. 归一化 gripper 值
        if self.gripper_config.get("gripper", False):  # 安全获取 boolean
            self.map_gripper_val()

        # 2. 执行修正函数 (直接调用预加载的方法)
        self.data_frame = self.fix_method(self.data_frame)

        # 3. 第一次运行时检查字段
        if not hasattr(self, "checked") or not self.checked:
            required_keys = set(item["data_key"] for item in self.mappings)
            required_keys.update(self.gripper_names)
            missing = required_keys - set(self.data_frame.keys())
            if missing:
                raise ValueError(f"Missing required data fields: {missing}")
            self.checked = True

        # 4. 赋值给 MuJoCo
        for item in self.mappings:
            key = item["data_key"]
            if key in self.data_frame:
                self.mjcf_data.qpos[item["qpos_adr"]] = self.data_frame[key]

        # 5. 更新物理状态
        mujoco.mj_forward(self.mjcf_model, self.mjcf_data)

        # 如果开启了界面，同步界面
        if self.mjcf_viewer is not None:
            self.mjcf_viewer.sync()

        return True

    def start_viewer(self) -> None:
        """只在非 headless 模式下启动 viewer"""
        if not self.headless and self.mjcf_viewer is None:
            print("启动 MuJoCo Viewer...")
            self.mjcf_viewer = mujoco.viewer.launch_passive(
                self.mjcf_model, self.mjcf_data
            )
            self.mjcf_viewer.sync()

    def sync_viewer(self) -> None:
        """每一帧都需要调用"""
        if self.mjcf_viewer is not None:
            self.mjcf_viewer.sync()

    def close_viewer(self) -> None:
        if self.mjcf_viewer is not None:
            self.mjcf_viewer.close()
            self.mjcf_viewer = None


import time

import cv2  # 用于保存图片


def main():
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "--robot_version",
        required=True,
        help="Robot version inside config, e.g. default_version",
    )
    parser.add_argument(
        "--repo_path", required=True, help="Path to the converted dataset (leformat)"
    )
    parser.add_argument(
        "--action", action="store_true", help="Whether to replay action data instead of state"
    )
    parser.add_argument(
        "--episode_idx",
        type=int,
        default=0,
        help="Index of the episode to replay within the dataset",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Basis for displaying the Mujoco window"
    )
    args = parser.parse_args()
    print(args.robot_version)
    replayer = LerobotSimReplayer(
        "configs/task_params/sim_replay/default.yaml",
        args.robot_version,
        args.repo_path,
        args.episode_idx,
        args.action,
        args.headless,
    )

    if not args.headless:
        replayer.start_viewer()

    print(f"开始回放 episode {args.episode_idx}...")

    # 创建保存目录
    save_dir = Path("output_frames")
    save_dir.mkdir(exist_ok=True)

    frame_idx = 0
    try:
        while replayer.step():
            # 获取当前帧图像
            img_rgb = replayer.get_img()

            # 保存图片 (OpenCV 使用 BGR 格式)
            if frame_idx % 5 == 0:  # 每5帧存一张，避免太多
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                cv2.imwrite(str(save_dir / f"{frame_idx:04d}.png"), img_bgr)

            frame_idx += 1

            # # 控制回放速度
            # time.sleep(0.02)

    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        replayer.close_viewer()
        print(f"Done. Images saved to {save_dir.absolute()}")


if __name__ == "__main__":
    main()
