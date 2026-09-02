# MechLoadout Renamer

Unofficial tool, not affiliated with Piranha Games / IGP — mech/weapon data extracted from MechWarrior Online's own game files.

A small interactive command-line tool to bulk-rename MechWarrior Online loadout files (`.xml` / `.mwl`). It decodes the mech chassis/variant and the equipped weapons directly from the loadout files, using lookup tables extracted from the game itself, and builds a readable filename such as:

```
PREFIX ANH-1P original_name 5ERLL
```

## Requirements

- Python 3 (standard library only, no extra packages to install)
- Works on Linux and Windows
- Optional, for the graphical folder picker: `tkinter` (bundled with most Python installs) or, on Linux, `zenity`/`kdialog`. If none of these are available the tool falls back to typing the path manually — it still works either way.

## Files

- `mwobuildmanager.py` — the program
- `mechs.csv` — mech id → chassis/variant lookup table
- `weapons.csv` — weapon id → name/tonnage/abbreviation lookup table (edit the `abbreviation` column freely if you don't like a generated abbreviation, it's read fresh on every run)
- `locales/` — one JSON file per language (`fr.json`, `en.json`, `de.json`, `th.json`, `zh.json`). Every UI string lives here, keyed the same way in every file.

### Adding a language

Copy `locales/en.json` to `locales/<code>.json`, translate every value (keep the `{placeholder}` names like `{path}` or `{n}` unchanged), and set `_language_name` to the language's own name (e.g. `"Deutsch"`). It shows up in the language menu automatically — no code changes needed. `yes_words`/`no_words` are the accepted answers for yes/no prompts (typing `y`/`n` always works too, regardless of language, as a safety net).

## How to use

1. Download the files above into the same folder, keeping `locales/` as a subfolder next to `mwobuildmanager.py`.
2. Run it:
   ```
   python3 mwobuildmanager.py
   ```
   (or `python mwobuildmanager.py` on Windows)
3. **First run only**: pick a language (the list is read from `locales/`) and locate the game's `MechLoadouts` folder (path ending in `Saved Games/MechWarrior Online/MechLoadouts`) — the tool tries to auto-detect it first (Steam/Proton on Linux, `%USERPROFILE%` on Windows), otherwise you pick it with a folder browser or type the path.
4. From then on you get a menu:
   - **Rename (quick)** — reuses your last prefix/suffix/keep-original settings, only asks which folder to rename.
   - **Rename (advanced)** — asks every option from scratch:
     1. Which folder contains the loadouts (folder picker)
     2. Add a prefix? (yes → type it)
     3. Add the abbreviated loadout as a suffix? (e.g. `3LL`, `2AC10-3LAC5-2LPPC` — top 3 heaviest weapon groups by quantity×tonnage, groups weighing 2 tons or less are dropped)
     4. Keep the original filename in the middle?
   - **Export my loadouts** — gathers every loadout from the configured game folder into a folder you name, packages it as `.7z` (open source, recommended) or `.rar` (proprietary — falls back to `.zip` automatically if no `7z`/`rar` tool is installed), and saves the archive wherever you pick.
   - **Update mech/weapon database** — re-reads the game's own files to refresh `mechs.csv` and `weapons.csv`: `mechs.csv` is fully regenerated (mechs aren't user-customized), while `weapons.csv` only gets new weapon ids appended — any row you already have (including custom abbreviations) is left untouched.
   - **Reset configuration** — same as Update but overwrites `weapons.csv` completely too (discarding custom abbreviations) and deletes `config.cfg`, dropping you straight back into the first-run setup. Asks for confirmation first.
   - **Settings** — change language, change the game's loadout folder, change the game's install folder (needed for Update/Reset — the folder containing `Game/GameData.pak`, auto-detected the first time it's needed), toggle the automatic backup (see below).
   - **Exit**
5. Either mode shows a numbered preview of every rename before touching anything. Confirm with `Enter`/`all`, skip everything with `none`, or pick a subset with `all except 1,2,5` / `only 1,3,4`.
6. If backup is enabled (on by default, toggle it in Settings), the whole source folder is copied to a timestamped sibling folder (`<folder>_backup_YYYYMMDD_HHMMSS`) right before renaming.
7. After renaming, if a game folder is configured, you're asked whether to also copy the renamed files there (existing files with the same name are overwritten).

## License

MIT — see [LICENSE](LICENSE).
