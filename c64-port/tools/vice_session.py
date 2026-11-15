"""Small native VICE fixture shared by full-game and rendering checks."""
import re
import socket
import subprocess
import time
from pathlib import Path

from verify_vice import Monitor
from symbols import read_symbols
from tool_paths import resolve_vice

BASE = Path(__file__).resolve().parents[1]


class ViceSession:
    def __init__(self, name='full_port', vice=None, fixed_ticks=True):
        self.name, self.vice, self.fixed_ticks = name, resolve_vice(vice), fixed_ticks
        self.labels = read_symbols()

    def __enter__(self):
        try:
            return self._start()
        except BaseException:
            self.close()
            raise

    def _start(self):
        with socket.socket() as free:
            free.bind(('127.0.0.1', 0))
            port = free.getsockname()[1]
        dbg = BASE/'build_dbg'
        dbg.mkdir(parents=True, exist_ok=True)
        (BASE/'docs/verification').mkdir(parents=True, exist_ok=True)
        init = dbg/f'{self.name}.mon'
        prg = BASE/'c64/build/iceclimber_game.prg'
        init.write_text(f'load "{prg.as_posix()}" 0\nbreak {self.labels["main_loop"]:04x}\ng 080e\n')
        startup = None
        if hasattr(subprocess, 'STARTUPINFO'):
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
        self.console = (dbg/f'{self.name}_console.log').open('wb')
        self.proc = subprocess.Popen([self.vice, '-default', '-warp', '-binarymonitor',
            '-binarymonitoraddress', f'ip4://127.0.0.1:{port}', '-initbreak', 'ready',
            '-moncommands', str(init), '-logfile', str(dbg/f'{self.name}.log'),
            '-sounddev', 'wav', '-soundarg', str(dbg/f'{self.name}.wav')],
            startupinfo=startup, stdout=self.console, stderr=subprocess.STDOUT)
        self.sock = None
        for _ in range(100):
            try:
                self.sock = socket.create_connection(('127.0.0.1', port), timeout=1)
                break
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError('VICE exited; see its console log')
                time.sleep(.1)
        if self.sock is None:
            raise RuntimeError('VICE monitor did not start')
        self.sock.settimeout(20)
        self.m = Monitor(self.sock)
        self.m.frame()
        assert self.m.read(self.labels['read_joy'], 3) == b'\xAD\x00\xDC'
        self.m.write(self.labels['read_joy'], b'\xA5\x4F\xEA')
        assert self.m.read(self.labels['read_joy2'], 3) == b'\xAD\x01\xDC'
        self.m.write(self.labels['read_joy2'], b'\xA5\x4E\xEA')
        self.m.write(0x4E, b'\xFF')
        # Route replays need the planned tick timing (see test_game.Machine).
        self.m.write(self.labels['fixed_ticks'], b'\x01' if self.fixed_ticks else b'\x00')
        return self

    def frame(self, joy=255, joy2=255):
        self.m.write(0x4E, bytes([joy2]))
        self.m.frame(joy)

    def title_code(self, mountain):
        """Drive the release parser through an eight-row CIA input fixture.

        The one keyboard read uses unused title terrain RAM as its matrix;
        restore the instruction before any protected-memory snapshot/play.
        """
        from level_codes import CODES, KEYS
        assert self.read('state') == b'\0'
        address = self.labels['title_key_columns']
        original = self.read(address, 3)
        assert original == b'\xAD\x01\xDC'
        try:
            self.write(address, b'\xBD\x00\x04')
            for char in CODES[mountain-1]:
                key = KEYS[char]
                matrix = bytearray([255])*8
                matrix[key//8] &= ~(1 << (key % 8))
                self.write(0x400, matrix)
                self.frame()
                self.write(0x400, bytes([255])*8)
                self.frame()
            assert self.read('selected_mountain')[0] == mountain
        finally:
            self.write(address, original)

    def finish_preview(self):
        """Run the actual video/controller sequence, then one normal idle tick."""
        frames = 0
        while self.read('state') == bytes([4]):
            self.frame()
            frames += 1
            assert frames < 600, 'Opening flyover did not finish'
        assert self.read('state') == bytes([1])
        self.frame()
        return frames

    def sync_player_zero(self):
        """Finish a controlled RAM fixture as normal gameplay does: P0 is
        both stored in its context and loaded in the live player fields."""
        names = ('lives', 'score_lo', 'score_hi', 'pxlo', 'pxhi', 'py',
                 'prevpy', 'curfloor', 'onground', 'vy', 'face', 'maxfloor',
                 'hammer_t', 'attack_t', 'air_init', 'fall_int', 'fall_frac',
                 'y_frac', 'rise_int', 'rise_frac', 'move_dir', 'walk_time',
                 'walk_frac', 'air_xfrac', 'skid_t', 'invul_t', 'pleft',
                 'pright', 'flow_frac', 'bonus_plat', None, 'score_top')
        values = self.read('PLAYER_STATES', 32)
        for name, value in zip(names, values):
            if name:                # offset 30 is unused
                self.write(name, value)
        self.write('player_index', 0)

    def read(self, name, length=1):
        return self.m.read(self.labels[name] if isinstance(name, str) else name, length)

    def write(self, name, value):
        self.m.write(self.labels[name] if isinstance(name, str) else name,
                     bytes([value]) if isinstance(value, int) else bytes(value))

    def left_out(self):
        """(sprites the multiplexer left out, Popo turned into two layers)
        for the frame just scheduled. sched_drop marks Popo's white layer
        (logical 0) with Y and colour $FF when it removes it instead."""
        two = self.read('LOG_Y')[0] == self.read('LOG_COL')[0] == 0xFF
        return self.read('logical_count')[0] - two - self.read('scheduled_count')[0], two

    def capture(self, path):
        return self.m.display(path)

    def __exit__(self, *exc):
        try:
            self.m.command(0xBB)
            self.proc.wait(timeout=10)
        finally:
            self.close()

    def close(self):
        if getattr(self, 'sock', None):
            self.sock.close()
        proc = getattr(self, 'proc', None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        console = getattr(self, 'console', None)
        if console is not None:
            console.close()
