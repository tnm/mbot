from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .board import SerialLightBoard
from .live import (
    format_pitch_bands,
    play_light_score,
    start_midi_with_timidity,
    stop_player_process,
)
from .midi import (
    build_light_score,
    build_light_score_for_tracks,
    choose_track,
    format_track_summary,
    load_midi,
    resolve_program_number,
    rewrite_midi_programs,
)
from .pieces import PIECES


REPO_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbot",
        description=(
            "Music-to-light CLI for the ESP32 renderer.\n\n"
            "Run `mbot <command> -h` for command-specific help."
        ),
        epilog=(
            "common commands:\n"
            "  mbot board-brightness 10 --port /dev/cu.usbserial-0001\n"
            "  mbot flash --port /dev/cu.usbserial-0001 flash\n"
            "  mbot interactive --port /dev/cu.usbserial-0001\n"
            "  mbot pieces\n"
            "  mbot run cavalleria_rusticana --port /dev/cu.usbserial-0001"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    board_brightness_parser = subparsers.add_parser(
        "board-brightness",
        help="Get or set the ESP32 renderer brightness percentage",
    )
    board_brightness_parser.add_argument("percent", nargs="?", type=int)
    board_brightness_parser.add_argument("--port", default="/dev/cu.usbserial-0001")

    flash_parser = subparsers.add_parser(
        "flash",
        help="Run the ESP-IDF firmware flash helper through the CLI",
        description=(
            "Run one or more ESP-IDF firmware actions through the repo flash helper.\n\n"
            "Examples:\n"
            "  mbot flash --port /dev/cu.usbserial-0001 flash\n"
            "  mbot flash --port /dev/cu.usbserial-0001 fullclean flash\n"
            "  mbot flash --port /dev/cu.usbserial-0001 monitor"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    flash_parser.add_argument("--port", default="/dev/cu.usbserial-0001")
    flash_parser.add_argument(
        "actions",
        nargs="*",
        choices=("build", "flash", "monitor", "flash_monitor", "fullclean"),
        metavar="action",
        help="idf.py actions to run in order; defaults to `flash`",
    )

    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Open a small interactive menu for playback and board controls",
    )
    interactive_parser.add_argument("--port", default="/dev/cu.usbserial-0001")

    midi_inspect_parser = subparsers.add_parser("midi-inspect", help="Inspect MIDI tracks")
    midi_inspect_parser.add_argument("midi_path")

    midi_play_parser = subparsers.add_parser(
        "midi-play",
        help="Stream 4-pin light events from a MIDI file to the ESP32 board",
    )
    midi_play_parser.add_argument("midi_path")
    midi_play_parser.add_argument("--track", type=int)
    midi_play_parser.add_argument("--port", default="/dev/cu.usbserial-0001")
    midi_play_parser.add_argument("--speed", type=float, default=1.0)
    midi_play_parser.add_argument("--start-delay", type=float, default=2.0)
    midi_play_parser.add_argument("--dry-run", action="store_true")
    midi_play_parser.add_argument("--list-tracks", action="store_true")

    midi_revoice_parser = subparsers.add_parser(
        "midi-revoice",
        help="Rewrite MIDI program changes to a specific GM patch",
    )
    midi_revoice_parser.add_argument("midi_path")
    midi_revoice_parser.add_argument("output_path")
    midi_revoice_parser.add_argument("--program", default="violin")
    midi_revoice_parser.add_argument("--track", dest="tracks", type=int, action="append")

    piece_play_parser = subparsers.add_parser(
        "piece-play",
        help="Stream a bundled piece preset through the 4-pin light renderer",
    )
    piece_play_parser.add_argument("piece", choices=sorted(PIECES))
    piece_play_parser.add_argument("--track", type=int)
    piece_play_parser.add_argument("--port", default="/dev/cu.usbserial-0001")
    piece_play_parser.add_argument("--speed", type=float, default=1.0)
    piece_play_parser.add_argument("--start-delay", type=float, default=2.0)
    piece_play_parser.add_argument("--dry-run", action="store_true")
    piece_play_parser.add_argument("--list-tracks", action="store_true")

    pieces_parser = subparsers.add_parser("pieces", help="List bundled MIDI piece presets")

    run_parser = subparsers.add_parser(
        "run",
        help="Play a bundled piece and start the board stream in one command",
    )
    run_parser.add_argument("piece", choices=sorted(PIECES))
    run_parser.add_argument("--track", type=int)
    run_parser.add_argument("--port", default="/dev/cu.usbserial-0001")
    run_parser.add_argument("--speed", type=float, default=1.0)
    run_parser.add_argument("--player", choices=("timidity", "none"))
    run_parser.add_argument("--launch-delay", type=float)
    run_parser.add_argument("--light-delay", type=float)
    run_parser.add_argument("--manual-start", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")

    return parser


def _print_tracks(midi_path: str) -> int:
    midi_data = load_midi(midi_path)
    print(f"{Path(midi_path).name} | ticks/quarter={midi_data.ticks_per_quarter}")
    for summary in midi_data.track_summaries:
        print(format_track_summary(summary))
    return 0


def _format_selected_tracks(selected_tracks: tuple) -> str:
    if len(selected_tracks) == 1:
        return format_track_summary(selected_tracks[0])
    return "\n".join(format_track_summary(track) for track in selected_tracks)


def _load_light_score(midi_path: str, track_indexes: tuple[int, ...] | None):
    midi_data = load_midi(midi_path)
    if track_indexes is None:
        selected_track = choose_track(midi_data, track_index=None)
        light_score = build_light_score(midi_data, selected_track.index, pin_count=4)
        return (selected_track,), light_score

    selected_tracks = tuple(choose_track(midi_data, track_index=track) for track in track_indexes)
    light_score = build_light_score_for_tracks(
        midi_data,
        tuple(track.index for track in selected_tracks),
        pin_count=4,
    )
    return selected_tracks, light_score


def _stop_playback_via_script(port: str) -> None:
    script_path = REPO_ROOT / "scripts" / "stop_playback.sh"
    if not script_path.exists():
        return
    subprocess.run(
        ["bash", str(script_path), port],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _flash_firmware_via_script(port: str, actions: tuple[str, ...]) -> int:
    script_path = REPO_ROOT / "scripts" / "flash_firmware.sh"
    if not script_path.exists():
        raise FileNotFoundError(f"missing flash helper: {script_path}")
    completed = subprocess.run(["bash", str(script_path), port, *actions], check=False)
    return completed.returncode


def _print_piece_choices() -> None:
    print("bundled pieces:")
    for index, piece in enumerate(PIECES.values(), start=1):
        print(f" {index:>2}. {piece.slug:<30} {piece.title}")


def _resolve_piece_choice(choice: str) -> str | None:
    stripped = choice.strip()
    if not stripped:
        return None
    if stripped in PIECES:
        return stripped
    if stripped.isdigit():
        index = int(stripped)
        piece_slugs = list(PIECES)
        if 1 <= index <= len(piece_slugs):
            return piece_slugs[index - 1]
    return None


def _interactive_loop(port: str) -> int:
    current_process: subprocess.Popen[bytes] | None = None
    last_piece: str | None = None

    def refresh_current_process() -> None:
        nonlocal current_process
        if current_process is not None and current_process.poll() is not None:
            current_process = None

    def stop_current_playback() -> None:
        nonlocal current_process
        _stop_playback_via_script(port)
        refresh_current_process()
        if current_process is not None:
            try:
                current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                current_process.kill()
                current_process.wait(timeout=5)
            current_process = None

    def start_piece(piece_slug: str) -> None:
        nonlocal current_process, last_piece
        stop_current_playback()
        current_process = subprocess.Popen(
            [sys.executable, "-m", "mbot", "run", piece_slug, "--port", port],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        last_piece = piece_slug
        print(f"started: {piece_slug}")

    print(f"interactive mode | port={port}")
    print("commands: play, replay, stop, brightness, status, pieces, quit")
    _print_piece_choices()

    while True:
        refresh_current_process()
        command = input("> ").strip().lower()

        if command in {"q", "quit", "exit"}:
            refresh_current_process()
            if current_process is not None:
                print("leaving current playback running")
            return 0

        if command in {"p", "play"}:
            _print_piece_choices()
            piece_choice = input("piece slug or number: ")
            piece_slug = _resolve_piece_choice(piece_choice)
            if piece_slug is None:
                print("unknown piece")
                continue
            start_piece(piece_slug)
            continue

        if command in {"r", "replay"}:
            if last_piece is None:
                print("no last piece")
                continue
            start_piece(last_piece)
            continue

        if command in {"s", "stop"}:
            stop_current_playback()
            print("stopped playback")
            continue

        if command in {"b", "brightness"}:
            value = input("brightness 0-100: ").strip()
            if not value.isdigit() or not (0 <= int(value) <= 100):
                print("brightness must be an integer between 0 and 100")
                continue
            with SerialLightBoard(port) as board:
                board.send_brightness(int(value))
                time.sleep(0.05)
                info_reply = board.query_info().raw_reply
                brightness = board.query_brightness(info_reply)
            if brightness is None:
                print("brightness: unavailable")
            else:
                print(f"brightness: {brightness}%")
            continue

        if command in {"i", "info", "status"}:
            with SerialLightBoard(port) as board:
                info = board.query_info().raw_reply.strip()
            if info:
                print(f"board: {info}")
            refresh_current_process()
            if current_process is None:
                print("playback: idle")
            else:
                print(f"playback: running ({last_piece})")
            continue

        if command in {"l", "list", "pieces"}:
            _print_piece_choices()
            continue

        if command == "":
            continue

        print("commands: play, replay, stop, brightness, status, pieces, quit")


def _play_midi(
    parser: argparse.ArgumentParser,
    *,
    midi_path: str,
    track_indexes: tuple[int, ...] | None,
    port: str,
    speed: float,
    start_delay: float,
    dry_run: bool,
    list_tracks: bool,
) -> int:
    if speed <= 0:
        parser.error("--speed must be > 0")
    if start_delay < 0:
        parser.error("--start-delay must be >= 0")

    if list_tracks:
        return _print_tracks(midi_path)

    selected_tracks, light_score = _load_light_score(midi_path, track_indexes)

    if len(selected_tracks) == 1:
        print(f"selected track: {format_track_summary(selected_tracks[0])}")
    else:
        print("selected tracks:")
        print(_format_selected_tracks(selected_tracks))
    print(f"pitch bands: {format_pitch_bands(light_score)}")
    print(f"duration: {light_score.total_ms} ms")

    if dry_run:
        for frame in light_score.frames[:20]:
            print(f"{frame.start_ms:>6} ms  mask={frame.mask:04b}")
        if len(light_score.frames) > 20:
            print("...")
        return 0

    with SerialLightBoard(port) as board:
        board.send_off()
        info = board.query_info().raw_reply.strip()
        if info:
            print(f"board: {info}")

        if start_delay > 0:
            print(f"starting light stream in {start_delay:.1f}s")
            time.sleep(start_delay)

        play_light_score(light_score, board, speed=speed)
    return 0


def _run_piece(
    parser: argparse.ArgumentParser,
    *,
    piece_name: str,
    track: int | None,
    port: str,
    speed: float,
    player: str | None,
    launch_delay: float | None,
    light_delay: float | None,
    manual_start: bool,
    dry_run: bool,
) -> int:
    piece = PIECES[piece_name]
    if not piece.midi_path.exists():
        raise FileNotFoundError(f"missing bundled MIDI: {piece.midi_path}")

    resolved_player = player or piece.default_player
    resolved_launch_delay = piece.launch_delay if launch_delay is None else launch_delay
    resolved_light_delay = piece.light_delay if light_delay is None else light_delay
    resolved_track_indexes = piece.preferred_tracks if track is None else (track,)

    if speed <= 0:
        parser.error("--speed must be > 0")
    if resolved_launch_delay < 0:
        parser.error("--launch-delay must be >= 0")
    if resolved_light_delay < 0:
        parser.error("--light-delay must be >= 0")
    if resolved_player != "none" and speed != 1.0:
        parser.error("--speed must stay at 1.0 when audio playback is enabled")

    selected_tracks, light_score = _load_light_score(str(piece.midi_path), resolved_track_indexes)

    print(f"piece: {piece.title}")
    print(f"note: {piece.note}")
    print(f"player: {resolved_player}")
    if len(selected_tracks) == 1:
        print(f"selected track: {format_track_summary(selected_tracks[0])}")
    else:
        print("selected tracks:")
        print(_format_selected_tracks(selected_tracks))
    print(f"pitch bands: {format_pitch_bands(light_score)}")
    print(f"duration: {light_score.total_ms} ms")
    print(
        f"coordination: launch_delay={resolved_launch_delay:.1f}s "
        f"light_delay={resolved_light_delay:.1f}s manual_start={manual_start}"
    )

    if dry_run:
        return 0

    player_process = None
    with SerialLightBoard(port) as board:
        board.send_off()
        info = board.query_info().raw_reply.strip()
        if info:
            print(f"board: {info}")

        try:
            if manual_start:
                if resolved_player == "timidity":
                    input("Press Enter to start TiMidity++ and the lights...")
                else:
                    input("Press Enter to start the lights...")

            if resolved_player == "timidity":
                print("starting TiMidity++")
                player_process = start_midi_with_timidity(piece.midi_path)
                if resolved_launch_delay > 0:
                    print(f"waiting {resolved_launch_delay:.1f}s for TiMidity++ to warm up")
                    time.sleep(resolved_launch_delay)

            if resolved_light_delay > 0:
                print(f"waiting {resolved_light_delay:.1f}s before starting lights")
                time.sleep(resolved_light_delay)

            play_light_score(light_score, board, speed=speed)
        finally:
            stop_player_process(player_process)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stdout)
        return 0

    if args.command == "midi-inspect":
        return _print_tracks(args.midi_path)

    if args.command == "midi-revoice":
        output_path = rewrite_midi_programs(
            args.midi_path,
            args.output_path,
            program=resolve_program_number(args.program),
            track_indexes=set(args.tracks) if args.tracks else None,
        )
        print(f"wrote {output_path}")
        return _print_tracks(str(output_path))

    if args.command == "pieces":
        for piece in PIECES.values():
            print(
                f"{piece.slug:<20} title={piece.title}  "
                f"tracks={','.join(str(track) for track in piece.preferred_tracks)}  midi={piece.midi_path}"
            )
        return 0

    if args.command == "board-brightness":
        if args.percent is not None and not (0 <= args.percent <= 100):
            parser.error("brightness percent must be between 0 and 100")

        with SerialLightBoard(args.port) as board:
            if args.percent is not None:
                board.send_brightness(args.percent)
                time.sleep(0.05)

            info_reply = board.query_info().raw_reply
            info = info_reply.strip()
            if info:
                print(f"board: {info}")

            brightness = board.query_brightness(info_reply)
            if brightness is None:
                print("brightness: unavailable")
            else:
                print(f"brightness: {brightness}%")
        return 0

    if args.command == "interactive":
        return _interactive_loop(args.port)

    if args.command == "flash":
        actions = tuple(args.actions) if args.actions else ("flash",)
        return _flash_firmware_via_script(args.port, actions)

    if args.command == "run":
        return _run_piece(
            parser,
            piece_name=args.piece,
            track=args.track,
            port=args.port,
            speed=args.speed,
            player=args.player,
            launch_delay=args.launch_delay,
            light_delay=args.light_delay,
            manual_start=args.manual_start,
            dry_run=args.dry_run,
        )

    if args.command == "piece-play":
        piece = PIECES[args.piece]
        if not piece.midi_path.exists():
            raise FileNotFoundError(f"missing bundled MIDI: {piece.midi_path}")
        selected_track = args.track if args.track is not None else None
        print(f"piece: {piece.title}")
        print(f"note: {piece.note}")
        return _play_midi(
            parser,
            midi_path=str(piece.midi_path),
            track_indexes=piece.preferred_tracks if selected_track is None else (selected_track,),
            port=args.port,
            speed=args.speed,
            start_delay=args.start_delay,
            dry_run=args.dry_run,
            list_tracks=args.list_tracks,
        )

    if args.command == "midi-play":
        return _play_midi(
            parser,
            midi_path=args.midi_path,
            track_indexes=None if args.track is None else (args.track,),
            port=args.port,
            speed=args.speed,
            start_delay=args.start_delay,
            dry_run=args.dry_run,
            list_tracks=args.list_tracks,
        )

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
