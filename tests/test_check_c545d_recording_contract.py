#!/usr/bin/env python3
"""No SDK or camera needed; also checks mutated recorder configuration fails."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_c545d_recording_contract import check

SOURCE = Path(__file__).resolve().parents[1] / "Record.ps1"


class RecordingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SOURCE.read_text(encoding="utf-8-sig")

    def test_current_recording_contract(self):
        result = check(self.src)
        self.assertEqual(result["static_contract"], "PASS")
        self.assertFalse(result["real_hourly_mp4_verified"])
        self.assertFalse(result["real_tapo_rtsp_verified"])

    def test_bad_split_duration_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            "'max-size-time=3600000000000'", "'max-size-time=3599000000000'"))

    def test_silent_encoder_quality_change_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            "'quantizer=24'", "'quantizer=26'"))

    def test_stream_mapping_change_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            "Add-Input 'cam2' $teleURL 1", "Add-Input 'cam2' $teleURL 0"))

    def test_wrong_camera_endpoint_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            ':554/stream6"', ':554/stream7"'))

    def test_no_eos_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            "$gstArgs = @('-e') + $pipeline.ToArray()", "$gstArgs = $pipeline.ToArray()"))

    def test_audio_routing_change_rejected(self):
        self.assertRaises(ValueError, check, self.src.replace(
            "'aacparse','!','mux.audio_0'", "'aacparse','!','fakesink'"))


if __name__ == "__main__":
    unittest.main()
