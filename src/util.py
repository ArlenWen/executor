# Variable substitution utility: supports ${var_name} and ${secret.secret_name}
import re

from src import secret

_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve(expr: str, vars_: dict):
    expr = expr.strip()
    if expr.startswith("secret."):
        return secret.get_secret(expr[len("secret."):])
    if expr in vars_:
        return vars_[expr]
    # dotted path lookup: vars.xxx / time.now / results.action.field
    value = vars_
    for part in expr.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"variable not defined: {expr}")
        value = value[part]
    return value


def render(value, vars_: dict):
    """Recursively substitute ${...} references in strings.
    If the whole string is a single reference, return the original type
    (preserving int etc.)."""
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
