#!/usr/bin/env python3
"""Build, test, run and package the C64 port from repository sources."""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = ROOT / "c64-port"
TOOLS = PORT / "tools"
SOURCE = PORT / "c64/src"
OUTPUT = PORT / "c64/build"
sys.path.insert(0, str(TOOLS))

from tool_paths import resolve_vice  # noqa: E402

VICE_CHECKS = (
    "verify_enemy_pan.py",
    "verify_stone_rules.py",
    "verify_title_stones.py",
    "verify_jump_topi.py", "verify_preview.py", "verify_mux_timing.py",
    "verify_adaptive_mux.py", "verify_scroll.py", "verify_display_pixels.py",
    "verify_cloud_timing.py", "verify_sprite_colours.py", "verify_player_sprites.py",
    "verify_stack_depth.py", "verify_vice.py",
)


def tool(name):
    executable = shutil.which(name)
    if not executable:
        raise FileNotFoundError(f"{name} was not found. Install cc65 and add its bin directory to PATH.")
    return executable


def run(command, cwd=ROOT):
    subprocess.run([str(arg) for arg in command], cwd=cwd, check=True)


def script(name, *args):
    run([sys.executable, "-u", "-X", "utf8", TOOLS / name, *args], cwd=PORT)


def prepare():
    for directory in (OUTPUT, PORT / "build_dbg", PORT / "docs/verification"):
        directory.mkdir(parents=True, exist_ok=True)


def build(demo=False):
    assembler, linker = tool("ca65"), tool("ld65")
    prepare()
    script("build_rom.py", ROOT, PORT / "extracted/rom")
    script("extract_gfx.py", PORT / "extracted/rom/chr_0000-1fff.bin", PORT / "extracted")
    script("extract_music.py", PORT / "extracted/rom", PORT / "extracted/music")
    script("extract_screens.py", ROOT, PORT / "extracted/screens")
    script("convert_c64_gfx.py")
    script("convert_music_c64.py", PORT / "extracted/music", PORT / "converted/music")
    for name in ("pack_title.py", "convert_terrain.py", "make_cloud_art.py"):
        script(name)
    run([sys.executable, "-X", "utf8", SOURCE / "make_assets.py"], cwd=SOURCE)
    for name in ("extract_levels.py", "transplant_objects.py", "transplant_sound.py",
                 "extract_respawn_clouds.py", "level_codes.py"):
        script(name)
    target = "demo" if demo else "game"
    image = OUTPUT / f"iceclimber_{target}.prg"
    run([assembler, "-g", "-t", "none", f"{target}.asm", "-o", OUTPUT / f"{target}.o",
         "-l", OUTPUT / f"{target}.lst"], cwd=SOURCE)
    run([linker, "-C", "c64.cfg", OUTPUT / f"{target}.o", "-o", image,
         "-m", OUTPUT / f"{target}.map", "-Ln", OUTPUT / f"{target}.lbl"], cwd=SOURCE)
    print(f"Built {image.relative_to(ROOT)} ({image.stat().st_size} bytes)", flush=True)
    return image


def test():
    build()
    completed = 0
    for path in sorted(TOOLS.glob("test_*.py")):
        if path.name == "test_native_planning.py":
            from native_planning import library
            if library is None:
                print("SKIP optional native CPU check; run 'python build.py native' to enable it.", flush=True)
                continue
        print(f"Testing {path.name}", flush=True)
        script(path.name)
        completed += 1
    print(f"PASS Python regression suite ({completed} scripts)", flush=True)


def verify(vice):
    vice = resolve_vice(vice)
    build()
    for name in VICE_CHECKS:
        print(f"Verifying {name}", flush=True)
        extra = ["--normal-only"] if name == "verify_vice.py" else []
        script(name, "--vice", vice, *extra)


def native():
    compiler = shutil.which("g++")
    if not compiler:
        raise FileNotFoundError("g++ was not found. It is needed only for the optional native CPU.")
    prepare()
    suffix = ".dll" if sys.platform == "win32" else ".so"
    flags = ["-static-libgcc", "-static-libstdc++"] if sys.platform == "win32" else ["-fPIC"]
    run([compiler, "-O3", "-std=c++17", "-shared", *flags,
         "-o", PORT / f"build_dbg/fast6502_wrap{suffix}", TOOLS / "fast6502.cpp"])
    build()
    script("test_native_planning.py")


def package():
    image = build()
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / "iceclimber-c64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as release:
        release.write(image, "iceclimber_game.prg")
        release.write(ROOT / "PLAYING.md", "README.md")
    print(f"Packaged {archive.relative_to(ROOT)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("build", help="Rebuild all assets and the PRG")
    compile_parser.add_argument("--demo", action="store_true", help="Build the original graphics/audio demo")
    commands.add_parser("test", help="Build and run the Python regression suite")
    for name, help_text in (("verify", "Build and run VICE regressions"), ("run", "Build and launch VICE")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--vice", help="VICE executable or installation directory")
    commands.add_parser("native", help="Build and validate the optional C++ test accelerator")
    commands.add_parser("package", help="Build a PRG release ZIP under dist")
    commands.add_parser("rom", help="Rebuild and verify the NES reference ROM")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.demo)
        elif args.command == "test":
            test()
        elif args.command == "verify":
            verify(args.vice)
        elif args.command == "run":
            vice = resolve_vice(args.vice)
            image = build()
            run([vice, "-default", "-autostartprgmode", "1", "-autostart", image])
        elif args.command == "native":
            native()
        elif args.command == "package":
            package()
        elif args.command == "rom":
            script("build_rom.py", ROOT, PORT / "extracted/rom")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
