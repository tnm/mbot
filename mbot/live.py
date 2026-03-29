from __future__ import annotations

import subprocess
import time

from .board import SerialLightBoard
from .midi import LightScore


def start_midi_with_timidity(path: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["timidity", "-Od", "-id", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_player_process(process: subprocess.Popen[bytes] | None, timeout: float = 2.0) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def play_light_score(score: LightScore, board: SerialLightBoard, speed: float = 1.0) -> None:
    if speed <= 0:
        raise ValueError("speed must be > 0")

    start_time = time.perf_counter()
    current_mask: int | None = None

    try:
        for frame in score.frames:
            target_seconds = frame.start_ms / (1000.0 * speed)
            while True:
                remaining = start_time + target_seconds - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.01))

            if current_mask == frame.mask:
                continue

            board.send_mask(frame.mask)
            current_mask = frame.mask
    finally:
        board.send_off()


def format_pitch_bands(score: LightScore) -> str:
    parts: list[str] = []
    for band in score.bands:
        if band.low_pitch is None or band.high_pitch is None:
            parts.append(f"pin {band.pin_index + 1}: unused")
            continue
        parts.append(f"pin {band.pin_index + 1}: {band.low_pitch}-{band.high_pitch}")
    return ", ".join(parts)
