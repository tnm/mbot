from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from mbot.midi import build_light_score_for_tracks, load_midi, rewrite_midi_programs

try:
    from tests.test_support import make_midi_file
except ImportError:
    from test_support import make_midi_file


class MidiSoakTests(unittest.TestCase):
    def test_parse_rewrite_and_build_is_stable_over_many_iterations(self) -> None:
        iterations = int(os.environ.get("MBOT_SOAK_ITERS", "100"))
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "soak.mid"
            rewritten = Path(tempdir) / "soak_violin.mid"
            make_midi_file(
                source,
                tracks=[
                    [
                        (0, bytes([0xFF, 0x03, 0x03]) + b"Pad"),
                        (0, bytes([0x90, 60, 90])),
                        (48, bytes([0x90, 64, 90])),
                        (48, bytes([0x80, 60, 0])),
                        (48, bytes([0x80, 64, 0])),
                    ],
                    [
                        (0, bytes([0xFF, 0x03, 0x04]) + b"Lead"),
                        (0, bytes([0xC1, 81])),
                        (0, bytes([0x91, 72, 110])),
                        (24, bytes([0x81, 72, 0])),
                        (24, bytes([0x91, 76, 110])),
                        (24, bytes([0x81, 76, 0])),
                        (24, bytes([0x91, 79, 110])),
                        (24, bytes([0x81, 79, 0])),
                    ],
                ],
            )

            for _ in range(iterations):
                midi_data = load_midi(source)
                score = build_light_score_for_tracks(midi_data, (0, 1), pin_count=4)
                self.assertGreater(score.total_ms, 0)
                self.assertEqual(score.frames[0].mask, 0)
                self.assertEqual(score.frames[-1].mask, 0)
                self.assertTrue(any(frame.mask != 0 for frame in score.frames))

                rewrite_midi_programs(source, rewritten, program=40)
                rewritten_data = load_midi(rewritten)
                rewritten_score = build_light_score_for_tracks(rewritten_data, (0, 1), pin_count=4)
                self.assertEqual(rewritten_score.total_ms, score.total_ms)
                self.assertEqual(rewritten_data.track_summaries[0].programs, (40,))
                self.assertEqual(rewritten_data.track_summaries[1].programs, (40,))


if __name__ == "__main__":
    unittest.main()
