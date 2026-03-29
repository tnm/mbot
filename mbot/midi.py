from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


GM_PROGRAM_NAMES = {
    40: "Violin",
    41: "Viola",
    42: "Cello",
    43: "Contrabass",
    44: "Tremolo Strings",
    45: "Pizzicato Strings",
    46: "Orchestral Harp",
    47: "Timpani",
}

GM_PROGRAM_NUMBERS = {
    name.lower().replace(" ", "_"): program for program, name in GM_PROGRAM_NAMES.items()
}


@dataclass(frozen=True)
class TempoChange:
    tick: int
    microseconds_per_quarter: int


@dataclass(frozen=True)
class MidiNote:
    track_index: int
    track_name: str
    channel: int
    pitch: int
    velocity: int
    start_tick: int
    end_tick: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class MidiTrackSummary:
    index: int
    name: str
    note_count: int
    channels: tuple[int, ...]
    programs: tuple[int, ...]
    min_pitch: int | None
    max_pitch: int | None

    @property
    def program_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for program in self.programs:
            names.append(GM_PROGRAM_NAMES.get(program, f"Program {program + 1}"))
        return tuple(names)


@dataclass(frozen=True)
class MidiData:
    path: Path
    ticks_per_quarter: int
    track_summaries: tuple[MidiTrackSummary, ...]
    notes: tuple[MidiNote, ...]


@dataclass(frozen=True)
class PitchBand:
    pin_index: int
    low_pitch: int | None
    high_pitch: int | None


@dataclass(frozen=True)
class LightFrame:
    start_ms: int
    mask: int


@dataclass(frozen=True)
class LightScore:
    title: str
    track_indexes: tuple[int, ...]
    track_name: str
    total_ms: int
    bands: tuple[PitchBand, ...]
    frames: tuple[LightFrame, ...]


@dataclass
class _RawMidiNote:
    track_index: int
    track_name: str
    channel: int
    pitch: int
    velocity: int
    start_tick: int
    end_tick: int


@dataclass
class _ParsedTrack:
    index: int
    name: str
    programs: set[int]
    channels: set[int]
    min_pitch: int | None
    max_pitch: int | None
    notes: list[_RawMidiNote]
    tempos: list[TempoChange]


@dataclass(frozen=True)
class _TempoSegment:
    start_tick: int
    start_microseconds: float
    microseconds_per_quarter: int


def load_midi(path: str | Path) -> MidiData:
    midi_path = Path(path)
    payload = midi_path.read_bytes()

    if payload[:4] != b"MThd":
        raise ValueError(f"{midi_path} is not a Standard MIDI file")

    header_length = int.from_bytes(payload[4:8], "big")
    if header_length != 6:
        raise ValueError(f"unsupported MIDI header length {header_length}")

    format_type = int.from_bytes(payload[8:10], "big")
    track_count = int.from_bytes(payload[10:12], "big")
    division = int.from_bytes(payload[12:14], "big")

    if division & 0x8000:
        raise ValueError("SMPTE time division is not supported")

    ticks_per_quarter = division
    if format_type not in (0, 1):
        raise ValueError(f"unsupported MIDI format {format_type}")

    offset = 14
    parsed_tracks: list[_ParsedTrack] = []
    for track_index in range(track_count):
        if payload[offset : offset + 4] != b"MTrk":
            raise ValueError(f"track {track_index} is missing MTrk header")
        track_length = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        offset += 8
        track_payload = payload[offset : offset + track_length]
        offset += track_length
        parsed_tracks.append(_parse_track(track_payload, track_index))

    tempo_segments = _build_tempo_segments(parsed_tracks, ticks_per_quarter)
    notes: list[MidiNote] = []
    summaries: list[MidiTrackSummary] = []

    for parsed_track in parsed_tracks:
        track_notes: list[MidiNote] = []
        for raw_note in parsed_track.notes:
            start_ms = _tick_to_ms(raw_note.start_tick, tempo_segments, ticks_per_quarter)
            end_ms = _tick_to_ms(raw_note.end_tick, tempo_segments, ticks_per_quarter)
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            track_notes.append(
                MidiNote(
                    track_index=raw_note.track_index,
                    track_name=raw_note.track_name,
                    channel=raw_note.channel,
                    pitch=raw_note.pitch,
                    velocity=raw_note.velocity,
                    start_tick=raw_note.start_tick,
                    end_tick=raw_note.end_tick,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )

        notes.extend(track_notes)
        summaries.append(
            MidiTrackSummary(
                index=parsed_track.index,
                name=parsed_track.name,
                note_count=len(track_notes),
                channels=tuple(sorted(channel + 1 for channel in parsed_track.channels)),
                programs=tuple(sorted(parsed_track.programs)),
                min_pitch=parsed_track.min_pitch,
                max_pitch=parsed_track.max_pitch,
            )
        )

    return MidiData(
        path=midi_path,
        ticks_per_quarter=ticks_per_quarter,
        track_summaries=tuple(summaries),
        notes=tuple(sorted(notes, key=lambda note: (note.start_ms, note.pitch, note.track_index))),
    )


def choose_track(data: MidiData, track_index: int | None = None) -> MidiTrackSummary:
    if track_index is not None:
        for summary in data.track_summaries:
            if summary.index == track_index:
                if summary.note_count == 0:
                    raise ValueError(f"track {track_index} has no note events")
                return summary
        raise ValueError(f"track {track_index} not found")

    note_tracks = [summary for summary in data.track_summaries if summary.note_count > 0]
    if not note_tracks:
        raise ValueError("MIDI file does not contain any note events")

    melodic_tracks = [summary for summary in note_tracks if not _is_percussion_only(summary)]
    candidate_tracks = melodic_tracks or note_tracks
    return max(candidate_tracks, key=lambda summary: summary.note_count)


def build_light_score(
    data: MidiData,
    track_index: int,
    pin_count: int = 4,
) -> LightScore:
    return build_light_score_for_tracks(data, (track_index,), pin_count=pin_count)


def build_light_score_for_tracks(
    data: MidiData,
    track_indexes: tuple[int, ...],
    pin_count: int = 4,
) -> LightScore:
    selected_indexes = tuple(dict.fromkeys(track_indexes))
    if not selected_indexes:
        raise ValueError("at least one track index is required")

    selected_notes = [note for note in data.notes if note.track_index in selected_indexes]
    if not selected_notes:
        joined = ", ".join(str(index) for index in selected_indexes)
        raise ValueError(f"tracks {joined} have no note events")

    selected_summaries = [
        summary for summary in data.track_summaries if summary.index in selected_indexes
    ]
    track_label = ", ".join(summary.name for summary in selected_summaries)
    min_pitch = min(note.pitch for note in selected_notes)
    max_pitch = max(note.pitch for note in selected_notes)
    span = max_pitch - min_pitch + 1
    active_pin_count = min(pin_count, span)

    def pin_for_pitch(pitch: int) -> int:
        offset = pitch - min_pitch
        return min(active_pin_count - 1, (offset * active_pin_count) // max(1, span))

    band_pitches: list[list[int]] = [[] for _ in range(pin_count)]
    for pitch in range(min_pitch, max_pitch + 1):
        band_pitches[pin_for_pitch(pitch)].append(pitch)

    bands: list[PitchBand] = []
    for pin_index, pitches in enumerate(band_pitches):
        if not pitches:
            bands.append(PitchBand(pin_index=pin_index, low_pitch=None, high_pitch=None))
            continue

        bands.append(
            PitchBand(
                pin_index=pin_index,
                low_pitch=min(pitches),
                high_pitch=max(pitches),
            )
        )

    changes: dict[int, list[tuple[int, int]]] = {}
    total_ms = 0
    for note in selected_notes:
        pin_index = pin_for_pitch(note.pitch)
        changes.setdefault(note.start_ms, []).append((pin_index, 1))
        changes.setdefault(note.end_ms, []).append((pin_index, -1))
        total_ms = max(total_ms, note.end_ms)

    active_counts = [0] * pin_count
    frames: list[LightFrame] = [LightFrame(start_ms=0, mask=0)]

    for timestamp_ms in sorted(changes):
        for pin_index, delta in changes[timestamp_ms]:
            active_counts[pin_index] = max(0, active_counts[pin_index] + delta)

        mask = 0
        for pin_index, count in enumerate(active_counts):
            if count > 0:
                mask |= 1 << pin_index

        if frames[-1].mask != mask:
            frames.append(LightFrame(start_ms=timestamp_ms, mask=mask))

    if frames[-1].mask != 0:
        frames.append(LightFrame(start_ms=total_ms, mask=0))

    return LightScore(
        title=data.path.stem,
        track_indexes=selected_indexes,
        track_name=track_label,
        total_ms=total_ms,
        bands=tuple(bands),
        frames=tuple(frames),
    )


def format_track_summary(summary: MidiTrackSummary) -> str:
    pitch_range = "-"
    if summary.min_pitch is not None and summary.max_pitch is not None:
        pitch_range = f"{summary.min_pitch}-{summary.max_pitch}"

    channels = ", ".join(str(channel) for channel in summary.channels) or "-"
    programs = ", ".join(summary.program_names) or "-"
    name = summary.name or f"track_{summary.index}"
    return (
        f"{summary.index:>2}  {name:<24} notes={summary.note_count:<4} "
        f"channels={channels:<8} programs={programs:<24} pitch={pitch_range}"
    )


def _is_percussion_only(summary: MidiTrackSummary) -> bool:
    return bool(summary.channels) and all(channel == 10 for channel in summary.channels)


def resolve_program_number(program: str) -> int:
    normalized = program.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.isdigit():
        value = int(normalized)
    else:
        if normalized not in GM_PROGRAM_NUMBERS:
            raise ValueError(f"unsupported program {program!r}")
        value = GM_PROGRAM_NUMBERS[normalized]

    if value < 0 or value > 127:
        raise ValueError("program must be between 0 and 127")
    return value


def rewrite_midi_programs(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    program: int,
    track_indexes: set[int] | None = None,
) -> Path:
    if program < 0 or program > 127:
        raise ValueError("program must be between 0 and 127")

    source = Path(source_path)
    destination = Path(destination_path)
    midi_data = load_midi(source)
    selected_tracks = track_indexes
    if selected_tracks is None:
        selected_tracks = {
            summary.index for summary in midi_data.track_summaries if summary.note_count > 0
        }

    payload = source.read_bytes()
    header = payload[:14]
    track_count = int.from_bytes(payload[10:12], "big")
    offset = 14
    rewritten_chunks: list[bytes] = []

    for track_index in range(track_count):
        if payload[offset : offset + 4] != b"MTrk":
            raise ValueError(f"track {track_index} is missing MTrk header")

        track_length = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        offset += 8
        track_payload = payload[offset : offset + track_length]
        offset += track_length

        if track_index in selected_tracks:
            track_payload = _rewrite_track_programs(track_payload, target_program=program)

        rewritten_chunks.append(b"MTrk" + len(track_payload).to_bytes(4, "big") + track_payload)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + b"".join(rewritten_chunks))
    return destination


def _parse_track(track_payload: bytes, track_index: int) -> _ParsedTrack:
    position = 0
    absolute_tick = 0
    running_status: int | None = None
    track_name = f"track_{track_index}"
    programs: set[int] = set()
    channels: set[int] = set()
    min_pitch: int | None = None
    max_pitch: int | None = None
    notes: list[_RawMidiNote] = []
    tempos: list[TempoChange] = []
    active_notes: dict[tuple[int, int], list[tuple[int, int]]] = {}

    while position < len(track_payload):
        delta, position = _read_variable_length(track_payload, position)
        absolute_tick += delta

        status_byte = track_payload[position]
        running_data: list[int] = []
        if status_byte & 0x80:
            position += 1
            status = status_byte
            if status < 0xF0:
                running_status = status
            else:
                running_status = None
        else:
            if running_status is None:
                raise ValueError(f"running status without previous status in track {track_index}")
            status = running_status
            running_data.append(status_byte)
            position += 1

        if status == 0xFF:
            meta_type = track_payload[position]
            position += 1
            data_length, position = _read_variable_length(track_payload, position)
            meta_data = track_payload[position : position + data_length]
            position += data_length

            if meta_type == 0x03 and meta_data:
                track_name = meta_data.decode("latin-1", errors="replace")
            elif meta_type == 0x51 and data_length == 3:
                tempos.append(
                    TempoChange(
                        tick=absolute_tick,
                        microseconds_per_quarter=int.from_bytes(meta_data, "big"),
                    )
                )
            elif meta_type == 0x2F:
                break
            continue

        if status in (0xF0, 0xF7):
            data_length, position = _read_variable_length(track_payload, position)
            position += data_length
            continue

        message_type = status & 0xF0
        channel = status & 0x0F
        data_length = 1 if message_type in (0xC0, 0xD0) else 2
        data = running_data
        while len(data) < data_length:
            data.append(track_payload[position])
            position += 1

        channels.add(channel)

        if message_type == 0x90:
            pitch, velocity = data
            if velocity == 0:
                _finish_note(active_notes, notes, track_index, track_name, channel, pitch, absolute_tick)
            else:
                active_notes.setdefault((channel, pitch), []).append((absolute_tick, velocity))
                min_pitch = pitch if min_pitch is None else min(min_pitch, pitch)
                max_pitch = pitch if max_pitch is None else max(max_pitch, pitch)
        elif message_type == 0x80:
            pitch = data[0]
            _finish_note(active_notes, notes, track_index, track_name, channel, pitch, absolute_tick)
        elif message_type == 0xC0:
            programs.add(data[0])

    for (channel, pitch), starts in active_notes.items():
        for start_tick, velocity in starts:
            notes.append(
                _RawMidiNote(
                    track_index=track_index,
                    track_name=track_name,
                    channel=channel,
                    pitch=pitch,
                    velocity=velocity,
                    start_tick=start_tick,
                    end_tick=absolute_tick,
                )
            )

    return _ParsedTrack(
        index=track_index,
        name=track_name,
        programs=programs,
        channels=channels,
        min_pitch=min_pitch,
        max_pitch=max_pitch,
        notes=notes,
        tempos=tempos,
    )


def _finish_note(
    active_notes: dict[tuple[int, int], list[tuple[int, int]]],
    notes: list[_RawMidiNote],
    track_index: int,
    track_name: str,
    channel: int,
    pitch: int,
    end_tick: int,
) -> None:
    key = (channel, pitch)
    starts = active_notes.get(key)
    if not starts:
        return

    start_tick, velocity = starts.pop()
    notes.append(
        _RawMidiNote(
            track_index=track_index,
            track_name=track_name,
            channel=channel,
            pitch=pitch,
            velocity=velocity,
            start_tick=start_tick,
            end_tick=end_tick,
        )
    )

    if not starts:
        active_notes.pop(key, None)


def _build_tempo_segments(parsed_tracks: list[_ParsedTrack], ticks_per_quarter: int) -> tuple[_TempoSegment, ...]:
    tempo_changes = sorted(
        (tempo for track in parsed_tracks for tempo in track.tempos),
        key=lambda tempo: tempo.tick,
    )
    segments: list[_TempoSegment] = [_TempoSegment(0, 0.0, 500_000)]
    current_tick = 0
    current_microseconds = 0.0
    current_tempo = 500_000

    for tempo in tempo_changes:
        delta_ticks = tempo.tick - current_tick
        current_microseconds += (delta_ticks * current_tempo) / ticks_per_quarter
        current_tick = tempo.tick
        current_tempo = tempo.microseconds_per_quarter
        if tempo.tick == 0:
            segments[0] = _TempoSegment(0, 0.0, current_tempo)
        else:
            segments.append(_TempoSegment(current_tick, current_microseconds, current_tempo))

    return tuple(segments)


def _tick_to_ms(tick: int, segments: tuple[_TempoSegment, ...], ticks_per_quarter: int) -> int:
    segment = segments[0]
    for candidate in segments:
        if candidate.start_tick > tick:
            break
        segment = candidate

    delta_ticks = tick - segment.start_tick
    total_microseconds = segment.start_microseconds + (
        (delta_ticks * segment.microseconds_per_quarter) / ticks_per_quarter
    )
    return int(round(total_microseconds / 1000.0))


def _read_variable_length(payload: bytes, position: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = payload[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            break
    return value, position


def _rewrite_track_programs(track_payload: bytes, target_program: int) -> bytes:
    position = 0
    running_status: int | None = None
    rewritten = bytearray()
    used_channels: set[int] = set()
    programmed_channels: set[int] = set()

    while position < len(track_payload):
        event_start = position
        _, position = _read_variable_length(track_payload, position)
        status_pos = position
        status_byte = track_payload[position]

        if status_byte & 0x80:
            status = status_byte
            position += 1
            data_start = position
            if status < 0xF0:
                running_status = status
            else:
                running_status = None
        else:
            if running_status is None:
                raise ValueError("running status without previous status while rewriting MIDI")
            status = running_status
            data_start = position

        if status == 0xFF:
            meta_type = track_payload[position]
            position += 1
            data_length, position = _read_variable_length(track_payload, position)
            position += data_length
            rewritten.extend(track_payload[event_start:position])
            if meta_type == 0x2F:
                break
            continue

        if status in (0xF0, 0xF7):
            data_length, position = _read_variable_length(track_payload, position)
            position += data_length
            rewritten.extend(track_payload[event_start:position])
            continue

        message_type = status & 0xF0
        channel = status & 0x0F
        used_channels.add(channel)
        data_length = 1 if message_type in (0xC0, 0xD0) else 2
        position = data_start + data_length

        event_bytes = bytearray(track_payload[event_start:position])
        if message_type == 0xC0:
            programmed_channels.add(channel)
            event_bytes[-1] = target_program

        rewritten.extend(event_bytes)

    missing_channels = tuple(sorted(used_channels - programmed_channels))
    if not missing_channels:
        return bytes(rewritten)

    inserted_programs = bytearray()
    for channel in missing_channels:
        inserted_programs.extend((0x00, 0xC0 | channel, target_program))

    insertion_point = _find_initial_program_insertion_point(bytes(rewritten))
    return (
        bytes(rewritten[:insertion_point])
        + bytes(inserted_programs)
        + bytes(rewritten[insertion_point:])
    )


def _find_initial_program_insertion_point(track_payload: bytes) -> int:
    position = 0
    running_status: int | None = None

    while position < len(track_payload):
        event_start = position
        delta, position = _read_variable_length(track_payload, position)
        if delta != 0:
            return event_start

        status_byte = track_payload[position]
        if status_byte & 0x80:
            status = status_byte
            position += 1
            if status < 0xF0:
                running_status = status
            else:
                running_status = None
        else:
            if running_status is None:
                raise ValueError("running status without previous status while rewriting MIDI")
            status = running_status

        if status == 0xFF:
            meta_type = track_payload[position]
            position += 1
            data_length, position = _read_variable_length(track_payload, position)
            position += data_length
            if meta_type == 0x2F:
                return event_start
            continue

        if status in (0xF0, 0xF7):
            data_length, position = _read_variable_length(track_payload, position)
            position += data_length
            continue

        return event_start

    return len(track_payload)
