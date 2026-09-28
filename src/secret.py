# 敏感数据管理：使用 config.yaml 中的 secret_key 加解密，
# 加密后的数据用 pickle 序列化存储在 secret_file 中
import base64
import hashlib
import os
import pickle

from cryptography.fernet import Fernet

from src import config


def _fernet() -> Fernet:
    key = config.get("secret_key")
    if not key:
        raise RuntimeError("config.yaml 中未配置 secret_key")
    # 由 secret_key 派生 Fernet 所需的 32 字节 urlsafe base64 key
    digest = hashlib.sha256(str(key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _secret_file() -> str:
    path = config.get("secret_file", "~/.executor/secret.bin")
    return os.path.expanduser(path)


def _load_all() -> dict:
    path = _secret_file()
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return pickle.load(f)


def _save_all(data: dict):
    path = _secret_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f)
    os.chmod(path, 0o600)


def set_secret(name: str, value: str):
    """加密存储一个 secret"""
    data = _load_all()
    data[name] = _fernet().encrypt(value.encode("utf-8"))
    _save_all(data)


def get_secret(name: str) -> str:
    """解密获取一个 secret，不存在则抛 KeyError"""
    data = _load_all()
    if name not in data:
        raise KeyError(f"secret 不存在: {name}")
    return _fernet().decrypt(data[name]).decode("utf-8")


def list_secrets() -> list:
    return sorted(_load_all().keys())


def delete_secret(name: str):
    data = _load_all()
    if name in data:
        del data[name]
        _save_all(data)
