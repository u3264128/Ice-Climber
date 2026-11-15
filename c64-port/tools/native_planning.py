"""Optional zero-copy native CPU for searches; release replays stay independent."""
import ctypes
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
FIELDS = ('pc', 'a', 'x', 'y', 'sp', 'c', 'z', 'i', 'd', 'v', 'n',
          'joystick', 'joystick2', 'raster', 'bad')


class State(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (*FIELDS, 'wrap_pc')]


try:
    suffix = '.dll' if sys.platform == 'win32' else '.so'
    library = ctypes.CDLL(str(BASE/f'build_dbg/fast6502_wrap{suffix}'))
    library.cpu_run.argtypes = [ctypes.POINTER(State), ctypes.POINTER(ctypes.c_ubyte),
                               ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
    library.cpu_run.restype = ctypes.c_int
except OSError:
    library = None


def run_to(machine, target, skip=()):
    state = State(*(getattr(machine, name, 0) for name in FIELDS), getattr(machine, 'wait_wrap_pc', 0))
    memory = (ctypes.c_ubyte*65536).from_buffer(machine.ram)
    if not hasattr(machine, 'under_io'):
        machine.under_io = bytearray(0x1000)    # a bare CPU: RAM under I/O
    under = (ctypes.c_ubyte*4096).from_buffer(machine.under_io)
    entries = (ctypes.c_uint32*len(skip))(*skip)
    error = library.cpu_run(ctypes.byref(state), memory, under, target, 500000, entries, len(skip))
    for name in FIELDS[:-1]:
        setattr(machine, name, getattr(state, name))
    if error == -1:
        raise AssertionError(f'Native planner did not reach ${target:04X}, PC=${state.pc:04X}')
    if error:
        raise RuntimeError(f'Native planner opcode ${error-1:02X} at ${state.bad:04X}')
