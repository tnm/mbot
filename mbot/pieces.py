from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PiecePreset:
    slug: str
    title: str
    midi_path: Path
    preferred_tracks: tuple[int, ...]
    default_player: str
    launch_delay: float
    light_delay: float
    note: str


PIECES = {
    "cavalleria_rusticana": PiecePreset(
        slug="cavalleria_rusticana",
        title="Cavalleria rusticana (Intermezzo)",
        midi_path=REPO_ROOT / "midi" / "cavalleria_rusticana_intermezzo.mid",
        preferred_tracks=(1,),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="Kunst der Fuge piano-roll sequence of the Intermezzo. The light score follows the single note-bearing track.",
    ),
    "chopin_prelude_e_minor": PiecePreset(
        slug="chopin_prelude_e_minor",
        title="Chopin Prelude in E minor",
        midi_path=REPO_ROOT / "midi" / "chopin_prelude_op28_no4_e_minor.mid",
        preferred_tracks=(1,),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="BitMidi piano sequence of Prelude Op. 28 No. 4. The light score follows the single note-bearing piano track.",
    ),
    "clair_de_lune": PiecePreset(
        slug="clair_de_lune",
        title="Clair de lune",
        midi_path=REPO_ROOT / "midi" / "clair_de_lune.mid",
        preferred_tracks=(1, 2),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="Mutopia piano score export. The light score follows both staves so the upper and lower motion stay present in the four-lane reduction.",
    ),
    "gymnopedie_no_1": PiecePreset(
        slug="gymnopedie_no_1",
        title="Gymnopedie No. 1",
        midi_path=REPO_ROOT / "midi" / "gymnopedie_no_1.mid",
        preferred_tracks=(1, 2),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="Mutopia piano score export. The light score follows both staves so the treble line and bass pulse stay together.",
    ),
    "o_mio_babbino_caro": PiecePreset(
        slug="o_mio_babbino_caro",
        title="O mio babbino caro",
        midi_path=REPO_ROOT / "midi" / "o_mio_babbino_caro_violin.mid",
        preferred_tracks=(1, 2),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="BitMidi arrangement revoiced to Violin. The light score follows both note-bearing tracks, and the default playback path uses the TiMidity++ CLI synth.",
    ),
    "pavane_pour_une_infante_defunte": PiecePreset(
        slug="pavane_pour_une_infante_defunte",
        title="Pavane pour une infante defunte",
        midi_path=REPO_ROOT / "midi" / "pavane_pour_une_infante_defunte.mid",
        preferred_tracks=(1,),
        default_player="timidity",
        launch_delay=0.0,
        light_delay=0.1,
        note="Kunst der Fuge piano sequence by K. Oguri. The light score follows the single note-bearing piano track.",
    ),
}
