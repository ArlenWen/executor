# 加载 config.yaml，提供全局配置
import logging
import logging.handlers
import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

_cache = None


def load() -> dict:
    global _cache
    if _cache is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
    return _cache


def get(key: str, default=None):
    return load().get(key, default)


def setup_logging(job_id: str = "executor") -> logging.Logger:
    """根据 config.yaml 中的 log 配置初始化日志，返回 logger"""
    cfg = load().get("log", {})
    level = getattr(logging, str(cfg.get("level", "info")).upper(), logging.INFO)
    logger = logging.getLogger("executor")
    logger.setLevel(level)
    logger.propagate = False
    # 避免重复添加 handler
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    if cfg.get("output", "file") == "console":
        handler = logging.StreamHandler()
    else:
        log_dir = os.path.expanduser(cfg.get("dir", "/tmp/executor/"))
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, f"{job_id}.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger
