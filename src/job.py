# Job 执行器：顺序执行 actions，concurrency 块内使用线程池并发执行
import concurrent.futures
import itertools
import logging
import time

from src.action import load_action
from src.parse import JobDef
from src.persist import persist
from src.util import render

logger = logging.getLogger("executor")


class Job:
    def __init__(self, job_def: JobDef, job_id: str):
        self.job_def = job_def
        self.job_id = job_id
        self.vars = job_def.vars
        self._seq = itertools.count(1)

    def _resolve_targets(self, target_names: list) -> list:
        targets = []
        for name in target_names or []:
            if name not in self.job_def.targets:
                raise KeyError(f"target 未定义: {name}")
            target = dict(self.job_def.targets[name])
            target["_name"] = name
            targets.append(target)
        return targets

    def _build_action(self, spec: dict):
        name = spec.get("name")
        if not name:
            raise ValueError("action 缺少 name")
        params = render(spec.get("params") or {}, self.vars)
        targets = render(self._resolve_targets(spec.get("targets")), self.vars)
        timeout = spec.get("timeout")
        retry_policy = spec.get("retry")
        cls = load_action(name)
        return cls(params, targets, timeout, retry_policy)

    def _run_action(self, spec: dict) -> dict:
        action = self._build_action(spec)
        retry = action.retry_policy or {}
        times = int(retry.get("times", 1))
        interval = int(retry.get("interval", 0))
        last_error = None
        for attempt in range(1, times + 1):
            try:
                logger.info("执行 action %s (第 %d/%d 次)", action.name, attempt, times)
                result = action.run()
                persist(self.job_def.persistence, self.job_id,
                        self.job_def.name, next(self._seq), action.name, result)
                return result
            except Exception as e:
                last_error = e
                logger.error("action %s 第 %d 次执行失败: %s",
                             action.name, attempt, e)
                if attempt < times and interval > 0:
                    time.sleep(interval)
        raise RuntimeError(
            f"action {action.name} 重试 {times} 次后仍失败: {last_error}"
        ) from last_error

    def run(self) -> bool:
        logger.info("=" * 60)
        logger.info("开始执行 job %s (id=%s, 文件=%s)",
                    self.job_def.name, self.job_id, self.job_def.path)
        for block in self.job_def.actions:
            if "concurrency" in block:
                specs = block["concurrency"]
                specs = [s["action"] if "action" in s else s for s in specs]
                logger.info("并发执行 %d 个 action", len(specs))
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=len(specs)
                ) as pool:
                    futures = [pool.submit(self._run_action, s) for s in specs]
                    for f in futures:
                        f.result()  # 抛出首个异常，终止 job
            elif "action" in block:
                self._run_action(block["action"])
            else:
                raise ValueError(f"未知的 action 块定义: {block}")
        logger.info("job %s (id=%s) 执行完成", self.job_def.name, self.job_id)
        return True
