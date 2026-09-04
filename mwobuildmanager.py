#!/usr/bin/env python3
"""Renommage en masse des loadouts MechWarrior Online (.xml / .mwl).

Usage: python3 shdrename.py
Necessite mechs.csv et weapons.csv dans le meme dossier que ce script.
Compatible Linux et Windows (bibliotheque standard uniquement).
"""

import configparser
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.cfg"
LOCALES_DIR = SCRIPT_DIR / "locales"
INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')
MAX_WEAPON_TYPES = 3
MWO_STEAM_APPID = "342200"
WEIGHT_CLASSES = ((35, "Light"), (55, "Medium"), (75, "Heavy"), (100, "Assault"))
LOADOUTS_SUFFIX = ("saved games", "mechwarrior online", "mechloadouts")

# base internal weapon name (Clan/DropShip prefix stripped) -> short abbreviation,
# used to auto-generate a row for a weapon id not yet in weapons.csv.
WEAPON_ABBR = {
    "AutoCannon20": "AC20", "NobleAutoCannon20": "AC20",
    "AutoCannon2": "AC2", "AutoCannon5": "AC5", "AutoCannon10": "AC10",
    "MediumLaser": "ML", "SmallLaser": "SL", "LargeLaser": "LL",
    "ERLargeLaser": "ERLL", "ERSmallLaser": "ERSL", "ERMediumLaser": "ERML",
    "ERPPC": "ERPPC", "PPC": "PPC", "LightPPC": "LPPC", "HeavyPPC": "HPPC",
    "SnubNosePPC": "SNPPC",
    "LargePulseLaser": "LPL", "MediumPulseLaser": "MPL", "SmallPulseLaser": "SPL",
    "LargeXPulseLaser": "LXPL", "MediumXPulseLaser": "MXPL", "SmallXPulseLaser": "SXPL",
    "Flamer": "FLMR",
    "AntiMissileSystem": "AMS", "LaserAntiMissileSystem": "LAMS",
    "GaussRifle": "GAUSS", "LightGaussRifle": "LGAUSS", "HeavyGaussRifle": "HGAUSS",
    "SilverBulletGaussRifle": "SBGR", "APGauss": "APG",
    "LBXAutoCannon2": "LB2X", "LBXAutoCannon5": "LB5X", "LBXAutoCannon10": "LB10X", "LBXAutoCannon20": "LB20X",
    "UltraAutoCannon2": "UAC2", "UltraAutoCannon5": "UAC5", "UltraAutoCannon10": "UAC10", "UltraAutoCannon20": "UAC20",
    "RotaryAutoCannon2": "RAC2", "RotaryAutoCannon5": "RAC5",
    "LightAutoCannon2": "LAC2", "LightAutoCannon5": "LAC5",
    "ProtoAutocannon2": "PAC2", "ProtoAutocannon4": "PAC4", "ProtoAutocannon8": "PAC8",
    "MachineGun": "MG", "LightMachineGun": "LMG", "HeavyMachineGun": "HMG",
    "LRM5": "LRM5", "LRM10": "LRM10", "LRM15": "LRM15", "LRM20": "LRM20",
    "LRM5_Artemis": "LRM5A", "LRM10_Artemis": "LRM10A", "LRM15_Artemis": "LRM15A", "LRM20_Artemis": "LRM20A",
    "SRM2": "SRM2", "SRM4": "SRM4", "SRM6": "SRM6",
    "SRM2_Artemis": "SRM2A", "SRM4_Artemis": "SRM4A", "SRM6_Artemis": "SRM6A",
    "StreakSRM2": "SSRM2", "StreakSRM4": "SSRM4", "StreakSRM6": "SSRM6",
    "MRM10": "MRM10", "MRM20": "MRM20", "MRM30": "MRM30", "MRM40": "MRM40",
    "RocketLauncher10": "RL10", "RocketLauncher15": "RL15", "RocketLauncher20": "RL20",
    "NarcBeacon": "NARC", "TAG": "TAG", "LightTAG": "LTAG",
    "BinaryLaserCannon": "BLC", "ArrowIV": "ARROW4", "Magshot": "MAGSHOT",
    "ThunderboltMissile1": "TB1", "ThunderboltMissile2": "TB2", "ThunderboltMissile3": "TB3", "ThunderboltMissile4": "TB4",
    "ERMicroLaser": "ERuL", "MicroPulseLaser": "uPL",
    "HeavySmallLaser": "HSL", "HeavyMediumLaser": "HML", "HeavyLargeLsr": "HLL",
    "ATM3": "ATM3", "ATM6": "ATM6", "ATM9": "ATM9", "ATM12": "ATM12",
    "HyperAssaultGaussRifle20": "HAG20", "HyperAssaultGaussRifle30": "HAG30", "HyperAssaultGaussRifle40": "HAG40",
    "BeamLaser": "BEAM", "PlasmaPPC": "PLPPC", "RailGun": "RAILGUN",
    "LargePulseLsr": "LPL",
}


def available_languages():
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


def load_strings(lang):
    path = LOCALES_DIR / f"{lang}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Translator:
    def __init__(self, lang):
        self.lang = lang
        self.strings = load_strings(lang)
        self._fallback = load_strings("en") if lang != "en" else self.strings

    def __call__(self, key, **kwargs):
        text = self.strings.get(key)
        if text is None:
            text = self._fallback.get(key, key)
        return text.format(**kwargs) if kwargs else text

    def words(self, key):
        return self.strings.get(key) or self._fallback.get(key) or []


# ---------------------------------------------------------------------------
# Config

def load_config():
    cfg = configparser.ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH, encoding="utf-8")
    if "general" not in cfg:
        cfg["general"] = {}
    if "last_used" not in cfg:
        cfg["last_used"] = {}
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


# ---------------------------------------------------------------------------
# Mechs / weapons CSV lookup tables (see rename rules from the game data)

def load_mechs(path):
    mechs = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mechs[row["id"]] = (row["chassis"], row["variant"])
    return mechs


def load_weapons(path):
    weapons = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            weapons[row["id"]] = (row["abbreviation"], float(row["tons"]))
    return weapons


def load_tonnage(path):
    """chassis -> tonnage. Table editable a la main, absente du GameData.pak."""
    tonnage = {}
    if not Path(path).exists():
        return tonnage
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = (row.get("tonnage") or "").strip()
            if raw.isdigit():
                tonnage[row["chassis"]] = int(raw)
    return tonnage


def weight_class(tons):
    for limit, name in WEIGHT_CLASSES:
        if tons <= limit:
            return name
    return ""


def current_profile_name(game_dir):
    """Nom du dernier profil joueur utilise (.../MechWarrior Online/Profiles/<nom>)."""
    profiles_dir = Path(game_dir).parent / "Profiles"
    if not profiles_dir.is_dir():
        return ""
    best_name, best_time = "", -1
    for profile_xml in profiles_dir.glob("*/profile.xml"):
        try:
            attrs = ET.parse(profile_xml).getroot().attrib
        except ET.ParseError:
            continue
        name = attrs.get("Name", "")
        if not name or name.lower() == "default":
            continue
        try:
            played = int(attrs.get("LastPlayed", "0"))
        except ValueError:
            played = 0
        if played > best_time:
            best_name, best_time = name, played
    return best_name


def sanitize(name):
    name = INVALID_CHARS.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def decode_loadout(xml_path, mechs, weapons):
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None, []

    mech_id = root.attrib.get("MechID")
    _chassis, variant = mechs.get(mech_id, (None, None))

    weapon_instances = []
    for weapon_el in root.iter("Weapon"):
        item_id = weapon_el.attrib.get("ItemID")
        abbr, tons = weapons.get(item_id, (f"ID{item_id}", 0.0))
        weapon_instances.append((abbr, tons))

    return variant, weapon_instances


# ---------------------------------------------------------------------------
# Codec des codes de build (contenu des .mwl)
#
# Un .mwl contient le code de partage du jeu : des chiffres base 64 en
# little-endian (valeur = ord(c) - 48, donc '0'..'o'), ce qui laisse 'p'..'w'
# et '|' libres comme marqueurs de structure. Format :
#   'A' | id du mech (2) | 3 chiffres d'en-tete | blocs composants | 'w' | 3x2 arriere
# Un bloc composant = [marqueur] armure (2) [omnipod (longueur variable, sans
# separateur)] puis chaque objet sous la forme '|' + chiffres (longueur variable).
# Les trois chiffres d'en-tete :
#   [0] index armure + 8 * index structure
#   [1] bit0 = Artemis, bits 1-2 = index refroidisseurs (bit3 inutilise)
#   [2] index actionneur gauche * 4 + index actionneur droit
# Les tables d'index suivent l'ordre de declaration de UpgradeTypes.xml.

ARMOR_TYPES = ["2810", "2811", "2812", "2814", "2815", "2816"]
STRUCTURE_TYPES = ["3100", "3101", "3102", "3103"]
HEATSINK_TYPES = ["3003", "3002", "3005", "3006"]
ACTUATOR_STATES = [
    "EActuatorState_HandsAndArms",
    "EActuatorState_ArmsOnly",
    "EActuatorState_None",
]
CODE_COMPONENTS = [
    ("centre_torso", None), ("right_torso", "p"), ("left_torso", "q"),
    ("left_arm", "r"), ("right_arm", "s"), ("left_leg", "t"),
    ("right_leg", "u"), ("head", "v"),
]
REAR_COMPONENTS = ["centre_torso_rear", "left_torso_rear", "right_torso_rear"]
# Un code ne contient jamais d'espace ni de virgule, mais ";" est un chiffre
# valide a l'interieur d'un code : on ne coupe sur ";" que s'il est suivi
# d'un espace, d'une virgule ou de la fin de la saisie.
CODE_SEPARATORS = re.compile(r";(?=[\s,]|$)|[,\s]+")


class BadBuildCode(ValueError):
    pass


def split_build_codes(raw):
    """Decoupe une saisie libre en codes : ', ', '; ' ou un code par ligne.
    Un meme code colle plusieurs fois n'est garde qu'une seule fois."""
    codes = []
    seen = set()
    for chunk in CODE_SEPARATORS.split(raw):
        chunk = chunk.strip('"\'')
        if chunk and chunk not in seen:
            seen.add(chunk)
            codes.append(chunk)
    return codes


def looks_like_build_code(text):
    try:
        decode_build_code(text)
    except BadBuildCode:
        return False
    return True


def extract_codes_from_csv(path):
    """Repere seule la colonne des codes de build, quel que soit l'en-tete.
    Plusieurs delimiteurs sont essayes : ';' est un caractere valide dans un
    code, seul celui qui donne le plus de codes lisibles est retenu."""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    best_codes = []
    for delimiter in (",", ";", "\t"):
        rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter))
        scores = {}
        for row in rows:
            for column, cell in enumerate(row):
                if looks_like_build_code(cell.strip()):
                    scores[column] = scores.get(column, 0) + 1
        if not scores:
            continue
        column = max(scores, key=scores.get)
        codes = [row[column].strip() for row in rows
                 if column < len(row) and looks_like_build_code(row[column].strip())]
        if len(codes) > len(best_codes):
            best_codes = codes
    return best_codes


def _code_value(chunk):
    value = 0
    for i, char in enumerate(chunk):
        digit = ord(char) - 48
        if not 0 <= digit < 64:
            raise BadBuildCode(chunk)
        value += digit * (64 ** i)
    return value


def _code_run_end(code, start):
    """Fin de la suite de chiffres commencant a start ('|' et 'p'..'w' arretent)."""
    end = start
    while end < len(code) and 48 <= ord(code[end]) < 112:
        end += 1
    return end


def decode_build_code(code):
    """Code de partage -> dict decrivant le loadout. Leve BadBuildCode si invalide."""
    code = code.strip()
    if not code.startswith("A"):
        raise BadBuildCode(code)

    def take(pos, n):
        if pos + n > len(code):
            raise BadBuildCode(code)
        return _code_value(code[pos:pos + n]), pos + n

    mech_id, i = take(1, 2)
    upgrades_digit, i = take(i, 1)
    flags_digit, i = take(i, 1)
    actuators_digit, i = take(i, 1)

    components = []
    for name, marker in CODE_COMPONENTS:
        if marker is not None:
            if i >= len(code) or code[i] != marker:
                raise BadBuildCode(code)
            i += 1
        armor, i = take(i, 2)

        omnipod = None
        end = _code_run_end(code, i)
        if end > i:
            omnipod = _code_value(code[i:end])
            i = end

        items = []
        while i < len(code) and code[i] == "|":
            end = _code_run_end(code, i + 1)
            if end == i + 1:
                raise BadBuildCode(code)
            items.append(_code_value(code[i + 1:end]))
            i = end
        components.append((name, armor, omnipod, items))

    if i >= len(code) or code[i] != "w":
        raise BadBuildCode(code)
    i += 1
    rear_armor = []
    for _ in range(3):
        value, i = take(i, 2)
        rear_armor.append(value)
    if i != len(code):
        raise BadBuildCode(code)

    armor_index, structure_index = upgrades_digit % 8, upgrades_digit // 8
    left_index, right_index = actuators_digit // 4, actuators_digit % 4
    if (armor_index >= len(ARMOR_TYPES) or structure_index >= len(STRUCTURE_TYPES)
            or left_index >= len(ACTUATOR_STATES) or right_index >= len(ACTUATOR_STATES)):
        raise BadBuildCode(code)

    return {
        "mech_id": str(mech_id),
        "armor": ARMOR_TYPES[armor_index],
        "structure": STRUCTURE_TYPES[structure_index],
        "heatsinks": HEATSINK_TYPES[(flags_digit >> 1) & 3],
        "artemis": flags_digit & 1,
        "left_actuator": ACTUATOR_STATES[left_index],
        "right_actuator": ACTUATOR_STATES[right_index],
        "components": components,
        "rear_armor": rear_armor,
    }


def build_loadout_xml(build, weapons):
    """Reconstruit le .xml exactement comme le jeu l'ecrit (indentation, CRLF)."""
    lines = [
        '<Loadout MechID="%s">' % build["mech_id"],
        " <Upgrades>",
        '  <Armor ItemID="%s"/>' % build["armor"],
        '  <Structure ItemID="%s"/>' % build["structure"],
        '  <Artemis Equipped="%d"/>' % build["artemis"],
        '  <HeatSinks ItemID="%s"/>' % build["heatsinks"],
        " </Upgrades>",
        ' <ActuatorState RightActuatorState="%s" LeftActuatorState="%s"/>'
        % (build["right_actuator"], build["left_actuator"]),
        " <ComponentList>",
    ]
    for name, armor, omnipod, items in build["components"]:
        attrs = 'name="%s" Armor="%d"' % (name, armor)
        if omnipod is not None:
            attrs += ' Omnipod="%d"' % omnipod
        if not items:
            lines.append("  <component %s/>" % attrs)
            continue
        lines.append("  <component %s>" % attrs)
        for item_id in items:
            tag = "Weapon" if str(item_id) in weapons else "Module"
            lines.append('   <%s ItemID="%d"/>' % (tag, item_id))
        lines.append("  </component>")
    for name, armor in zip(REAR_COMPONENTS, build["rear_armor"]):
        lines.append('  <component name="%s" Armor="%d"/>' % (name, armor))
    lines += [" </ComponentList>", "</Loadout>"]
    return "\r\n".join(lines) + "\r\n"


def build_weapon_instances(build, weapons):
    """Armes du build sous la forme attendue par build_suffix()."""
    instances = []
    for _name, _armor, _omnipod, items in build["components"]:
        for item_id in items:
            entry = weapons.get(str(item_id))
            if entry:
                instances.append(entry)
    return instances


class NoQualifyingWeapon(ValueError):
    pass


def build_suffix(weapon_instances, t):
    """Regroupe par arme, poids_total = quantite x tonnage, ne garde que
    poids_total > 2, trie du plus lourd au plus leger, max MAX_WEAPON_TYPES."""
    totals = {}
    for abbr, tons in weapon_instances:
        qty, weight = totals.get(abbr, (0, 0.0))
        totals[abbr] = (qty + 1, weight + tons)

    qualifying = [(abbr, qty, weight) for abbr, (qty, weight) in totals.items() if weight > 2]
    if not qualifying:
        raise NoQualifyingWeapon(t("no_qualifying_weapon"))

    qualifying.sort(key=lambda item: item[2], reverse=True)
    top = qualifying[:MAX_WEAPON_TYPES]
    parts = [abbr if qty == 1 else f"{qty}{abbr}" for abbr, qty, _ in top]
    return "-".join(parts)


def find_loadout_basenames(folder):
    """Un loadout = un .xml ; le .mwl associe (meme nom) est renomme avec."""
    return sorted(p.stem for p in folder.glob("*.xml"))


def make_backup(folder):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = folder.parent / f"{folder.name}_backup_{timestamp}"
    n = 2
    while backup_dir.exists():
        backup_dir = folder.parent / f"{folder.name}_backup_{timestamp}_{n}"
        n += 1
    shutil.copytree(folder, backup_dir)
    return backup_dir


def unique_target(base_name, ext, used_names):
    candidate = f"{base_name}{ext}"
    n = 2
    while candidate.lower() in used_names:
        candidate = f"{base_name} ({n}){ext}"
        n += 1
    used_names.add(candidate.lower())
    return candidate


def unique_pair_stem(base_name, used_names):
    """Nom de base libre pour la paire .xml + .mwl d'un loadout importe."""
    candidate = base_name
    n = 2
    while (f"{candidate}.xml".lower() in used_names
           or f"{candidate}.mwl".lower() in used_names):
        candidate = f"{base_name} ({n})"
        n += 1
    used_names.add(f"{candidate}.xml".lower())
    used_names.add(f"{candidate}.mwl".lower())
    return candidate


def parse_selection(raw, total, t):
    raw = raw.strip().lower()
    all_idx = set(range(1, total + 1))

    if raw in ("", "all", "tout", "tous", "o", "oui", "y", "yes"):
        return all_idx
    if raw in ("none", "aucun", "n", "non", "cancel", "annuler"):
        return set()

    if raw.startswith("all except") or raw.startswith("except") or raw.startswith("tout sauf"):
        nums = re.findall(r"\d+", raw)
        excluded = {int(n) for n in nums}
        return all_idx - excluded
    if raw.startswith("only") or raw.startswith("seulement"):
        nums = re.findall(r"\d+", raw)
        return {int(n) for n in nums} & all_idx

    print(t("selection_invalid"))
    return None


# ---------------------------------------------------------------------------
# GUI folder picker (tkinter, with zenity/kdialog fallback on Linux, then
# manual text entry as a last resort so the tool still works headless).

def pick_folder_gui(title, initial_dir=None):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title=title, initialdir=initial_dir or str(Path.home()))
        root.destroy()
        if path:
            return path
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        for cmd in (
            ["zenity", "--file-selection", "--directory", "--title", title],
            ["kdialog", "--getexistingdirectory", initial_dir or str(Path.home()), "--title", title],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                out = result.stdout.strip()
                if result.returncode == 0 and out:
                    return out
            except FileNotFoundError:
                continue

    return None


def ask_folder(t, title_key, initial_dir=None, allow_skip=False,
               manual_prompt_key="manual_folder_prompt"):
    picked = pick_folder_gui(t(title_key), initial_dir)
    if picked:
        folder = Path(picked)
        if folder.is_dir():
            return folder

    print(t("gui_unavailable"))
    while True:
        folder_input = input(t(manual_prompt_key)).strip().strip('"')
        if allow_skip and not folder_input:
            return None
        folder = Path(folder_input).expanduser()
        if folder.is_dir():
            return folder
        print(t("folder_not_found"))


def pick_file_gui(title, initial_dir=None):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title=title, initialdir=initial_dir or str(Path.home()))
        root.destroy()
        if path:
            return path
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        for cmd in (
            ["zenity", "--file-selection", "--title", title],
            ["kdialog", "--getopenfilename", initial_dir or str(Path.home()), "--title", title],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                out = result.stdout.strip()
                if result.returncode == 0 and out:
                    return out
            except FileNotFoundError:
                continue

    return None


def ask_file(t, title_key, initial_dir=None):
    picked = pick_file_gui(t(title_key), initial_dir)
    if picked and Path(picked).is_file():
        return Path(picked)

    print(t("gui_unavailable"))
    while True:
        raw = input(t("manual_file_prompt")).strip().strip('"')
        if not raw:
            return None
        path = Path(raw).expanduser()
        if path.is_file():
            return path
        print(t("file_not_found"))


def looks_like_loadouts_dir(path):
    parts = [p.lower() for p in path.parts[-3:]]
    return parts == list(LOADOUTS_SUFFIX)


def autodetect_loadouts_dir():
    home = Path.home()
    candidates = []

    if sys.platform.startswith("linux"):
        steam_roots = [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
        for root in steam_roots:
            users_dir = root / "steamapps/compatdata" / MWO_STEAM_APPID / "pfx/drive_c/users"
            if users_dir.is_dir():
                for user_dir in users_dir.iterdir():
                    candidate = user_dir / "Saved Games/MechWarrior Online/MechLoadouts"
                    if candidate.is_dir():
                        candidates.append(candidate)
    elif sys.platform.startswith("win"):
        candidate = home / "Saved Games/MechWarrior Online/MechLoadouts"
        if candidate.is_dir():
            candidates.append(candidate)

    return candidates[0] if candidates else None


def has_gamedata_pak(path):
    return (Path(path) / "Game" / "GameData.pak").is_file()


def autodetect_install_dir():
    home = Path.home()
    roots = []

    if sys.platform.startswith("linux"):
        roots = [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
    elif sys.platform.startswith("win"):
        roots = [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]

    for root in roots:
        candidate = root / "steamapps/common/MechWarrior Online"
        if has_gamedata_pak(candidate):
            return candidate
    return None


def resolve_install_dir(cfg, t):
    """Return a valid game install folder (contains Game/GameData.pak),
    reusing the cached config value, auto-detecting, or asking the user."""
    cached = cfg["general"].get("game_install_dir", "")
    if cached and has_gamedata_pak(Path(cached)):
        return Path(cached)

    detected = autodetect_install_dir()
    if detected:
        print(t("installdir_autodetect_found", path=detected))
        if ask_yes_no(t, "autodetect_confirm"):
            cfg["general"]["game_install_dir"] = str(detected)
            save_config(cfg)
            return detected

    while True:
        picked = ask_folder(t, "pick_installdir_title", allow_skip=True,
                             manual_prompt_key="manual_installdir_prompt")
        if picked is None:
            return None
        if has_gamedata_pak(picked):
            cfg["general"]["game_install_dir"] = str(picked)
            save_config(cfg)
            return picked
        print(t("installdir_invalid"))


# ---------------------------------------------------------------------------
# Yes/no + first-run setup

def ask_yes_no(t, question_key, **kwargs):
    # universal fallback (y/n/1/0) always works, on top of the locale's own
    # yes/no words, so nobody gets stuck regardless of language.
    yes_words = {w.lower() for w in t.words("yes_words")} | {"y", "yes", "1"}
    no_words = {w.lower() for w in t.words("no_words")} | {"n", "no", "0"}
    while True:
        answer = input(t(question_key, **kwargs) + t("yes_no_suffix")).strip().lower()
        if answer in yes_words:
            return True
        if answer in no_words:
            return False
        print(t("yes_no_invalid"))


LANGUAGE_PROMPT_HEADER = (
    "Choose your language / Choisis ta langue / "
    "Sprache waehlen / เลือกภาษา / 选择语言"
)


def ask_language():
    codes = available_languages()
    names = [load_strings(code).get("_language_name", code) for code in codes]

    print(LANGUAGE_PROMPT_HEADER)
    for i, name in enumerate(names, start=1):
        print(f"{i}) {name}")

    while True:
        answer = input("> ").strip().lower()
        if answer.isdigit() and 1 <= int(answer) <= len(codes):
            return codes[int(answer) - 1]
        if answer in codes:
            return answer
        print("?")


def first_run_setup(cfg):
    lang = ask_language()
    t = Translator(lang)
    print(t("welcome"))

    game_dir = autodetect_loadouts_dir()
    if game_dir:
        print(t("autodetect_found", path=game_dir))
        if not ask_yes_no(t, "autodetect_confirm"):
            game_dir = None
    else:
        print(t("autodetect_not_found"))

    if not game_dir:
        game_dir = ask_folder(t, "pick_gamedir_title", allow_skip=True, manual_prompt_key="manual_gamedir_prompt")

    cfg["general"]["language"] = lang
    cfg["general"]["backup_before_rename"] = "true"
    if game_dir:
        if not looks_like_loadouts_dir(game_dir):
            print(t("gamedir_suffix_warning"))
        cfg["general"]["game_dir"] = str(game_dir)
        print(t("gamedir_saved", path=game_dir))
    else:
        print(t("gamedir_none"))

    cfg["last_used"]["add_prefix"] = "false"
    cfg["last_used"]["prefix"] = ""
    cfg["last_used"]["add_suffix"] = "true"
    cfg["last_used"]["keep_original"] = "true"
    cfg["last_used"]["source_dir"] = ""
    save_config(cfg)
    return t


# ---------------------------------------------------------------------------
# Update mechs.csv / weapons.csv straight from the game's GameData.pak

def read_pak_xml(pak_path, entry_name):
    with zipfile.ZipFile(pak_path) as z:
        return ET.fromstring(z.read(entry_name))


def fetch_mechs_from_pak(pak_path):
    root = read_pak_xml(pak_path, "Libs/Items/Mechs/Mechs.xml")
    rows = [(el.attrib["id"], el.attrib.get("chassis", "?"), el.attrib.get("name", "?"))
            for el in root.iter("Mech")]
    rows.sort(key=lambda r: int(r[0]))
    return rows


def fetch_weapons_from_pak(pak_path):
    root = read_pak_xml(pak_path, "Libs/Items/Weapons/Weapons.xml")
    rows = []
    for el in root.iter("Weapon"):
        name = el.attrib.get("name", "?")
        if name == "FakeMachineGun":
            continue
        stats = el.find("WeaponStats")
        tons = stats.attrib.get("tons", "0") if stats is not None else "0"
        rows.append((el.attrib["id"], name, tons))
    rows.sort(key=lambda r: int(r[0]))
    return rows


def guess_abbreviation(name):
    base = name
    for prefix in ("Clan", "DropShip"):
        if base.startswith(prefix):
            base = base[len(prefix):]
    return WEAPON_ABBR.get(base, base.upper()[:8])


def write_mechs_csv(pak_path, mechs_csv_path):
    rows = fetch_mechs_from_pak(pak_path)
    with open(mechs_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "chassis", "variant"])
        w.writerows(rows)
    return len(rows)


def update_weapons_csv(pak_path, weapons_csv_path, overwrite_existing):
    """Regenerate weapons.csv. When overwrite_existing is False, any row whose
    id is already present is kept untouched (preserves custom abbreviations);
    only genuinely new weapon ids are appended."""
    fresh = {wid: (name, tons) for wid, name, tons in fetch_weapons_from_pak(pak_path)}

    existing_rows = {}
    if weapons_csv_path.exists():
        with open(weapons_csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_rows[row["id"]] = row

    out = {}
    added = 0
    if overwrite_existing:
        for wid, (name, tons) in fresh.items():
            out[wid] = {"id": wid, "name": name, "tons": tons, "abbreviation": guess_abbreviation(name)}
        added = len(out)
    else:
        out = dict(existing_rows)
        for wid, (name, tons) in fresh.items():
            if wid not in out:
                out[wid] = {"id": wid, "name": name, "tons": tons, "abbreviation": guess_abbreviation(name)}
                added += 1

    rows_sorted = sorted(out.values(), key=lambda r: int(r["id"]))
    with open(weapons_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "tons", "abbreviation"])
        for r in rows_sorted:
            w.writerow([r["id"], r["name"], r["tons"], r["abbreviation"]])
    return added


def update_tonnage_csv(mechs_csv_path, tonnage_csv_path):
    """Ajoute les chassis inconnus avec un tonnage vide, a remplir a la main.
    Le tonnage n'est nulle part dans les fichiers du jeu : on ne l'ecrase jamais."""
    known = []
    seen = set()
    if Path(tonnage_csv_path).exists():
        with open(tonnage_csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                known.append((row["chassis"], row.get("tonnage", "")))
                seen.add(row["chassis"])

    added = 0
    with open(mechs_csv_path, newline="", encoding="utf-8") as f:
        for chassis in sorted({row["chassis"] for row in csv.DictReader(f)}):
            if chassis not in seen:
                known.append((chassis, ""))
                seen.add(chassis)
                added += 1

    if added or not Path(tonnage_csv_path).exists():
        known.sort()
        with open(tonnage_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["chassis", "tonnage"])
            writer.writerows(known)
    return added


def do_update(cfg, mechs, weapons, tonnage, t):
    install_dir = resolve_install_dir(cfg, t)
    if not install_dir:
        print(t("installdir_cancelled"))
        return

    pak_path = install_dir / "Game" / "GameData.pak"
    mech_count = write_mechs_csv(pak_path, SCRIPT_DIR / "mechs.csv")
    added_weapons = update_weapons_csv(pak_path, SCRIPT_DIR / "weapons.csv", overwrite_existing=False)
    added_chassis = update_tonnage_csv(SCRIPT_DIR / "mechs.csv", SCRIPT_DIR / "mech_tonnage.csv")

    mechs.clear()
    mechs.update(load_mechs(SCRIPT_DIR / "mechs.csv"))
    weapons.clear()
    weapons.update(load_weapons(SCRIPT_DIR / "weapons.csv"))
    tonnage.clear()
    tonnage.update(load_tonnage(SCRIPT_DIR / "mech_tonnage.csv"))

    print(t("update_done", mechs=mech_count, weapons=added_weapons))
    if added_chassis:
        print(t("update_tonnage_added", n=added_chassis))


def do_reset(cfg, mechs, weapons, tonnage, t):
    if not ask_yes_no(t, "reset_confirm"):
        return t

    install_dir = resolve_install_dir(cfg, t)
    if not install_dir:
        print(t("installdir_cancelled"))
        return t

    pak_path = install_dir / "Game" / "GameData.pak"
    write_mechs_csv(pak_path, SCRIPT_DIR / "mechs.csv")
    update_weapons_csv(pak_path, SCRIPT_DIR / "weapons.csv", overwrite_existing=True)
    update_tonnage_csv(SCRIPT_DIR / "mechs.csv", SCRIPT_DIR / "mech_tonnage.csv")

    mechs.clear()
    mechs.update(load_mechs(SCRIPT_DIR / "mechs.csv"))
    weapons.clear()
    weapons.update(load_weapons(SCRIPT_DIR / "weapons.csv"))
    tonnage.clear()
    tonnage.update(load_tonnage(SCRIPT_DIR / "mech_tonnage.csv"))

    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    cfg.clear()
    cfg["general"] = {}
    cfg["last_used"] = {}

    print(t("reset_done"))
    return first_run_setup(cfg)


# ---------------------------------------------------------------------------
# Export: gather the game's saved loadouts into a named, packaged archive

def ask_archive_format(t):
    while True:
        answer = input(t("export_format_prompt")).strip().lower()
        if answer in ("1", "7z"):
            return "7z"
        if answer in ("2", "rar"):
            return "rar"
        print(t("export_format_invalid"))


def create_archive(staging_dir, dest_dir, name, fmt):
    dest_dir = Path(dest_dir)
    parent = staging_dir.parent

    if fmt == "7z":
        archive_path = dest_dir / f"{name}.7z"
        for exe in ("7z", "7za", "7zr"):
            try:
                result = subprocess.run([exe, "a", "-y", str(archive_path), name],
                                         cwd=str(parent), capture_output=True, text=True)
                if result.returncode == 0 and archive_path.exists():
                    return archive_path, "7z"
            except FileNotFoundError:
                continue
    elif fmt == "rar":
        archive_path = dest_dir / f"{name}.rar"
        try:
            result = subprocess.run(["rar", "a", str(archive_path), name],
                                     cwd=str(parent), capture_output=True, text=True)
            if result.returncode == 0 and archive_path.exists():
                return archive_path, "rar"
        except FileNotFoundError:
            pass

    archive_path = dest_dir / f"{name}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in staging_dir.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(parent))
    return archive_path, "zip"


def ask_export_kind(t):
    while True:
        choice = input(t("export_kind_prompt")).strip()
        if choice in ("1", ""):
            return "archive"
        if choice == "2":
            return "csv"
        print(t("export_kind_invalid"))


def export_csv(game_dir, basenames, dest_dir, name, mechs, tonnage):
    """Une ligne par build : nom, code, variante, tonnage, classe, proprietaire."""
    owner = current_profile_name(game_dir)
    rows = []
    missing = set()
    for basename in basenames:
        mwl_path = game_dir / f"{basename}.mwl"
        code = mwl_path.read_text(encoding="utf-8", errors="replace").strip() if mwl_path.exists() else ""
        try:
            mech_id = ET.parse(game_dir / f"{basename}.xml").getroot().attrib.get("MechID", "")
        except ET.ParseError:
            mech_id = ""
        chassis, variant = mechs.get(mech_id, ("", ""))
        tons = tonnage.get(chassis)
        if chassis and tons is None:
            missing.add(chassis)
        rows.append([basename, code, (variant or "").upper(),
                     tons or "", weight_class(tons) if tons else "", owner])

    csv_path = dest_dir / f"{name}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "buildcode", "mechvariant", "tonnage", "class", "owner"])
        writer.writerows(rows)
    return csv_path, len(rows), sorted(missing), owner


def do_export(cfg, mechs, tonnage, t):
    game_dir = cfg["general"].get("game_dir", "")
    if not game_dir or not Path(game_dir).is_dir():
        print(t("export_no_gamedir"))
        return
    game_dir = Path(game_dir)

    basenames = find_loadout_basenames(game_dir)
    if not basenames:
        print(t("export_no_files"))
        return

    kind = ask_export_kind(t)

    name = sanitize(input(t("export_name_prompt")).strip())
    if not name:
        print(t("export_cancelled"))
        return

    fmt = ask_archive_format(t) if kind == "archive" else None

    last_export_dir = cfg["last_used"].get("export_dir", "")
    dest_dir = ask_folder(t, "pick_export_dest_title", last_export_dir or None, allow_skip=True,
                          manual_prompt_key="manual_export_dest_prompt")
    if dest_dir is None:
        print(t("export_cancelled"))
        return

    if kind == "csv":
        csv_path, count, missing, owner = export_csv(game_dir, basenames, dest_dir, name, mechs, tonnage)
        cfg["last_used"]["export_dir"] = str(dest_dir)
        save_config(cfg)
        print(t("export_csv_done", n=count, path=csv_path))
        if not owner:
            print(t("export_csv_no_owner"))
        if missing:
            print(t("export_csv_no_tonnage", n=len(missing), chassis=", ".join(missing)))
        return

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / name
        staging.mkdir()
        copied = 0
        for basename in basenames:
            for ext in (".xml", ".mwl"):
                src = game_dir / f"{basename}{ext}"
                if src.exists():
                    shutil.copy2(src, staging / src.name)
                    copied += 1
        archive_path, used_fmt = create_archive(staging, dest_dir, name, fmt)

    cfg["last_used"]["export_dir"] = str(dest_dir)
    save_config(cfg)

    print(t("export_done", n=copied, path=archive_path))
    if used_fmt != fmt:
        print(t("export_fallback_zip", requested=fmt))


# ---------------------------------------------------------------------------
# Import de builds depuis des codes de partage

# Fin de saisie : une ligne vide ne suffit pas, un bloc colle en contient
# souvent (separateurs entre groupes de builds).
CODE_INPUT_END = {".", "end"}


def read_pasted_codes(t):
    print(t("import_intro"))
    lines = []
    first = True
    while True:
        try:
            line = input(t("import_codes_prompt") if first else "")
        except EOFError:
            break
        first = False
        if line.strip().lower() in CODE_INPUT_END:
            break
        lines.append(line)
    return split_build_codes("\n".join(lines))


def read_build_codes(cfg, t):
    """1) saisie directe  2) fichier .txt  3) fichier .csv (colonne auto-detectee)"""
    while True:
        choice = input(t("import_source_prompt")).strip()
        if choice in ("1", ""):
            return read_pasted_codes(t)
        if choice in ("2", "3"):
            break
        print(t("import_source_invalid"))

    title_key = "pick_txt_title" if choice == "2" else "pick_csv_title"
    path = ask_file(t, title_key, cfg["last_used"].get("import_dir", "") or None)
    if path is None:
        return []

    cfg["last_used"]["import_dir"] = str(path.parent)
    save_config(cfg)

    try:
        if choice == "3":
            codes = extract_codes_from_csv(path)
        else:
            codes = split_build_codes(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError as e:
        print(t("import_file_error", path=path, reason=e))
        return []

    print(t("import_file_loaded", n=len(codes), path=path))
    return codes


def ask_import_dest(cfg, t):
    """Dossier du jeu, ou n'importe quel autre dossier."""
    game_dir = cfg["general"].get("game_dir", "")
    if game_dir and Path(game_dir).is_dir():
        while True:
            choice = input(t("import_dest_prompt", path=game_dir)).strip()
            if choice in ("1", ""):
                return Path(game_dir)
            if choice == "2":
                break
            print(t("import_dest_invalid"))
    else:
        print(t("import_dest_no_gamedir"))

    return ask_folder(t, "pick_import_dest_title", game_dir or None, allow_skip=True,
                      manual_prompt_key="manual_import_dest_prompt")


def do_import(cfg, mechs, weapons, t):
    codes = read_build_codes(cfg, t)
    if not codes:
        print(t("import_no_codes"))
        return

    add_prefix = ask_yes_no(t, "ask_prefix_yn")
    prefix = input(t("ask_prefix_text")).strip() if add_prefix else ""
    add_suffix = ask_yes_no(t, "ask_suffix_yn")

    plan = []
    skipped = []
    for code in codes:
        label = code if len(code) <= 24 else code[:24] + "..."
        try:
            build = decode_build_code(code)
        except BadBuildCode:
            skipped.append((label, t("import_invalid_code")))
            continue

        _chassis, variant = mechs.get(build["mech_id"], (None, None))
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(variant.upper() if variant else "UNKNOWN")
        if add_suffix:
            try:
                parts.append(build_suffix(build_weapon_instances(build, weapons), t))
            except NoQualifyingWeapon as e:
                skipped.append((label, str(e)))
                continue
        plan.append((code, build, sanitize(" ".join(parts))))

    if skipped:
        print(t("skipped_header", n=len(skipped)))
        for label, reason in skipped:
            print(t("skipped_line", name=label, reason=reason))

    if not plan:
        print(t("import_nothing"))
        return

    print(t("import_preview_header"))
    for i, (_code, _build, name) in enumerate(plan, start=1):
        print(f" {i:3d}. {name}")

    print(t("selection_help"))
    while True:
        selection = parse_selection(input(t("selection_prompt")), len(plan), t)
        if selection is not None:
            break
    if not selection:
        print(t("import_none"))
        return

    dest = ask_import_dest(cfg, t)
    if dest is None:
        print(t("import_cancelled"))
        return

    used_names = {p.name.lower() for p in dest.iterdir()}
    written = 0
    for i, (code, build, name) in enumerate(plan, start=1):
        if i not in selection:
            continue
        stem = unique_pair_stem(name, used_names)
        with open(dest / f"{stem}.xml", "w", encoding="utf-8", newline="") as f:
            f.write(build_loadout_xml(build, weapons))
        with open(dest / f"{stem}.mwl", "w", encoding="utf-8", newline="") as f:
            f.write(code)
        written += 1

    print(t("import_done", n=written, path=dest))


# ---------------------------------------------------------------------------
# Core rename flow, shared by advanced and quick modes

def build_plan(folder, prefix, add_suffix, keep_original, mechs, weapons, t):
    plan = []
    skipped = []
    for basename in find_loadout_basenames(folder):
        xml_path = folder / f"{basename}.xml"
        variant, weapon_instances = decode_loadout(xml_path, mechs, weapons)

        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(variant.upper() if variant else "UNKNOWN")
        if keep_original:
            parts.append(basename)
        if add_suffix:
            try:
                suffix = build_suffix(weapon_instances, t)
            except NoQualifyingWeapon as e:
                skipped.append((basename, str(e)))
                continue
            parts.append(suffix)

        plan.append((basename, sanitize(" ".join(parts))))
    return plan, skipped


def run_rename(folder, prefix, add_suffix, keep_original, cfg, mechs, weapons, t):
    basenames = find_loadout_basenames(folder)
    if not basenames:
        print(t("no_xml_found"))
        return

    plan, skipped = build_plan(folder, prefix, add_suffix, keep_original, mechs, weapons, t)

    if skipped:
        print(t("skipped_header", n=len(skipped)))
        for basename, reason in skipped:
            print(t("skipped_line", name=basename, reason=reason))

    if not plan:
        print(t("no_files_to_rename"))
        return

    print(t("preview_header"))
    for i, (old, new) in enumerate(plan, start=1):
        marker = t("unchanged_marker") if old == new else ""
        print(f" {i:3d}. {old}  ->  {new}{marker}")

    print(t("selection_help"))
    while True:
        selection = parse_selection(input(t("selection_prompt")), len(plan), t)
        if selection is not None:
            break

    if not selection:
        print(t("none_renamed"))
        return

    if cfg["general"].getboolean("backup_before_rename", fallback=True):
        backup_path = make_backup(folder)
        print(t("backup_created", path=backup_path))

    used_names = {p.name.lower() for p in folder.iterdir()}
    renamed_stems = []
    for i, (old, new_stem) in enumerate(plan, start=1):
        if i not in selection or old == new_stem:
            continue
        final_stem = new_stem
        for ext in (".xml", ".mwl"):
            src = folder / f"{old}{ext}"
            if not src.exists():
                continue
            used_names.discard(src.name.lower())
            target_name = unique_target(new_stem, ext, used_names)
            final_stem = Path(target_name).stem
            src.rename(folder / target_name)
        renamed_stems.append(final_stem)

    print(t("renamed_count", n=len(renamed_stems)))

    cfg["last_used"]["source_dir"] = str(folder)
    save_config(cfg)

    game_dir = cfg["general"].get("game_dir", "")
    if not game_dir or not renamed_stems:
        return
    if ask_yes_no(t, "ask_copy_to_game", path=game_dir):
        dest = Path(game_dir)
        copied = 0
        overwritten = 0
        for stem in renamed_stems:
            for ext in (".xml", ".mwl"):
                src = folder / f"{stem}{ext}"
                if not src.exists():
                    continue
                target = dest / f"{stem}{ext}"
                if target.exists():
                    overwritten += 1
                shutil.copy2(src, target)
                copied += 1
        print(t("copy_done", n=copied))
        if overwritten:
            print(t("copy_overwritten", n=overwritten))


def do_advanced(cfg, mechs, weapons, t):
    source_dir = cfg["last_used"].get("source_dir", "")
    folder = ask_folder(t, "pick_source_title", source_dir or None)

    add_prefix = ask_yes_no(t, "ask_prefix_yn")
    prefix = input(t("ask_prefix_text")).strip() if add_prefix else ""
    add_suffix = ask_yes_no(t, "ask_suffix_yn")
    keep_original = ask_yes_no(t, "ask_keep_original_yn")

    cfg["last_used"]["add_prefix"] = str(add_prefix).lower()
    cfg["last_used"]["prefix"] = prefix
    cfg["last_used"]["add_suffix"] = str(add_suffix).lower()
    cfg["last_used"]["keep_original"] = str(keep_original).lower()
    save_config(cfg)

    run_rename(folder, prefix, add_suffix, keep_original, cfg, mechs, weapons, t)


def do_quick(cfg, mechs, weapons, t):
    last = cfg["last_used"]
    prefix = last.get("prefix", "") if last.getboolean("add_prefix", fallback=False) else ""
    add_suffix = last.getboolean("add_suffix", fallback=True)
    keep_original = last.getboolean("keep_original", fallback=True)

    source_dir = last.get("source_dir", "")
    folder = ask_folder(t, "pick_source_title", source_dir or None)

    run_rename(folder, prefix, add_suffix, keep_original, cfg, mechs, weapons, t)


def quick_example(cfg):
    last = cfg["last_used"]
    parts = []
    if last.getboolean("add_prefix", fallback=False) and last.get("prefix", ""):
        parts.append(last.get("prefix"))
    parts.append("ANH-1P")
    if last.getboolean("keep_original", fallback=True):
        parts.append("1v1")
    if last.getboolean("add_suffix", fallback=True):
        parts.append("3LL")
    return " ".join(parts)


def settings_menu(cfg, t):
    while True:
        print(t("settings_title"))
        lang = cfg["general"].get("language", "en")
        game_dir = cfg["general"].get("game_dir", "") or t("settings_gamedir_none")
        install_dir = cfg["general"].get("game_install_dir", "") or t("settings_gamedir_none")
        backup_state = t("state_on") if cfg["general"].getboolean("backup_before_rename", fallback=True) else t("state_off")
        print(f"1) {t('settings_lang', lang=lang)}")
        print(f"2) {t('settings_gamedir', path=game_dir)}")
        print(f"3) {t('settings_installdir', path=install_dir)}")
        print(f"4) {t('settings_backup', state=backup_state)}")
        print(f"5) {t('settings_back')}")
        choice = input(t("menu_prompt")).strip()

        if choice == "1":
            new_lang = ask_language()
            cfg["general"]["language"] = new_lang
            save_config(cfg)
            t = Translator(new_lang)
        elif choice == "2":
            picked_path = ask_folder(t, "pick_gamedir_title", allow_skip=True, manual_prompt_key="manual_gamedir_prompt")
            if picked_path:
                if not looks_like_loadouts_dir(picked_path):
                    print(t("gamedir_suffix_warning"))
                cfg["general"]["game_dir"] = str(picked_path)
                save_config(cfg)
                print(t("gamedir_saved", path=picked_path))
        elif choice == "3":
            picked_path = ask_folder(t, "pick_installdir_title", allow_skip=True, manual_prompt_key="manual_installdir_prompt")
            if picked_path:
                if not has_gamedata_pak(picked_path):
                    print(t("installdir_invalid"))
                else:
                    cfg["general"]["game_install_dir"] = str(picked_path)
                    save_config(cfg)
                    print(t("installdir_saved", path=picked_path))
        elif choice == "4":
            current = cfg["general"].getboolean("backup_before_rename", fallback=True)
            cfg["general"]["backup_before_rename"] = str(not current).lower()
            save_config(cfg)
        elif choice == "5":
            return t
        else:
            print(t("menu_invalid"))


def main():
    mechs_csv = SCRIPT_DIR / "mechs.csv"
    weapons_csv = SCRIPT_DIR / "weapons.csv"
    if not mechs_csv.exists() or not weapons_csv.exists():
        print(f"Erreur : mechs.csv et weapons.csv doivent etre a cote de ce script ({SCRIPT_DIR})")
        sys.exit(1)
    if not (LOCALES_DIR / "en.json").exists():
        print(f"Erreur : le dossier locales/ (avec au moins en.json) doit etre a cote de ce script ({SCRIPT_DIR})")
        sys.exit(1)

    mechs = load_mechs(mechs_csv)
    weapons = load_weapons(weapons_csv)
    tonnage = load_tonnage(SCRIPT_DIR / "mech_tonnage.csv")

    cfg = load_config()
    if not CONFIG_PATH.exists():
        t = first_run_setup(cfg)
    else:
        lang = cfg["general"].get("language", "en")
        if lang not in available_languages():
            lang = "en"
        t = Translator(lang)

    while True:
        print(t("menu_title"))
        print(f"1) {t('menu_quick')}  ({t('menu_quick_example', example=quick_example(cfg))})")
        print(f"2) {t('menu_advanced')}")
        print(f"3) {t('menu_import')}")
        print(f"4) {t('menu_export')}")
        print(f"5) {t('menu_update')}")
        print(f"6) {t('menu_reset')}")
        print(f"7) {t('menu_settings')}")
        print(f"8) {t('menu_exit')}")
        choice = input(t("menu_prompt")).strip()

        if choice == "1":
            do_quick(cfg, mechs, weapons, t)
        elif choice == "2":
            do_advanced(cfg, mechs, weapons, t)
        elif choice == "3":
            do_import(cfg, mechs, weapons, t)
        elif choice == "4":
            do_export(cfg, mechs, tonnage, t)
        elif choice == "5":
            do_update(cfg, mechs, weapons, tonnage, t)
        elif choice == "6":
            t = do_reset(cfg, mechs, weapons, tonnage, t)
        elif choice == "7":
            t = settings_menu(cfg, t)
        elif choice == "8":
            break
        else:
            print(t("menu_invalid"))


if __name__ == "__main__":
    main()
