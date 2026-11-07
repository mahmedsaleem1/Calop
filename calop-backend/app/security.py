import hashlib


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
