# Executor

English | [中文](README.md)

A YAML-orchestrated task executor: runs jobs in dependency order, executes actions (bash, mysqlcli, etc.) on local or remote target hosts, and persists execution results to local directories or MongoDB.

## Features

- **YAML orchestration**: define jobs in YAML with variables, target hosts, and dependencies
- **Dependency resolution**: jobs can declare `depends` and are automatically executed in dependency order
- **Concurrent execution**: actions inside a `concurrency` block run in parallel via a thread pool
- **Pluggable actions**: built-in `bash` and `mysqlcli` plugins; extend with custom plugins under `src/plugins/`, loaded on demand
- **build-in operations**: plugin-free builtin operations (`sleep`, `format`, `getter`) inside actions, supporting string formatting and extracting values from results/variables into `vars`
- **Multiple target protocols**: `ssh` (remote hosts) and `local` (this machine)
- **Result persistence**: persist results to local JSON files and/or MongoDB
- **Result notification**: notify the execution status and final results to email / webhook / kafka / rabbitmq after a job finishes
- **Secret management**: symmetrically encrypted storage for passwords and keys, referenced in jobs as `${secret.xxx}`
- **Retry mechanism**: failed actions (non-zero exit code / exception) are retried per configuration; an action that still fails after retries is handled per its `failed` field: `skip` (default) skips it and continues the job, `exit` terminates the current job without affecting subsequent jobs

## Requirements

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recommended, for dependency management)

## Installation

```bash
uv sync
```

Dependencies (see `pyproject.toml`): `pyyaml`, `paramiko` (SSH), `pymysql`, `pymongo`, `cryptography`, `kafka-python` (Kafka), `pika` (RabbitMQ).

## Quick Start

```bash
# Run a single job file
python3 main.py run -f examples/job.demo.yaml

# Run all jobs in a directory (deduplicated, in dependency order)
python3 main.py run -d examples/

# Run the http server (reserved, not implemented yet)
python3 main.py serve -H 0.0.0.0 -p 8000
```

Each job execution generates a unique id (current datetime + 4 random digits, e.g. `202609211234567890`), used in log file names and persistence file names.

## Secret Management

Secrets are encrypted with the `secret_key` from `config.yaml` and stored in `secret_file`:

```bash
python3 main.py secret set <name> <value>  # Set a secret
python3 main.py secret get <name>          # Read a secret
python3 main.py secret list                # List all secret names
python3 main.py secret delete <name>       # Delete a secret
```

Reference secrets in job YAML as `${secret.<name>}`, e.g. `password: ${secret.debian_password}`.

## Configuration

`config.yaml`:

```yaml
log:
  level: info          # Log level
  output: file         # file or console
  dir: /tmp/executor/  # Log directory; log files are named <job_id>.log

secret_key: "yours-secret-key"       # Encryption key for secrets
secret_file: ~/.executor/secret.bin  # Secret storage file
```

## Job Orchestration

See [examples/job.demo.yaml](examples/job.demo.yaml) for a complete example. A job file contains the following fields:

| Field | Description |
| --- | --- |
| `version` | Version number |
| `name` | Job name; defaults to the file name |
| `description` | Description |
| `depends` | Other jobs this job depends on (paths relative to the current file, without the `.yaml` suffix); dependencies run first |
| `vars` | Variable definitions; referenced as `${var_name}` when an action runs. Missing variables raise an error |
| `targets` | Target hosts for actions; `protocol` supports `ssh` and `local` |
| `persistence` | List of persistence destinations; supports `local` (a directory) and `mongodb`. Results are not persisted if omitted. Each destination may set `on_failure` (boolean, default `true`) to control whether completed action results are persisted when the job fails |
| `notify` | List of notification targets for the job result; supports `email` / `webhook` / `kafka` / `rabbitmq`. No notification if omitted. Each target may set `on_failure` (boolean, default `true`) to control whether to notify when the job fails |
| `actions` | Actions executed sequentially; actions inside a `concurrency` block run in parallel, a `build-in` block runs builtin operations (sleep / format / getter) |

Common action fields:

- `name`: plugin name (e.g. `bash`, `mysqlcli`)
- `params`: plugin parameters
- `targets`: list of target names to run against
- `timeout`: timeout in seconds
- `retry`: retry policy with `times` (attempts) and `interval` (seconds between attempts)

```yaml
actions:
  - concurrency:  # Run in parallel
      - action:
          name: "bash"
          params:
            command: "ls -la"
          targets: [debian]
          timeout: 10
  - action:  # Run sequentially
      name: "bash"
      params:
        command: "echo \"${demo_var1}\""
      targets: [debian, ubuntu]
```

### notify Result Notification

`notify` sends the execution status and final results to the configured targets when a job ends, whether it succeeds or fails. All targets receive the same JSON payload:

```json
{
  "job_id": "202610071200001234",
  "job_name": "demo",
  "status": "success",          // or failed
  "error": null,                // failure reason, null on success
  "finished_at": "2026-10-07T12:00:05",
  "results": [                  // results of finished actions
    {"seq": 1, "action": "bash", "data": {...}}
  ]
}
```

Config values support `${var}` and `${secret.xxx}` references plus the built-in variables `${status}`, `${job_id}`, `${job_name}`, `${error}` and `${result}` (the payload as a JSON string). A failed notification is logged and does not affect the job result.

```yaml
notify:
  - email:
      to: ["ops@example.com"]   # a string or a list of strings
      from: "executor@example.com"
      subject: "job demo ${status}"
      body: "job demo finished, result ${result}"
      smtp_host: "smtp.example.com"  # required; smtp settings can only be defined in the job
      # smtp_port: 465
      # smtp_user: "executor@example.com"
      # smtp_password: ${secret.smtp_password}
      # smtp_ssl: true
  - webhook:                    # POSTs the full payload (JSON)
      url: "http://localhost:8080/webhook"
      method: "post"            # optional; default post
      # headers:                # optional
      #   Authorization: "Bearer xxx"
  - kafka:                      # sends the payload as a JSON string
      topic: "executor"
      broker: "localhost:9092"  # a string or a list of strings
  - rabbitmq:                   # sends the payload as a JSON string to the queue
      queue: "executor"
      # host: "localhost"       # optional; default localhost
      # port: 5672              # optional; default 5672
      # username: "guest"       # optional
      # password: ${secret.rabbitmq_password}
      # virtual_host: "/"       # optional; default /
    on_failure: false           # optional; whether to notify when the job fails, default true
```

### build-in Operations

A `build-in` block is a group of builtin operations executed sequentially. They need no plugin and no target host, and are meant for simple local operations. Params support `${var}` and `${secret.xxx}` references plus the built-in context: `${time.now}` (current time), `${vars.<name>}` (variables) and `${results.<action_name>...}` (results of finished actions, accessed by dotted path):

```yaml
  - build-in:
      - name: "sleep"       # Pause for the given seconds
        params:
          seconds: 5
      - name: "format"      # Render string and save it into vars
        params:
          string: "job finished at ${time.now}"
          save_as: "finished_at_str"
      - name: "getter"      # Extract a value from variables/results into vars
        params:
          value_from: "${results.bash}"    # or ${vars.xxx} / ${secret.xxx}
          value_getter: "results.local.stdout"  # dotted path for dicts; for strings it is treated as a regex (group 1 if present, else the whole match); omit to skip extraction
          save_as: "demo_save_as_var"
```

## Plugin Development

A plugin file is named `<plugin_name>_action.py` and placed in `src/actions/` (built-in, loaded with priority) or `src/plugins/` (user extensions). The file defines a class with the same name as the plugin, inheriting from `BaseAction` (see `src/action.py`):

```python
from src.action import BaseAction

class myplugin(BaseAction):
    name = "myplugin"

    def exec(self):
        # Execution logic; return the raw result
        ...

    def process_result(self) -> dict:
        # Return the data to persist
        ...
```

Optionally override `format_before_exec()` (parameter validation / preparation) and `clean()` (resource cleanup). A non-zero exit code or raised exception is treated as a failure and triggers retry.

## Directory Layout

```
├── config.yaml        # Global configuration
├── main.py            # Entry point
├── examples/          # Example jobs
└── src/
    ├── action.py      # BaseAction and the plugin loader
    ├── actions/       # Built-in plugins (bash, mysqlcli), loaded before plugins/
    ├── builtin.py     # Builtin operations for build-in blocks (sleep / format / getter)
    ├── plugins/       # User plugin directory
    ├── job.py         # Job executor
    ├── parse.py       # Job YAML parsing and dependency ordering
    ├── persist.py     # Result persistence (local / mongodb)
    ├── notify.py      # Result notification after a job finishes (email / webhook / kafka / rabbitmq)
    ├── secret.py      # Secret encryption/decryption
    ├── config.py      # Configuration loading and logging setup
    └── util.py        # Variable rendering and other utilities
```

## Execution Conventions

- A non-zero exit code marks an action as failed and triggers retry
- An action that still fails after all retries is handled per its `failed` field: `skip` (default) skips it and continues the job; `exit` terminates the current job, subsequent jobs also do not execute. 
- A `local` target uses `protocol: local` and runs commands on this machine
- Local persistence files are named `<job_id>_<seq>_<action>.json`
