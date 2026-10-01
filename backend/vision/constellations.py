"""88 星座对照表 + 名称规范化。"""
import re

_PAIRS = [
    ("And", "Andromeda"), ("Ant", "Antlia"), ("Aps", "Apus"),
    ("Aqr", "Aquarius"), ("Aql", "Aquila"), ("Ara", "Ara"),
    ("Ari", "Aries"), ("Aur", "Auriga"), ("Boo", "Bootes"),
    ("Cae", "Caelum"), ("Cam", "Camelopardalis"), ("Cnc", "Cancer"),
    ("CMa", "Canis Major"), ("CMi", "Canis Minor"),
    ("Cap", "Capricornus"), ("Car", "Carina"), ("Cas", "Cassiopeia"),
    ("Cen", "Centaurus"), ("Cep", "Cepheus"), ("Cet", "Cetus"),
    ("Cha", "Chamaeleon"), ("Cir", "Circinus"), ("Col", "Columba"),
    ("Com", "Coma Berenices"), ("CrA", "Corona Australis"),
    ("CrB", "Corona Borealis"), ("Crv", "Corvus"), ("Crt", "Crater"),
    ("Cru", "Crux"), ("Cyg", "Cygnus"), ("Del", "Delphinus"),
    ("Dor", "Dorado"), ("Dra", "Draco"), ("Equ", "Equuleus"),
    ("Eri", "Eridanus"), ("For", "Fornax"), ("Gem", "Gemini"),
    ("Gru", "Grus"), ("Her", "Hercules"), ("Hor", "Horologium"),
    ("Hya", "Hydra"), ("Hyi", "Hydrus"), ("Ind", "Indus"),
    ("Lac", "Lacerta"), ("Leo", "Leo"), ("LMi", "Leo Minor"),
    ("Lep", "Lepus"), ("Lib", "Libra"), ("Lup", "Lupus"),
    ("Lyn", "Lynx"), ("Lyr", "Lyra"), ("Men", "Mensa"),
    ("Mic", "Microscopium"), ("Mon", "Monoceros"), ("Mus", "Musca"),
    ("Nor", "Norma"), ("Oct", "Octans"), ("Oph", "Ophiuchus"),
    ("Ori", "Orion"), ("Peg", "Pegasus"), ("Per", "Perseus"),
    ("Phe", "Phoenix"), ("Pic", "Pictor"), ("Psc", "Pisces"),
    ("PsA", "Piscis Austrinus"), ("Pup", "Puppis"), ("Pyx", "Pyxis"),
    ("Ret", "Reticulum"), ("Sge", "Sagitta"), ("Sgr", "Sagittarius"),
    ("Sco", "Scorpius"), ("Scl", "Sculptor"), ("Sct", "Scutum"),
    ("Ser", "Serpens"), ("Sex", "Sextans"), ("Tau", "Taurus"),
    ("Tel", "Telescopium"), ("Tri", "Triangulum"),
    ("TrA", "Triangulum Australe"), ("Tuc", "Tucana"),
    ("UMa", "Ursa Major"), ("UMi", "Ursa Minor"), ("Vel", "Vela"),
    ("Vir", "Virgo"), ("Vol", "Volans"), ("Vul", "Vulpecula"),
]

ABBR_TO_FULL = {a: f for a, f in _PAIRS}
ALL_ABBRS = set(ABBR_TO_FULL)
_ABBR_LOWER = {a.lower(): a for a in ABBR_TO_FULL}
_FULL_LOWER = {f.lower(): a for a, f in _PAIRS}


def normalize_constellation(name: str) -> str:
    """任意输入 → 3 字母缩写；不认识返回 ''。"""
    if not name:
        return ""
    n = re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()
    if not n:
        return ""
    compact = n.replace(" ", "")
    if compact in _ABBR_LOWER:
        return _ABBR_LOWER[compact]
    if n in _FULL_LOWER:
        return _FULL_LOWER[n]
    return ""


def to_full(abbr: str) -> str:
    return ABBR_TO_FULL.get(abbr, abbr)