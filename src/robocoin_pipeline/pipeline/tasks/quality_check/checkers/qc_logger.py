#!/usr/bin/env python3
"""
独立的日志配置工具 - 无任何项目依赖

可直接复制到任何项目中使用，无需依赖 robocoin_dataset 或其他项目库
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(
    name: str,
    log_dir: str | Path | None = None,
    level: int = logging.INFO,
    log_file: str | None = None,
) -> logging.Logger:
    """
    配置日志系统

    Args:
        name: logger名称
        log_dir: 日志目录（默认: ./logs）
        level: 日志级别（默认: INFO）
        log_file: 日志文件名（默认: {name}_{timestamp}.log）

    Returns:
        配置好的logger对象

    示例:
        logger = setup_logger("MY_APP", log_dir="./logs")
        logger.info("应用启动")
    """
    logger = logging.getLogger(name)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 创建formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件handler（可选）
    if log_dir is not None or log_file is not None:
        log_dir = Path(log_dir or "./logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名
        if log_file is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = f"{name}_{timestamp}.log"

        log_path = log_dir / log_file

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 简化的快速使用函数
def get_logger(name: str) -> logging.Logger:
    """
    获取或创建logger（简化版本）

    示例:
        logger = get_logger("QC")
        logger.info("开始检查")
    """
    logger = logging.getLogger(name)

    # 如果还没有handler，添加一个简单的console handler
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)

    return logger


if __name__ == "__main__":
    # 测试
    logger = setup_logger("TEST", log_dir="./test_logs")
    logger.info("测试信息")
    logger.warning("测试警告")
    logger.error("测试错误")

    print("✅ Logger test passed!")
