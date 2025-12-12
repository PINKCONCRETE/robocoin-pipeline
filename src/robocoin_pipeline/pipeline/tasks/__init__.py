# robocoin/tasks/__init__.py
import importlib
from pathlib import Path

# 获取当前目录
TASKS_DIR = Path(__file__).parent

# 自动导入所有 .py 文件（除 __init__.py）
for file in TASKS_DIR.glob("*.py"):
    if file.name.startswith("_") or file.name == "__init__.py":
        continue
    module_name = file.stem
    importlib.import_module(f".{module_name}", package=__package__)
