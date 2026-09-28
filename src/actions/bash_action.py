# bash 插件：通过 ssh（或 local）在目标主机上执行命令
import io
import logging
import subprocess

import paramiko

from src.action import BaseAction

logger = logging.getLogger("executor")


class bash(BaseAction):
    name = "bash"
    description = "execute bash command on targets via ssh or locally"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._clients = []

    def format_before_exec(self):
        if not self.params.get("command"):
            raise ValueError("bash action 缺少参数: command")
        if not self.targets:
            raise ValueError("bash action 缺少 targets")

    def _ssh_client(self, target: dict) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": target["host"],
            "port": int(target.get("port", 22)),
            "username": target.get("user"),
            "timeout": self.timeout or 10,
        }
        if target.get("ssh_key"):
            key_file = io.StringIO(target["ssh_key"])
            pkey = None
            for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                try:
                    key_file.seek(0)
                    pkey = key_cls.from_private_key(key_file)
                    break
                except paramiko.SSHException:
                    continue
            if pkey is None:
                raise ValueError("无法解析 ssh_key")
            kwargs["pkey"] = pkey
        elif target.get("password"):
            kwargs["password"] = target["password"]
        else:
            raise ValueError(f"target {target.get('host')} 缺少认证信息")
        client.connect(**kwargs)
        self._clients.append(client)
        return client

    def _exec_ssh(self, target: dict) -> dict:
        client = self._ssh_client(target)
        _, stdout, stderr = client.exec_command(
            self.params["command"], timeout=self.timeout
        )
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return {
            "exit_code": stdout.channel.recv_exit_status(),
            "stdout": out,
            "stderr": err,
        }

    def _exec_local(self) -> dict:
        proc = subprocess.run(
            ["bash", "-c", self.params["command"]],
            capture_output=True, text=True, timeout=self.timeout,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def exec(self) -> dict:
        results = {}
        for target in self.targets:
            name = target.get("_name") or target.get("host", "local")
            protocol = target.get("protocol", "ssh")
            logger.info("[%s] 执行命令: %s", name, self.params["command"])
            if protocol == "local":
                results[name] = self._exec_local()
            elif protocol == "ssh":
                results[name] = self._exec_ssh(target)
            else:
                raise ValueError(f"不支持的 protocol: {protocol}")
            logger.info("[%s] 退出码: %s", name, results[name]["exit_code"])
        self.result = results
        failed = {n: r["exit_code"] for n, r in results.items() if r["exit_code"] != 0}
        if failed:
            raise RuntimeError(f"命令执行失败，退出码: {failed}")
        return results

    def process_result(self) -> dict:
        return {
            "action": self.name,
            "command": self.params["command"],
            "results": self.result,
        }

    def clean(self):
        for client in self._clients:
            try:
                client.close()
            except Exception:
                pass
        self._clients = []
