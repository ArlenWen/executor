# mysqlcli 插件：执行 mysql 命令
import datetime
import decimal
import logging

import pymysql

from src.action import BaseAction

logger = logging.getLogger("executor")


def _to_jsonable(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class mysqlcli(BaseAction):
    name = "mysqlcli"
    description = "execute mysql command"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conn = None

    def format_before_exec(self):
        for key in ("command", "host", "user", "password"):
            if self.params.get(key) is None:
                raise ValueError(f"mysqlcli action 缺少参数: {key}")

    def exec(self) -> dict:
        conn_kwargs = {
            "host": self.params["host"],
            "port": int(self.params.get("port", 3306)),
            "user": self.params["user"],
            "password": str(self.params["password"]),
            "database": self.params.get("database"),
            "connect_timeout": self.timeout or 10,
            "read_timeout": self.timeout or 10,
            "cursorclass": pymysql.cursors.DictCursor,
        }
        if self.params.get("ssl"):
            conn_kwargs["ssl"] = {"ssl": {}}
        logger.info("连接 mysql %s:%s", conn_kwargs["host"], conn_kwargs["port"])
        self._conn = pymysql.connect(**conn_kwargs)
        with self._conn.cursor() as cur:
            cur.execute(self.params["command"])
            rows = cur.fetchall() if cur.description else []
            rowcount = cur.rowcount
        self._conn.commit()
        return {
            "rowcount": rowcount,
            "rows": [{k: _to_jsonable(v) for k, v in row.items()} for row in rows],
        }

    def process_result(self) -> dict:
        return {
            "action": self.name,
            "command": self.params["command"],
            "results": self.result,
        }

    def clean(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
