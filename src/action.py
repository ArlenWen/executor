# Action 基类及插件加载器
import importlib.util
import logging
import os

logger = logging.getLogger("executor")

# 内置插件目录优先，其次是用户插件目录
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
        """检查 params 的合法性，准备工作"""
        pass

    def exec(self):
        """执行 action，返回原始结果"""
        raise NotImplementedError

    def process_result(self) -> dict:
        """处理执行结果，返回需要持久化的数据（dict 会转成 json）"""
        raise NotImplementedError

    def clean(self):
        """清理资源"""
        pass

    def run(self):
        """完整执行流程"""
        self.format_before_exec()
        try:
            self.result = self.exec()
            return self.process_result()
        finally:
            self.clean()


def load_action(name: str):
    """按名称加载 action 插件类。
    插件文件名为 <name>_action.py，类名为 <name>，继承 BaseAction。
    优先从内置插件目录加载，其次从 plugins 目录加载。"""
    for directory in (_BUILTIN_DIR, _PLUGIN_DIR):
        path = os.path.join(directory, f"{name}_action.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"executor_action_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, name, None)
        if cls is None:
            raise AttributeError(f"{path} 中未定义类 {name}")
        if not issubclass(cls, BaseAction):
            raise TypeError(f"{path} 中的类 {name} 未继承 BaseAction")
        logger.debug("加载插件 %s (来自 %s)", name, path)
        return cls
    raise FileNotFoundError(f"找不到 action 插件: {name}")
