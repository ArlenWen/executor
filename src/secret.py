# Secret management: encrypt/decrypt with the secret_key from config.yaml;
# encrypted data is serialized with pickle and stored in secret_file
import base64
import hashlib
import os
import pickle

from cryptography.fernet import Fernet

from src import config


def _fernet() -> Fernet:
    key = config.get("secret_key")
    if not key:
        raise RuntimeError("secret_key is not configured in config.yaml")
    # Derive the 32-byte urlsafe base64 key required by Fernet from secret_key
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
    """Encrypt and store a secret"""
    data = _load_all()
    data[name] = _fernet().encrypt(value.encode("utf-8"))
    _save_all(data)


def get_secret(name: str) -> str:
    """Decrypt and return a secret; raise KeyError if it does not exist"""
    data = _load_all()
    if name not in data:
        raise KeyError(f"secret not found: {name}")
    return _fernet().decrypt(data[name]).decode("utf-8")


def list_secrets() -> list:
    return sorted(_load_all().keys())


def delete_secret(name: str):
    data = _load_all()
    if name in data:
        del data[name]
        _save_all(data)
