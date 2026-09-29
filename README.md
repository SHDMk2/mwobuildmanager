# MechLoadout Renamer

Unofficial tool, not affiliated with Piranha Games / IGP — mech/weapon data extracted from MechWarrior Online's own game files.

An interactive tool to manage MechWarrior Online saved builds (`.xml` / `.mwl` loadout files) without opening the game. It decodes each build straight from its files — mech variant, weapons, equipment, engine, armor — using tables extracted from the game itself, and can rename them in bulk, import them from build codes, and export them as an archive or as a spreadsheet with computed stats.

```
PREFIX  ANH-1P  original_name  5ERLL-2LGAUSS-JJ  XL300
```

## Features

- **Bulk rename** with a custom prefix, the mech variant, the original name, the main weapons (e.g. `5ERLL`), special equipment (`JJ`, `ECM`, `BAP`, `MASC`…) and the engine (`XL300`)
- **Import from build codes** — paste codes or load a `.txt`/`.csv` file to create saved builds without launching the game
- **Export** your builds as a `.7z`/`.rar`/`.zip` archive, or as a `.csv` list with stats: tonnage, class, speed, optimal range, leg/kill/total HP, equipment, owner, date…
- **Owner and date** stored in each build and kept across renames, imports and exports
- **Update** from the game files after a patch (new mechs, weapons, quirks…), without losing your custom abbreviations
- **Languages:** English, French, German, Thai, Chinese

**Compatibility:** Linux (tested), Windows, macOS (launcher provided, untested).

## Requirements

- **Python 3** (standard library only, nothing else to install)
  - Windows / macOS: download it from [python.org](https://www.python.org/downloads/). On Windows, tick *"Add python.exe to PATH"* during the install.
  - Linux: the `python3` package of your distribution (usually already installed).
- Optional, for the graphical folder picker: `tkinter` (bundled with most Python installs) or, on Linux, `zenity`/`kdialog`. Without them the tool asks you to type the path instead — it works either way.

## Installation

Download the project (green **Code** button → **Download ZIP**, or `git clone`) and keep every file together, with `locales/` as a subfolder next to `mwobuildmanager.py`.

## Launching

### Option 1 — double-click a launcher (easiest)

| System | File to double-click |
|---|---|
| Windows | `launch_windows.bat` |
| Linux | `launch_linux.sh` |
| macOS | `launch_mac.command` |

- The launcher opens a terminal window and starts the tool. If the tool stops on an error, the window stays open so you can read it.
- **Linux:** if your file manager asks, choose *Execute* / *Run*. If double-clicking does nothing, the file may have lost its "executable" permission when unzipping: right-click → *Properties* → *Permissions* → tick *Is executable* (or run `chmod +x launch_linux.sh`).
- **Windows:** SmartScreen may warn you the first time, since the file is not signed. You can open `launch_windows.bat` in Notepad to check it first — it only runs `py mwobuildmanager.py`.

### Option 2 — command line

If you'd rather not run a `.bat`/`.sh` file, open a terminal in the project folder and type:

```
python3 mwobuildmanager.py
```

On Windows, use `py mwobuildmanager.py` (or `python mwobuildmanager.py`).

## First run

1. Pick a language (the list is read from `locales/`).
2. Confirm or pick the game's `MechLoadouts` folder (path ending in `Saved Games/MechWarrior Online/MechLoadouts`). The tool tries to find it automatically (Steam/Proton on Linux, your user folder on Windows).

## Menu

### 1. Rename (quick) / 2. Rename (advanced)

*Quick* reuses your last settings and only asks for the folder. *Advanced* asks every option:

1. The folder containing the loadouts
2. Add a prefix?
3. Add the main weapons? Top 3 heaviest weapon groups by quantity × tonnage, groups of 2 tons or less are dropped (e.g. `3LL`, `2AC10-3LAC5-2LPPC`)
4. Add special equipment after the weapons? (`JJ`, `MASC`, `SC`, `ECM`, `BAP`, `TAG`, `NARC`, `AMS`)
5. Engine in the name: type + rating (`XL300`), type only (`XL`) or none. Types: `STD`, `XL`, `LFE` (light engine), `CXL` (Clan XL)
6. Keep the original filename in the middle?

Items built into the mech are counted too: OmniMech engines, jump jets fixed in OmniPods, fixed MASC, built-in weapons…

A numbered preview is shown before anything is touched. Confirm with `Enter`/`all`, cancel with `none`, or pick a subset with `all except 1,2,5` / `only 1,3,4`.

If backup is enabled (on by default, see Settings), the whole folder is copied to `<folder>_backup_YYYYMMDD_HHMMSS` right before renaming. Afterwards, you can copy the renamed builds directly into the game folder.

### 3. Import from build code

1. Choose where the codes come from:
   - type or paste them — separated by `, ` or `; `, or one per line; blank lines are ignored; finish with a line containing `.` or `end`
   - a `.txt` file
   - a `.csv` file — the build code column is detected automatically, and `owner`/`date` columns are reused if present
2. Answer the same naming questions as for a rename.
3. Check the preview and select which builds to import.
4. Choose the destination: the game folder directly, or any other folder.

Invalid codes are listed and skipped, and a code pasted twice is imported once.

### 4. Export my loadouts

Exports every build from the game folder, either as:

- **an archive** — `.7z` (recommended) or `.rar`, or `.zip` automatically if neither tool is installed;
- **a `.csv` list**, one row per build:

| Column | Content |
|---|---|
| `name`, `buildcode`, `mechvariant` | build name, share code, variant (e.g. `ANH-1P`) |
| `tonnage`, `class`, `tech` | tonnage, Light/Medium/Heavy/Assault, IS/CLAN |
| `owner`, `date` | owner and date stored in the build (see *Build owner and date*) |
| `jumpjets` | number of jump jets |
| `engine_type`, `engine_rating` | e.g. `XL`, `300` |
| `max_speed` | engine rating ÷ tonnage × 16.2 × (1 + speed quirks), in km/h |
| `equipment` | special equipment except jump jets, e.g. `ECM/TAG` |
| `optimal_range` | optimal range of the heaviest weapon group × (1 + range quirks) × Targeting Computer bonus |
| `leg_hp` | both legs |
| `kill_hp` | weakest side torso with an Inner Sphere XL engine, otherwise centre torso |
| `total_hp` | all components |

**HP** = front armor placed on the build + armor quirks + (structure + structure quirks) × structure modifier. The modifier is 0.5 by default (Settings) plus half of the mech's *crit chance receiving* quirk, so a mech with a −100 % quirk has its structure count fully. Mech, OmniPod and set bonus quirks are all included.

### 5. Update mech/weapon database

Re-reads the game files after a patch. Point it once to the game's install folder (the one containing `Game/GameData.pak`); it is auto-detected when possible.

- Fully regenerated: `mechs.csv`, `omnipods.csv`, `weapon_ranges.csv`, `targeting_computers.csv`.
- New entries only: `weapons.csv`, `equipment.csv`, `engines.csv` — rows you already have, including your custom abbreviations, are never changed.

### 6. Reset configuration

Same as Update, but also rewrites `weapons.csv`, `equipment.csv` and `engines.csv` with the default abbreviations, then deletes `config.cfg` and restarts the first-run setup. Asks for confirmation first.

### 7. Settings

Language, game loadouts folder, game install folder, automatic backup on/off, structure modifier used for the HP stats.

## Build owner and date

Every build the tool touches (rename, import, CSV export) gets three comment lines in its `.xml` file. The game ignores them, and the `.mwl` share code is left untouched:

```xml
<Loadout MechID="570">
 <!-- owner: SHD2 -->
 <!-- date: 2026-09-29 -->
 <!-- Generated by Mwobuildmanager (https://github.com/SHDMk2/mwobuildmanager) -->
```

- Existing values are never replaced.
- A missing value is taken from the imported `.csv` if there is one, otherwise from your most recently used game profile and today's date (`YYYY-MM-DD`).
- Saving a build in game may erase these comments, so the tool also keeps a local copy in `build_registry.csv` and restores the original owner and date from it.

## Files

| File | Content | Editable? |
|---|---|---|
| `mwobuildmanager.py` | the program | — |
| `launch_windows.bat`, `launch_linux.sh`, `launch_mac.command` | double-click launchers | — |
| `weapons.csv` | weapon id → name, tonnage, abbreviation | yes — change any `abbreviation` |
| `equipment.csv` | equipment id → abbreviation | yes — change or empty an abbreviation to hide it; row order sets the display order |
| `engines.csv` | engine id → type, rating | yes — the `type` column |
| `mechs.csv` | mechs: variant, tech, tonnage, structure, quirks, fixed items | no — regenerated by Update |
| `omnipods.csv` | OmniPods and set bonuses | no — regenerated by Update |
| `weapon_ranges.csv`, `targeting_computers.csv` | weapon ranges, Targeting Computer bonuses | no — regenerated by Update |
| `locales/` | one JSON file per language | yes |
| `config.cfg` | your settings (created on first run) | via Settings |
| `build_registry.csv` | backup of build owners and dates (created automatically) | — |

### Adding a language

Copy `locales/en.json` to `locales/<code>.json`, translate every value (keep the `{placeholder}` names like `{path}` or `{n}` unchanged), and set `_language_name` to the language's own name (e.g. `"Deutsch"`). It appears in the language menu automatically — no code change needed. `yes_words`/`no_words` are the accepted answers for yes/no prompts (`y`/`n` always work too, whatever the language).

## License

MIT — see [LICENSE](LICENSE).
