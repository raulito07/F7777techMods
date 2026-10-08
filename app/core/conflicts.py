# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre: usted puede redistribuirlo y/o
modificarlo bajo los términos de la Licencia Pública General de GNU
publicada por la Free Software Foundation, ya sea la versión 3
de la Licencia, o (a su elección) cualquier versión posterior.

Este programa se distribuye con la esperanza de que sea útil, pero
SIN NINGUNA GARANTÍA; sin siquiera la garantía implícita de
COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Vea la
Licencia Pública General de GNU para más detalles.

Debería haber recibido una copia de la Licencia Pública General de GNU
junto con este programa. Si no, vea <https://www.gnu.org/licenses/>.

Heurísticas semánticas por nombre (opcionales por adaptador).

La detección real de archivos vive en conflict_engine.py (S03).
"""

from __future__ import annotations

from collections import defaultdict

from .inventory import ModEntry

# Solo usados si el adaptador tiene semantic_slots=True (p. ej. ue4_paks_mods / FF7R).
SLOTS: list[tuple[str, int, str, list[str]]] = [
    ("CLOUD_BODY", 1, "Cloud body/textura", ["enhanced cloud", "cloud hyper hd", "nude cloud", "cloud 1st class", "cloud kingdom", "cloud in new pants", "noctis", "squall cloud", "sephiroth cloud", "ac cloud", "rocker outfit", "black and yellow"]),
    ("CLOUD_EYES", 1, "Cloud eyes", ["cloud's eyes", "cloudeyes"]),
    ("CLOUD_BUSTER", 1, "Buster Sword", ["buster sword", "cloud cc buster", "fusion sword", "kh buster", "lightningbuster", "zcloudlightning"]),
    ("CLOUD_HARDEDGE", 1, "Hard Edge", ["hard edge"]),
    ("TIFA_BODY", 1, "Tifa body/outfit", ["tifa undressed", "tifa hyper hd", "tifa nude", "tifa rebirth", "tifa reshape", "tifa classic", "tifa default", "tifa purple", "tifa china", "tifa wutai", "tifa sport", "tifa maid", "tifa - marin", "tifa advent", "tifa 4k", "tifa no shorts", "tifa standard", "ytifabunny", "ztifabunny", "purple dress tifa", "black costume", "red costume", "sheer stockings", "original tifa"]),
    ("AERITH_OUTFIT", 1, "Aerith outfit", ["aerith sexy", "aerith cheap", "aerith ordinary", "aerith default", "aerith rebirth", "aerith advent", "aerith casual", "sexy dress aerith", "aerithordinary", "canon proportions"]),
    ("AERITH_BODY_SKIN", 1, "Aerith nude/skin", ["pale skin", "zznudeaerith", "aerith_reshape", "aerith reshape", "photorealistic pale"]),
    ("SEPH_EYES", 1, "Sephiroth eyes/model", ["sephiroth rebirth", "sephiroth_rebirth"]),
    ("SEPH_BODY", 1, "Sephiroth body", ["nude sephiroth", "sephiroth_female", "sephiroth female", "fem sephiroth", "noshoulder"]),
    ("YUFFIE_OUTFIT", 1, "Yuffie outfit", ["yuffie ninja", "yuffie's cape", "yuffie - advent", "yuffie pink", "yuffie rebirth"]),
    ("YUFFIE_EYES", 1, "Yuffie eyes", ["yuffie rebirth", "yuffie's eyes"]),
    ("SHIVA_BODY", 1, "Shiva body", ["shiva nude", "sexiershiva", "sexier shiva", "classicshiva", "1_f80h_shiva"]),
    ("SCARLET_BODY", 1, "Scarlet body", ["scarlet reshape", "scarlet nip", "1_f80h_scarlett", "scarlet physics"]),
    ("MADAM_BODY", 1, "Madam M body", ["madame m", "madam m - nude", "madam m risque", "1_f80h_madame"]),
    ("HONEYBEE", 1, "Honeybee Inn", ["adult honeybee"]),
    ("BARRET_BODY", 1, "Barret body", ["7th heaven", "barret - shirtless", "barret - nude", "barret rebirth", "barret's advent"]),
    ("JESSIE_BODY", 1, "Jessie body", ["enhanced jessie", "jessie nude", "jessie - 2b", "jessie - bikini", "jessie - marksqueen", "jessie red leather", "jessie reshape", "jessie-raspiery", "camo and kevlar"]),
]


def match_slots(name: str, paks: list[str]) -> list[str]:
    blob = (name + " " + " ".join(paks)).lower()
    return [sid for sid, _m, _d, keys in SLOTS if any(k in blob for k in keys)]


def annotate_slots(mods: list[ModEntry], *, enabled: bool = True) -> None:
    for m in mods:
        m.slots = match_slots(m.name, m.paks) if enabled else []


def evaluate(
    mods: list[ModEntry],
    *,
    semantic: bool = True,
) -> tuple[dict[str, list[str]], int]:
    """Heurística semántica. Variantes .pak se reportan aquí solo si semantic=True
    para no duplicar; el motor de archivos también las bloquea.
    """
    annotate_slots(mods, enabled=semantic)
    by_slot: dict[str, list[ModEntry]] = defaultdict(list)
    problems = 0

    for m in mods:
        m.conflicto = ""
        if not m.usar:
            continue
        if m.multi and not m.pak_elegido:
            m.conflicto = "Falta elegir variante (.pak)"
            problems += 1
        if semantic:
            for s in m.slots:
                by_slot[s].append(m)

    slot_conflicts: dict[str, list[str]] = {}
    if not semantic:
        return slot_conflicts, problems

    max_map = {s[0]: s[1] for s in SLOTS}
    for sid, group in by_slot.items():
        vmax = max_map.get(sid, 1)
        names = list(dict.fromkeys(x.name for x in group))
        if len(names) > vmax:
            slot_conflicts[sid] = names
            for m in group:
                if m.usar:
                    extra = f"Choque {sid}"
                    m.conflicto = f"{m.conflicto}; {extra}".strip("; ") if m.conflicto else extra
            problems += 1

    return slot_conflicts, problems
