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

Human-readable Spanish descriptions for FF7R mods.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import DESC_OVERRIDE
from .inventory import ModEntry

# Exact / substring overrides for known mods (name contains key)
KNOWN: list[tuple[str, str, str]] = [
    # (match lowercase in name, category, description)
    ("cloud's brighter eyes", "Aspecto", "Ojos de Cloud más brillantes (variante Brighter). Solo 1 variante de ojos."),
    ("cloud's eyes", "Aspecto", "Pack de ojos de Cloud (Bright/Brighter/Brightest). Elige UNA variante."),
    ("cloud hyper hd", "Textura", "Texturas CGI Hyper HD de Cloud (sin retocar ojos). Reemplaza body/cara."),
    ("enhanced cloud", "Modelo", "Modelo/outfit Enhanced Cloud con texturas. Choca con Hyper HD u otros bodies."),
    ("buster sword - enhance", "Arma", "Reemplaza la Buster Sword por Enhance Sword (First Soldier)."),
    ("cloud cc buster", "Arma", "Buster Sword estilo Crisis Core / rayo. Solo 1 reemplazo de Buster a la vez."),
    ("hard edge 02", "Arma", "Reemplazo Hard Edge (arma + icono menú)."),
    ("iron sword - enhance", "Arma", "Reemplaza Iron Sword por Enhance Sword."),
    ("mythril saber", "Arma", "Reemplaza Mythril Saber por rapier de Genesis."),
    ("tifa undressed", "Modelo NSFW", "Tifa desvestida V2 (varias tallas/commando). Elige 1 .pak. Choca con Hyper HD/outfits."),
    ("tifa hyper hd", "Textura", "Texturas Hyper HD de Tifa. Choca con Undress y muchos outfits de body."),
    ("tifa menu nude", "Menú", "Renders/nude de Tifa en menús. Suele ser seguro con gameplay."),
    ("tifas_present", "Atrezzo", "Regalo/presente de Tifa (prop de escena). Bajo riesgo."),
    ("tifa purple dress", "Outfit", "Outfit vestido morado de Tifa."),
    ("tifa china dress", "Outfit", "Outfit cheongsam/china dress de Tifa."),
    ("tifa wutai", "Outfit", "Outfit Wutai de Tifa."),
    ("tifa default outfit", "Outfit", "Outfit por defecto modificado de Tifa."),
    ("tifa rebirth", "Modelo", "Modelo Tifa estilo Rebirth."),
    ("tifa nude natural", "Modelo NSFW", "Tifa nude natural (body completo)."),
    ("tifa reshape", "Modelo", "Reshape corporal de Tifa (Aerosmith)."),
    ("aerith sexy dress", "Outfit", "Vestido sexy Enhanced de Aerith."),
    ("aerith cheap dress", "Outfit", "Vestido cheap Enhanced de Aerith."),
    ("aerith ordinary dress", "Outfit", "Vestido ordinary Enhanced de Aerith."),
    ("aerith default short", "Outfit", "Vestido corto default Enhanced de Aerith."),
    ("aerith rebirth", "Modelo", "Modelo Aerith estilo Rebirth. Choca con dresses/pale/reshape."),
    ("photorealistic pale skin", "Modelo NSFW", "Aerith nude pale photorealistic. Choca con dresses/Rebirth."),
    ("aerith menu graphic nude", "Menú", "Arte/nude de Aerith en menús."),
    ("aerith_reshape", "Modelo", "Reshape barefoot Aerith (Aerosmith). Pak muy grande."),
    ("home away from home", "Música/Escena", "Cambia tema/escena del despertar en habitación de Aerith."),
    ("sephiroth rebirth", "Modelo", "Sephiroth estilo Rebirth (variantes de ojos). Elige 1 .pak."),
    ("nude sephiroth", "Modelo NSFW", "Sephiroth nude (variante corporal). Solo 1 nude a la vez."),
    ("sephiroth_female", "Modelo", "Sephiroth versión female."),
    ("fem sephiroth voice", "Audio", "Voces female para Sephiroth."),
    ("jenova mix", "Combate/Contenido", "Mezcla/contenido relacionado con Jenova (altera encuentros/assets)."),
    ("yuffie's cape", "Outfit", "Capa kunoichi azul para Yuffie."),
    ("yuffie ninja outfit", "Outfit", "Outfit ninja de Yuffie."),
    ("yuffie rebirth", "Modelo", "Yuffie estilo Rebirth (ojos/variantes)."),
    ("shiva nude natural", "Invocación NSFW", "Shiva nude natural."),
    ("sexiershiva", "Invocación", "Shiva más sexy (fixed)."),
    ("sexier shiva", "Invocación", "Shiva más sexy."),
    ("scarlet reshape", "Modelo", "Reshape corporal Scarlet (Aerosmith)."),
    ("scarlet - reshape fix", "Modelo", "Addon fix del reshape de Scarlet (usar con el reshape)."),
    ("scarlet nip-slip", "Modelo NSFW", "Scarlet nip-slip. Alternativa al reshape, no combinar líneas."),
    ("scarlet physics", "Física", "Física adicional para Scarlet."),
    ("madame m", "NPC", "Modelo Enhanced Madame M."),
    ("madam m - nude", "NPC NSFW", "Madame M nude V2."),
    ("madam m risque", "NPC NSFW", "Madame M risqué."),
    ("adult honeybee inn", "Escenario NSFW", "Honeybee Inn adulto. Solo 1 versión (V2/V3/upgrade)."),
    ("7th heaven outfit", "Outfit", "Barret con outfit 7th Heaven."),
    ("barret - shirtless", "Outfit", "Barret sin camiseta. Puede chocar con otros bodies de Barret."),
    ("barrett -no sunglasses", "Aspecto", "Quita gafas de sol a Barret."),
    ("barret rebirth", "Modelo", "Barret estilo Rebirth."),
    ("enhanced jessie", "NPC", "Jessie Enhanced (modelo/textura)."),
    ("jessie 4k nude", "NPC NSFW", "Jessie nude NPC."),
    ("jessie biggs and wedge camo", "Outfit", "Camo/kevlar para Jessie/Biggs/Wedge."),
    ("biggs_shirtless", "NPC", "Biggs sin camiseta."),
    ("kyrie jiggle", "Física", "Física/jiggle para Kyrie."),
    ("kyrie pink", "Aspecto", "Recolor rosa de Kyrie."),
    ("rude - kiryu", "NPC", "Rude con aspecto Kiryu Kazuma."),
    ("killzone", "Enemigos", "Reskin soldados Shinra estilo Killzone."),
    ("shinra soldier sexy", "Enemigos", "Variante sexy de soldados Shinra."),
    ("atb x2", "Combate", "ATB x2 y Limit que no se detiene. Alto impacto en batallas."),
    ("stagger time duration", "Combate", "Alarga la ventana de stagger."),
    ("lv99", "Combate", "Niveles/stats orientados a Lv99."),
    ("equalaggro", "Combate", "Agro repartido equitativo entre compañeros."),
    ("aggressive companions", "Combate", "Compañeros más agresivos."),
    ("owa mod", "Combate/Contenido", "Overpowered / overhaul de habilidades (OWA)."),
    ("summons 3x", "Combate", "Invocaciones hacen x3 de daño."),
    ("enemies 2x hp", "Combate", "Enemigos normales con x2 HP (no bosses)."),
    ("equipment rebalance", "Combate", "Rebalanceo de equipo."),
    ("betterweaponupgrades", "Combate", "Mejoras de arma más generosas."),
    ("double ap", "Combate", "Duplica AP de enemigos."),
    ("enemy respawn", "Combate", "Enemigos reaparecen más rápido."),
    ("learn enemy skill", "Combate", "Aprender enemy skills facilitado."),
    ("timer", "Combate", "Ajuste de temporizadores de misión."),
    ("fov70", "Cámara", "Campo de visión 70."),
    ("invincible motorcycle", "Jugabilidad", "Moto invencible."),
    ("no red warnings", "UI", "Quita avisos rojos en pantalla."),
    ("hide grappling hook", "Visual", "Oculta el gancho (versión anti-crash)."),
    ("pakchunk99_slayer", "Combate", "Mod 'slayer' de dificultad/enemigos."),
    ("fixed color", "Cutscene", "Corrección de color en cutscenes (.emov)."),
    ("chapter 12", "Música", "Rescore musical del Capítulo 12."),
    ("chapter 2 anxious", "Música", "Fix BGM Anxious Heart cap. 2."),
    ("mako-rescore", "Música", "Rescore de zonas Mako."),
    ("wall market music", "Música", "Música Wall Market v2."),
    ("eligor", "Música", "Música batalla Eligor."),
    ("flowersblooming", "Música", "Música Flowers Blooming."),
    ("roche fight bgm", "Música", "Fix BGM pelea Roche."),
    ("sewers", "Música", "Música batallas alcantarillas."),
    ("multilingual citizens", "Diálogo", "Ciudadanos Midgar multilingües/subs."),
    ("bilingual team", "Diálogo", "Equipo Wutai bilingüe (Yuffie/Sonon)."),
    ("bilingual madam", "Diálogo", "Madam M / Andrea bilingüe."),
    ("castellano", "Audio/Idioma", "Instalador/voces o doblaje castellano."),
    ("less obnoxious grunt", "Audio", "Reduce gruñidos en cutscenes."),
    ("classic blood", "Efectos", "Sangre estilo clásico."),
    ("advent reshade", "Gráficos", "Preset ReShade Advent/HDR (injector; no va en ~mods como pak)."),
    ("3dmigoto", "Herramienta", "Base 3DMigoto / BaseMod (injector)."),
    ("ffviihook", "Herramienta", "UE4 console unlocker / hook."),
    ("zack pic", "Atrezzo", "Foto/poster de Zack."),
    ("red xiii - erect", "NSFW", "Mod NSFW Red XIII."),
    ("dancingqueen", "Gameplay", "Mod Dancing Queen."),
    ("unnamed npcs", "NPC", "Mejora/variante de NPCs sin nombre."),
]


RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"eyes?", re.I), "Aspecto", "Modifica ojos del personaje."),
    (re.compile(r"hyper\s*hd|texture", re.I), "Textura", "Pack de texturas de alta resolución."),
    (re.compile(r"nude|undress|nsfw|risque", re.I), "NSFW", "Contenido adulto / modelo sin ropa."),
    (re.compile(r"reshape|physics|jiggle", re.I), "Modelo/Física", "Cambia proporciones o física del cuerpo."),
    (re.compile(r"rebirth", re.I), "Modelo", "Apariencia estilo FF7 Rebirth."),
    (re.compile(r"dress|outfit|costume|armor", re.I), "Outfit", "Cambia la ropa/outfit del personaje."),
    (re.compile(r"sword|buster|hard.?edge|weapon", re.I), "Arma", "Reemplazo de arma."),
    (re.compile(r"bgm|music|rescore|score", re.I), "Música", "Cambia o arregla música/BGM."),
    (re.compile(r"fixed color|cutscene|emov", re.I), "Cutscene", "Arreglo visual de cinemáticas."),
    (re.compile(r"atb|stagger|lv99|aggro|enemy|summon|ap\b|timer|owa|slayer", re.I), "Combate", "Altera reglas o dificultad de combate."),
    (re.compile(r"bilingual|multilingual|voice|dub|castellano|subtit", re.I), "Idioma/Audio", "Voces, doblaje o subtítulos."),
    (re.compile(r"reshade|hdr|3dmigoto|hook|basemod", re.I), "Herramienta gráfica", "Injector/herramienta (no solo .pak)."),
    (re.compile(r"shinra|trooper|killzone|soldier", re.I), "Enemigos", "Reskin de enemigos/soldados."),
    (re.compile(r"menu", re.I), "Menú", "Cambia imágenes o renders del menú."),
    (re.compile(r"honeybee|wall market", re.I), "Escenario", "Contenido de localización (Wall Market/Honeybee)."),
]


def load_overrides(path: Path | None = None) -> dict[str, dict]:
    p = path if path is not None else DESC_OVERRIDE
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_override(
    folder: str,
    description: str,
    category: str = "",
    path: Path | None = None,
) -> None:
    p = path if path is not None else DESC_OVERRIDE
    data = load_overrides(p)
    data[folder] = {"description": description, "category": category}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def describe(mod: ModEntry, overrides_path: Path | None = None) -> tuple[str, str]:
    """Return (category, description)."""
    ov = load_overrides(overrides_path).get(mod.folder)
    if ov:
        return ov.get("category") or "Personalizado", ov.get("description") or ""

    name_l = mod.name.lower()
    blob = name_l + " " + " ".join(mod.paks).lower()

    for key, cat, desc in KNOWN:
        if key in name_l or key in blob:
            return cat, desc

    for rx, cat, desc in RULES:
        if rx.search(blob):
            who = mod.character_main if mod.character_main != "OTROS" else "general"
            return cat, f"{desc} Ámbito: {who}."

    if mod.paks:
        return "Pak", f"Mod .pak ({len(mod.paks)} archivo/s). Revisar compatibilidad por personaje/slot."
    return "Recurso", "Mod sin .pak (cutscene/emov, injector o instalador). Revisar destino de instalación."


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def apply_descriptions(
    mods: list[ModEntry],
    vortex_meta: dict | None = None,
    *,
    overrides_path: Path | None = None,
) -> None:
    vortex_meta = vortex_meta or {}
    for m in mods:
        ov = load_overrides(overrides_path).get(m.folder)
        if ov and ov.get("description"):
            m.category = ov.get("category") or "Personalizado"
            m.description = ov["description"]
            continue

        meta = vortex_meta.get(m.folder) or {}
        short = _strip_html(meta.get("shortDescription") or "")
        long = _strip_html(meta.get("description") or "")
        cat, fallback = describe(m, overrides_path)
        m.category = cat
        if short:
            m.description = short[:280]
        elif long:
            m.description = long[:280]
        else:
            m.description = fallback
        if meta.get("modName") and not m.nexus_mod_name:
            m.nexus_mod_name = meta.get("modName") or ""
        if meta.get("author"):
            m.author = meta.get("author") or ""
        if meta.get("pictureUrl"):
            m.picture_url = meta.get("pictureUrl") or ""
        if meta.get("modId") and not m.nexus_id:
            m.nexus_id = str(meta.get("modId"))
