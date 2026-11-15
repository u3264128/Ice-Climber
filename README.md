# Ice Climber for Commodore 64

A port of NES Ice Climber to the Commodore 64, developed with Codex and
Claude Code. It includes all 32 mountains, one or two players, bonus stages,
and SID audio. The target is a PAL C64.

## Build and run

Install Python 3.10 or newer and cc65. Put `python`, `ca65`, and `ld65` on
`PATH`. The build uses the Python standard library and the source assets in
this repository; it does not download tools or require another checkout.

Run from the repository root:

```text
python build.py build
python build.py test
python build.py run
```

The program is written to `c64-port/c64/build/iceclimber_game.prg`.
See [PLAYING.md](PLAYING.md) for controls.

Running and emulator checks require VICE with `x64sc`. If it is not on
`PATH`, set `VICE_ROOT` to the VICE installation directory in your shell.
The launcher checks both that directory and its `bin` subdirectory. A
single command can also use `--vice` with an executable or directory.
Keep local paths in the environment, outside version control.
Use `$env:VICE_ROOT = '<directory>'` in PowerShell or
`export VICE_ROOT='<directory>'` in a POSIX shell.

```text
python build.py verify
python build.py package
```

`verify` runs the VICE regression checks. `package` builds
`dist/iceclimber-c64.zip` with the PRG and controls. Run both test
commands before distributing a changed build. Generated files are ignored.

## Hidden mountain codes

On the title screen, type a four-character code to select a starting
mountain for verification. Complete the code within five seconds of the
first key. Typing produces no visible text or sound. An invalid code or an
expired partial code resets the selection to mountain 1.

After entering the code, press fire, Space, or Right Shift to start. The
code works with either one or two players; use up/down to select the player
count. For example, enter `jd3q`, then press fire to start mountain 31.

| Mountain | Code | Mountain | Code |
| --- | --- | --- | --- |
| 1 | `r7cq` | 17 | `h2qb` |
| 2 | `b2nf` | 18 | `t9fn` |
| 3 | `h9vz` | 19 | `c4zx` |
| 4 | `t4am` | 20 | `v7ag` |
| 5 | `c6qe` | 21 | `n3re` |
| 6 | `v3rb` | 22 | `q8hm` |
| 7 | `n8ht` | 23 | `a5vc` |
| 8 | `q5xc` | 24 | `e6bt` |
| 9 | `a9fv` | 25 | `m2zf` |
| 10 | `e2zg` | 26 | `f9xq` |
| 11 | `m7br` | 27 | `x4nr` |
| 12 | `f4qn` | 28 | `g7ae` |
| 13 | `x6ca` | 29 | `z3ch` |
| 14 | `g3vh` | 30 | `b8vm` |
| 15 | `z8em` | 31 | `jd3q` |
| 16 | `d5rt` | 32 | `r6gt` |

The code definitions are in
[`c64-port/tools/level_codes.py`](c64-port/tools/level_codes.py).
RUN/STOP returns to the title screen from gameplay or the opening flyover.

## Development

Read [AGENT.md](AGENT.md) for the workflow and
[c64-port/README.md](c64-port/README.md) for the source layout.
The NES disassembly and CHR inputs are at the repository root.
