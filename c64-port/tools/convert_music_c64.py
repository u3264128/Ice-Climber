#!/usr/bin/env python3
"""Convert the decoded NES music into a binary for the C64 SID player.

The C64 player (c64/src/player.asm) consumes:

    +0        number of songs
    +1        per song: 3 x 16-bit stream offsets (p2, p1, tri, relative to
              the music blob) + 1 loop flag
    ...       pulse SID frequency table: 32 x 16-bit little-endian
              (0x0000 = rest)
    ...       triangle SID frequency table: 32 x 16-bit
    ...       event streams: (pitch_index, duration_frames) byte pairs,
              pitch 0 = end of stream

Frequencies: NES pulse f = 1789773/(16*(period+1)); SID uses a phase
             increment F = round(f * 2**24 / 985248), NOT an NES timer.
             See MOS 6581 datasheet, frequency register description.
Durations are scaled from NTSC 60 Hz frames to PAL 50 Hz (x 5/6).
"""
import json
import sys
from pathlib import Path

NTSC_CPU = 1789773.0
PAL_CPU = 985248.0

# songs to embed: name -> loops on stream end (like the NES engine)
EMBED = [("logo_start", 1), ("background", 1), ("mountain_preview", 0),
         ("mountain_complete", 0)]


def sid_value(freq: float) -> int:
    if freq <= 0:
        return 0
    v = round(freq * (1 << 24) / PAL_CPU)
    return max(0, min(0xFFFF, v))


def main(extracted_dir: str, out_dir: str) -> None:
    src = Path(extracted_dir) / "nes_music.json"
    meta = json.loads(src.read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    periods = meta["period_table_ff00"]

    def nes_freq(idx: int, triangle: bool) -> float:
        p = periods[idx]
        if p & 0xFF == 0:
            return 0.0
        div = 32.0 if triangle else 16.0
        return NTSC_CPU / (div * (p + 1))

    # --- frequency tables ---------------------------------------------------
    pulse_tbl = b"".join(sid_value(nes_freq(i, False)).to_bytes(2, "little")
                         for i in range(32))
    tri_tbl = b"".join(sid_value(nes_freq(i, True)).to_bytes(2, "little")
                       for i in range(32))

    # --- streams -------------------------------------------------------------
    songs_meta = meta["songs"]
    header_size = 1 + len(EMBED) * 7
    streams_blob = bytearray()
    offsets = []          # per song: (p2, p1, tri, loop)
    for name, loop in EMBED:
        song = songs_meta[name]
        offs = []
        for ch in ("pulse2", "pulse1", "triangle"):
            data = bytearray()
            ntsc_frames = pal_frames = 0
            for ev in song["streams"][ch]["events"]:
                if ev.get("marker"):    # NES duty/volume markers: no C64 use
                    continue
                ntsc_frames += ev["frames"]
                target = round(ntsc_frames * 50 / 60)
                dur = min(255, max(1, target - pal_frames))
                pal_frames += dur
                # pitch 0 = end-of-stream marker, 32 = rest (holds duration)
                pitch = 32 if ev["note"] == "rest" else ev["pitch"]
                data += bytes([pitch, dur])
            data += bytes([0, 1])       # end marker
            offs.append(header_size + 128 + len(streams_blob))
            streams_blob += data
        offsets.append((offs[0], offs[1], offs[2], loop))

    blob = bytearray()
    blob.append(len(EMBED))
    for p2, p1, tri, loop in offsets:
        blob += p2.to_bytes(2, "little")
        blob += p1.to_bytes(2, "little")
        blob += tri.to_bytes(2, "little")
        blob.append(loop)
    assert len(blob) == header_size
    blob += pulse_tbl + tri_tbl
    blob += streams_blob
    (out / "c64_music.bin").write_bytes(blob)

    info = {"songs": [{"name": n, "loop": lp} for n, lp in EMBED],
            "blob_size": len(blob),
            "format": "see header of convert_music_c64.py",
            "first_notes": {n: [e["note"] for e in
                                songs_meta[n]["streams"]["pulse1"]["events"][:8]]
                            for n, _ in EMBED}}
    (out / "c64_music.json").write_text(json.dumps(info, indent=1))
    print(f"music blob: {len(blob)} bytes, {len(EMBED)} songs")
    for n, _ in EMBED:
        print(f"  {n}: pulse1 starts " +
              " ".join(info["first_notes"][n]))


if __name__ == "__main__":
    ext = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "extracted/music")
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "converted/music")
    main(ext, dst)
