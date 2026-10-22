"""密码生成与强度校验。"""
import re
import secrets
import string


def generate_password(length: int = 10) -> str:
    """生成同时包含字母和数字的随机密码。"""
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if re.search(r"[A-Za-z]", password) and re.search(r"\d", password):
            return password


def is_strong_password(password: str) -> bool:
    return (
        8 <= len(password) <= 32
        and re.search(r"[A-Za-z]", password) is not None
        and re.search(r"\d", password) is not None
    )
