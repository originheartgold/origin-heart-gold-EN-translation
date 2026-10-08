# Licence of this folder

`melonds_shim.cpp` and `build.py` are written for this project. The shim is linked with the melonDS core, which is
licensed under the GNU General Public License version 3 (or later), so the shim and the library built from it
(`libmelonds_shim.dylib`) are distributed under the **GNU General Public License, version 3 or any later version**
(<https://www.gnu.org/licenses/gpl-3.0.html>).

- melonDS: <https://github.com/melonDS-emu/melonDS>, tag `1.1`, commit `b86390e4428bf38ce4c1ce0e9ca446d6d25955e8`.
  Copyright the melonDS team, GPLv3. Its source is not copied into this repository; `build.py` builds it from a
  separate checkout of that tag.
- The built library is not committed and not released with the translation patch. It is a local test tool.
- melonDS's built-in FreeBIOS is used; no BIOS or firmware dump is needed or stored.

The rest of the repository is not affected: `work/tools/melonds.py` only loads the library at run time
through ctypes and runs without it (the tests skip).
