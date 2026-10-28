"""音乐分析模型主流程。"""

from __future__ import annotations

import io
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import librosa
import numpy as np
import soundfile as sf

from . import features
from .errors import AudioAnalysisError
from .schema import (
    SCHEMA_VERSION,
    AnalysisResult,
    AudioInfo,
    DynamicsInfo,
    ModelInfo,
    MoodInfo,
    QualityInfo,
    RhythmInfo,
    SectionInfo,
    StructureInfo,
    Summary,
    TimbreInfo,
    TonalityInfo,
    null_result,
    utc_now_iso,
)

# 兼容从 __init__ 导出前循环引用：版本常量直接在 schema 层维护
MODEL_NAME = "ArtEval Music Analyzer"
MODEL_VERSION = SCHEMA_VERSION
BACKEND_NAME = "dsp-librosa-v1"

AudioSource = Union[str, Path, io.BufferedIOBase]


@dataclass
class AnalysisConfig:
    """推理配置；所有阈值集中在此，便于评测时冻结。"""

    sample_rate: int = 22050
    max_duration_sec: float = 120.0
    include_structure: bool = True
    max_sections: int = 6
    min_section_sec: float = 2.0
    device: str = "cpu"


class MusicAnalyzer:
    """离线音乐分析器（DSP + 调性轮廓 + 启发式情绪映射）。"""

    def __init__(self, config: Optional[AnalysisConfig] = None):
        self.config = config or AnalysisConfig()

    # -- 公共入口 ---------------------------------------------------------
    def analyze_file(self, path: Union[str, Path], filename: Optional[str] = None) -> AnalysisResult:
        audio_path = Path(path)
        if not audio_path.is_file():
            raise AudioAnalysisError("file_not_found", f"文件不存在: {audio_path}", http_status=404)
        try:
            info = sf.info(str(audio_path))
        except Exception as exc:
            raise AudioAnalysisError(
                "invalid_audio", f"无法识别的音频文件: {exc}", http_status=415
            ) from exc
        return self._analyze(audio_path, info, filename or audio_path.name)

    def analyze_bytes(self, data: bytes, filename: str = "upload.wav") -> AnalysisResult:
        if not data:
            raise AudioAnalysisError("empty_audio", "音频内容为空", http_status=422)
        buffer = io.BytesIO(data)
        try:
            info = sf.info(buffer)
        except Exception as exc:
            raise AudioAnalysisError(
                "invalid_audio", f"无法识别的音频内容: {exc}", http_status=415
            ) from exc
        buffer.seek(0)
        return self._analyze(buffer, info, filename)

    # -- 主流程 -----------------------------------------------------------
    def _analyze(self, source: AudioSource, info: sf._SoundFileInfo, filename: str) -> AnalysisResult:
        started = time.perf_counter()
        analysis_id = uuid.uuid4().hex[:16]
        created_at = utc_now_iso()
        filename = _safe_filename(filename)

        duration = float(info.frames / info.samplerate) if info.samplerate else 0.0
        if duration <= 0.0:
            raise AudioAnalysisError("empty_audio", "音频时长为 0", http_status=422)

        truncated = duration > self.config.max_duration_sec
        try:
            y, _ = _load_audio(
                source,
                target_sr=self.config.sample_rate,
                max_duration=self.config.max_duration_sec if truncated else None,
            )
        except Exception as exc:
            raise AudioAnalysisError(
                "decode_failed", f"音频解码失败: {exc}", http_status=422
            ) from exc
        sr = self.config.sample_rate

        y = np.asarray(y, dtype=np.float32)
        analyzed_duration = float(len(y) / sr) if sr else 0.0
        audio_info = AudioInfo(
            filename=filename,
            format=str(info.format or "UNKNOWN"),
            duration_sec=round(duration, 3),
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            analyzed_duration_sec=round(analyzed_duration, 3),
            truncated=truncated,
        )
        warnings: List[str] = []
        if truncated:
            warnings.append("audio_truncated")

        peak = float(np.max(np.abs(y))) if y.size else 0.0
        if peak < 1e-5 or analyzed_duration < 0.5:
            quality, extra_warnings = self._degenerate_quality(y, analyzed_duration)
            warnings.extend(extra_warnings)
            return null_result(
                analysis_id=analysis_id,
                created_at=created_at,
                model=ModelInfo(
                    name=MODEL_NAME,
                    version=MODEL_VERSION,
                    backend=BACKEND_NAME,
                    device=self.config.device,
                    runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
                ),
                audio=audio_info,
                warnings=warnings,
                quality=quality,
                metadata={
                    "analysis_sample_rate": int(sr),
                    "hop_length": features.HOP_LENGTH,
                    "feature_version": "1.0",
                    "reason": "silent_or_too_short",
                },
            )

        rhythm = features.estimate_rhythm(y, sr, analyzed_duration)
        tonality = features.estimate_tonality(y, sr)
        dynamics = features.estimate_dynamics(y, sr)
        timbre = features.estimate_timbre(y, sr)
        mood = features.estimate_mood(
            tempo_bpm=rhythm["tempo_bpm"],
            loudness_db=dynamics["loudness_db"],
            onset_rate_per_sec=rhythm["onset_rate_per_sec"],
            spectral_centroid_hz=timbre["spectral_centroid_hz"],
            spectral_flatness=timbre["spectral_flatness"],
            mode=tonality["mode"],
            beat_regularity=rhythm["beat_regularity"],
        )
        energy = features.energy_label(
            mood["arousal"],
            dynamics["loudness_db"],
            rhythm["onset_rate_per_sec"],
        )
        tags = features.build_tags(
            mode=tonality["mode"],
            tempo_bpm=rhythm["tempo_bpm"],
            texture=timbre["texture"],
            brightness=timbre["brightness"],
            energy=energy,
            spectral_flatness=timbre["spectral_flatness"],
        )

        if self.config.include_structure:
            raw_sections = features.estimate_structure(
                y=y,
                sr=sr,
                beat_frames=rhythm["beat_frames"],
                duration_sec=analyzed_duration,
                rms_db_frames=dynamics["rms_db_frames"],
                loudness_db=dynamics["loudness_db"],
                max_sections=self.config.max_sections,
                min_section_sec=self.config.min_section_sec,
            )
        else:
            raw_sections = [
                {
                    "start_sec": 0.0,
                    "end_sec": round(analyzed_duration, 3),
                    "energy_db": round(float(dynamics["loudness_db"]), 2),
                    "energy": "medium",
                }
            ]
            warnings.append("structure_disabled")

        sections = [
            SectionInfo(
                index=i,
                label=_section_label(i),
                start_sec=float(item["start_sec"]),
                end_sec=float(item["end_sec"]),
                duration_sec=round(float(item["end_sec"]) - float(item["start_sec"]), 3),
                energy=str(item["energy"]),
                energy_db=float(item["energy_db"]),
            )
            for i, item in enumerate(raw_sections)
        ]

        quality = self._quality(y, analyzed_duration, dynamics)
        warnings.extend(_analysis_warnings(rhythm, tonality, quality))

        key_confidence = tonality["key_confidence"]
        tempo_confidence = rhythm["tempo_confidence"]
        model_info = ModelInfo(
            name=MODEL_NAME,
            version=MODEL_VERSION,
            backend=BACKEND_NAME,
            device=self.config.device,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )

        return AnalysisResult(
            schema_version=SCHEMA_VERSION,
            analysis_id=analysis_id,
            created_at=created_at,
            model=model_info,
            audio=audio_info,
            summary=Summary(
                key=f"{tonality['key']} {tonality['mode']}",
                tempo_bpm=_round_opt(rhythm["tempo_bpm"], 2),
                energy=energy,
                mood=mood["label"],
                valence=mood["valence"],
                arousal=mood["arousal"],
                tags=tags,
            ),
            rhythm=RhythmInfo(
                tempo_bpm=_round_opt(rhythm["tempo_bpm"], 2),
                tempo_confidence=rhythm["tempo_confidence"],
                beat_count=int(rhythm["beat_frames"].size),
                beat_regularity=_round_opt(rhythm["beat_regularity"], 4),
                onset_rate_per_sec=_round_opt(rhythm["onset_rate_per_sec"], 3),
                offbeat_energy_ratio=_round_opt(rhythm["offbeat_energy_ratio"], 4),
                time_signature=None,
            ),
            tonality=TonalityInfo(
                key=tonality["key"],
                mode=tonality["mode"],
                key_confidence=key_confidence,
                tuning_cents=tonality["tuning_cents"],
                chroma_profile=tonality["chroma_profile"],
            ),
            dynamics=DynamicsInfo(
                loudness_db=dynamics["loudness_db"],
                dynamic_range_db=dynamics["dynamic_range_db"],
                peak_dbfs=dynamics["peak_dbfs"],
                silence_ratio=dynamics["silence_ratio"],
                clipping_ratio=dynamics["clipping_ratio"],
            ),
            timbre=TimbreInfo(
                brightness=timbre["brightness"],
                spectral_centroid_hz=timbre["spectral_centroid_hz"],
                spectral_rolloff_hz=timbre["spectral_rolloff_hz"],
                spectral_flatness=timbre["spectral_flatness"],
                zero_crossing_rate=timbre["zero_crossing_rate"],
                harmonic_ratio=timbre["harmonic_ratio"],
                texture=timbre["texture"],
            ),
            mood=MoodInfo(
                valence=mood["valence"],
                arousal=mood["arousal"],
                label=mood["label"],
                confidence=mood["confidence"],
            ),
            structure=StructureInfo(section_count=len(sections), sections=sections),
            quality=quality,
            warnings=warnings,
            metadata={
                "analysis_sample_rate": int(sr),
                "hop_length": features.HOP_LENGTH,
                "frame_length": features.FRAME_LENGTH,
                "max_duration_sec": self.config.max_duration_sec,
                "feature_version": "1.0",
                "tempo_confidence": tempo_confidence,
                "key_confidence": key_confidence,
            },
        )

    # -- 质量与降级 -------------------------------------------------------
    def _degenerate_quality(self, y: np.ndarray, duration: float) -> tuple[QualityInfo, List[str]]:
        rms = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
        loudness = features._db(rms)
        clipping_ratio = float(np.mean(np.abs(y) >= 0.999)) if y.size else 0.0
        duration_ok = duration >= 3.0
        not_silent = bool(np.max(np.abs(y)) >= 1e-5) if y.size else False
        checks = {
            "duration_ok": duration_ok,
            "not_silent": not_silent,
            "not_clipped": clipping_ratio < 0.01,
            "loudness_ok": loudness >= -35.0,
        }
        flags = _flags_from_checks(checks)
        warnings = []
        if "silent_audio" in flags:
            warnings.append("silent_audio")
        if "very_short" in flags:
            warnings.append("very_short_audio")
        return QualityInfo(usable=duration_ok and not_silent, flags=flags, checks=checks), warnings

    def _quality(
        self, y: np.ndarray, duration: float, dynamics: Dict[str, Any]
    ) -> QualityInfo:
        checks = {
            "duration_ok": duration >= 3.0,
            "not_silent": float(np.max(np.abs(y))) >= 1e-5 if y.size else False,
            "not_clipped": float(dynamics["clipping_ratio"]) < 0.01,
            "loudness_ok": float(dynamics["loudness_db"]) >= -35.0,
        }
        return QualityInfo(
            usable=checks["duration_ok"] and checks["not_silent"],
            flags=_flags_from_checks(checks),
            checks=checks,
        )


def _analysis_warnings(
    rhythm: Dict[str, Any], tonality: Dict[str, Any], quality: QualityInfo
) -> List[str]:
    warnings: List[str] = []
    tempo_conf = rhythm.get("tempo_confidence")
    key_conf = tonality.get("key_confidence")
    if tempo_conf is not None and tempo_conf < 0.30:
        warnings.append("low_tempo_confidence")
    if key_conf is not None and key_conf < 0.35:
        warnings.append("low_key_confidence")
    if "clipped_audio" in quality.flags:
        warnings.append("clipped_audio")
    if "low_loudness" in quality.flags:
        warnings.append("low_loudness")
    if "very_short" in quality.flags:
        warnings.append("very_short_audio")
    return warnings


def _flags_from_checks(checks: Dict[str, bool]) -> List[str]:
    mapping = (
        ("duration_ok", "very_short"),
        ("not_silent", "silent_audio"),
        ("not_clipped", "clipped_audio"),
        ("loudness_ok", "low_loudness"),
    )
    return [flag for key, flag in mapping if not checks.get(key, True)]


def _section_label(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else f"S{index + 1}"


def _round_opt(value: Optional[float], digits: int) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def _safe_filename(filename: str) -> str:
    name = os.path.basename(str(filename).replace("\\", "/")).strip()
    return name[:255] or "audio"


def _load_audio(
    source: AudioSource, *, target_sr: int, max_duration: Optional[float]
) -> tuple[np.ndarray, int]:
    """用 soundfile 解码并混单声道；仅在采样率不一致时重采样。

    相比 ``librosa.load`` 可避免每次进程启动时的额外加载开销。
    """
    with sf.SoundFile(source) as handle:
        native_sr = int(handle.samplerate)
        frames = -1
        if max_duration is not None:
            frames = max(1, int(round(max_duration * native_sr)))
        data = handle.read(frames=frames, dtype="float32", always_2d=True)

    if data.size == 0:
        return np.zeros(0, dtype=np.float32), native_sr
    mono = data.mean(axis=1, dtype=np.float32) if data.shape[1] > 1 else data[:, 0]
    if native_sr != target_sr:
        mono = librosa.resample(mono, orig_sr=native_sr, target_sr=target_sr).astype(np.float32)
    return np.ascontiguousarray(mono), native_sr
