from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from music_analysis.analyzer import AnalysisConfig, MusicAnalyzer  # noqa: E402
from music_analysis.errors import AudioAnalysisError  # noqa: E402
from music_analysis.schema import validate_result  # noqa: E402

from tests.helpers import synth_chord_with_beats, write_silence  # noqa: E402


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="arteval-test-"))
        cls.wav = synth_chord_with_beats(cls.tmp / "c_major_120.wav")
        cls.silence = write_silence(cls.tmp / "silence.wav")
        cls.analyzer = MusicAnalyzer(AnalysisConfig(max_duration_sec=30))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_result_is_schema_valid_and_structured(self) -> None:
        result = self.analyzer.analyze_file(self.wav).to_dict()
        self.assertEqual(validate_result(result), [])
        self.assertTrue(result["quality"]["usable"])
        self.assertEqual(result["tonality"]["mode"], "major")
        self.assertAlmostEqual(result["summary"]["tempo_bpm"], 120.0, delta=6.0)
        self.assertIn(result["summary"]["mood"], ("happy", "calm", "sad", "tense", "neutral"))
        self.assertGreaterEqual(result["structure"]["section_count"], 1)
        self.assertEqual(
            len(result["structure"]["sections"]), result["structure"]["section_count"]
        )
        self.assertGreater(result["model"]["runtime_ms"], 0.0)
        # 必须可 JSON 序列化且无 NaN
        json.loads(json.dumps(result, allow_nan=False))

    def test_analyze_bytes(self) -> None:
        data = self.wav.read_bytes()
        result = self.analyzer.analyze_bytes(data, filename="upload.wav").to_dict()
        self.assertEqual(validate_result(result), [])
        self.assertEqual(result["audio"]["filename"], "upload.wav")
        self.assertTrue(result["quality"]["usable"])

    def test_silence_degrades_gracefully(self) -> None:
        result = self.analyzer.analyze_file(self.silence).to_dict()
        self.assertEqual(validate_result(result), [])
        self.assertFalse(result["quality"]["usable"])
        self.assertIn("silent_audio", result["quality"]["flags"])
        self.assertIsNone(result["summary"]["tempo_bpm"])
        self.assertIsNone(result["summary"]["key"])
        self.assertEqual(result["structure"]["section_count"], 0)

    def test_invalid_audio_raises(self) -> None:
        bad = self.tmp / "bad.wav"
        bad.write_bytes(b"this is not audio")
        with self.assertRaises(AudioAnalysisError) as ctx:
            self.analyzer.analyze_file(bad)
        self.assertEqual(ctx.exception.code, "invalid_audio")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(AudioAnalysisError) as ctx:
            self.analyzer.analyze_file(self.tmp / "nope.wav")
        self.assertEqual(ctx.exception.code, "file_not_found")

    def test_structure_can_be_disabled(self) -> None:
        analyzer = MusicAnalyzer(AnalysisConfig(include_structure=False))
        result = analyzer.analyze_file(self.wav).to_dict()
        self.assertEqual(result["structure"]["section_count"], 1)
        self.assertIn("structure_disabled", result["warnings"])


if __name__ == "__main__":
    unittest.main()
