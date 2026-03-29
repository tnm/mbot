from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from mbot.__main__ import (
    _format_piece_listing_rows,
    _format_track_summary_rows,
    _interactive_loop,
    _resolve_piece_choice,
    build_parser,
    main,
)
from mbot.midi import MidiTrackSummary


class CliContractTests(unittest.TestCase):
    def test_main_without_command_prints_help_and_returns_zero(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main([])
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Music-to-light CLI for the ESP32 renderer.", output)
        self.assertIn("common commands:", output)
        self.assertIn("flash", output)
        self.assertIn("mbot interactive\n", output)
        self.assertIn("use --port /path/to/device", output)

    def test_run_player_choices_only_include_real_playback_modes(self) -> None:
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["run", "o_mio_babbino_caro", "--player", "default"])

    def test_run_player_still_accepts_timidity(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run", "o_mio_babbino_caro", "--player", "timidity"])
        self.assertEqual(args.player, "timidity")

    def test_board_brightness_accepts_percent_and_port(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["board-brightness", "75", "--port", "/dev/test"])
        self.assertEqual(args.command, "board-brightness")
        self.assertEqual(args.percent, 75)
        self.assertEqual(args.port, "/dev/test")

    def test_interactive_accepts_port(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["interactive", "--port", "/dev/test"])
        self.assertEqual(args.command, "interactive")
        self.assertEqual(args.port, "/dev/test")

    def test_interactive_help_lists_menu_commands(self) -> None:
        parser = build_parser()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit):
                parser.parse_args(["interactive", "--help"])
        output = stdout.getvalue()
        self.assertIn("Menu commands:", output)
        self.assertIn("brightness", output)
        self.assertIn("quit", output)

    def test_interactive_play_stops_existing_playback_before_starting(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        stdout = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            mock.patch("mbot.__main__.input", side_effect=["play", "1", "quit"]),
            mock.patch("mbot.__main__._stop_playback_via_script") as stop_mock,
            mock.patch("mbot.__main__.subprocess.Popen", return_value=process) as popen_mock,
        ):
            exit_code = _interactive_loop("/dev/test")
        self.assertEqual(exit_code, 0)
        stop_mock.assert_called_once_with("/dev/test")
        popen_mock.assert_called_once()

    def test_flash_accepts_port_and_actions(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["flash", "--port", "/dev/test", "fullclean", "flash"])
        self.assertEqual(args.command, "flash")
        self.assertEqual(args.port, "/dev/test")
        self.assertEqual(args.actions, ["fullclean", "flash"])

    def test_flash_defaults_to_flash_action(self) -> None:
        with mock.patch("mbot.__main__._flash_firmware_via_script", return_value=0) as flash_mock:
            exit_code = main(["flash"])
        self.assertEqual(exit_code, 0)
        flash_mock.assert_called_once_with("/dev/cu.usbserial-0001", ("flash",))

    def test_resolve_piece_choice_accepts_slug(self) -> None:
        self.assertEqual(_resolve_piece_choice("clair_de_lune"), "clair_de_lune")

    def test_resolve_piece_choice_accepts_number(self) -> None:
        self.assertEqual(_resolve_piece_choice("1"), "cavalleria_rusticana")

    def test_piece_listing_is_rendered_as_a_table_with_relative_paths(self) -> None:
        lines = _format_piece_listing_rows()
        self.assertGreaterEqual(len(lines), 3)
        self.assertEqual(lines[0].split(), ["slug", "title", "tracks", "midi"])
        self.assertIn("midi/", lines[2])
        self.assertNotIn("/Users/", lines[2])

    def test_track_summary_rows_are_rendered_as_a_table(self) -> None:
        lines = _format_track_summary_rows(
            (
                MidiTrackSummary(
                    index=4,
                    name="Lead",
                    note_count=220,
                    channels=(1, 2),
                    programs=(40,),
                    min_pitch=60,
                    max_pitch=81,
                ),
            )
        )
        self.assertEqual(lines[0].split(), ["id", "name", "notes", "channels", "programs", "pitch"])
        self.assertIn("Lead", lines[2])
        self.assertIn("Violin", lines[2])

    def test_board_brightness_prints_compact_result(self) -> None:
        board = mock.Mock()
        board.query_info.return_value.raw_reply = "OK PINS 26 25 33 32 BRIGHTNESS 75\n"
        board.query_brightness.return_value = 75
        board_context = mock.Mock()
        board_context.__enter__ = mock.Mock(return_value=board)
        board_context.__exit__ = mock.Mock(return_value=False)
        stdout = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            mock.patch("mbot.__main__.SerialLightBoard", return_value=board_context),
        ):
            exit_code = main(["board-brightness"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "brightness: 75%")

    def test_piece_open_command_is_removed(self) -> None:
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["piece-open", "clair_de_lune"])

    def test_midi_play_open_flag_is_removed(self) -> None:
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["midi-play", "demo.mid", "--open"])
