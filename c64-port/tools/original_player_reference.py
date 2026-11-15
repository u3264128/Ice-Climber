"""Execute original controller and normal-player handlers, including OAM.

The level comes from the original generator. C247/C272's initial camera,
floor and body position are 4, 1 and 192; C64 logical Y is source Y+24.
"""
from extract_levels import generate
from test_original_physics import Reference, PRG


class PlayerReference(Reference):
    def __init__(self, mountain=0):
        super().__init__()
        self.pad = self.serial = 0
        self.hooks = {0x4016: self.controller, 0x4017: lambda *args: 0}
        raw, _, _, _ = generate(PRG, mountain)
        self.ram[0x400:0x4D8] = raw[:216]
        self.ram[0x500:0x5D8] = raw[216:]
        for address, value in ((0x55, 1), (0x59, mountain), (0x90, 4),
                               (0x5A, 1), (0x6A, 1), (0x62, 1), (0x64, 48), (0x66, 192)):
            self.ram[address] = value

    def controller(self, memory, address, value):
        if value is not None:
            if value & 1:
                self.serial = 0
            return
        result = (self.pad >> (7-min(self.serial, 7))) & 1
        self.serial += 1
        return result

    def tick(self, pad):
        self.pad = pad
        self.call(0xCAED)  # serial controller and actual press/held decoding
        self.call(0xCB9D)  # timers precede the player handler in the original
        self.ram[0x70] = self.ram[0x15]
        self.call(0xCD13)
        self.call(0xDA99)
        self.call(0xD1E5)
