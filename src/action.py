# Action base class and plugin loader
import importlib.util
import logging
import os

logger = logging.getLogger("executor")

# Built-in plugin directory takes precedence over the user plugin directory
_BUILTIN_DIR = os.path.join(os.path.dirname(__file__), "actions")
_PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "plugins")


class BaseAction:
    name = "BaseAction"
    description = "This is a base plugin"

    def __init__(self, params: dict, targets: list = None, timeout: int = None,
                 retry_policy: dict = None):
        self.params = params or {}
        self.targets = targets or []
        self.timeout = timeout
        self.retry_policy = retry_policy
        self.result = None

    def format_before_exec(self):
        """Validate params and prepare for execution"""
        pass

    def exec(self):
        """Execute the action and return the raw result"""
        raise NotImplementedError

    def process_result(self) -> dict:
        """Process the execution result and return the data to persist
        (dicts are converted to json)"""
        raise NotImplementedError

    def clean(self):
        """Clean up resources"""
        pass

    def run(self):
        """Full execution workflow"""
        self.format_before_exec()
        try:
            self.result = self.exec()
            return self.process_result()
        finally:
            self.clean()


def load_action(name: str):
    """Load an action plugin class by name.
    The plugin file is named <name>_action.py, defines a class named <name>
    that inherits BaseAction. Built-in plugin directory is searched first,
    then the plugins directory."""
    for directory in (_BUILTIN_DIR, _PLUGIN_DIR):
        path = os.path.join(directory, f"{name}_action.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"executor_action_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, name, None)
        if cls is None:
            raise AttributeError(f"class {name} is not defined in {path}")
        if not issubclass(cls, BaseAction):
            raise TypeError(f"class {name} in {path} does not inherit BaseAction")
        logger.debug("loaded plugin %s (from %s)", name, path)
        return cls
    raise FileNotFoundError(f"action plugin not found: {name}")
