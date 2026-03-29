from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from mbot.__main__ import _interactive_loop, build_parser, _resolve_piece_choice, main


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
