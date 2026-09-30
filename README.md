# MechLoadout Renamer

Unofficial tool, not affiliated with Piranha Games / IGP — mech/weapon data extracted from MechWarrior Online's own game files.

A tool to manage your MechWarrior Online saved builds without opening the game: rename them in bulk, create them from build codes, and export them with their stats. Everything is read from the game's own files.

```
PREFIX  ANH-1P  original_name  5ERLL-2LGAUSS-JJ  SHS  XL300
```
*prefix · variant · original name · weapons-equipment · heat sinks · engine — each block is optional.*

## Features

- **Bulk rename** your builds with a readable name
- **Import from build codes** — paste them or load a `.txt`/`.csv` file
- **Export** as an archive, or as a `.csv` with stats: speed, range, HP, heat, role, Standard/Hero/Legend…
- **Role detection**: LRM Boat, Sniper, Brawler, Laser Vomit…
- **Update** from the game files after a patch
- **Languages:** English, French, German, Thai, Chinese

**Compatibility:** Linux (tested), Windows, macOS (launcher provided, untested).

## Install

1. Install **Python 3**: from [python.org](https://www.python.org/downloads/) on Windows/macOS — on Windows, tick *"Add python.exe to PATH"* during the install. On Linux it is usually already there.
2. Download the project (green **Code** button → **Download ZIP**) and unzip it. Keep the folder as it is.

## Launch

| System | Double-click |
|---|---|
| Windows | `launch_windows.bat` |
| Linux | `launch_linux.sh` |
| macOS | `launch_mac.command` |

- **Linux:** if double-clicking does nothing, right-click the file → *Properties* → *Permissions* → tick *Is executable*.
- **Windows:** SmartScreen may warn you the first time, since the file is not signed. You can open it in Notepad to check it first.

Or from a terminal, in the project folder: `python3 mwobuildmanager.py` (`py mwobuildmanager.py` on Windows).

## First run

Pick a language, then confirm the game's `MechLoadouts` folder (`Saved Games/MechWarrior Online/MechLoadouts`). It is found automatically in most cases.

## Using the tool

### Rename

*Rename (quick)* reuses your last answers. *Rename (advanced)* asks for:

1. the folder containing the builds
2. a prefix
3. the main weapons — the 3 heaviest groups (quantity × tonnage), groups of 2 tons or less are left out
4. special equipment: `JJ`, `MASC`, `SC`, `ECM`, `BAP`, `TAG`, `NARC`, `AMS`
5. the engine: type + rating (`XL300`), type only (`XL`) or none
6. whether to keep the original name

Builds on single heat sinks get `SHS` in their name; doubles, being the norm, get nothing.

Every change is previewed first. Confirm with `Enter`, cancel with `none`, or pick some with `all except 1,2,5` / `only 1,3,4`. The folder is backed up before renaming (can be turned off in Settings), and you can then copy the renamed builds straight into the game folder.

### Import from build codes

1. Paste the codes (separated by `, ` or `; `, or one per line; finish with a line containing `.`), or load a `.txt` or `.csv` file.
2. Answer the same naming questions as for a rename, check the preview.
3. Choose the destination: the game folder or another folder.

Invalid codes and builds already in the folder are skipped. The folder is then tidied up: builds missing their `.mwl` file get one, and duplicate builds are removed after you confirm (the oldest copy is kept, the folder is backed up first).

### Export

Exports every build of the game folder, either as a `.7z`/`.rar`/`.zip` archive, or as a `.csv` list. In the `.csv`, a build present several times appears once. An export never deletes a file.

<details>
<summary>CSV columns</summary>

| Column | Content |
|---|---|
| `name`, `mechvariant`, `buildcode` | build name, variant (e.g. `ANH-1P`), share code |
| `mechtype` | chassis as named in game, e.g. `Commando IIC` |
| `variant_type` | `Standard`, `Hero` or `Legend` — Legends include their twin without the (L), often banned in competitions |
| `class`, `tonnage`, `tech` | Light/Medium/Heavy/Assault, tonnage, IS/CLAN |
| `cockpit_height` | cockpit height in meters |
| `engine_type`, `engine_rating` | e.g. `XL`, `300` |
| `max_speed` | km/h |
| `weapons` | every weapon group, heaviest first, e.g. `5ERLL/6ERML` |
| `equipment` | special equipment except jump jets, e.g. `ECM/TAG` |
| `jumpjets` | number of jump jets |
| `heatsink_type`, `heatsinks` | `SHS`/`DHS`, total number (engine ones included) |
| `heat_dissipation`, `max_heat` | heat per second, heat capacity |
| `optimal_range` | optimal range of the heaviest weapon group, in meters |
| `leg_hp`, `kill_hp`, `total_hp` | both legs; weakest side torso with an Inner Sphere XL engine, otherwise centre torso; all components |
| `role`, `owner`, `date` | see *Role, owner and date* |

</details>

<details>
<summary>How speed, range, HP and heat are computed</summary>

Mech quirks, OmniPod quirks and set bonuses are always included.

- **Speed** = engine rating ÷ tonnage × 16.2 × (1 + speed quirks).
- **Range** = optimal range of the heaviest weapon group × (1 + range quirks) × Targeting Computer bonus.
- **HP** = front armor placed on the build + armor quirks + (structure + structure quirks) × structure modifier. The modifier is 0.5 by default (Settings), plus half of the mech's *crit chance receiving* quirk: a mech with a −100 % quirk has its structure count fully.
- **Heat.** An engine holds up to 10 heat sinks for free, more above 250 rating; heat sinks inside the engine are worth more than the others.
  - `heat_dissipation` = (engine ones × engine dissipation + others × dissipation) × (1 + heat dissipation quirks)
  - `max_heat` = (30 + engine ones × engine capacity + others × capacity) × (1 + max heat quirks)

</details>

### Update after a game patch

Re-reads the game files (new mechs, weapons, quirks…). The first time, point it to the game's install folder, the one containing `Game/GameData.pak`.

Abbreviations can be changed in `data/weapons.csv`, `data/equipment.csv` and `data/engines.csv`; Update keeps your changes.

### Reset

Same as Update, but also **restores the default abbreviations** (your changes are lost) and restarts the first-run setup. Asks for confirmation first.

## Settings

Language, game folder, install folder, backup before renaming, structure modifier for HP, new version check at startup.

<details>
<summary>All <code>config.cfg</code> options</summary>

| `[general]` option | Default | Meaning |
|---|---|---|
| `language` | asked on first run | `en`, `fr`, `de`, `th`, `zh` |
| `game_dir` | auto-detected | the game's `MechLoadouts` folder |
| `game_install_dir` | auto-detected | the game's install folder |
| `backup_before_rename` | `true` | back up the folder before renaming |
| `structure_modifier` | `0.5` | share of the internal structure counted in HP |
| `dhs_rename` | `false` | also write `DHS` in names, not just `SHS` |
| `check_updates` | `true` | look for a newer version on GitHub at startup |
| `name_order` | see below | blocks of a renamed build's name, in order |
| `csv_columns` | see below | columns of the exported `.csv`, in order |

`name_order` — remove a name to drop that block. `weapons` and `equipment` side by side are joined by `-`:

```
name_order = prefix,variant,original,weapons,equipment,heatsink,engine
```

`csv_columns` — any column from *CSV columns*, in any order. Removing `role`, `owner` or `date` means a build imported back from that `.csv` can't recover them:

```
csv_columns = name,mechvariant,mechtype,variant_type,class,tonnage,tech,cockpit_height,buildcode,engine_type,engine_rating,max_speed,weapons,equipment,jumpjets,heatsink_type,heatsinks,heat_dissipation,max_heat,optimal_range,leg_hp,kill_hp,total_hp,role,owner,date
```

</details>

## Role, owner and date

Each build the tool handles gets four comment lines in its `.xml` file. The game ignores them:

```xml
<Loadout MechID="570">
 <!-- role: Sniper -->
 <!-- owner: SHD2 -->
 <!-- date: 2026-09-29 -->
 <!-- Generated by Mwobuildmanager (https://github.com/SHDMk2/mwobuildmanager) -->
```

- The role is detected automatically; edit the `role` line to set your own, it will be kept.
- The owner is your game profile, the date the day the build was found.
- If the game rewrites a build and erases these lines, the tool restores them from its own copy.

Roles: LRM Boat, ATM Boat, Streak Boat, MRM Boat, NARC Support, ECM Support, Scout, Poptart, Brawler, Dakka, Sniper, Laser Vomit, PPFLD, Mid-Range.

<details>
<summary>Customizing roles (<code>data/roles.csv</code>)</summary>

A build gets the role of the first rule it matches, by increasing `priority`; the last rule catches everything else. Empty cell = no condition.

| Column | Condition |
|---|---|
| `priority`, `role` | evaluation order, and the role given |
| `families`, `min_share` | weapon families joined by `\|` (game families such as `lrm`, `laser`, `ppcfamily`, or internal weapon names), and the minimum share of the weapon tonnage they must represent |
| `min_range`, `max_range` | optimal range of the heaviest weapon group, in meters |
| `min_speed`, `max_speed` | max speed in km/h |
| `min_tonnage`, `max_tonnage` | mech tonnage |
| `requires` | equipment joined by `+`: `JJ`, `MASC`, `SC`, `ECM`, `BAP`, `TAG`, `NARC`, `AMS` |

</details>

## Support

The tool is free and stays free. If it saves you time, you can help me pay for Claude:

[![Support me on PayPal](https://img.shields.io/badge/Support%20me-paypal.me%2FToulouseServers-0070ba?logo=paypal&logoColor=white)](https://paypal.me/ToulouseServers)

## License

MIT — see [LICENSE](LICENSE).
