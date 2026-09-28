# 变量替换工具：支持 ${var_name} 和 ${secret.secret_name}
import re

from src import secret

_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve(expr: str, vars_: dict):
    expr = expr.strip()
    if expr.startswith("secret."):
        return secret.get_secret(expr[len("secret."):])
    if expr in vars_:
        return vars_[expr]
    raise KeyError(f"变量未定义: {expr}")


def render(value, vars_: dict):
    """递归替换字符串中的 ${...} 引用。
    若整个字符串就是一个引用，则返回原始类型（保持 int 等类型）。"""
    if isinstance(value, str):
        m = _PATTERN.fullmatch(value)
        if m:
            return _resolve(m.group(1), vars_)
        return _PATTERN.sub(lambda m: str(_resolve(m.group(1), vars_)), value)
    if isinstance(value, list):
        return [render(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: render(v, vars_) for k, v in value.items()}
    return value
