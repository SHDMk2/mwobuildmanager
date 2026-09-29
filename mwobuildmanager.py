#!/usr/bin/env python3
"""MechLoadout Renamer : renommage, import/export et statistiques des loadouts
MechWarrior Online (.xml / .mwl).

Usage : python3 mwobuildmanager.py (ou les lanceurs launch_*).
Les tables CSV (mechs, armes, equipements...) doivent etre a cote de ce script.
Compatible Linux et Windows (bibliotheque standard uniquement).
"""

import configparser
import csv
import functools
import io
import json
import os
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
DATA_DIR = SCRIPT_DIR / "data"
# toutes les tables CSV vivent dans data/ (avant la 1.6 : a cote du script)
DATA_FILES = ("mechs.csv", "weapons.csv", "equipment.csv", "engines.csv", "omnipods.csv",
              "weapon_ranges.csv", "targeting_computers.csv", "heatsinks.csv",
              "build_registry.csv")
INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')
MAX_WEAPON_TYPES = 3
MWO_STEAM_APPID = "342200"
WEIGHT_CLASSES = ((35, "Light"), (55, "Medium"), (75, "Heavy"), (100, "Assault"))
ENGINE_MODES = ("all", "type", "none")
DEFAULT_STRUCTURE_MODIFIER = 0.5
# Capacite de chaleur de base d'un mech : codee dans le moteur du jeu, elle
# n'apparait nulle part dans GameData.pak (les refroidisseurs s'y ajoutent).
BASE_HEAT_CAPACITY = 30.0
# Tout moteur fournit gratuitement jusqu'a 10 refroidisseurs internes ; au-dela
# de 250 de puissance il garde des emplacements internes en plus, a remplir.
FREE_ENGINE_HEATSINKS = 10

# Blocs du nom, dans l'ordre par defaut (option name_order du cfg). Deux blocs
# voisins de NAME_CHAIN_BLOCKS sont joints par "-", les autres par une espace.
NAME_BLOCKS = ("prefix", "variant", "original", "weapons", "equipment", "heatsink", "engine")
NAME_CHAIN_BLOCKS = ("weapons", "equipment")
# Colonnes connues de l'export CSV, dans l'ordre par defaut (option csv_columns
# du cfg) : identite, chassis, moteur, armement, chaleur, PV, puis provenance.
EXPORT_CSV_COLUMNS = ("name", "mechvariant", "class", "tonnage", "tech", "buildcode",
                      "engine_type", "engine_rating", "max_speed",
                      "weapons", "equipment", "jumpjets",
                      "heatsink_type", "heatsinks", "heat_dissipation", "max_heat",
                      "optimal_range", "leg_hp", "kill_hp", "total_hp",
                      "owner", "date")
PROJECT_URL = "https://github.com/SHDMk2/mwobuildmanager"
REGISTRY_PATH = DATA_DIR / "build_registry.csv"

# Engine_<type>_<rating> dans Engines.xml -> abreviation du type
ENGINE_TYPE_ABBR = {"Std": "STD", "XL": "XL", "Light": "LFE", "Clan_XL": "CXL"}

# Equipements speciaux : (motif sur le nom interne, abreviation). Le premier
# motif qui correspond gagne ("MASCSuperchargerMKIII" doit donner SC, pas MASC).
JUMP_JET_PATTERN = re.compile(r"JumpJets|^Wing_")
EQUIPMENT_PATTERNS = (
    (JUMP_JET_PATTERN, "JJ"),
    (re.compile(r"Supercharger"), "SC"),
    (re.compile(r"MASC"), "MASC"),
    (re.compile(r"ECM$"), "ECM"),
    (re.compile(r"Probe$"), "BAP"),
    (re.compile(r"TAG$"), "TAG"),
    (re.compile(r"NarcBeacon$"), "NARC"),
    (re.compile(r"AntiMissileSystem$"), "AMS"),
)
EQUIPMENT_ORDER = ["JJ", "MASC", "SC", "ECM", "BAP", "TAG", "NARC", "AMS"]
EQUIPMENT_SOURCES = (
    ("Libs/Items/Modules/JumpJets.xml", "Module"),
    ("Libs/Items/Modules/MASC.xml", "Module"),
    ("Libs/Items/Modules/Equipment.xml", "Module"),
    ("Libs/Items/Weapons/Weapons.xml", "Weapon"),
)
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

# Options ecrites dans config.cfg quand elles manquent, pour que le fichier
# montre tous les reglages disponibles. "language" en est absent : il est
# demande au premier lancement.
CONFIG_DEFAULTS = {
    "general": {
        "game_dir": "",
        "game_install_dir": "",
        "backup_before_rename": "true",
        "structure_modifier": f"{DEFAULT_STRUCTURE_MODIFIER:g}",
        "dhs_rename": "false",
        "name_order": ",".join(NAME_BLOCKS),
        "csv_columns": ",".join(EXPORT_CSV_COLUMNS),
    },
    "last_used": {
        "add_prefix": "false",
        "prefix": "",
        "add_suffix": "true",
        "add_equipment": "false",
        "engine_mode": "none",
        "keep_original": "true",
        "source_dir": "",
        "import_dir": "",
        "export_dir": "",
    },
}


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


def apply_config_defaults(cfg):
    """Complete config.cfg avec les options manquantes (voir CONFIG_DEFAULTS) et
    renvoie le nombre de lignes ajoutees. Une option deja presente, meme vide,
    n'est jamais touchee."""
    added = 0
    for section, defaults in CONFIG_DEFAULTS.items():
        if section not in cfg:
            cfg[section] = {}
        for key, value in defaults.items():
            if key not in cfg[section]:
                cfg[section][key] = value
                added += 1
    if added:
        save_config(cfg)
    return added


def bool_option(cfg, key, default):
    """getboolean tolerant : une valeur illisible retombe sur le defaut."""
    try:
        return cfg["general"].getboolean(key, fallback=default)
    except ValueError:
        return default


def list_option(cfg, key, allowed, default):
    """Option "a,b,c" du cfg -> (liste retenue, noms inconnus ignores).
    Liste vide ou illisible = ordre par defaut."""
    kept, unknown = [], []
    for name in re.split(r"[,;]", cfg["general"].get(key, "")):
        name = name.strip().lower()
        if not name:
            continue
        if name not in allowed:
            if name not in unknown:
                unknown.append(name)
        elif name not in kept:
            kept.append(name)
    return (kept or list(default)), unknown


def naming_options(cfg):
    """Reglages de nommage venant de [general], ajoutes aux options de renommage."""
    order, _unknown = list_option(cfg, "name_order", NAME_BLOCKS, NAME_BLOCKS)
    return {"name_order": order, "dhs_rename": bool_option(cfg, "dhs_rename", False)}


def csv_columns(cfg):
    columns, _unknown = list_option(cfg, "csv_columns", EXPORT_CSV_COLUMNS, EXPORT_CSV_COLUMNS)
    return columns


def warn_unknown_options(cfg, t):
    for key, allowed in (("name_order", NAME_BLOCKS), ("csv_columns", EXPORT_CSV_COLUMNS)):
        _kept, unknown = list_option(cfg, key, allowed, ())
        if unknown:
            print(t("option_unknown_values", option=key, values=", ".join(unknown),
                    known=", ".join(allowed)))


# ---------------------------------------------------------------------------
# Mechs / weapons CSV lookup tables (see rename rules from the game data)

def load_mechs(path):
    mechs = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mechs[row["id"]] = (row["chassis"], row["variant"])
    return mechs


def load_weapons(path):
    """id -> (abreviation, tonnage). Un tonnage vide ou illisible (edition a la
    main) compte pour 0 au lieu de faire planter le programme."""
    return {row["id"]: (row.get("abbreviation", "").strip(), _to_float(row.get("tons")) or 0.0)
            for row in read_csv_rows(path)}


def read_csv_rows(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_engines(path):
    """id -> (type, rating, refroidisseurs internes), ex. "3558" -> ("LFE",
    "300", 12), plus les ids des XL Inner Sphere (seuls moteurs qui meurent a la
    perte d'un side torso). La colonne internal_heatsinks manque dans un
    engines.csv d'avant la 1.7 : elle compte alors pour 0."""
    engines = {}
    is_xl = set()
    for row in read_csv_rows(path):
        engines[row["id"]] = (row["type"].strip(), row["rating"].strip(),
                              _to_int(row.get("internal_heatsinks")) or 0)
        if row.get("name", "").startswith("Engine_XL_"):
            is_xl.add(row["id"])
    return engines, is_xl


def load_equipment(path):
    """-> (id -> abreviation, ordre d'affichage, ids des jump jets). L'ordre est
    celui de la premiere apparition de chaque abreviation dans le fichier ; une
    abreviation vide desactive la ligne (sauf pour le comptage des jump jets)."""
    equipment = {}
    order = []
    jump_jets = set()
    for row in read_csv_rows(path):
        if JUMP_JET_PATTERN.search(row.get("name", "")):
            jump_jets.add(row["id"])
        abbr = row["abbreviation"].strip()
        if not abbr:
            continue
        equipment[row["id"]] = abbr
        if abbr not in order:
            order.append(abbr)
    return equipment, order, jump_jets


def _to_int(text):
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def load_mech_specs(path):
    """id -> caracteristiques du chassis lues dans mechs.csv (colonnes
    ajoutees par Update ; absentes d'un ancien mechs.csv = pas de stats)."""
    specs = {}
    for row in read_csv_rows(path):
        tonnage = _to_int(row.get("tonnage"))
        if tonnage is None:
            continue
        specs[row["id"]] = {
            "tech": row.get("tech", ""),
            "tonnage": tonnage,
            "speed_factor": _to_float(row.get("speed_factor")) or 16.2,
            "ct_omnipod": row.get("ct_omnipod", ""),
            "fixed_items": [i for i in row.get("fixed_items", "").split(";") if i],
            "hp": {code: _to_float(row.get(f"hp_{code}")) or 0.0 for code in COMPONENT_CODES.values()},
            "quirks": quirks_from_text(row.get("quirks", "")),
        }
    return specs


def load_omnipods(path):
    """-> (id -> pod, set -> [(nb de pods requis, quirks)])."""
    pods = {}
    set_bonuses = {}
    for row in read_csv_rows(path):
        quirks = quirks_from_text(row.get("quirks", ""))
        if row["component"].startswith("set_bonus_"):
            pieces = _to_int(row["component"][len("set_bonus_"):]) or 8
            set_bonuses.setdefault(row["set"], []).append((pieces, quirks))
        elif row["id"]:
            pods[row["id"]] = {
                "set": row["set"],
                "fixed_items": [i for i in row.get("fixed_items", "").split(";") if i],
                "quirks": quirks,
            }
    return pods, set_bonuses


def load_heatsinks(path):
    """id du type de refroidisseur (balise <Upgrades><HeatSinks>) -> stats du
    refroidisseur correspondant : abreviation (SHS / DHS), dissipation et
    capacite de chaleur, en version interne au moteur ou externe."""
    sinks = {}
    for row in read_csv_rows(path):
        sinks[row["upgrade_id"]] = {
            "item": row.get("item_id", "").strip(),
            "abbr": row.get("abbreviation", "").strip(),
            "dissipation": _to_float(row.get("dissipation")) or 0.0,
            "engine_dissipation": _to_float(row.get("engine_dissipation")) or 0.0,
            "capacity": _to_float(row.get("capacity")) or 0.0,
            "engine_capacity": _to_float(row.get("engine_capacity")) or 0.0,
        }
    return sinks


def load_weapon_ranges(path):
    """id -> (nom interne, portee optimale, familles pour les quirks)."""
    return {row["id"]: (row["name"], _to_float(row.get("optimal_range")),
                        set(filter(None, row.get("aliases", "").split(";"))))
            for row in read_csv_rows(path)}


def load_targeting_computers(path):
    """id du TC -> [(noms d'armes compatibles, multiplicateur de portee)]."""
    tcs = {}
    for row in read_csv_rows(path):
        multiplier = _to_float(row.get("range_multiplier"))
        if multiplier:
            tcs.setdefault(row["id"], []).append((set(row["weapons"].split(";")), multiplier))
    return tcs


def load_gamedata():
    equipment, order, jump_jets = load_equipment(DATA_DIR / "equipment.csv")
    engines, is_xl = load_engines(DATA_DIR / "engines.csv")
    pods, set_bonuses = load_omnipods(DATA_DIR / "omnipods.csv")
    return {
        "engines": engines,
        "is_xl_engines": is_xl,
        "equipment": equipment,
        "equipment_order": order,
        "jump_jets": jump_jets,
        "mech_specs": load_mech_specs(DATA_DIR / "mechs.csv"),
        "pods": pods,
        "set_bonuses": set_bonuses,
        "heatsinks": load_heatsinks(DATA_DIR / "heatsinks.csv"),
        "weapon_ranges": load_weapon_ranges(DATA_DIR / "weapon_ranges.csv"),
        "targeting_computers": load_targeting_computers(DATA_DIR / "targeting_computers.csv"),
    }


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


# ---------------------------------------------------------------------------
# Metadonnees d'un build (proprietaire, date de decouverte) : 3 lignes de
# commentaire XML sous la balise <Loadout>, doublees d'un registre local
# (build_registry.csv, cle = code de build) qui les restaure si le jeu reecrit
# le fichier et efface les commentaires.

META_OWNER = re.compile(r"<!--\s*owner:(.*?)-->")
META_DATE = re.compile(r"<!--\s*date:(.*?)-->")
META_CREDIT = f"Generated by Mwobuildmanager ({PROJECT_URL})"
# reconnait aussi l'ancienne ligne (lien seul) pour la remplacer
META_LINE = re.compile(r"^[ \t]*<!--\s*(?:owner:|date:|Generated by Mwobuildmanager|"
                       + re.escape(PROJECT_URL) + r").*?-->[ \t]*\r?\n",
                       re.MULTILINE)


def today():
    return datetime.now().strftime("%Y-%m-%d")


def normalize_date(text):
    """aaaa-mm-jj ; accepte aussi jj.mm.aaaa et jj/mm/aaaa. "" si illisible."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def clean_owner(text):
    # "--" est interdit dans un commentaire XML
    return re.sub(r"-{2,}", "-", (text or "").replace("\n", " ")).strip()


def read_build_meta(xml_path):
    try:
        raw = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"owner": "", "date": ""}
    owner = META_OWNER.search(raw)
    date = META_DATE.search(raw)
    return {"owner": clean_owner(owner.group(1)) if owner else "",
            "date": normalize_date(date.group(1)) if date else ""}


def write_build_meta(xml_path, meta):
    """(Re)ecrit les 3 lignes juste apres la balise <Loadout ...>, en gardant
    les fins de ligne du fichier. N'ecrit rien si le contenu est identique."""
    with open(xml_path, encoding="utf-8", errors="replace", newline="") as f:
        raw = f.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    body = META_LINE.sub("", raw)
    first_line_end = body.find("\n") + 1
    if first_line_end == 0:
        return
    block = newline.join([f" <!-- owner: {meta['owner']} -->", f" <!-- date: {meta['date']} -->",
                          f" <!-- {META_CREDIT} -->"]) + newline
    updated = body[:first_line_end] + block + body[first_line_end:]
    if updated != raw:
        with open(xml_path, "w", encoding="utf-8", newline="") as f:
            f.write(updated)


def load_registry():
    return {row["code"]: {"owner": row.get("owner", ""), "date": row.get("date", "")}
            for row in read_csv_rows(REGISTRY_PATH) if row.get("code")}


def save_registry(registry):
    rows = [[code, meta["owner"], meta["date"]] for code, meta in sorted(registry.items())]
    with open(REGISTRY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["code", "owner", "date"])
        writer.writerows(rows)


def stamp_build(folder, stem, registry, fallback_owner, preferred=None):
    """Complete les metadonnees d'un build : ce qui est deja dans le fichier est
    garde ; sinon les valeurs importees (CSV), puis le registre, puis le profil
    courant et la date du jour. Ecrit le fichier et le registre, renvoie le resultat."""
    xml_path = Path(folder) / f"{stem}.xml"
    mwl_path = Path(folder) / f"{stem}.mwl"
    if not xml_path.exists():
        return {"owner": "", "date": ""}
    code = mwl_path.read_text(encoding="utf-8", errors="replace").strip() if mwl_path.exists() else ""

    sources = [read_build_meta(xml_path), preferred or {}, registry.get(code, {}),
               {"owner": fallback_owner, "date": today()}]
    meta = {}
    for field in ("owner", "date"):
        clean = clean_owner if field == "owner" else normalize_date
        meta[field] = next((clean(src.get(field)) for src in sources if clean(src.get(field))), "")

    write_build_meta(xml_path, meta)
    if code:
        registry[code] = meta
    return meta


def fallback_owner(cfg):
    game_dir = cfg["general"].get("game_dir", "")
    return current_profile_name(game_dir) if game_dir else ""


def sanitize(name):
    name = INVALID_CHARS.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def loadout_from_xml(xml_path):
    """Loadout sauvegarde -> {mech_id, heatsinks (type de refroidisseur), items,
    pods (composant -> id), armor (armure avant par composant)} ; None si le
    fichier est illisible."""
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None
    loadout = {"mech_id": root.attrib.get("MechID", ""), "heatsinks": "",
               "items": [], "pods": {}, "armor": {}}
    upgrade = root.find("Upgrades/HeatSinks")
    if upgrade is not None:
        loadout["heatsinks"] = upgrade.attrib.get("ItemID", "")
    for comp in root.iter("component"):
        name = comp.attrib.get("name", "")
        if name in COMPONENT_CODES:
            loadout["armor"][name] = _to_int(comp.attrib.get("Armor")) or 0
            if comp.attrib.get("Omnipod"):
                loadout["pods"][name] = comp.attrib["Omnipod"]
        loadout["items"].extend(el.attrib["ItemID"] for el in comp
                                if el.tag in ("Weapon", "Module") and el.attrib.get("ItemID"))
    return loadout


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
    code, seul celui qui donne le plus de codes lisibles est retenu.
    -> (codes, code -> {owner, date}) si l'en-tete a des colonnes owner / date."""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    checked = {}

    def is_code(cell):
        cell = cell.strip()
        if cell not in checked:
            checked[cell] = looks_like_build_code(cell)
        return checked[cell]

    best_codes, best_meta = [], {}
    for delimiter in (",", ";", "\t"):
        rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter))
        scores = {}
        for row in rows:
            for column, cell in enumerate(row):
                if is_code(cell):
                    scores[column] = scores.get(column, 0) + 1
        if not scores:
            continue
        column = max(scores, key=scores.get)
        header = [cell.strip().lower() for cell in rows[0]] if rows else []
        extra = {field: header.index(field) for field in ("owner", "date") if field in header}
        codes, meta = [], {}
        for row in rows:
            if column < len(row) and is_code(row[column]):
                code = row[column].strip()
                if code in meta:  # meme code sur plusieurs lignes : un seul build
                    continue
                codes.append(code)
                meta[code] = {field: row[index] for field, index in extra.items() if index < len(row)}
        if len(codes) > len(best_codes):
            best_codes, best_meta = codes, meta
    return best_codes, best_meta


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


def loadout_from_build(build):
    """Build decode depuis un code -> meme forme que loadout_from_xml()."""
    loadout = {"mech_id": build["mech_id"], "heatsinks": build["heatsinks"],
               "items": [], "pods": {}, "armor": {}}
    for name, armor, omnipod, items in build["components"]:
        loadout["armor"][name] = armor
        if omnipod is not None:
            loadout["pods"][name] = str(omnipod)
        loadout["items"].extend(str(item_id) for item_id in items)
    return loadout


def equipped_pods(loadout, gamedata):
    """Pods montes, y compris le pod de centre torse (fixe, absent du loadout)."""
    spec = gamedata["mech_specs"].get(loadout["mech_id"])
    pod_ids = list(loadout["pods"].values())
    if spec and spec["ct_omnipod"] and "centre_torso" not in loadout["pods"]:
        pod_ids.append(spec["ct_omnipod"])
    return [gamedata["pods"][pod_id] for pod_id in pod_ids if pod_id in gamedata["pods"]]


def effective_item_ids(loadout, gamedata):
    """Objets du loadout + objets fixes du chassis (moteur d'OmniMech, MASC...)
    et des pods (jump jets...), qui n'apparaissent pas dans le loadout."""
    if loadout is None:
        return []
    items = list(loadout["items"])
    spec = gamedata["mech_specs"].get(loadout["mech_id"])
    if spec:
        items.extend(spec["fixed_items"])
    for pod in equipped_pods(loadout, gamedata):
        items.extend(pod["fixed_items"])
    return items


def mech_quirks(loadout, gamedata):
    """Quirks du chassis + des pods montes + bonus de set atteints."""
    quirks = {}

    def add(source):
        for name, value in source.items():
            quirks[name] = quirks.get(name, 0.0) + value

    spec = gamedata["mech_specs"].get(loadout["mech_id"])
    if spec:
        add(spec["quirks"])
    pieces = {}
    for pod in equipped_pods(loadout, gamedata):
        add(pod["quirks"])
        pieces[pod["set"]] = pieces.get(pod["set"], 0) + 1
    for set_name, count in pieces.items():
        for required, bonus in gamedata["set_bonuses"].get(set_name, []):
            if count >= required:
                add(bonus)
    return quirks


def optimal_range_of_build(item_ids, quirks, weapons, gamedata):
    """Portee optimale du groupe d'armes le plus lourd (quantite x tonnage) :
    optimale x (1 + quirks de portee applicables) x bonus du Targeting Computer."""
    groups = {}
    for item_id in item_ids:
        if item_id in weapons and item_id not in gamedata["equipment"]:
            qty, tons = groups.get(item_id, (0, 0.0))
            groups[item_id] = (qty + 1, tons + weapons[item_id][1])
    if not groups:
        return None
    heaviest = max(groups, key=lambda item_id: groups[item_id][1])
    name, base_range, aliases = gamedata["weapon_ranges"].get(heaviest, ("", None, set()))
    if base_range is None:
        return None

    bonus = 0.0
    for quirk, value in quirks.items():
        if quirk.endswith("_range_multiplier"):
            family = quirk[:-len("_range_multiplier")]
            if family == "all" or family in aliases:
                bonus += value

    tc_multiplier = 1.0
    for item_id in item_ids:
        for compatible, multiplier in gamedata["targeting_computers"].get(item_id, []):
            if name in compatible:
                tc_multiplier = max(tc_multiplier, multiplier)
    return base_range * (1 + bonus) * tc_multiplier


def heatsink_counts(loadout, item_ids, gamedata):
    """-> (stats du type de refroidisseur, nombre dans le moteur, nombre hors
    moteur). Le moteur en fournit gratuitement min(10, ses emplacements) ; les
    refroidisseurs poses remplissent d'abord ses emplacements restants (au-dela
    de 250 de puissance), puis les emplacements de crit normaux.
    (None, 0, 0) si le type de refroidisseur est inconnu."""
    info = gamedata["heatsinks"].get((loadout or {}).get("heatsinks", ""))
    if not info:
        return None, 0, 0
    slots = next((gamedata["engines"][i][2] for i in item_ids if i in gamedata["engines"]), 0)
    total = min(FREE_ENGINE_HEATSINKS, slots) + sum(1 for i in item_ids if i == info["item"])
    in_engine = min(slots, total)
    return info, in_engine, total - in_engine


def heat_stats(loadout, item_ids, quirks, gamedata):
    """Colonnes de chaleur : type, nombre total (refroidisseurs du moteur
    compris), dissipation par seconde et capacite de chaleur, quirks du mech et
    de ses pods appliques. {} si le type de refroidisseur est inconnu."""
    info, in_engine, outside = heatsink_counts(loadout, item_ids, gamedata)
    if not info:
        return {}
    dissipation = in_engine * info["engine_dissipation"] + outside * info["dissipation"]
    capacity = (BASE_HEAT_CAPACITY + in_engine * info["engine_capacity"]
                + outside * info["capacity"])
    return {
        "heatsink_type": info["abbr"],
        "heatsinks": in_engine + outside,
        "heat_dissipation": f"{dissipation * (1 + quirks.get('heatdissipation_multiplier', 0.0)):.2f}",
        "max_heat": f"{capacity * (1 + quirks.get('maxheat_multiplier', 0.0)):.1f}",
    }


def weapon_summary(item_ids, weapons, gamedata):
    """Armes du build ("3ERLL/2ML"), du groupe le plus lourd au plus leger.
    Les equipements comptes a part (TAG, AMS...) sont exclus."""
    totals = {}
    for item_id in item_ids:
        if item_id in weapons and item_id not in gamedata["equipment"]:
            abbr, tons = weapons[item_id]
            qty, weight = totals.get(abbr, (0, 0.0))
            totals[abbr] = (qty + 1, weight + tons)
    ordered = sorted(totals.items(), key=lambda item: (-item[1][1], item[0]))
    return "/".join(abbr if qty == 1 else f"{qty}{abbr}" for abbr, (qty, _weight) in ordered)


def component_hp(loadout, spec, quirks, structure_modifier):
    """PV par composant : armure avant + quirks d'armure
    + (structure + quirks de structure) x modificateur de structure."""
    modifier = structure_modifier + abs(quirks.get("critchance_receiving_multiplier", 0.0)) / 2
    structure_bonus = 1 + quirks.get("increasedstructure_multiplier", 0.0)
    hp = {}
    for name, code in COMPONENT_CODES.items():
        armor = (loadout["armor"].get(name, 0)
                 + quirks.get(f"armorresist_{code}_additive", 0.0)
                 + quirks.get("armorresist_all_additive", 0.0))
        structure = (spec["hp"][code] * structure_bonus
                     + quirks.get(f"internalresist_{code}_additive", 0.0)
                     + quirks.get("internalresist_all_additive", 0.0))
        hp[code] = armor + structure * modifier
    return hp


def build_stats(loadout, weapons, gamedata, structure_modifier):
    """Colonnes statistiques de l'export CSV ; {} si le mech est inconnu de mechs.csv."""
    spec = gamedata["mech_specs"].get(loadout["mech_id"]) if loadout else None
    if not spec:
        return {}
    item_ids = effective_item_ids(loadout, gamedata)
    quirks = mech_quirks(loadout, gamedata)

    stats = {"tech": spec["tech"], "tonnage": spec["tonnage"],
             "weapons": weapon_summary(item_ids, weapons, gamedata),
             "jumpjets": sum(1 for item_id in item_ids if item_id in gamedata["jump_jets"])}
    stats.update(heat_stats(loadout, item_ids, quirks, gamedata))

    engine_id = next((item_id for item_id in item_ids if item_id in gamedata["engines"]), None)
    if engine_id:
        engine_type, rating, _internal = gamedata["engines"][engine_id]
        stats["engine_type"] = engine_type
        stats["engine_rating"] = rating
        if rating.isdigit():
            speed = (int(rating) / spec["tonnage"] * spec["speed_factor"]
                     * (1 + quirks.get("mechtopspeed_multiplier", 0.0)))
            stats["max_speed"] = f"{speed:.1f}"

    found = {gamedata["equipment"][item_id] for item_id in item_ids
             if item_id in gamedata["equipment"] and item_id not in gamedata["jump_jets"]}
    stats["equipment"] = "/".join(abbr for abbr in gamedata["equipment_order"] if abbr in found)

    rng = optimal_range_of_build(item_ids, quirks, weapons, gamedata)
    if rng is not None:
        stats["optimal_range"] = f"{rng:.0f}"

    hp = component_hp(loadout, spec, quirks, structure_modifier)
    kill = min(hp["lt"], hp["rt"]) if engine_id in gamedata["is_xl_engines"] else hp["ct"]
    stats["leg_hp"] = f"{hp['ll'] + hp['rl']:.1f}"
    stats["kill_hp"] = f"{kill:.1f}"
    stats["total_hp"] = f"{sum(hp.values()):.1f}"
    return stats


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


def engine_tag(item_ids, engines, mode):
    """XL300 (mode all), XL (mode type) ou "" (mode none, ou aucun moteur trouve)."""
    if mode == "none":
        return ""
    for item_id in item_ids:
        if item_id in engines:
            engine_type, rating, _internal = engines[item_id]
            return f"{engine_type}{rating}" if mode == "all" else engine_type
    return ""


def heatsink_tag(loadout, gamedata, dhs_rename):
    """"SHS" pour des refroidisseurs simples ; rien pour des doubles, sauf si
    l'option dhs_rename est activee (les doubles sont la norme)."""
    info = gamedata["heatsinks"].get((loadout or {}).get("heatsinks", ""))
    if not info or not info["abbr"]:
        return ""
    if info["abbr"].upper() == "DHS" and not dhs_rename:
        return ""
    return info["abbr"]


def join_name_blocks(order, blocks):
    """Assemble les blocs non vides dans l'ordre demande : "-" entre deux blocs
    voisins de NAME_CHAIN_BLOCKS (armes-equipements), une espace sinon."""
    parts = []
    previous = None
    for block in order:
        value = blocks.get(block, "")
        if not value:
            continue
        if parts:
            parts.append("-" if block in NAME_CHAIN_BLOCKS
                         and previous in NAME_CHAIN_BLOCKS else " ")
        parts.append(value)
        previous = block
    return "".join(parts)


def compose_name(loadout, item_ids, prefix, variant, original, opts, weapons, gamedata, t):
    """Par defaut : prefixe VARIANTE [original] [armes-equipements] [SHS] [moteur],
    l'ordre des blocs venant de opts["name_order"].
    Leve NoQualifyingWeapon si le suffixe d'armes est demande mais vide."""
    # avec l'option equipement, TAG/NARC/AMS passent dans le groupe equipement
    # au lieu d'etre classes (et comptes deux fois) parmi les armes
    equipment = gamedata["equipment"] if opts["add_equipment"] else {}
    blocks = {
        "prefix": prefix,
        "variant": variant.upper() if variant else "UNKNOWN",
        "original": original,
        "heatsink": heatsink_tag(loadout, gamedata, opts["dhs_rename"]),
        "engine": engine_tag(item_ids, gamedata["engines"], opts["engine_mode"]),
    }
    if opts["add_suffix"]:
        instances = [weapons[i] for i in item_ids if i in weapons and i not in equipment]
        blocks["weapons"] = build_suffix(instances, t)
    if equipment:
        found = {equipment[i] for i in item_ids if i in equipment}
        blocks["equipment"] = "-".join(abbr for abbr in gamedata["equipment_order"]
                                      if abbr in found)
    return sanitize(join_name_blocks(opts["name_order"], blocks))


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


def unique_pair_stem(base_name, used_names):
    """Nom de base libre a la fois pour le .xml et le .mwl d'un loadout."""
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

def has_display():
    """Faux sur un Linux sans session graphique : inutile d'essayer une fenetre."""
    if not sys.platform.startswith("linux"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pick_path_gui(title, initial_dir=None, directory=True):
    """-> (fenetre affichee, chemin). (True, None) = l'utilisateur a annule ;
    (False, None) = aucun selecteur graphique disponible."""
    if not has_display():
        return False, None
    start = initial_dir or str(Path.home())
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if directory:
            path = filedialog.askdirectory(title=title, initialdir=start)
        else:
            path = filedialog.askopenfilename(title=title, initialdir=start)
        root.destroy()
        return True, path or None
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        if directory:
            commands = (["zenity", "--file-selection", "--directory", f"--filename={start}/", "--title", title],
                        ["kdialog", "--getexistingdirectory", start, "--title", title])
        else:
            commands = (["zenity", "--file-selection", f"--filename={start}/", "--title", title],
                        ["kdialog", "--getopenfilename", start, "--title", title])
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
            except FileNotFoundError:
                continue
            if result.returncode == 0 and result.stdout.strip():
                return True, result.stdout.strip()
            if result.returncode == 1:  # zenity et kdialog : 1 = annule
                return True, None

    return False, None


def ask_folder(t, title_key, initial_dir=None, manual_prompt_key="manual_folder_prompt"):
    """Dossier choisi, ou None si l'utilisateur annule (fenetre fermee ou saisie vide)."""
    shown, picked = pick_path_gui(t(title_key), initial_dir, directory=True)
    if shown:
        return Path(picked) if picked and Path(picked).is_dir() else None

    print(t("gui_unavailable"))
    while True:
        folder_input = input(t(manual_prompt_key)).strip().strip('"')
        if not folder_input:
            return None
        folder = Path(folder_input).expanduser()
        if folder.is_dir():
            return folder
        print(t("folder_not_found"))


def ask_file(t, title_key, initial_dir=None):
    """Fichier choisi, ou None si l'utilisateur annule."""
    shown, picked = pick_path_gui(t(title_key), initial_dir, directory=False)
    if shown:
        return Path(picked) if picked and Path(picked).is_file() else None

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


def resolve_path_case(path):
    """Le meme chemin avec la casse reelle du disque, ou None s'il n'existe pas.
    Proton recree parfois le prefixe en minuscules ("saved games/mechwarrior
    online") : un chemin enregistre avec la casse du jeu semble alors disparu
    sous Linux alors que le dossier, lui, est toujours la."""
    path = Path(path)
    if path.exists():
        return path
    parts = path.parts
    if not parts:
        return None
    current = Path(parts[0])
    if not current.exists():
        return None
    for part in parts[1:]:
        if (current / part).exists():
            current = current / part
            continue
        try:
            matches = [c for c in current.iterdir() if c.name.lower() == part.lower()]
        except OSError:
            return None
        if len(matches) != 1:  # introuvable, ou plusieurs casses : on ne devine pas
            return None
        current = matches[0]
    return current


def steam_roots():
    home = Path.home()
    if sys.platform.startswith("linux"):
        return [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
    if sys.platform.startswith("win"):
        return [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    return []


def proton_users_dirs():
    """Dossiers 'users' des prefixes Proton de MWO (un par racine Steam)."""
    for root in steam_roots():
        users_dir = root / "steamapps/compatdata" / MWO_STEAM_APPID / "pfx/drive_c/users"
        if users_dir.is_dir():
            yield users_dir


def autodetect_loadouts_dir():
    """Dossier MechLoadouts le plus plausible : un prefixe Proton contient
    souvent un 'steamuser' fantome a cote du vrai profil, on garde celui qui a
    le plus de builds."""
    candidates = []

    if sys.platform.startswith("linux"):
        for users_dir in proton_users_dirs():
            for user_dir in sorted(users_dir.iterdir()):
                candidate = resolve_path_case(user_dir / "Saved Games/MechWarrior Online/MechLoadouts")
                if candidate and candidate.is_dir():
                    candidates.append(candidate)
    elif sys.platform.startswith("win"):
        candidate = Path.home() / "Saved Games/MechWarrior Online/MechLoadouts"
        if candidate.is_dir():
            candidates.append(candidate)

    if not candidates:
        return None
    return max(candidates, key=lambda d: (len(find_loadout_basenames(d)), d.stat().st_mtime))


def has_gamedata_pak(path):
    return (Path(path) / "Game" / "GameData.pak").is_file()


def autodetect_install_dir():
    for root in steam_roots():
        candidate = root / "steamapps/common/MechWarrior Online"
        if has_gamedata_pak(candidate):
            return candidate
    return None


def installdir_picker_start(cfg):
    """Dossier sur lequel ouvrir le selecteur d'installation."""
    cached = cfg["general"].get("game_install_dir", "")
    if cached and Path(cached).is_dir():
        return cached
    for root in steam_roots():
        common = root / "steamapps/common"
        if common.is_dir():
            return str(common)
    return None


def cached_game_dir(cfg):
    """Dossier de jeu enregistre, avec reparation de casse si le prefixe Proton
    a ete recree. None s'il n'est pas (ou plus) utilisable."""
    cached = cfg["general"].get("game_dir", "")
    if not cached:
        return None
    if Path(cached).is_dir():
        return Path(cached)
    repaired = resolve_path_case(cached)
    if repaired and repaired.is_dir():
        cfg["general"]["game_dir"] = str(repaired)
        save_config(cfg)
        return repaired
    return None


def gamedir_picker_start(cfg):
    """Dossier sur lequel ouvrir le selecteur : le plus proche du dossier de jeu
    connu, sinon le prefixe Proton, sinon rien (= home)."""
    cached = cfg["general"].get("game_dir", "")
    if cached:
        for candidate in (Path(cached), *Path(cached).parents):
            resolved = resolve_path_case(candidate)
            if resolved and resolved.is_dir():
                return str(resolved)
    for users_dir in proton_users_dirs():
        return str(users_dir)
    return None


def resolve_game_dir(cfg, t, use_cached=True, allow_pick=True):
    """Dossier MechLoadouts valide : valeur enregistree, auto-detection, ou
    dossier choisi par le joueur. None si celui-ci annule."""
    if use_cached:
        cached_raw = cfg["general"].get("game_dir", "")
        cached = cached_game_dir(cfg)
        if cached:
            if str(cached) != cached_raw:
                print(t("gamedir_repaired", path=cached))
            return cached
        if cached_raw:
            print(t("gamedir_missing", path=cached_raw))

    detected = autodetect_loadouts_dir()
    if detected:
        print(t("autodetect_found", path=detected))
        if ask_yes_no(t, "autodetect_confirm"):
            cfg["general"]["game_dir"] = str(detected)
            save_config(cfg)
            print(t("gamedir_saved", path=detected))
            return detected
    else:
        print(t("autodetect_not_found"))

    if not allow_pick:
        return None

    picked = ask_folder(t, "pick_gamedir_title", gamedir_picker_start(cfg),
                        manual_prompt_key="manual_gamedir_prompt")
    if picked is None:
        return None
    if not looks_like_loadouts_dir(picked):
        print(t("gamedir_suffix_warning"))
    cfg["general"]["game_dir"] = str(picked)
    save_config(cfg)
    print(t("gamedir_saved", path=picked))
    return picked


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
        picked = ask_folder(t, "pick_installdir_title", installdir_picker_start(cfg),
                             manual_prompt_key="manual_installdir_prompt")
        if picked is None:
            return None
        if has_gamedata_pak(picked):
            cfg["general"]["game_install_dir"] = str(picked)
            save_config(cfg)
            return picked
        print(t("installdir_invalid"))


def ask_engine_mode(t):
    answers = {"1": "all", "2": "type", "3": "none", "": "none"}
    while True:
        choice = input(t("ask_engine_mode")).strip()
        if choice in answers:
            return answers[choice]
        print(t("engine_mode_invalid"))


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

    cfg["general"]["language"] = lang
    cfg["general"]["backup_before_rename"] = "true"
    cfg["general"]["structure_modifier"] = str(DEFAULT_STRUCTURE_MODIFIER)
    if not resolve_game_dir(cfg, t, use_cached=False):
        print(t("gamedir_none"))

    cfg["last_used"]["add_prefix"] = "false"
    cfg["last_used"]["prefix"] = ""
    cfg["last_used"]["add_suffix"] = "true"
    cfg["last_used"]["add_equipment"] = "false"
    cfg["last_used"]["engine_mode"] = "none"
    cfg["last_used"]["keep_original"] = "true"
    cfg["last_used"]["source_dir"] = ""
    save_config(cfg)
    apply_config_defaults(cfg)
    return t


# ---------------------------------------------------------------------------
# Lecture des fichiers du jeu (Update / Reset)

@functools.lru_cache(maxsize=None)
def read_pak_xml(pak_path, entry_name):
    """Weapons.xml sert a trois tables : il n'est lu et analyse qu'une fois
    par Update (cache vide a la fin, cf. reload_tables)."""
    with zipfile.ZipFile(pak_path) as z:
        return ET.fromstring(z.read(entry_name))


# ---------------------------------------------------------------------------
# Donnees de jeu pour les statistiques (export CSV) : extraites de GameData.pak
# et des Game/mechs/<chassis>.pak (fichiers .mdf et <chassis>-omnipods.xml)

COMPONENT_CODES = {
    "head": "hd", "centre_torso": "ct", "left_torso": "lt", "right_torso": "rt",
    "left_arm": "la", "right_arm": "ra", "left_leg": "ll", "right_leg": "rl",
}
# seules les quirks utiles aux statistiques sont conservees dans les CSV
STAT_QUIRK = re.compile(
    r"^(mechtopspeed_multiplier|critchance_receiving_multiplier|increasedstructure_multiplier"
    r"|heatdissipation_multiplier|maxheat_multiplier"
    r"|(internalresist|armorresist)_[a-z]+_additive|[a-z0-9]+_range_multiplier)$")


def quirks_to_text(quirk_elements):
    """<Quirk name= value=> -> "nom=valeur;..." (valeurs identiques cumulees)."""
    totals = {}
    for el in quirk_elements:
        name = el.attrib.get("name", "").lower()
        if not STAT_QUIRK.match(name):
            continue
        try:
            totals[name] = totals.get(name, 0.0) + float(el.attrib.get("value", "0"))
        except ValueError:
            continue
    return ";".join(f"{name}={value:g}" for name, value in sorted(totals.items()))


def quirks_from_text(text):
    quirks = {}
    for pair in (text or "").split(";"):
        if "=" in pair:
            name, value = pair.split("=", 1)
            quirks[name] = quirks.get(name, 0.0) + float(value)
    return quirks


def iter_mech_pak_files(game_root, suffix):
    """(nom, racine XML) de chaque fichier se terminant par suffix dans Game/mechs/*.pak."""
    for pak in sorted((Path(game_root) / "mechs").glob("*.pak")):
        with zipfile.ZipFile(pak) as z:
            for name in z.namelist():
                if name.lower().endswith(suffix):
                    try:
                        yield name, ET.fromstring(z.read(name))
                    except ET.ParseError:
                        continue


MECHS_CSV_HEADER = (["id", "chassis", "variant", "tech", "tonnage", "speed_factor",
                     "ct_omnipod", "fixed_items"]
                    + [f"hp_{code}" for code in COMPONENT_CODES.values()] + ["quirks"])


def fetch_mechs_from_game(game_root):
    mdfs = {Path(name).stem.lower(): root for name, root in iter_mech_pak_files(game_root, ".mdf")}
    rows = []
    for el in read_pak_xml(Path(game_root) / "GameData.pak", "Libs/Items/Mechs/Mechs.xml").iter("Mech"):
        variant = el.attrib.get("name", "?")
        tech = "CLAN" if "clan" in el.attrib.get("faction", "").lower() else "IS"
        row = {"id": el.attrib["id"], "chassis": el.attrib.get("chassis", "?"),
               "variant": variant, "tech": tech}
        mdf = mdfs.get(variant.lower())
        if mdf is not None:
            mech = mdf.find("Mech")
            movement = mdf.find("MovementTuningConfiguration")
            row["tonnage"] = mech.attrib.get("MaxTons", "") if mech is not None else ""
            row["speed_factor"] = movement.attrib.get("MaxMovementSpeed", "") if movement is not None else ""
            fixed = []
            for comp in mdf.iter("Component"):
                code = COMPONENT_CODES.get(comp.attrib.get("Name", ""))
                if code:
                    row[f"hp_{code}"] = comp.attrib.get("HP", "")
                if comp.attrib.get("Name") == "centre_torso":
                    row["ct_omnipod"] = comp.attrib.get("OmniPod", "")
                fixed.extend(f.attrib["ItemID"] for f in comp.iter("Fixed") if f.attrib.get("ItemID"))
            row["fixed_items"] = ";".join(fixed)
            row["quirks"] = quirks_to_text(mdf.iter("Quirk"))
        rows.append([row.get(col, "") for col in MECHS_CSV_HEADER])
    rows.sort(key=lambda r: int(r[0]))
    return rows


def fetch_omnipods_from_game(game_root):
    """Une ligne par pod (id, chassis, set, composant, objets fixes, quirks) et
    une ligne par bonus de set (id vide, composant "set_bonus_<nb de pods>").
    Plusieurs ids peuvent partager le meme set + composant."""
    details = {}
    bonuses = []
    for _name, root in iter_mech_pak_files(game_root, "-omnipods.xml"):
        for pod_set in root.iter("Set"):
            set_name = pod_set.attrib.get("name", "").lower()
            for comp in pod_set.findall("component"):
                fixed = ";".join(f.attrib["ItemID"] for f in comp.iter("Fixed") if f.attrib.get("ItemID"))
                details[(set_name, comp.attrib.get("name", ""))] = (fixed, quirks_to_text(comp.iter("Quirk")))
            for bonus in pod_set.iter("Bonus"):
                quirks = quirks_to_text(bonus.iter("Quirk"))
                if quirks:
                    bonuses.append((set_name, bonus.attrib.get("PieceCount", "8"), quirks))

    rows = []
    chassis_of = {}
    for el in read_pak_xml(Path(game_root) / "GameData.pak", "Libs/Items/OmniPods.xml").iter("OmniPod"):
        set_name = el.attrib.get("set", "").lower()
        component = el.attrib.get("component", "")
        chassis_of[set_name] = el.attrib.get("chassis", "")
        fixed, quirks = details.get((set_name, component), ("", ""))
        rows.append([el.attrib["id"], chassis_of[set_name], set_name, component, fixed, quirks])
    for set_name, pieces, quirks in bonuses:
        rows.append(["", chassis_of.get(set_name, ""), set_name, f"set_bonus_{pieces}", "", quirks])
    rows.sort(key=lambda r: (r[2], r[0] == "", int(r[0] or 0)))
    return rows


def optimal_range(weapon_el):
    """Fin de la zone plein degats : le plus grand debut de palier a 100 %."""
    best = None
    for rng in weapon_el.iter("Range"):
        try:
            start = float(rng.attrib["start"])
            modifier = float(rng.attrib.get("damageModifier", "0"))
        except (KeyError, ValueError):
            continue
        if modifier >= 1.0 and (best is None or start > best):
            best = start
    return best


def fetch_weapon_ranges_from_pak(pak_path):
    rows = []
    for el in read_pak_xml(pak_path, "Libs/Items/Weapons/Weapons.xml").iter("Weapon"):
        rng = optimal_range(el)
        aliases = ";".join(a.strip().lower() for a in el.attrib.get("HardpointAliases", "").split(",") if a.strip())
        rows.append([el.attrib["id"], el.attrib.get("name", ""), f"{rng:g}" if rng is not None else "", aliases])
    rows.sort(key=lambda r: int(r[0]))
    return rows


def fetch_targeting_computers_from_pak(pak_path):
    rows = []
    for el in read_pak_xml(pak_path, "Libs/Items/Modules/Equipment.xml").iter("Module"):
        if el.attrib.get("CType") != "CTargetingComputerStats":
            continue
        for flt in el.iter("WeaponStatsFilter"):
            rng = flt.find("Range")
            if rng is None or not rng.attrib.get("multiplier"):
                continue
            rows.append([el.attrib["id"], el.attrib.get("name", ""),
                         flt.attrib.get("compatibleWeapons", "").replace(",", ";"), rng.attrib["multiplier"]])
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


def fetch_engines_from_pak(pak_path):
    root = read_pak_xml(pak_path, "Libs/Items/Modules/Engines.xml")
    rows = []
    for el in root:
        match = re.match(r"Engine_(.+)_(\d+)$", el.attrib.get("name", ""))
        if match:
            engine_type = ENGINE_TYPE_ABBR.get(match.group(1), match.group(1).upper())
            stats = el.find("EngineStats")
            internal = stats.attrib.get("heatsinks", "") if stats is not None else ""
            rows.append((el.attrib["id"], el.attrib["name"], engine_type, match.group(2), internal))
    rows.sort(key=lambda r: int(r[0]))
    return rows


HEATSINKS_CSV_HEADER = ["upgrade_id", "item_id", "name", "abbreviation",
                        "dissipation", "engine_dissipation", "capacity", "engine_capacity"]


def _positive(value):
    """Les capacites sont stockees en negatif dans le pak (elles retirent de la
    chaleur) ; on les garde en positif, c'est ce qu'elles ajoutent au maximum."""
    number = _to_float(value)
    return "" if number is None else f"{abs(number):g}"


def fetch_heatsinks_from_pak(pak_path):
    """Une ligne par type de refroidisseur (simple / double, IS / Clan), reliant
    l'id d'upgrade ecrit dans les loadouts aux stats de l'objet correspondant."""
    stats_by_id = {}
    for el in read_pak_xml(pak_path, "Libs/Items/Modules/Equipment.xml").iter("Module"):
        stats = el.find("HeatSinkStats")
        if stats is not None:
            stats_by_id[el.attrib["id"]] = stats.attrib

    rows = []
    for el in read_pak_xml(pak_path, "Libs/Items/UpgradeTypes/UpgradeTypes.xml").iter("UpgradeType"):
        if el.attrib.get("CType") != "HeatSink":
            continue
        type_stats = el.find("HeatSinkTypeStats")
        item_id = type_stats.attrib.get("compatibleHeatSink", "") if type_stats is not None else ""
        sink = stats_by_id.get(item_id)
        if not sink:
            continue
        loc = el.find("Loc")
        short_name = loc.attrib.get("shortNameTag", "") if loc is not None else ""
        rows.append((el.attrib["id"], item_id, el.attrib.get("name", ""),
                     "SHS" if "single" in short_name.lower() else "DHS",
                     sink.get("cooling", ""), sink.get("engineCooling", ""),
                     _positive(sink.get("heatbase")), _positive(sink.get("engineHeatbase"))))
    rows.sort(key=lambda r: int(r[0]))
    return rows


def guess_equipment_abbreviation(name):
    for pattern, abbr in EQUIPMENT_PATTERNS:
        if pattern.search(name):
            return abbr
    return None


def fetch_equipment_from_pak(pak_path):
    rows = []
    for entry, tag in EQUIPMENT_SOURCES:
        for el in read_pak_xml(pak_path, entry).iter(tag):
            name = el.attrib.get("name", "")
            abbr = guess_equipment_abbreviation(name)
            if abbr:
                rows.append((el.attrib["id"], name, abbr))
    return rows


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def _id_order(row):
    return (0, int(row[0])) if str(row[0]).isdigit() else (1, str(row[0]))


def _equipment_order(row):
    abbr = row[2]
    rank = EQUIPMENT_ORDER.index(abbr) if abbr in EQUIPMENT_ORDER else len(EQUIPMENT_ORDER)
    return (rank,) + _id_order(row)


def csv_header(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f), [])


def merge_table(path, header, fresh_rows, overwrite_existing, sort_key=_id_order):
    """Tables editables a la main (armes, equipements, moteurs). En mode ajout,
    une ligne deja presente n'est jamais modifiee (abreviations personnalisees
    conservees) : seuls les nouveaux ids du jeu sont ajoutes, et une colonne
    apparue avec une nouvelle version est remplie depuis le jeu. Le mode
    ecrasement (Reset) reecrit tout. Renvoie le nombre de lignes ajoutees."""
    rows = {}
    if not overwrite_existing:
        known = set(csv_header(path))
        fresh_by_id = {row[0]: list(row) for row in fresh_rows}
        for row in read_csv_rows(path):
            key = row[header[0]]
            fresh = fresh_by_id.get(key)
            rows[key] = [row.get(col, "") if col in known
                         else (fresh[i] if fresh and i < len(fresh) else "")
                         for i, col in enumerate(header)]
    added = 0
    for row in fresh_rows:
        if row[0] not in rows:
            rows[row[0]] = list(row)
            added += 1
    write_csv(path, header, sorted(rows.values(), key=sort_key))
    return added


def update_editable_tables(pak_path, overwrite_existing):
    """-> (armes ajoutees, equipements ajoutes, moteurs ajoutes)."""
    weapons = [(wid, name, tons, guess_abbreviation(name)) for wid, name, tons in fetch_weapons_from_pak(pak_path)]
    return (
        merge_table(DATA_DIR / "weapons.csv", ["id", "name", "tons", "abbreviation"], weapons,
                    overwrite_existing),
        merge_table(DATA_DIR / "equipment.csv", ["id", "name", "abbreviation"],
                    fetch_equipment_from_pak(pak_path), overwrite_existing, _equipment_order),
        merge_table(DATA_DIR / "engines.csv", ["id", "name", "type", "rating", "internal_heatsinks"],
                    fetch_engines_from_pak(pak_path), overwrite_existing),
    )


def write_game_tables(game_root):
    """Tables 100 % issues du jeu, regenerees entierement (jamais editees a la main)."""
    pak_path = game_root / "GameData.pak"
    return {
        "mechs": write_csv(DATA_DIR / "mechs.csv", MECHS_CSV_HEADER, fetch_mechs_from_game(game_root)),
        "pods": write_csv(DATA_DIR / "omnipods.csv",
                          ["id", "chassis", "set", "component", "fixed_items", "quirks"],
                          fetch_omnipods_from_game(game_root)),
        "ranges": write_csv(DATA_DIR / "weapon_ranges.csv", ["id", "name", "optimal_range", "aliases"],
                            fetch_weapon_ranges_from_pak(pak_path)),
        "tcs": write_csv(DATA_DIR / "targeting_computers.csv", ["id", "name", "weapons", "range_multiplier"],
                         fetch_targeting_computers_from_pak(pak_path)),
        "heatsinks": write_csv(DATA_DIR / "heatsinks.csv", HEATSINKS_CSV_HEADER,
                               fetch_heatsinks_from_pak(pak_path)),
    }


def reload_tables(mechs, weapons, gamedata):
    read_pak_xml.cache_clear()
    mechs.clear()
    mechs.update(load_mechs(DATA_DIR / "mechs.csv"))
    weapons.clear()
    weapons.update(load_weapons(DATA_DIR / "weapons.csv"))
    gamedata.clear()
    gamedata.update(load_gamedata())


def do_update(cfg, mechs, weapons, gamedata, t):
    install_dir = resolve_install_dir(cfg, t)
    if not install_dir:
        print(t("installdir_cancelled"))
        return

    game_root = install_dir / "Game"
    pak_path = game_root / "GameData.pak"
    counts = write_game_tables(game_root)
    added_weapons, added_equipment, added_engines = update_editable_tables(pak_path, overwrite_existing=False)
    reload_tables(mechs, weapons, gamedata)

    print(t("update_done", mechs=counts["mechs"], weapons=added_weapons))
    print(t("update_gear_done", engines=added_engines, equipment=added_equipment))
    print(t("update_stats_done", pods=counts["pods"], ranges=counts["ranges"],
            tcs=counts["tcs"], heatsinks=counts["heatsinks"]))


def do_reset(cfg, mechs, weapons, gamedata, t):
    if not ask_yes_no(t, "reset_confirm"):
        return t

    install_dir = resolve_install_dir(cfg, t)
    if not install_dir:
        print(t("installdir_cancelled"))
        return t

    game_root = install_dir / "Game"
    pak_path = game_root / "GameData.pak"
    write_game_tables(game_root)
    update_editable_tables(pak_path, overwrite_existing=True)
    reload_tables(mechs, weapons, gamedata)

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


def structure_modifier(cfg):
    value = _to_float(cfg["general"].get("structure_modifier", ""))
    return DEFAULT_STRUCTURE_MODIFIER if value is None else value


def export_csv(game_dir, basenames, dest_dir, name, mechs, weapons, gamedata, modifier, columns):
    """Une ligne par build : identite du build puis statistiques calculees.
    Les metadonnees manquantes sont completees dans les fichiers au passage."""
    owner = current_profile_name(game_dir)
    registry = load_registry()
    rows = []
    unknown = 0
    for basename in basenames:
        mwl_path = game_dir / f"{basename}.mwl"
        code = mwl_path.read_text(encoding="utf-8", errors="replace").strip() if mwl_path.exists() else ""
        loadout = loadout_from_xml(game_dir / f"{basename}.xml")
        _chassis, variant = mechs.get(loadout["mech_id"] if loadout else "", ("", ""))
        stats = build_stats(loadout, weapons, gamedata, modifier)
        if not stats:
            unknown += 1
        meta = stamp_build(game_dir, basename, registry, owner)
        stats.update({"name": basename, "buildcode": code, "mechvariant": (variant or "").upper(),
                      "owner": meta["owner"], "date": meta["date"]})
        if stats.get("tonnage"):
            stats["class"] = weight_class(stats["tonnage"])
        rows.append([stats.get(column, "") for column in columns])

    save_registry(registry)
    csv_path = dest_dir / f"{name}.csv"
    write_csv(csv_path, columns, rows)
    return csv_path, len(rows), unknown, owner


def do_export(cfg, mechs, weapons, gamedata, t):
    game_dir = resolve_game_dir(cfg, t)
    if game_dir is None:
        print(t("export_cancelled"))
        return

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
    dest_dir = ask_folder(t, "pick_export_dest_title", last_export_dir or None,
                          manual_prompt_key="manual_export_dest_prompt")
    if dest_dir is None:
        print(t("export_cancelled"))
        return

    if kind == "csv":
        csv_path, count, unknown, owner = export_csv(game_dir, basenames, dest_dir, name, mechs, weapons,
                                                     gamedata, structure_modifier(cfg), csv_columns(cfg))
        cfg["last_used"]["export_dir"] = str(dest_dir)
        save_config(cfg)
        print(t("export_csv_done", n=count, path=csv_path))
        if not owner:
            print(t("export_csv_no_owner"))
        if unknown:
            print(t("export_csv_no_specs", n=unknown))
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
            return read_pasted_codes(t), {}
        if choice in ("2", "3"):
            break
        print(t("import_source_invalid"))

    title_key = "pick_txt_title" if choice == "2" else "pick_csv_title"
    path = ask_file(t, title_key, cfg["last_used"].get("import_dir", "") or None)
    if path is None:
        return [], {}

    cfg["last_used"]["import_dir"] = str(path.parent)
    save_config(cfg)

    meta = {}
    try:
        if choice == "3":
            codes, meta = extract_codes_from_csv(path)
        else:
            codes = split_build_codes(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError as e:
        print(t("import_file_error", path=path, reason=e))
        return [], {}

    print(t("import_file_loaded", n=len(codes), path=path))
    return codes, meta


def ask_import_dest(cfg, t):
    """Dossier du jeu, ou n'importe quel autre dossier."""
    game_dir = cached_game_dir(cfg)
    if game_dir is None:
        print(t("import_dest_no_gamedir"))
        # auto-detection seule : le selecteur qui suit choisit une destination,
        # pas le dossier du jeu, et ne doit donc rien enregistrer dans le cfg
        game_dir = resolve_game_dir(cfg, t, allow_pick=False)
    if game_dir is not None:
        while True:
            choice = input(t("import_dest_prompt", path=game_dir)).strip()
            if choice in ("1", ""):
                return game_dir
            if choice == "2":
                break
            print(t("import_dest_invalid"))

    return ask_folder(t, "pick_import_dest_title", str(game_dir) if game_dir else None,
                      manual_prompt_key="manual_import_dest_prompt")


def do_import(cfg, mechs, weapons, gamedata, t):
    codes, imported_meta = read_build_codes(cfg, t)
    if not codes:
        print(t("import_no_codes"))
        return

    add_prefix = ask_yes_no(t, "ask_prefix_yn")
    prefix = input(t("ask_prefix_text")).strip() if add_prefix else ""
    opts = {
        "add_suffix": ask_yes_no(t, "ask_suffix_yn"),
        "add_equipment": ask_yes_no(t, "ask_equipment_yn"),
        "engine_mode": ask_engine_mode(t),
    }
    opts.update(naming_options(cfg))

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
        try:
            loadout = loadout_from_build(build)
            item_ids = effective_item_ids(loadout, gamedata)
            name = compose_name(loadout, item_ids, prefix, variant, "", opts, weapons, gamedata, t)
        except NoQualifyingWeapon as e:
            skipped.append((label, str(e)))
            continue
        plan.append((code, build, name))

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
    registry = load_registry()
    owner = fallback_owner(cfg)
    written = 0
    for i, (code, build, name) in enumerate(plan, start=1):
        if i not in selection:
            continue
        stem = unique_pair_stem(name, used_names)
        with open(dest / f"{stem}.xml", "w", encoding="utf-8", newline="") as f:
            f.write(build_loadout_xml(build, weapons))
        with open(dest / f"{stem}.mwl", "w", encoding="utf-8", newline="") as f:
            f.write(code)
        stamp_build(dest, stem, registry, owner, imported_meta.get(code))
        written += 1
    save_registry(registry)

    print(t("import_done", n=written, path=dest))


# ---------------------------------------------------------------------------
# Core rename flow, shared by advanced and quick modes

def build_plan(folder, opts, mechs, weapons, gamedata, t):
    plan = []
    skipped = []
    for basename in find_loadout_basenames(folder):
        loadout = loadout_from_xml(folder / f"{basename}.xml")
        _chassis, variant = mechs.get(loadout["mech_id"] if loadout else "", (None, None))
        item_ids = effective_item_ids(loadout, gamedata)
        original = basename if opts["keep_original"] else ""
        try:
            name = compose_name(loadout, item_ids, opts["prefix"], variant, original,
                                opts, weapons, gamedata, t)
        except NoQualifyingWeapon as e:
            skipped.append((basename, str(e)))
            continue
        plan.append((basename, name))
    return plan, skipped


def run_rename(folder, opts, cfg, mechs, weapons, gamedata, t):
    basenames = find_loadout_basenames(folder)
    if not basenames:
        print(t("no_xml_found"))
        return

    plan, skipped = build_plan(folder, opts, mechs, weapons, gamedata, t)

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
    registry = load_registry()
    owner = fallback_owner(cfg)
    renamed_stems = []
    for i, (old, new_stem) in enumerate(plan, start=1):
        if i not in selection:
            continue
        if old == new_stem:
            stamp_build(folder, old, registry, owner)
            continue
        used_names.discard(f"{old}.xml".lower())
        used_names.discard(f"{old}.mwl".lower())
        final_stem = unique_pair_stem(new_stem, used_names)
        for ext in (".xml", ".mwl"):
            src = folder / f"{old}{ext}"
            if src.exists():
                src.rename(folder / f"{final_stem}{ext}")
        stamp_build(folder, final_stem, registry, owner)
        renamed_stems.append(final_stem)
    save_registry(registry)

    print(t("renamed_count", n=len(renamed_stems)))

    cfg["last_used"]["source_dir"] = str(folder)
    save_config(cfg)

    if not renamed_stems:
        return
    known = cached_game_dir(cfg) or cfg["general"].get("game_dir", "") or t("settings_gamedir_none")
    if ask_yes_no(t, "ask_copy_to_game", path=known):
        dest = resolve_game_dir(cfg, t)
        if dest is None:
            return
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


def do_advanced(cfg, mechs, weapons, gamedata, t):
    source_dir = cfg["last_used"].get("source_dir", "")
    folder = ask_folder(t, "pick_source_title", source_dir or None)
    if folder is None:
        print(t("none_renamed"))
        return

    add_prefix = ask_yes_no(t, "ask_prefix_yn")
    prefix = input(t("ask_prefix_text")).strip() if add_prefix else ""
    add_suffix = ask_yes_no(t, "ask_suffix_yn")
    add_equipment = ask_yes_no(t, "ask_equipment_yn")
    engine_mode = ask_engine_mode(t)
    keep_original = ask_yes_no(t, "ask_keep_original_yn")

    cfg["last_used"]["add_prefix"] = str(add_prefix).lower()
    cfg["last_used"]["prefix"] = prefix
    cfg["last_used"]["add_suffix"] = str(add_suffix).lower()
    cfg["last_used"]["add_equipment"] = str(add_equipment).lower()
    cfg["last_used"]["engine_mode"] = engine_mode
    cfg["last_used"]["keep_original"] = str(keep_original).lower()
    save_config(cfg)

    run_rename(folder, last_used_options(cfg), cfg, mechs, weapons, gamedata, t)


def last_used_options(cfg):
    last = cfg["last_used"]
    engine_mode = last.get("engine_mode", "none")
    opts = {
        "prefix": last.get("prefix", "") if last.getboolean("add_prefix", fallback=False) else "",
        "add_suffix": last.getboolean("add_suffix", fallback=True),
        "add_equipment": last.getboolean("add_equipment", fallback=False),
        "engine_mode": engine_mode if engine_mode in ENGINE_MODES else "none",
        "keep_original": last.getboolean("keep_original", fallback=True),
    }
    opts.update(naming_options(cfg))
    return opts


def do_quick(cfg, mechs, weapons, gamedata, t):
    source_dir = cfg["last_used"].get("source_dir", "")
    folder = ask_folder(t, "pick_source_title", source_dir or None)
    if folder is None:
        print(t("none_renamed"))
        return

    run_rename(folder, last_used_options(cfg), cfg, mechs, weapons, gamedata, t)


def quick_example(cfg):
    """Exemple de nom avec les reglages courants (mech a refroidisseurs simples)."""
    opts = last_used_options(cfg)
    blocks = {
        "prefix": opts["prefix"],
        "variant": "ANH-1P",
        "original": "1v1" if opts["keep_original"] else "",
        "weapons": "3LL" if opts["add_suffix"] else "",
        "equipment": "JJ" if opts["add_equipment"] else "",
        "heatsink": "SHS",
        "engine": {"all": "XL300", "type": "XL"}.get(opts["engine_mode"], ""),
    }
    return join_name_blocks(opts["name_order"], blocks)


def settings_menu(cfg, t):
    while True:
        print(t("settings_title"))
        lang = cfg["general"].get("language", "en")
        game_dir = str(cached_game_dir(cfg) or cfg["general"].get("game_dir", "")
                       or t("settings_gamedir_none"))
        install_dir = cfg["general"].get("game_install_dir", "") or t("settings_gamedir_none")
        backup_state = t("state_on") if cfg["general"].getboolean("backup_before_rename", fallback=True) else t("state_off")
        print(f"1) {t('settings_lang', lang=lang)}")
        print(f"2) {t('settings_gamedir', path=game_dir)}")
        print(f"3) {t('settings_installdir', path=install_dir)}")
        print(f"4) {t('settings_backup', state=backup_state)}")
        print(f"5) {t('settings_structure_modifier', value=structure_modifier(cfg))}")
        print(f"6) {t('settings_back')}")
        choice = input(t("menu_prompt")).strip()

        if choice == "1":
            new_lang = ask_language()
            cfg["general"]["language"] = new_lang
            save_config(cfg)
            t = Translator(new_lang)
        elif choice == "2":
            resolve_game_dir(cfg, t, use_cached=False)
        elif choice == "3":
            picked_path = ask_folder(t, "pick_installdir_title", installdir_picker_start(cfg),
                                     manual_prompt_key="manual_installdir_prompt")
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
            raw = input(t("ask_structure_modifier")).strip().replace(",", ".")
            value = _to_float(raw)
            if value is None or value < 0:
                print(t("structure_modifier_invalid"))
            else:
                cfg["general"]["structure_modifier"] = f"{value:g}"
                save_config(cfg)
        elif choice == "6":
            return t
        else:
            print(t("menu_invalid"))


def migrate_data_files():
    """Deplace dans data/ les CSV laisses a cote du script par une version
    anterieure (ex. build_registry.csv, non suivi par git). Ne remplace jamais
    un fichier deja present dans data/."""
    for name in DATA_FILES:
        old, new = SCRIPT_DIR / name, DATA_DIR / name
        if old.is_file() and not new.exists():
            DATA_DIR.mkdir(exist_ok=True)
            shutil.move(str(old), str(new))


def main():
    migrate_data_files()
    mechs_csv = DATA_DIR / "mechs.csv"
    weapons_csv = DATA_DIR / "weapons.csv"
    if not mechs_csv.exists() or not weapons_csv.exists():
        print(f"Erreur : mechs.csv et weapons.csv doivent etre dans le dossier data/ ({DATA_DIR})")
        sys.exit(1)
    if not (LOCALES_DIR / "en.json").exists():
        print(f"Erreur : le dossier locales/ (avec au moins en.json) doit etre a cote de ce script ({SCRIPT_DIR})")
        sys.exit(1)

    mechs = load_mechs(mechs_csv)
    weapons = load_weapons(weapons_csv)
    gamedata = load_gamedata()

    cfg = load_config()
    if not CONFIG_PATH.exists():
        t = first_run_setup(cfg)
    else:
        lang = cfg["general"].get("language", "en")
        if lang not in available_languages():
            lang = "en"
        t = Translator(lang)
        added = apply_config_defaults(cfg)
        if added:
            print(t("config_defaults_added", n=added, path=CONFIG_PATH))
    warn_unknown_options(cfg, t)

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
            do_quick(cfg, mechs, weapons, gamedata, t)
        elif choice == "2":
            do_advanced(cfg, mechs, weapons, gamedata, t)
        elif choice == "3":
            do_import(cfg, mechs, weapons, gamedata, t)
        elif choice == "4":
            do_export(cfg, mechs, weapons, gamedata, t)
        elif choice == "5":
            do_update(cfg, mechs, weapons, gamedata, t)
        elif choice == "6":
            t = do_reset(cfg, mechs, weapons, gamedata, t)
        elif choice == "7":
            t = settings_menu(cfg, t)
        elif choice == "8":
            break
        else:
            print(t("menu_invalid"))


if __name__ == "__main__":
    main()
