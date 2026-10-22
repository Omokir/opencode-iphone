"""Render geometric pixel mark without image-library dependencies."""
import pathlib
import struct
import sys
import zlib

def png(size):
    grid = [
        '................',
        '................',
        '..##........##..',
        '..#..........#..',
        '..#..##.###..#..',
        '..#.#..##....#..',
        '..#.#..##....#..',
        '..#.#..##....#..',
        '..#..##.###..#..',
        '..#..........#..',
        '..##........##..',
        '................',
        '.....######.....',
        '................',
        '................',
        '................',
    ]
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            on = grid[min(15, y * 16 // size)][min(15, x * 16 // size)] == '#'
            raw.extend((237, 243, 255) if on else (32, 81, 194))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

if __name__ == '__main__':
    folder = pathlib.Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    for name, size in [('AppIcon60x60@2x.png', 120), ('AppIcon60x60@3x.png', 180), ('Artwork.png', 1024)]:
        (folder / name).write_bytes(png(size))
