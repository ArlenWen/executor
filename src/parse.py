# Parse job.yaml files and return the list of jobs to execute.
# Handles depends dependencies and returns jobs in dependency order
# (dependent jobs first).
import glob
import os

import yaml

_TOP_KEYS = {"version", "name", "description", "depends", "vars",
             "targets", "persistence", "notify", "actions"}

_BUILTIN_NAMES = ("sleep", "format", "getter")


def _fail(path: str, msg: str):
    raise ValueError(f"validation failed for job file {path}: {msg}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate_depends(depends, path: str):
    if not isinstance(depends, list):
        _fail(path, "depends must be a list")
    for dep in depends:
        if isinstance(dep, str):
            continue
        if isinstance(dep, dict) and isinstance(dep.get("job"), str):
            continue
        _fail(path, f"depends item must be a string or a dict with a job field: {dep}")


def _validate_targets(targets, path: str):
    if not isinstance(targets, dict):
        _fail(path, "targets must be a dict")
    for name, t in targets.items():
        if not isinstance(t, dict):
            _fail(path, f"target {name} must be a dict")
        protocol = t.get("protocol")
        if protocol not in ("ssh", "local"):
            _fail(path, f"protocol of target {name} must be ssh or local: {protocol}")
        if protocol == "ssh":
            for field in ("host", "user"):
                if not isinstance(t.get(field), str) or not t.get(field):
                    _fail(path, f"target {name} missing a valid {field} field")
        port = t.get("port")
        if port is not None and (not _is_int(port) or port <= 0):
            _fail(path, f"port of target {name} must be a positive integer: {port}")


def _validate_persistence(persistence, path: str):
    if not isinstance(persistence, list):
        _fail(path, "persistence must be a list")
    for dest in persistence:
        if not isinstance(dest, dict):
            _fail(path, f"persistence item must be a dict: {dest}")
        if len(set(dest) - {"on_failure"}) != 1:
            _fail(path, f"persistence item must be a dict with exactly one destination key: {dest}")
        if "on_failure" in dest and not isinstance(dest["on_failure"], bool):
            _fail(path, f"on_failure of persistence must be a bool: {dest}")
        if "local" in dest:
            if not isinstance(dest["local"], str):
                _fail(path, f"persistence local must be a string path: {dest}")
        elif "mongodb" in dest:
            cfg = dest["mongodb"]
            if not isinstance(cfg, dict) or not isinstance(cfg.get("uri"), str):
                _fail(path, f"persistence mongodb missing a valid uri: {dest}")
            for field in ("database", "collection", "username", "password"):
                if field in cfg and not isinstance(cfg[field], str):
                    _fail(path, f"{field} of persistence mongodb must be a string")
            if "ssl" in cfg and not isinstance(cfg["ssl"], bool):
                _fail(path, "ssl of persistence mongodb must be a bool")
        else:
            _fail(path, f"unknown persistence type: {dest}")


def _validate_notify(notify, path: str):
    if not isinstance(notify, list):
        _fail(path, "notify must be a list")
    for dest in notify:
        if not isinstance(dest, dict):
            _fail(path, f"notify item must be a dict: {dest}")
        if len(set(dest) - {"on_failure"}) != 1:
            _fail(path, f"notify item must be a dict with exactly one type key: {dest}")
        if "on_failure" in dest and not isinstance(dest["on_failure"], bool):
            _fail(path, f"on_failure of notify must be a bool: {dest}")
        if "email" in dest:
            cfg = dest["email"]
            if not isinstance(cfg, dict):
                _fail(path, f"notify email must be a dict: {dest}")
            for field in ("from", "subject", "body", "smtp_host"):
                if not isinstance(cfg.get(field), str) or not cfg[field]:
                    _fail(path, f"{field} of notify email must be a non-empty string: {cfg}")
            to = cfg.get("to")
            if not (isinstance(to, str) and to) and not (
                    isinstance(to, list) and to and
                    all(isinstance(t, str) for t in to)):
                _fail(path, f"to of notify email must be a non-empty string or list of strings: {cfg}")
            smtp_port = cfg.get("smtp_port")
            if smtp_port is not None and (not _is_int(smtp_port) or smtp_port <= 0):
                _fail(path, f"smtp_port of notify email must be a positive integer: {cfg}")
            for field in ("smtp_user", "smtp_password"):
                if field in cfg and not isinstance(cfg[field], str):
                    _fail(path, f"{field} of notify email must be a string: {cfg}")
            if "smtp_ssl" in cfg and not isinstance(cfg["smtp_ssl"], bool):
                _fail(path, f"smtp_ssl of notify email must be a bool: {cfg}")
        elif "webhook" in dest:
            cfg = dest["webhook"]
            if not isinstance(cfg, dict) or not isinstance(cfg.get("url"), str):
                _fail(path, f"notify webhook missing a valid url: {dest}")
            if "method" in cfg and not isinstance(cfg["method"], str):
                _fail(path, f"method of notify webhook must be a string: {cfg}")
            headers = cfg.get("headers")
            if headers is not None and (not isinstance(headers, dict) or
                                        not all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in headers.items())):
                _fail(path, f"headers of notify webhook must be a dict of strings: {cfg}")
        elif "kafka" in dest:
            cfg = dest["kafka"]
            if not isinstance(cfg, dict) or not isinstance(cfg.get("topic"), str):
                _fail(path, f"notify kafka missing a valid topic: {dest}")
            broker = cfg.get("broker")
            if not (isinstance(broker, str) and broker) and not (
                    isinstance(broker, list) and broker and
                    all(isinstance(b, str) for b in broker)):
                _fail(path, f"broker of notify kafka must be a non-empty string or list of strings: {cfg}")
        elif "rabbitmq" in dest:
            cfg = dest["rabbitmq"]
            if not isinstance(cfg, dict) or not isinstance(cfg.get("queue"), str):
                _fail(path, f"notify rabbitmq missing a valid queue: {dest}")
            port = cfg.get("port")
            if port is not None and (not _is_int(port) or port <= 0):
                _fail(path, f"port of notify rabbitmq must be a positive integer: {cfg}")
            for field in ("host", "username", "password", "virtual_host"):
                if field in cfg and not isinstance(cfg[field], str):
                    _fail(path, f"{field} of notify rabbitmq must be a string: {cfg}")
        else:
            _fail(path, f"unknown notify type: {dest}")


def _validate_action(spec, targets: dict, path: str, where: str):
    if not isinstance(spec, dict):
        _fail(path, f"{where} must be a dict")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        _fail(path, f"{where} missing a valid name field")
    params = spec.get("params")
    if params is not None and not isinstance(params, dict):
        _fail(path, f"params of {where} must be a dict")
    tnames = spec.get("targets")
    if tnames is not None:
        if not isinstance(tnames, list) or \
                not all(isinstance(t, str) for t in tnames):
            _fail(path, f"targets of {where} must be a list of strings")
        for t in tnames:
            if t not in targets:
                _fail(path, f"{where} references an undefined target: {t}")
    timeout = spec.get("timeout")
    if timeout is not None and (not _is_int(timeout) or timeout <= 0):
        _fail(path, f"timeout of {where} must be a positive integer: {timeout}")
    failed = spec.get("failed", "skip")
    if failed not in ("skip", "exit"):
        _fail(path, f"failed of {where} must be skip or exit: {failed}")
    retry = spec.get("retry")
    if retry is not None:
        if not isinstance(retry, dict):
            _fail(path, f"retry of {where} must be a dict")
        times = retry.get("times", 1)
        if not _is_int(times) or times < 1:
            _fail(path, f"retry.times of {where} must be an integer >= 1: {times}")
        interval = retry.get("interval", 0)
        if not _is_int(interval) or interval < 0:
            _fail(path, f"retry.interval of {where} must be an integer >= 0: {interval}")


def _validate_builtin(spec, path: str, where: str):
    if not isinstance(spec, dict):
        _fail(path, f"{where} must be a dict")
    unknown = set(spec) - {"name", "params"}
    if unknown:
        _fail(path, f"unknown fields of {where}: {sorted(unknown)}")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        _fail(path, f"{where} missing a valid name field")
    if name not in _BUILTIN_NAMES:
        _fail(path, f"unknown builtin name of {where}: {name}")
    params = spec.get("params") or {}
    if not isinstance(params, dict):
        _fail(path, f"params of {where} must be a dict")
    if name == "sleep":
        seconds = params.get("seconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) \
                or seconds <= 0:
            _fail(path, f"seconds of {where} must be a positive number: {seconds}")
    elif name == "format":
        if not isinstance(params.get("string"), str) or not params["string"]:
            _fail(path, f"string of {where} must be a non-empty string")
        if not isinstance(params.get("save_as"), str) or not params["save_as"]:
            _fail(path, f"save_as of {where} must be a non-empty string")
    else:  # getter
        if not isinstance(params.get("value_from"), str) or not params["value_from"]:
            _fail(path, f"value_from of {where} must be a non-empty string")
        if not isinstance(params.get("save_as"), str) or not params["save_as"]:
            _fail(path, f"save_as of {where} must be a non-empty string")
        if params.get("value_getter") is not None and \
                not isinstance(params["value_getter"], str):
            _fail(path, f"value_getter of {where} must be a string")


def _validate_actions(actions, targets: dict, path: str):
    if not isinstance(actions, list) or not actions:
        _fail(path, "actions must be a non-empty list")
    for i, block in enumerate(actions, 1):
        where = f"actions[{i}]"
        if not isinstance(block, dict) or len(block) != 1:
            _fail(path, f"{where} must be a dict with only concurrency, "
                        f"action or build-in: {block}")
        if "concurrency" in block:
            specs = block["concurrency"]
            if not isinstance(specs, list) or not specs:
                _fail(path, f"concurrency of {where} must be a non-empty list")
            for j, item in enumerate(specs, 1):
                spec = item.get("action") if isinstance(item, dict) and \
                    "action" in item else item
                _validate_action(spec, targets, path,
                                 f"{where}.concurrency[{j}]")
        elif "action" in block:
            _validate_action(block["action"], targets, path, f"{where}.action")
        elif "build-in" in block:
            specs = block["build-in"]
            if not isinstance(specs, list) or not specs:
                _fail(path, f"build-in of {where} must be a non-empty list")
            for j, item in enumerate(specs, 1):
                _validate_builtin(item, path, f"{where}.build-in[{j}]")
        else:
            _fail(path, f"unknown action block definition: {block}")


def validate(data: dict, path: str):
    """Validate the fields of a job file; raise ValueError on any violation"""
    unknown = set(data) - _TOP_KEYS
    if unknown:
        _fail(path, f"unknown fields: {sorted(unknown)}")
    version = data.get("version")
    if version is not None and not _is_int(version):
        _fail(path, f"version must be an integer: {version}")
    for field in ("name", "description"):
        if data.get(field) is not None and not isinstance(data[field], str):
            _fail(path, f"{field} must be a string")
    if data.get("depends"):
        _validate_depends(data["depends"], path)
    if data.get("vars") is not None and not isinstance(data["vars"], dict):
        _fail(path, "vars must be a dict")
    targets = data.get("targets") or {}
    _validate_targets(targets, path)
    if data.get("persistence"):
        _validate_persistence(data["persistence"], path)
    if data.get("notify"):
        _validate_notify(data["notify"], path)
    _validate_actions(data.get("actions"), targets, path)


class JobDef:
    def __init__(self, path: str, data: dict):
        self.path = path  # absolute path of the job file
        self.name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
        self.description = data.get("description", "")
        self.depends = data.get("depends") or []
        self.vars = data.get("vars") or {}
        self.targets = data.get("targets") or {}
        self.persistence = data.get("persistence") or []
        self.notify = data.get("notify") or []
        self.actions = data.get("actions") or []

    def __repr__(self):
        return f"<JobDef {self.name} ({self.path})>"


def _resolve_dep_path(dep: str, base_dir: str) -> str:
    """Job references in depends are paths relative to the current job file,
    without the .yaml suffix"""
    path = os.path.normpath(os.path.join(base_dir, dep))
    if not path.endswith(".yaml"):
        path += ".yaml"
    return os.path.abspath(path)


def load_job(path: str, _seen: dict = None, _order: list = None) -> list:
    """Parse a single job file and its dependencies; return JobDef list in
    dependency order"""
    if _seen is None:
        _seen, _order = {}, []
    path = os.path.abspath(path)
    if path in _seen:
        return _order
    if not os.path.exists(path):
        raise FileNotFoundError(f"job file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"invalid job file format: {path}")
    validate(data, path)
    job = JobDef(path, data)
    _seen[path] = job
    for dep in job.depends:
        dep_ref = dep.get("job") if isinstance(dep, dict) else dep
        dep_path = _resolve_dep_path(dep_ref, os.path.dirname(path))
        load_job(dep_path, _seen, _order)
    _order.append(job)
    return _order


def load_dir(directory: str) -> list:
    """Parse all job files in a directory; deduplicate and return them in
    dependency order"""
    seen, order = {}, []
    files = sorted(
        glob.glob(os.path.join(directory, "*.yaml"))
        + glob.glob(os.path.join(directory, "*.yml"))
    )
    if not files:
        raise FileNotFoundError(f"no job files in directory: {directory}")
    for f in files:
        load_job(f, seen, order)
    return order
