"""Original E05E PPU writes for the five-tile hanging stone columns."""
from test_original_physics import Reference, PRG


def stone_cells(mountain):
    class Columns(Reference):
        def __init__(self):
            super().__init__()
            self.cells = {}
            self.ram[0x59] = mountain-1

        def step(self):
            if self.pc != 0xC14E:
                return super().step()
            data, offset = self.ram[0x301:0x380], 0
            bases = [(PRG[0x178B+i] << 8) | PRG[0x1794+i] for i in range(9)]
            while data[offset]:
                address = (data[offset] << 8) | data[offset+1]
                assert data[offset+2] == 0xC5 and data[offset+3] == 0xEB
                column = address & 31
                floor = bases.index(address-column)
                for row in range(floor*6+2, floor*6-3, -1):
                    self.cells[row, column] = 0xEB
                offset += 4
            self.ram[0x300] = self.ram[0x301] = 0
            self.pc = (self.pop() | self.pop() << 8)+1

    source = Columns()
    source.call(0xE05E)
    return source.cells
