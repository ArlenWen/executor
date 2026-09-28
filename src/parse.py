# 解析job.yaml，返回需要执行的job列表
# 处理 depends 依赖，按依赖顺序返回（依赖的 job 在前）
import glob
import os

import yaml


class JobDef:
    def __init__(self, path: str, data: dict):
        self.path = path  # job 文件绝对路径
        self.name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
        self.description = data.get("description", "")
        self.depends = data.get("depends") or []
        self.vars = data.get("vars") or {}
        self.targets = data.get("targets") or {}
        self.persistence = data.get("persistence") or []
        self.actions = data.get("actions") or []

    def __repr__(self):
        return f"<JobDef {self.name} ({self.path})>"


def _resolve_dep_path(dep: str, base_dir: str) -> str:
    """depends 中的 job 引用是相对于当前 job 文件的路径，不带 .yaml 后缀"""
    path = os.path.normpath(os.path.join(base_dir, dep))
    if not path.endswith(".yaml"):
        path += ".yaml"
    return os.path.abspath(path)


def load_job(path: str, _seen: dict = None, _order: list = None) -> list:
    """解析单个 job 文件及其依赖，返回按依赖顺序排列的 JobDef 列表"""
    if _seen is None:
        _seen, _order = {}, []
    path = os.path.abspath(path)
    if path in _seen:
        return _order
    if not os.path.exists(path):
        raise FileNotFoundError(f"job 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"job 文件格式错误: {path}")
    job = JobDef(path, data)
    _seen[path] = job
    for dep in job.depends:
        dep_ref = dep.get("job") if isinstance(dep, dict) else dep
        dep_path = _resolve_dep_path(dep_ref, os.path.dirname(path))
        load_job(dep_path, _seen, _order)
    _order.append(job)
    return _order


def load_dir(directory: str) -> list:
    """解析目录下所有 job 文件，去重并按依赖顺序返回"""
    seen, order = {}, []
    files = sorted(
        glob.glob(os.path.join(directory, "*.yaml"))
        + glob.glob(os.path.join(directory, "*.yml"))
    )
    if not files:
        raise FileNotFoundError(f"目录下没有 job 文件: {directory}")
    for f in files:
        load_job(f, seen, order)
    return order
