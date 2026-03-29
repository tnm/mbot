from __future__ import annotations

import os
import pty
import termios
import threading
import unittest

from mbot.board import SerialLightBoard


class SerialBoardTests(unittest.TestCase):
    def test_configures_requested_baud_rate(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path, baud_rate=9600)
            board.open()
            attrs = termios.tcgetattr(board.fd)
            self.assertEqual(attrs[4], termios.B9600)
            self.assertEqual(attrs[5], termios.B9600)
            board.close()
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_rejects_unsupported_baud_rate(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path, baud_rate=12345)
            with self.assertRaises(ValueError):
                board.open()
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_send_brightness_writes_expected_command(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path)
            board.open()
            board.send_brightness(75)
            self.assertEqual(os.read(master_fd, 32), b"BRIGHTNESS 75\n")
            board.close()
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_send_brightness_rejects_out_of_range_value(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path)
            board.open()
            with self.assertRaises(ValueError):
                board.send_brightness(101)
            board.close()
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_query_brightness_parses_info_reply(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path)
            board.open()
            result: dict[str, int | None] = {}

            def run_query() -> None:
                result["brightness"] = board.query_brightness()

            query_thread = threading.Thread(target=run_query)
            query_thread.start()
            self.assertEqual(os.read(master_fd, 16), b"PING\n")
            os.write(master_fd, b"OK PINS 26 25 33 32 BRIGHTNESS 75\n")
            query_thread.join(timeout=1.0)

            self.assertEqual(result["brightness"], 75)
            board.close()
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_query_info_flushes_stale_bytes_and_reads_single_reply_line(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            path = os.ttyname(slave_fd)
            board = SerialLightBoard(path)
            board.open()
            os.write(master_fd, b"stale\n")

            result: dict[str, str] = {}

            def run_query() -> None:
                result["reply"] = board.query_info().raw_reply

            query_thread = threading.Thread(target=run_query)
            query_thread.start()
            self.assertEqual(os.read(master_fd, 16), b"PING\n")
            os.write(master_fd, b"OK PINS 26 25 33 32 BRIGHTNESS 75\nextra")
            query_thread.join(timeout=1.0)

            self.assertEqual(result["reply"], "OK PINS 26 25 33 32 BRIGHTNESS 75\n")
            board.close()
        finally:
            os.close(master_fd)
            os.close(slave_fd)
