# Builtin operations used by build-in action blocks: simple in-process
# steps (sleep / format / getter) that need no plugin and no target.
# Params are rendered before being passed in, so values here are final.
import logging
import re
import time

logger = logging.getLogger("executor")


def run_builtin(name: str, params: dict, vars_: dict):
    """Run one builtin operation; it may update vars_ in place"""
    handler = _BUILTINS.get(name)
    if handler is None:
        raise ValueError(f"unknown builtin operation: {name}")
    return handler(params, vars_)


def _sleep(params: dict, vars_: dict):
    seconds = params["seconds"]
    logger.info("builtin sleep: %.1f seconds", seconds)
    time.sleep(seconds)


def _format(params: dict, vars_: dict):
    value = params["string"]
    vars_[params["save_as"]] = value
    logger.info("builtin format: saved var %s = %r", params["save_as"], value)


def _getter(params: dict, vars_: dict):
    value = params["value_from"]
    getter = (params.get("value_getter") or "").strip()
    if getter:
        value = _extract(value, getter)
    vars_[params["save_as"]] = value
    logger.info("builtin getter: saved var %s = %r", params["save_as"], value)


def _extract(value, getter: str):
    """Extract a value with the getter: a dotted path for dicts
    (a.b.c means dict['a']['b']['c']), otherwise a regex applied to the
    string form (group 1 is returned if present, else the whole match)"""
    if isinstance(value, dict):
        for part in getter.split("."):
            if not isinstance(value, dict) or part not in value:
                raise KeyError(f"getter path not found: {getter}")
            value = value[part]
        return value
    m = re.search(getter, str(value))
    if m is None:
        raise ValueError(f"getter regex did not match: {getter}")
    return m.group(1) if m.groups() else m.group(0)


_BUILTINS = {
    "sleep": _sleep,
    "format": _format,
    "getter": _getter,
}
