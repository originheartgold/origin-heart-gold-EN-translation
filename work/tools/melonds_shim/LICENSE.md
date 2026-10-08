# Licence of this folder

Everything in this folder (`melonds_shim.cpp`, `build.py`, this note) is written for this project and is licensed
under the **GNU General Public License, version 3 or any later version** (GPL-3.0-or-later,
<https://www.gnu.org/licenses/gpl-3.0.html>), and so is the library built from it (`libmelonds_shim.dylib`): the shim
is linked with the melonDS core, which is GPLv3. The rest of the repository keeps its own licences (see README.md).

- melonDS: <https://github.com/melonDS-emu/melonDS>, tag `1.1`, commit `b86390e4428bf38ce4c1ce0e9ca446d6d25955e8`.
  Copyright the melonDS team, GPLv3. Its source is not copied into this repository; `build.py` builds it from a
  separate checkout of that tag.
- The built library is not committed and not released with the translation patch. It is a local test tool.
- melonDS's built-in FreeBIOS is used; no BIOS or firmware dump is needed or stored.

`work/tools/melonds.py` (outside this folder, Apache 2.0 like the other tools) only loads the library at run time
through ctypes; without it the tests skip.
