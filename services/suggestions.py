"""Complementary product suggestions (Phase 36).

"Tracking shaving blades? You might also want shaving gel / after-shave."
A free, deterministic, no-data approach: detect the product's category from its
name (keyword match) and return curated complementary **search terms** (Turkish,
for the local market). Terms are then opened as a Google search, like Phase 35.

No ML, no scraping, no API. Extend by adding rows to _RULES.
"""
import re
from typing import List

# Normalize Turkish letters to ASCII so keyword matching is robust
# (e.g. "İşlemci" -> "islemci").
_TR = str.maketrans({
    "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o", "ç": "c", "Ç": "c", "ı": "i", "İ": "i",
})


def _norm(text: str) -> str:
    return (text or "").translate(_TR).lower()


# (category keywords [normalized/ASCII], complementary search terms [shown to user])
# First matching rule wins; order more specific categories first.
_RULES = [
    (["islemci", "ryzen", "core i", " cpu"],
     ["CPU soğutucu", "termal macun", "anakart"]),
    (["anakart", "motherboard"],
     ["işlemci", "RAM bellek", "CPU soğutucu"]),
    (["ekran karti", "rtx", "radeon", "geforce", " gpu"],
     ["güç kaynağı", "bilgisayar kasası", "kasa fanı"]),
    (["ram ", "ddr5", "ddr4", "bellek"],
     ["anakart", "işlemci"]),
    (["ssd", "nvme", "hard disk", " hdd"],
     ["harici disk kutusu", "harici ssd"]),
    (["tiras bicagi", "tiras makinesi", "jilet", "tiras"],
     ["tıraş jeli", "tıraş sonrası losyon", "tıraş köpüğü"]),
    (["dis macunu", "dis fircasi"],
     ["diş fırçası", "ağız suyu", "diş ipi"]),
    (["iphone", "galaxy", "redmi", "xiaomi", "telefon"],
     ["telefon kılıfı", "ekran koruyucu", "şarj aleti"]),
    (["laptop", "notebook"],
     ["laptop çantası", "kablosuz mouse", "laptop soğutucu"]),
    (["kahve makinesi", "espresso", "french press"],
     ["kahve çekirdeği", "süt köpürtücü"]),
    (["pil", "alkalin", "battery"],
     ["pil şarj cihazı"]),
    (["klavye", "keyboard"],
     ["mouse pad", "bilek desteği"]),
    (["kulaklik", "headset", "airpods"],
     ["kulaklık kılıfı", "kulak süngeri"]),
    (["monitor", "monitör"],
     ["monitör kolu", "ekran temizleyici"]),
]


def complement_terms(product_name: str, limit: int = 5) -> List[str]:
    """Complementary search terms for a product, or [] if no category matched."""
    name = _norm(product_name)
    name = re.sub(r"\s+", " ", f" {name} ")  # pad so " cpu"/"ram " word-ish keys match
    for keywords, complements in _RULES:
        if any(k in name for k in keywords):
            return complements[:limit]
    return []
