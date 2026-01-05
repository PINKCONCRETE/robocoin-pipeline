# 🛠️ 开发者指南：本地开发环境设置

本项目采用 **Black** 进行代码格式化，**Ruff** 进行静态检查与自动修复。为确保代码风格统一，请按以下步骤配置你的开发环境。

---

## 0. vscode插件推荐
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Black Formatter](https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter)

## 1. 项目安装
```bash
git clone https://github.com/your-username/robocoin-pipeline.git
cd robocoin-pipeline
uv venv
source venv/bin/activate
uv pip install -e ".[dev]"
uv pre-commit install
```

## 2.环境配置
### 单机模式
```bash
# cd your-local-repo-dir:
# 设置运行模式为单机模式
export ROBOCOIN_PIPELINE_REMOTE_MODE=0
# 设置本地存储cache目录
export ROBOCOIN_PIPELINE_CACHE_ROOT_PATH = $HOME/.cache/robocoin-pipeline
# 设置本地存储缓存大小（GB）
export ROBOCOIN_PIPELINE_MAX_CACHE = 1024
# 设置任务资源配置目录
export ROBOCOIN_PIPELINE_TASK_RESOURCE_CONFIG_ROOT=$PWD/configs/task_resources
```
如果想使得设置永久生效，请使用：
```bash
#!/bin/bash

# ==============================
# RoboCOIN Pipeline - 单机模式
# 自动写入正确的 Shell 配置文件
# ==============================

# 定义要写入的环境变量（使用 $HOME 替代 ~ 以确保兼容性）
# cd your-local-repo-dir:
ENV_LINES=(
    'export ROBOCOIN_PIPELINE_REMOTE_MODE=0'
    'export ROBOCOIN_PIPELINE_CACHE_ROOT_PATH=$HOME/.cache/robocoin-pipeline'
    'export ROBOCOIN_PIPELINE_MAX_CACHE=1024'
    'export ROBOCOIN_PIPELINE_TASK_RESOURCE_CONFIG_ROOT=$PWD/configs/task_resources'
)

# 判断当前默认 Shell
SHELL_NAME=$(basename "$SHELL")

if [[ "$SHELL_NAME" == "zsh" ]]; then
    TARGET_FILE="$HOME/.zshrc"
elif [[ "$SHELL_NAME" == "bash" ]]; then
    # 在 macOS 中，登录 shell 通常读取 ~/.bash_profile
    # 在 Linux 中，交互式非登录 shell 读取 ~/.bashrc
    if [[ "$OSTYPE" == "darwin"* ]]; then
        TARGET_FILE="$HOME/.bash_profile"
    else
        TARGET_FILE="$HOME/.bashrc"
    fi
else
    echo "警告: 未知的 Shell ($SHELL)，默认写入 ~/.bashrc"
    TARGET_FILE="$HOME/.bashrc"
fi

# 避免重复写入：检查是否已存在标记
MARKER="# RoboCOIN Pipeline - 单机模式 (auto-added)"
if grep -qF "$MARKER" "$TARGET_FILE" 2>/dev/null; then
    echo "检测到已有单机模式配置，跳过写入。"
else
    echo "" >> "$TARGET_FILE"
    echo "$MARKER" >> "$TARGET_FILE"
    for line in "${ENV_LINES[@]}"; do
        echo "$line" >> "$TARGET_FILE"
    done
    echo "✅ 已将单机模式环境变量写入 $TARGET_FILE"
fi

echo "请运行以下命令使配置立即生效："
echo "  source \"$TARGET_FILE\""
```
### 分布式模式
```bash

# cd your-local-repo-dir:
# 设置运行模式为DASK模式
export ROBOCOIN_PIPELINE_REMOTE_MODE=1
# 设置远程存储cache目录
export ROBOCOIN_PIPELINE_REMOTE_ROOT_PATH=/mnt/nas/synnas/docker2/robocoin-pipeline
# 设置本地存储cache目录
export ROBOCOIN_PIPELINE_CACHE_ROOT_PATH=$HOME/.cache/robocoin-pipeline
# 设置本地存储缓存大小（GB）
export ROBOCOIN_PIPELINE_MAX_CACHE=1024
# 配置任务资源配置目录
export ROBOCOIN_PIPELINE_TASK_RESOURCE_CONFIG_ROOT=$ROBOCOIN_PIPELINE_REMOTE_ROOT_PATH/task_resources
```

如果想使得设置永久生效，请使用：
```bash
#!/bin/bash

# ==============================
# RoboCOIN Pipeline - 分布式模式
# 自动写入正确的 Shell 配置文件
# ==============================

# 定义要写入的环境变量
ENV_LINES=(
    'export ROBOCOIN_PIPELINE_REMOTE_MODE=1'
    'export ROBOCOIN_PIPELINE_REMOTE_ROOT_PATH=/mnt/nas/synnas/docker2/robocoin-pipeline'
    'export ROBOCOIN_PIPELINE_CACHE_ROOT_PATH=$HOME/.cache/robocoin-pipeline'
    'export ROBOCOIN_PIPELINE_MAX_CACHE=1024'
    'export ROBOCOIN_PIPELINE_TASK_RESOURCE_CONFIG_ROOT=$ROBOCOIN_PIPELINE_REMOTE_ROOT_PATH/task_resources'
)

# 判断当前默认 Shell
SHELL_NAME=$(basename "$SHELL")

if [[ "$SHELL_NAME" == "zsh" ]]; then
    TARGET_FILE="$HOME/.zshrc"
elif [[ "$SHELL_NAME" == "bash" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        TARGET_FILE="$HOME/.bash_profile"
    else
        TARGET_FILE="$HOME/.bashrc"
    fi
else
    echo "警告: 未知的 Shell ($SHELL)，默认写入 ~/.bashrc"
    TARGET_FILE="$HOME/.bashrc"
fi

# 避免重复写入
MARKER="# RoboCOIN Pipeline - 分布式模式 (auto-added)"
if grep -qF "$MARKER" "$TARGET_FILE" 2>/dev/null; then
    echo "检测到已有分布式模式配置，跳过写入。"
else
    echo "" >> "$TARGET_FILE"
    echo "$MARKER" >> "$TARGET_FILE"
    for line in "${ENV_LINES[@]}"; do
        echo "$line" >> "$TARGET_FILE"
    done
    echo "✅ 已将分布式模式环境变量写入 $TARGET_FILE"
fi

echo "请运行以下命令使配置立即生效："
echo "  source \"$TARGET_FILE\""
```
