from __future__ import annotations

import os
import select
import termios
import time
from dataclasses import dataclass
import re


DEFAULT_BAUD_RATE = 115200
_BAUD_RATES = {
    rate: getattr(termios, name)
    for rate, name in (
        (9600, "B9600"),
        (19200, "B19200"),
        (38400, "B38400"),
        (57600, "B57600"),
        (115200, "B115200"),
        (230400, "B230400"),
    )
    if hasattr(termios, name)
}


@dataclass(frozen=True)
class BoardInfo:
    raw_reply: str


class SerialLightBoard:
    def __init__(self, path: str, baud_rate: int = DEFAULT_BAUD_RATE) -> None:
        self.path = path
        self.baud_rate = baud_rate
        self.fd: int | None = None

    def __enter__(self) -> "SerialLightBoard":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self.fd is not None:
            return

        self.fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY)
        self._configure_tty(self.fd, self.baud_rate)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        time.sleep(0.05)

    def close(self) -> None:
        if self.fd is None:
            return

        os.close(self.fd)
        self.fd = None

    def send_mask(self, mask: int) -> None:
        self.write_line(f"M{mask}")

    def send_off(self) -> None:
        self.send_mask(0)

    def send_brightness(self, percent: int) -> None:
        if percent < 0 or percent > 100:
            raise ValueError("brightness percent must be between 0 and 100")
        self.write_line(f"BRIGHTNESS {percent}")

    def query_info(self) -> BoardInfo:
        self.write_line("PING")
        time.sleep(0.05)
        return BoardInfo(raw_reply=self.read_available(timeout=0.25))

    def query_brightness(self) -> int | None:
        info = self.query_info().raw_reply
        match = re.search(r"\bBRIGHTNESS\s+(\d+)\b", info)
        if match is None:
            return None
        return int(match.group(1))

    def write_line(self, line: str) -> None:
        if self.fd is None:
            raise RuntimeError("serial board is not open")
        os.write(self.fd, (line + "\n").encode("ascii"))

    def read_available(self, timeout: float = 0.0) -> str:
        if self.fd is None:
            raise RuntimeError("serial board is not open")

        chunks: list[bytes] = []
        ready, _, _ = select.select([self.fd], [], [], timeout)
        while ready:
            chunk = os.read(self.fd, 4096)
            if not chunk:
                break
            chunks.append(chunk)
            ready, _, _ = select.select([self.fd], [], [], 0)
        return b"".join(chunks).decode("utf-8", errors="replace")

    @staticmethod
    def _configure_tty(fd: int, baud_rate: int) -> None:
        if baud_rate not in _BAUD_RATES:
            supported = ", ".join(str(rate) for rate in sorted(_BAUD_RATES))
            raise ValueError(f"unsupported baud_rate {baud_rate}; supported values: {supported}")

        baud = _BAUD_RATES[baud_rate]
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] &= ~(termios.PARENB | termios.CSTOPB | termios.CSIZE)
        attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0
        attrs[4] = baud
        attrs[5] = baud
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
