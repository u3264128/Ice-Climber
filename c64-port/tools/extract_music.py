#!/usr/bin/env python3
"""Decode the Ice Climber music engine data into readable, portable formats.

Engine layout (all in the 16 KiB PRG bank at $C000-$FFFF):

  $F91E  update_sound_engine  - frame driver, called from NMI game loop
  $F9EB  play_sfx_3           - jump/death/hammer sfx   (pulse 1)
  $FAC4  play_sfx_2           - collect/kill sfx        (pulse 2)
  $FBFC  initialize_music     - song sequencer
  $FD22  tbl_FD22_offset      - music ID -> descriptor offset
  $FD2A  song descriptors     - [dur_base, ptr_lo, ptr_hi, tri_off, p1_off, 0]
  $FD4D  note streams         - per song: pulse2 at +0, pulse1 at +p1_off,
                                triangle at +tri_off, $00 = end
  $FF00  period table         - 32 little-endian words (hi byte 0 = rest)
  $FF40  duration table       - frame counts, indexed [dur_base + note_dur]
  $FFD9  pulse2 volume decay  - 32-entry envelope used while a note plays
  $FFD2/$FFD8  pause/off jingle data

Note byte encoding (sub_F983 and callers):
  bits 1-5 : pitch index (0 = rest) into the $FF00 period table
  bits 0,6,7 : duration index 0-7  (d = bit0*4 + bits6-7)
  $00      : end of stream

NTSC formulas: pulse f = 1789773/(16*(p+1)), triangle f = 1789773/(32*(p+1)).
"""
import json
import math
import sys
from pathlib import Path

NTSC_CPU = 1789773.0

SONGS = {
    0x01: "mountain_preview",
    0x02: "background",
    0x04: "logo_start",
    0x08: "logo_loop",
    0x10: "mountain_complete",
    0x20: "pause_jingle",
    0x40: "unpause_jingle",
    0x80: "music_off_jingle",
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def freq_to_note(freq: float) -> str:
    if freq <= 0:
        return "rest"
    midi = round(69 + 12 * math.log2(freq / 440.0))
    octave = midi // 12 - 1
    return f"{NOTE_NAMES[midi % 12]}({octave})" if octave < 0 \
        else f"{NOTE_NAMES[midi % 12]}{octave}"


def b(data: bytes, addr: int) -> int:
    return data[addr - 0xC000]


def read_word(data: bytes, addr: int) -> int:
    return b(data, addr) | (b(data, addr + 1) << 8)


def period_at(data: bytes, idx: int) -> int:
    """Period for pitch index from the interleaved table at $FF00.

    Engine (sub_F964): low byte = tbl_FF01[Y] (odd address -> written to
    $4002), high byte = tbl_FF00[Y] (even -> $4003, & $07 used).
    A zero LOW byte means the pitch is skipped (rest).
    """
    lo = b(data, 0xFF00 + idx * 2 + 1)
    hi = b(data, 0xFF00 + idx * 2) & 0x07
    return (hi << 8) | lo


def decode_stream(data: bytes, addr: int, dur_base: int, dur_tbl: list,
                  channel: str, bound: int):
    """Decode one note stream.  $00 semantics differ per channel:

      pulse2   : end of stream (the song loops/restarts on the next frame)
      pulse1   : $00 + next byte = duty/volume marker; two $00 in a row = end
      triangle : $00 is a plain rest note - the stream never ends by itself,
                 it is bounded by the next song's data
    """
    events = []
    p = addr
    is_tri = channel == "triangle"
    while p < bound:
        byte = b(data, p)
        p += 1
        if byte == 0:
            if channel == "pulse2":
                break
            if channel == "pulse1":
                marker = b(data, p)
                p += 1
                if marker == 0:
                    break
                events.append({"pitch": 0, "note": f"marker ${marker:02X}",
                               "frames": 0, "marker": marker})
                continue
        pitch = (byte >> 1) & 0x1F
        dur_idx = ((byte & 1) << 2) | (byte >> 6)
        dur = dur_tbl[dur_base + dur_idx]
        if pitch == 0:
            events.append({"pitch": 0, "note": "rest", "frames": dur})
            continue
        period = period_at(data, pitch)
        if period & 0xFF == 0:
            events.append({"pitch": pitch, "note": "rest", "frames": dur})
        else:
            div = 32.0 if is_tri else 16.0
            f = NTSC_CPU / (div * (period + 1))
            events.append({"pitch": pitch, "note": freq_to_note(f),
                           "period": period, "freq": round(f, 2),
                           "frames": dur})
    return events, p


def main(rom_dir: str, out_dir: str) -> None:
    data = (Path(rom_dir) / "prg_c000-ffff.bin").read_bytes()
    out = Path(out_dir)
    (out / "songs").mkdir(parents=True, exist_ok=True)
    (out / "sfx").mkdir(parents=True, exist_ok=True)

    # --- tables -------------------------------------------------------------
    periods = [period_at(data, i) for i in range(32)]
    durations = [b(data, 0xFF40 + i) for i in range(16)]
    envelope = [b(data, 0xFFD9 + i) for i in range(32)]
    offs_tbl = [b(data, 0xFD22 + i) for i in range(8)]

    # --- songs --------------------------------------------------------------
    # stream reads are bounded by the next song's data blob
    song_ptrs = sorted({0xFD4D, 0xFDEF, 0xFE4A, 0xFEB9, 0xFF71, 0xFFD2,
                        0xFFD8})
    songs = {}
    for mid, name in SONGS.items():
        y = mid.bit_length()          # 1-based bit index
        desc_off = offs_tbl[y - 1]
        base = 0xFD2A + desc_off - 8
        dur_base = b(data, base)
        ptr = read_word(data, base + 1)
        tri_off = b(data, base + 3)
        p1_off = b(data, base + 4)
        bound = min((p for p in song_ptrs if p > ptr), default=0xFFD9)
        streams = {}
        for label, off in (("pulse2", 0), ("pulse1", p1_off),
                           ("triangle", tri_off)):
            ev, end = decode_stream(data, ptr + off, dur_base, durations,
                                    label, bound)
            streams[label] = {"data_addr": f"${ptr + off:04X}",
                              "end_addr": f"${end:04X}", "events": ev}
        songs[name] = {"music_id": f"${mid:02X}", "duration_base": dur_base,
                       "data_ptr": f"${ptr:04X}", "streams": streams}

    # --- write human-readable + JSON ---------------------------------------
    for name, song in songs.items():
        lines = [f"Ice Climber - {name} (music id {song['music_id']})",
                 f"data at {song['data_ptr']}, duration base "
                 f"{song['duration_base']}", ""]
        for ch, st in song["streams"].items():
            total = sum(e["frames"] for e in st["events"])
            lines.append(f"[{ch}]  {st['data_addr']} .. {st['end_addr']}"
                         f"  ({len(st['events'])} notes, {total} frames"
                         f" = {total/60:.2f}s @60fps)")
            row = []
            for e in st["events"]:
                row.append(f"{e['note']:>4}:{e['frames']}")
                if len(row) == 8:
                    lines.append("  " + " ".join(row))
                    row = []
            if row:
                lines.append("  " + " ".join(row))
            lines.append("")
        (out / "songs" / f"{name}.txt").write_text("\n".join(lines))

    meta = {
        "period_table_ff00": periods,
        "period_notes_pulse": [freq_to_note(NTSC_CPU / (16 * (p + 1)))
                               if p & 0xFF else "rest" for p in periods],
        "period_notes_triangle": [freq_to_note(NTSC_CPU / (32 * (p + 1)))
                                  if p & 0xFF else "rest" for p in periods],
        "duration_table_ff40": durations,
        "pulse2_envelope_ffd9": envelope,
        "offset_table_fd22": offs_tbl,
        "songs": songs,
    }
    (out / "nes_music.json").write_text(json.dumps(meta, indent=1))

    # --- raw table dumps ----------------------------------------------------
    (out / "period_table_ff00.bin").write_bytes(
        b"".join(p.to_bytes(2, "little") for p in periods))
    (out / "duration_table_ff40.bin").write_bytes(bytes(durations))
    (out / "pulse2_envelope_ffd9.bin").write_bytes(bytes(envelope))

    for name, song in songs.items():
        n2 = len(song["streams"]["pulse2"]["events"])
        n1 = len(song["streams"]["pulse1"]["events"])
        n3 = len(song["streams"]["triangle"]["events"])
        t = sum(e["frames"] for e in song["streams"]["pulse2"]["events"])
        print(f"{name:18s} p2={n2:3d} p1={n1:3d} tri={n3:3d} notes, "
              f"{t/60:6.2f}s")


if __name__ == "__main__":
    romd = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "extracted/rom")
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "extracted/music")
    main(romd, dst)
