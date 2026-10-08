"""Create an isolated, authored renderer-control fixture; never edit bank sources."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import msgtool as m

TEXT = ('First page.{SCROLL}Second line.{NEWLINE}Bottom line.{CLEAR}'
        'Scrolled line.{SCROLL}Before pause.{VAR:0201:60}After pause.{SCROLL}'
        '{VAR:FF01:200}BIG{VAR:FF01:100} small.{SCROLL}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build = Path(__file__).resolve().parents[2] / 'build'
    if args.source.resolve() == args.output.resolve() or not args.output.resolve().is_relative_to(build):
        parser.error('Use a separate output under this worktree work/build')
    rom = m.load_rom(args.source)
    narc = m.Narc.parse(m.get_file(rom, 'a/0/2/7'))
    cm = m.Charmap.load(['work/tools/charmap_en.tsv', 'work/tools/charmaps/charmap_zh_xzonn_gen4.tsv'])
    seed, strings, trailer = m.decrypt_bank(narc.files[718])
    strings[160] = m.encode_text(TEXT, cm)
    narc.files[718] = m.encrypt_bank(seed, strings, trailer)
    m.set_file(rom, 'a/0/2/7', narc.build())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rom.saveToFile(str(args.output))

if __name__ == '__main__':
    main()
