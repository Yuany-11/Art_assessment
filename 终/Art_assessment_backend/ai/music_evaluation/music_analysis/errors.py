"""模型层错误类型。"""

from __future__ import annotations


class AudioAnalysisError(Exception):
    """可安全返回给调用方的音频分析错误。"""

    def __init__(self, code: str, message: str, http_status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
