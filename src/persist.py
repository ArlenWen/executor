# 持久化：将 action 的 process_result 结果保存到对应目的地
import datetime
import json
import logging
import os

logger = logging.getLogger("executor")


def _doc(job_id: str, job_name: str, seq: int, action_name: str, data: dict) -> dict:
    return {
        "job_id": job_id,
        "job_name": job_name,
        "seq": seq,
        "action": action_name,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "data": data,
    }


def persist(persistence: list, job_id: str, job_name: str, seq: int,
            action_name: str, data):
    """按 job 定义的 persistence 列表持久化一条结果"""
    if data is None:
        return
    if isinstance(data, dict):
        payload = data
    else:
        payload = {"result": str(data)}
    doc = _doc(job_id, job_name, seq, action_name, payload)
    for dest in persistence:
        try:
            if "local" in dest:
                _save_local(dest["local"], doc)
            elif "mongodb" in dest:
                _save_mongodb(dest["mongodb"], doc)
            else:
                logger.warning("未知的 persistence 类型: %s", dest)
        except Exception as e:
            logger.error("持久化失败 (%s): %s", dest, e)


def _save_local(directory: str, doc: dict):
    os.makedirs(directory, exist_ok=True)
    filename = f"{doc['job_id']}_{doc['seq']:03d}_{doc['action']}.json"
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, default=str)
    logger.info("结果已保存到 %s", path)


def _save_mongodb(cfg: dict, doc: dict):
    from pymongo import MongoClient

    client = MongoClient(
        cfg["uri"],
        username=cfg.get("username"),
        password=cfg.get("password"),
        tls=bool(cfg.get("ssl", False)),
        serverSelectionTimeoutMS=5000,
    )
    try:
        db = client[cfg.get("database", "executor")]
        collection = db[cfg.get("collection", "results")]
        collection.insert_one(dict(doc))
        logger.info("结果已保存到 mongodb %s/%s", db.name, collection.name)
    finally:
        client.close()
