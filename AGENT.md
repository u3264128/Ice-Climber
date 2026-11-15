# Agent guide

- Use concise English in code, comments, documentation, and messages.
- Read `README.md` and `c64-port/README.md`. The NES reference sources are
  at the root; C64 assembly is in `c64-port/c64/src`; tools and regression
  fixtures are in `c64-port/tools`.
- Use Python 3.10+ and cc65 (`ca65`, `ld65`) on `PATH`. All paths in scripts
  must resolve from the repository, independent of the working directory.
- Build: `python build.py build`. Run: `python build.py run`.
- Test changes: `python build.py test`. Check video, timing, and audio with
  `python build.py verify`; VICE is the authority for those checks.
- Discover `x64sc` through `VICE_ROOT` or `PATH`. If VICE cannot be found,
  ask the user for its installation path, then have the agent harness set
  `VICE_ROOT` in the command environment. Never commit the path or local
  machine settings. Individual emulator tools also accept `--vice`.
- Preserve the NES rules and protected memory regions. Keep assembly
  changes small; use the existing tests and add focused regressions for
  behaviour changes. Keep reference fixtures independent of new output.
- Generated assets, binaries, reports, caches, and local settings stay
  ignored. Rebuild them with `build.py`; do not commit them.
- Before distribution, run both test commands and `python build.py package`.
  The release ZIP is under `dist`; source changes belong in Git.
