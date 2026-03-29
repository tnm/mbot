from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mbot.midi import build_light_score_for_tracks, load_midi, rewrite_midi_programs

try:
    from tests.test_support import make_midi_file
except ImportError:
    from test_support import make_midi_file


class MidiPipelineTests(unittest.TestCase):
    def test_revoice_inserts_program_change_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "no_program.mid"
            output = Path(tempdir) / "no_program_violin.mid"
            make_midi_file(
                source,
                tracks=[
                    [
                        (0, bytes([0x90, 60, 100])),
                        (96, bytes([0x80, 60, 0])),
                    ]
                ],
            )

            rewrite_midi_programs(source, output, program=40)
            rewritten = load_midi(output)

            self.assertEqual(rewritten.track_summaries[0].programs, (40,))

    def test_narrow_pitch_range_marks_unused_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "single_note.mid"
            make_midi_file(
                source,
                tracks=[
                    [
                        (0, bytes([0x90, 60, 100])),
                        (96, bytes([0x80, 60, 0])),
                    ]
                ],
            )

            midi_data = load_midi(source)
            score = build_light_score_for_tracks(midi_data, (0,), pin_count=4)

            self.assertEqual((score.bands[0].low_pitch, score.bands[0].high_pitch), (60, 60))
            self.assertEqual((score.bands[1].low_pitch, score.bands[1].high_pitch), (None, None))
            self.assertEqual((score.bands[2].low_pitch, score.bands[2].high_pitch), (None, None))
            self.assertEqual((score.bands[3].low_pitch, score.bands[3].high_pitch), (None, None))
            self.assertEqual(tuple(frame.mask for frame in score.frames), (0, 1, 0))

    def test_multitrack_score_combines_note_bearing_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "two_tracks.mid"
            make_midi_file(
                source,
                tracks=[
                    [
                        (0, bytes([0xFF, 0x03, 0x03]) + b"Pad"),
                        (0, bytes([0x90, 60, 100])),
                        (96, bytes([0x80, 60, 0])),
                    ],
                    [
                        (0, bytes([0xFF, 0x03, 0x04]) + b"Lead"),
                        (0, bytes([0x91, 72, 100])),
                        (96, bytes([0x81, 72, 0])),
                    ],
                ],
            )

            midi_data = load_midi(source)
            score = build_light_score_for_tracks(midi_data, (0, 1), pin_count=4)

            self.assertEqual(score.track_indexes, (0, 1))
            self.assertIn("Pad", score.track_name)
            self.assertIn("Lead", score.track_name)
            self.assertTrue(any(frame.mask != 0 for frame in score.frames))
