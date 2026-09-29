# Job executor: run actions sequentially; concurrency blocks run in parallel
# via a thread pool
import concurrent.futures
import itertools
import logging
import time

from src.action import load_action
from src.parse import JobDef
from src.persist import persist
from src.util import render

logger = logging.getLogger("executor")


class JobExitError(Exception):
    """Raised when an action has failed=exit: aborts the current job and
    prevents any subsequent jobs from running"""


class Job:
    def __init__(self, job_def: JobDef, job_id: str):
        self.job_def = job_def
        self.job_id = job_id
        self.vars = job_def.vars
        self._seq = itertools.count(1)
        # Cache of finished action results, persisted together when the job ends
        self._results = []

    def _resolve_targets(self, target_names: list) -> list:
        targets = []
        for name in target_names or []:
            if name not in self.job_def.targets:
                raise KeyError(f"target not defined: {name}")
            target = dict(self.job_def.targets[name])
            target["_name"] = name
            targets.append(target)
        return targets

    def _build_action(self, spec: dict):
        name = spec.get("name")
        if not name:
            raise ValueError("action missing name")
        params = render(spec.get("params") or {}, self.vars)
        targets = render(self._resolve_targets(spec.get("targets")), self.vars)
        timeout = spec.get("timeout")
        retry_policy = spec.get("retry")
        cls = load_action(name)
        return cls(params, targets, timeout, retry_policy)

    def _run_action(self, spec: dict) -> dict:
        failed_policy = spec.get("failed", "skip")
        if failed_policy not in ("skip", "exit"):
            raise ValueError(
                f"invalid failed field of action {spec.get('name')}: "
                f"{failed_policy} (only skip/exit supported)"
            )
        action = self._build_action(spec)
        retry = action.retry_policy or {}
        times = int(retry.get("times", 1))
        interval = int(retry.get("interval", 0))
        last_error = None
        for attempt in range(1, times + 1):
            try:
                logger.info("running action %s (attempt %d/%d)", action.name, attempt, times)
                result = action.run()
                self._results.append((next(self._seq), action.name, result))
                return result
            except Exception as e:
                last_error = e
                logger.error("action %s attempt %d failed: %s",
                             action.name, attempt, e)
                if attempt < times and interval > 0:
                    time.sleep(interval)
        if failed_policy == "exit":
            raise JobExitError(
                f"action {action.name} still failed after {times} attempts: {last_error}"
            ) from last_error
        logger.warning("action %s still failed after %d attempts, skipped per failed=skip: %s",
                       action.name, times, last_error)
        return None

    def _flush_results(self, success: bool):
        """Persist cached results together when the job ends;
        on job failure only write to destinations whose on_failure is true
        (the default)"""
        dests = [d for d in self.job_def.persistence
                 if success or d.get("on_failure", True)]
        for seq, action_name, result in self._results:
            persist(dests, self.job_id, self.job_def.name,
                    seq, action_name, result)

    def run(self) -> bool:
        logger.info("=" * 60)
        logger.info("starting job %s (id=%s, file=%s)",
                    self.job_def.name, self.job_id, self.job_def.path)
        success = False
        try:
            for block in self.job_def.actions:
                if "concurrency" in block:
                    specs = block["concurrency"]
                    specs = [s["action"] if "action" in s else s for s in specs]
                    logger.info("running %d actions concurrently", len(specs))
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=len(specs)
                    ) as pool:
                        futures = [pool.submit(self._run_action, s) for s in specs]
                        for f in futures:
                            f.result()  # raise the first exception and abort the job
                elif "action" in block:
                    self._run_action(block["action"])
                else:
                    raise ValueError(f"unknown action block definition: {block}")
            success = True
            logger.info("job %s (id=%s) finished", self.job_def.name, self.job_id)
            return True
        finally:
            self._flush_results(success)
