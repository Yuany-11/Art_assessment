"""ArtEval 音乐分析模型.

一个可离线运行、结果可解释的音乐分析基线：
节奏、调性、动态、音色、情绪与曲式结构的统一结构化输出。
"""

__version__ = "1.0.0"

from .schema import AnalysisResult  # noqa: E402
from .analyzer import MODEL_NAME, MusicAnalyzer  # noqa: E402

__all__ = ["AnalysisResult", "MusicAnalyzer", "MODEL_NAME", "__version__"]
