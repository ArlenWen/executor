# Executor

[English](README_EN.md) | 中文

一个基于 YAML 编排的任务执行器：按依赖顺序执行编排好的 job，在本地或远程目标主机上运行 action（bash、mysqlcli 等），并将执行结果持久化到本地目录或 MongoDB。

## 功能特性

- **YAML 编排**：通过 YAML 文件定义 job，支持变量、目标主机、依赖关系
- **依赖解析**：job 之间可声明 `depends`，自动按依赖顺序执行
- **并发执行**：`concurrency` 块内的 action 使用线程池并发执行
- **插件化 action**：内置 `bash`、`mysqlcli` 插件，支持在 `src/plugins/` 下按需扩展自定义插件
- **多种目标协议**：支持 `ssh`（远程主机）与 `local`（本机）
- **结果持久化**：支持本地 JSON 文件与 MongoDB 两种持久化目的地
- **敏感数据管理**：使用对称加密存储密码、密钥等敏感数据，通过 `${secret.xxx}` 在 job 中引用
- **重试机制**：action 失败（非零退出码/异常）时按配置重试，重试仍失败则终止当前 job，不影响后续 job

## 环境要求

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/)（推荐，用于依赖管理）

## 安装

```bash
uv sync
```

依赖见 `pyproject.toml`：`pyyaml`、`paramiko`（SSH）、`pymysql`、`pymongo`、`cryptography`。

## 快速开始

```bash
# 执行单个任务文件
python3 main.py run -f examples/job.demo.yaml

# 执行目录下的所有任务（自动去重并按依赖顺序执行）
python3 main.py run -d examples/

# 运行 http server（保留，暂未实现）
python3 main.py serve -H 0.0.0.0 -p 8000
```

每次 job 执行会生成一个唯一 id（当前日期时间 + 4 位随机数，例如 `202609211234567890`），用于日志文件名与持久化文件名。

## 敏感数据管理

敏感数据使用 `config.yaml` 中的 `secret_key` 加密后存储在 `secret_file` 中：

```bash
python3 main.py secret set <name> <value>  # 设置 secret
python3 main.py secret get <name>          # 查看 secret
python3 main.py secret list                # 列出所有 secret 名称
python3 main.py secret delete <name>       # 删除 secret
```

在 job YAML 中通过 `${secret.<name>}` 引用，例如 `password: ${secret.debian_password}`。

## 配置

`config.yaml`：

```yaml
log:
  level: info        # 日志级别
  output: file       # file 或 console
  dir: /tmp/executor/  # 日志目录，日志文件名为 <job_id>.log

secret_key: "yours-secret-key"     # 敏感数据加密密钥
secret_file: ~/.executor/secret.bin  # 敏感数据存储文件
```

## Job 编排

完整示例见 [examples/job.demo.yaml](examples/job.demo.yaml)。一个 job 文件包含以下字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 版本号 |
| `name` | job 名称，缺省使用文件名 |
| `description` | 描述 |
| `depends` | 依赖的其他 job（相对当前文件路径，不带 `.yaml` 后缀），按依赖顺序先执行 |
| `vars` | 变量定义，action 执行时通过 `${var_name}` 引用，不存在则报错 |
| `targets` | action 执行的目标主机，`protocol` 支持 `ssh` 与 `local` |
| `persistence` | 结果持久化目的地列表，支持 `local`（本地目录）与 `mongodb`，不定义则不持久化 |
| `actions` | 顺序执行的 action 列表；`concurrency` 块内的 action 并发执行 |

action 通用字段：

- `name`：插件名称（如 `bash`、`mysqlcli`）
- `params`：插件参数
- `targets`：引用的 target 名称列表
- `timeout`：超时时间（秒）
- `retry`：重试策略，`times`（次数）与 `interval`（间隔秒数）

```yaml
actions:
  - concurrency:  # 并发执行
      - action:
          name: "bash"
          params:
            command: "ls -la"
          targets: [debian]
          timeout: 10
  - action:  # 顺序执行
      name: "bash"
      params:
        command: "echo \"${demo_var1}\""
      targets: [debian, ubuntu]
```

## 插件开发

插件文件命名为 `<plugin_name>_action.py`，放置在 `src/actions/`（内置，优先加载）或 `src/plugins/`（用户扩展）目录下。文件中定义与插件同名的类，继承 `BaseAction`（见 `src/action.py`）：

```python
from src.action import BaseAction

class myplugin(BaseAction):
    name = "myplugin"

    def exec(self):
        # 执行逻辑，返回原始结果
        ...

    def process_result(self) -> dict:
        # 返回需要持久化的数据
        ...
```

可选重写 `format_before_exec()`（参数校验/准备）与 `clean()`（资源清理）。非零退出码或抛出异常视为执行失败，会触发重试。

## 目录结构

```
├── config.yaml        # 全局配置
├── main.py            # 入口
├── examples/          # 示例 job
└── src/
    ├── action.py      # BaseAction 基类与插件加载器
    ├── actions/       # 内置插件（bash、mysqlcli），优先于 plugins 加载
    ├── plugins/       # 用户插件目录
    ├── job.py         # job 执行器
    ├── parse.py       # job YAML 解析与依赖排序
    ├── persist.py     # 结果持久化（local / mongodb）
    ├── secret.py      # 敏感数据加解密
    ├── config.py      # 配置加载与日志初始化
    └── util.py        # 变量渲染等工具
```

## 执行约定

- 非零退出码视为 action 执行失败，触发 retry
- 某个 action 重试后仍失败则终止当前 job，但不影响后续其他 job 的执行
- `local` target 使用 `protocol: local`，在本机执行命令
- 本地持久化文件命名：`<job_id>_<seq>_<action>.json`
