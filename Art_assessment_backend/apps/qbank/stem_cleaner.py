"""题干文本清理：去掉种子数据留下的标签，只保留题目本身。"""
import re

# 这些前缀只用于区分课程/年级/单元，不应出现在展示给用户的题干里。
_PREFIX_PATTERNS = (
    re.compile(r"^\s*【单元练习】\s*"),
    re.compile(r"^\s*【(?:音乐|美术)[^】]*】\s*"),
    re.compile(r"^\s*\[[^\]]*(?:年级音乐|年级美术|音乐|美术)[^\]]*\]\s*"),
    re.compile(r"^\s*【(?:单选|多选|判断|填空|简答|实践|拓展|基础|提高)[^】]*】\s*"),
)

# “（变式 2）”“（拓展练习）”是生成题库时用于避免重名的临时后缀。
_SUFFIX_PATTERN = re.compile(
    r"\s*[（(](?:变式\s*\d+|拓展练习)[）)]\s*$"
)


def clean_stem(text: str | None) -> str:
    """把题干清洗成纯题目文本，幂等。"""
    value = (text or "").strip()
    if not value:
        return value
    for _ in range(8):
        before = value
        for pattern in _PREFIX_PATTERNS:
            value = pattern.sub("", value, count=1).strip()
        value = _SUFFIX_PATTERN.sub("", value, count=1).strip()
        if value == before:
            break
    return re.sub(r"\s+", " ", value).strip()
