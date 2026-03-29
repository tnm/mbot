# mbot

`mbot` is a small music-to-light project built around an ESP32.

The idea is straightforward: the computer plays the music, keeps the clock, and
decides which light lanes should be active. The ESP32 stays simple and acts as a
four-output light renderer over USB serial.

This repo contains both halves of that setup:

- the ESP32 firmware that listens for light commands and flips GPIO outputs
- the Python harness that inspects MIDI, reduces it into four lanes, and
  streams those lane changes to the board

## Quick Start

If you just want to get the board doing something quickly, use this path.

The default serial port is `/dev/cu.usbserial-0001`. If your board shows up
somewhere else, pass `--port /path/to/device` to the CLI commands below.

1. Install the CLI from the repo root:

   ```bash
   bash scripts/install.sh
   ```

2. If `mbot` is not found in a fresh shell, add uv's tool bin directory to your
   shell setup:

   ```bash
   uv tool update-shell
   ```

3. Flash the firmware to the ESP32:

   ```bash
   mbot flash
   ```

4. Confirm the board is reachable:

   ```bash
   mbot board-brightness
   ```

5. List the bundled pieces:

   ```bash
   mbot pieces
   ```

6. Play one:

   ```bash
   mbot run cavalleria_rusticana
   ```

7. Change brightness live if needed:

   ```bash
   mbot board-brightness 10
   ```

8. Stop playback:

   ```bash
   bash scripts/stop_playback.sh
   ```

That is the shortest end-to-end path: install, flash, verify, play, adjust,
stop.

The install script is just a thin wrapper around `uv tool install --editable .`
so the repo has one documented install path.

If you prefer a small menu instead of individual commands, use:

```bash
mbot interactive
```

## Included Pieces

These bundled presets are available today:

- `cavalleria_rusticana`
  Cavalleria rusticana (Intermezzo)
- `chopin_prelude_e_minor`
  Chopin Prelude in E minor
- `clair_de_lune`
  Clair de lune
- `e_lucevan_le_stelle`
  E lucevan le stelle
- `gymnopedie_no_1`
  Gymnopedie No. 1
- `nessun_dorma`
  Nessun dorma
- `o_mio_babbino_caro`
  O mio babbino caro
- `pavane_pour_une_infante_defunte`
  Pavane pour une infante defunte
- `vissi_darte`
  Vissi d'arte

Use:

```bash
mbot pieces
mbot run <piece_slug>
mbot piece-play <piece_slug> --dry-run
```

`run` is the main happy-path command. It uses the preset's default player and
timing offsets, starts TiMidity++, and then starts the light stream.

## What The Project Does

This project does not try to synthesize a violin on the ESP32. MIDI is the
source score, the computer handles playback, and the board reflects the music
as light.

## How It Fits Together

The two halves have different jobs.

The firmware is responsible for:

- configuring the ESP32 GPIO outputs
- accepting serial commands such as `PING`, `OFF`, and `MASK 5`
- applying a 4-bit light mask to the board outputs

The harness is responsible for:

- loading Standard MIDI files without external Python MIDI packages
- summarizing tracks so you can see what is in a file
- choosing or preconfiguring the musical line to follow
- turning note activity into four light lanes
- streaming those lane changes to the board in time with playback

In other words: the computer conducts, the board reflects.

## End-To-End Flow

At runtime, the whole loop works like this:

1. A command such as `midi-play`, `piece-play`, or `run` loads a MIDI file.
2. The host parser scans the file, collects note events, and summarizes each
   track.
3. The command decides which track or tracks to follow.
4. The selected note activity is converted from MIDI ticks into millisecond
   timestamps.
5. The full pitch range in use is divided into four bands.
6. For each timestamp, the host computes a 4-bit mask that says which lanes
   should be on.
7. The host opens the ESP32 serial port and sends masks such as `M0`, `M3`,
   or `M15` in time.
8. The ESP32 sets four GPIO outputs high or low and the attached LEDs reflect
   the current mask.

The board does not know anything about songs, tempo maps, tracks, or phrase
structure. It only knows how to receive commands and set outputs.

## Repo Layout

- `firmware/esp32/light_renderer/`
  ESP-IDF firmware for the four-lane serial renderer
- `mbot/`
  host-side MIDI tools and board streaming code
- `midi/`
  bundled MIDI assets
- `pyproject.toml`
  packaging for the host-side harness

## Current Hardware Target

The repo is currently tuned for the ELEGOO USB-C ESP-WROOM-32 board with a
CP2102 USB-serial bridge.

The current firmware lane order is:

- lane 1 -> `GPIO26`
- lane 2 -> `GPIO25`
- lane 3 -> `GPIO33`
- lane 4 -> `GPIO32`

On the current breadboard setup, that is wired left-to-right as low-to-high
note bands.

This is a board-specific choice, not a universal ESP32 rule. On the classic
ESP32 family:

- `GPIO20` does not exist
- `GPIO34` through `GPIO39` are input-only
- `GPIO6` through `GPIO11` should be avoided because they are tied to flash

If the wiring changes, update the pin order in
`firmware/esp32/light_renderer/main/main.c`.

The firmware drives each lane with PWM rather than plain binary GPIO. The
default global brightness is set to `75%`, which is a 25% reduction from full
output. That brightness can be changed at runtime over serial or from the host
CLI.

## CLI Usage

### Inspect a MIDI file

```bash
mbot midi-inspect path/to/file.mid
```

This shows track names, note counts, channels, programs, and pitch ranges so
you can decide what to follow.

### Stream lights from a MIDI file

```bash
mbot midi-play path/to/file.mid
mbot midi-play path/to/file.mid --track 2
mbot midi-play path/to/file.mid --dry-run
```

Useful flags:

```bash
mbot midi-play path/to/file.mid --list-tracks
mbot midi-play path/to/file.mid --speed 1.25
mbot midi-revoice path/to/file.mid path/to/violin.mid --program violin
```

If `--track` is omitted, `midi-play` picks the densest note-bearing track.

### What Each Command Does

The host-side commands are intentionally small and composable:

- `midi-inspect`
  reads a MIDI file and prints track summaries without touching the board
- `midi-play`
  chooses one track, builds a four-lane light score, and streams it
- `piece-play`
  does the same thing, but uses a named preset from `mbot/pieces.py`
- `run`
  uses a named preset and also starts local audio playback through TiMidity++
- `midi-revoice`
  rewrites MIDI program changes so playback uses a different General MIDI patch
- `board-brightness`
  queries or sets the board-wide PWM brightness percentage
- `flash`
  runs the repo's ESP-IDF flash helper through the CLI
- `interactive`
  opens a small menu for piece playback, brightness changes, status, replay, and stop

The practical difference between `piece-play` and `run` is that `piece-play`
only handles the board stream, while `run` tries to coordinate the board stream
with local audio playback.

### Flash the firmware

```bash
mbot flash
mbot flash fullclean flash
mbot flash monitor
```

`mbot flash` is a thin wrapper around `scripts/flash_firmware.sh`, which
loads the ESP-IDF environment and then runs `idf.py` inside
`firmware/esp32/light_renderer`.

If your ESP32 is on a different device path, use `mbot flash --port
/path/to/device ...`.

After flashing, the board reports its lane order with `PING` or `INFO`, for
example:

```text
OK PINS 26 25 33 32 BRIGHTNESS 75
```

You usually do not need to send commands by hand, but the firmware understands:

- `PING`
- `INFO`
- `OFF`
- `RESET`
- `MASK 5`
- `M5`
- `BRIGHTNESS`
- `BRIGHTNESS 60`

`PING` and `INFO` return the board identity line. `OFF` and `RESET` clear all
lanes. `MASK n` and `Mn` set the active 4-bit lane mask directly, where bit 0
is lane 1 and bit 3 is lane 4. `BRIGHTNESS` reports the current global PWM
brightness percentage. `BRIGHTNESS n` sets it, where `n` must be between `0`
and `100`.

### Change Board Brightness

Query the current brightness:

```bash
mbot board-brightness
```

Set it explicitly:

```bash
mbot board-brightness 75
mbot board-brightness 60
mbot board-brightness 100
```

This is a board-wide setting. It changes the duty cycle used when a lane is on,
but it does not change the note-to-lane reduction logic. You can change it
while a piece is already playing.

## Playback Coordination

There are two clocks involved during a normal `run`:

- audio playback on the host computer
- light-mask streaming to the ESP32

The Python harness is the source of truth for timing. It starts the player,
waits for the configured launch and light delays, then sends the light masks at
the required millisecond offsets.

That means the quality of sync depends on:

- how quickly the local player starts
- whether the configured `launch_delay` and `light_delay` suit that piece
- whether the machine is busy enough to delay scheduling

For repeatable setups, keep the same player, port, and delay values for a given
piece preset.

## Stopping Playback

If a run is still active and you want to stop it quickly, use:

```bash
bash scripts/stop_playback.sh
```

By default that helper targets `/dev/cu.usbserial-0001`. You can pass a
different serial port as the first argument.

The helper tries to:

- send `OFF` to the board
- stop active `mbot` playback commands
- stop the associated `timidity` process
- send `OFF` again so the lanes are left dark

## Typical Workflow For A New Piece

1. Find or export a MIDI file.
2. Run `mbot midi-inspect ...`.
3. Decide whether one track is enough or whether the piece wants a preset.
4. Revoice the file if needed with `midi-revoice`.
5. Dry-run the light score.
6. Stream it to the board.

For quick experimentation, `midi-play` is enough. For repeatable setups, add a
piece preset in `mbot/pieces.py`.

## Adding A New MIDI

There are two ways to bring in a new piece.

### Quick Path: Use A MIDI File Directly

If you just want to try a file with the board, you do not need to edit the
repo at all:

```bash
mbot midi-inspect path/to/file.mid
mbot midi-play path/to/file.mid
```

If the auto-selected track is not the musical line you want, choose a track
explicitly:

```bash
mbot midi-play path/to/file.mid --track N
```

### Preset Path: Add A Bundled Piece

If you want the piece to show up under `pieces`, `piece-play`, and `run`:

1. Copy the MIDI file into `midi/`.
2. Optionally revoice it with `midi-revoice`.
3. Add a `PiecePreset` entry in `mbot/pieces.py`.

Example:

```python
"new_piece": PiecePreset(
    slug="new_piece",
    title="New Piece",
    midi_path=REPO_ROOT / "midi" / "new_piece.mid",
    preferred_tracks=(2,),
    default_player="timidity",
    launch_delay=0.0,
    light_delay=0.1,
    note="Short note about the arrangement and chosen track(s).",
),
```

Then you can use:

```bash
mbot pieces
mbot piece-play new_piece --dry-run
mbot run new_piece
```

### Will A New MIDI Automatically Work?

Usually yes, mechanically.

If the file is a Standard MIDI file with note events, `midi-play` will parse it
and turn the selected notes into four light lanes automatically.

What is not automatic is musical taste. The current reducer is still simple:

- `midi-play` follows one selected track at a time
- bundled presets can follow more than one note-bearing track
- notes are reduced into four pitch bands

So a new file will often work immediately, but it may need:

- a better track choice
- a revoiced copy for nicer audio playback
- a preset if you want repeatable `run` behavior

### Current Format Limits

- supported MIDI formats: `0` and `1`
- SMPTE time division is not supported
- best results come from melody-forward arrangements or carefully chosen track
  presets

## Testing

The repo uses Python's built-in `unittest` runner, so there is no extra test
dependency to install.

Run the regular suite with:

```bash
uv run python -m unittest discover -s tests -v
```

Run the longer soak pass with:

```bash
uv run python -m unittest tests.soak -v
```

You can scale the soak loop count if you want a longer run:

```bash
MBOT_SOAK_ITERS=500 uv run python -m unittest tests.soak -v
```

## Current Limits

The project is still intentionally narrow:

- four output lanes
- one board profile hard-coded in the firmware
- one global brightness value for all lanes rather than per-lane brightness
- pitch-band mapping rather than richer phrase or dynamics mapping
- preset-based multi-track support instead of a fully general arrangement layer
