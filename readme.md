# 🛠️ 开发者指南：本地开发环境设置

本项目采用 **Black** 进行代码格式化，**Ruff** 进行静态检查与自动修复。为确保代码风格统一，请按以下步骤配置你的开发环境。

---

## 0. vscode插件推荐
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Black Formatter](https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter)

## 1. 项目安装与开发环境配置
```bash
git clone https://github.com/your-username/robocoin-pipeline.git
cd robocoin-pipeline
uv venv
source venv/bin/activate
uv pip install -e ".[dev]"
uv pre-commit install
```
