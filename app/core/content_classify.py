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

S08 — clasificación de archivos de staging por adaptador (solo lectura).
No modifica ni borra archivos del staging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .adapters import get_adapter
from .inventory import ModEntry

CASEFOLD = True


class ContentKind(str, Enum):
    INSTALLABLE = "INSTALABLE"
    DOCUMENTATION = "DOCUMENTACION"
    VARIANT_ALT = "VARIANTE_ALT"
    SPECIAL_DEST = "DESTINO_ESPECIAL"
    UNKNOWN = "DESCONOCIDO"
    SKIP = "OMITIR"  # thumbs.db, vortex meta, etc.


DOC_NAMES = {
    "readme",
    "readme.txt",
    "readme.md",
    "license",
    "license.txt",
    "licence",
    "changelog",
    "changelog.txt",
    "credits",
    "credits.txt",
    "authors",
    "authors.txt",
    "notice",
    "copying",
}
DOC_SUFFIXES = {".md", ".txt", ".rtf", ".pdf", ".doc", ".docx"}
DOC_DIR_PARTS = {
    "docs",
    "doc",
    "documentation",
    "readmes",
    "licenses",
    "meta",
    "info",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
# Destinos que no van a ~mods (herramientas / inyección)
SPECIAL_HINTS = (
    "reshade",
    "3dmigoto",
    "d3dx",
    "dxgi",
    "xinput",
    "asi",
    "injector",
    ".dll",
    "ffviihook",
    "engine.ini",
    "scalability",
)
UE4_INSTALLABLE_SUFFIXES = {".pak"}  # ~mods FF7R / UE4 típico
IOSTORE_SUFFIXES = {".pak", ".utoc", ".ucas"}


def _norm(s: str) -> str:
    return s.replace("\\", "/").strip("/")


@dataclass
class FileClassification:
    path: Path
    rel: str
    kind: ContentKind
    dest_rel: str = ""
    note: str = ""


@dataclass
class ModClassification:
    folder: str
    name: str
    adapter_id: str
    files: list[FileClassification] = field(default_factory=list)
    installable: list[str] = field(default_factory=list)
    documentation: list[str] = field(default_factory=list)
    special: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    variant_alts: list[str] = field(default_factory=list)
    has_installable: bool = False
    variant_pending: bool = False
    pak_names: list[str] = field(default_factory=list)

    def summary_kind(self) -> str:
        if self.variant_pending:
            return "VARIANTE_PENDIENTE"
        if self.has_installable:
            return "INSTALABLE"
        if self.special and not self.has_installable:
            return "DESTINO_ESPECIAL"
        if self.documentation and not self.has_installable:
            return "SOLO_DOCS"
        if self.unknown and not self.has_installable:
            return "DESCONOCIDO"
        return "SIN_INSTALABLES"


def _is_doc(name: str, parts: tuple[str, ...]) -> bool:
    low = name.lower()
    stem = Path(low).stem.lower()
    if low in DOC_NAMES or stem in {"readme", "license", "licence", "changelog", "credits"}:
        return True
    if any(p.lower() in DOC_DIR_PARTS for p in parts):
        if Path(low).suffix.lower() in DOC_SUFFIXES | IMAGE_SUFFIXES | {""}:
            return True
    if Path(low).suffix.lower() in DOC_SUFFIXES and (
        stem.startswith("readme")
        or "license" in stem
        or "changelog" in stem
        or "credit" in stem
    ):
        return True
    # Imágenes sueltas en raíz del mod (capturas Nexus) → documentación
    if Path(low).suffix.lower() in IMAGE_SUFFIXES and len(parts) <= 1:
        return True
    return False


def _is_special(rel: str, name: str) -> bool:
    blob = f"{rel}/{name}".lower()
    return any(h in blob for h in SPECIAL_HINTS)


def classify_file(
    path: Path,
    stage_root: Path,
    *,
    adapter_id: str,
    chosen_pak: str | None,
    pak_names: list[str],
) -> FileClassification:
    """Clasifica un archivo respecto al adaptador. No toca disco salvo lectura de path."""
    try:
        rel = _norm(path.relative_to(stage_root).as_posix())
    except ValueError:
        rel = path.name
    parts = Path(rel).parts
    name = path.name
    low = name.lower()

    if low in SKIP_NAMES or low.startswith("vortex"):
        return FileClassification(path, rel, ContentKind.SKIP, note="sistema/vortex")

    ad = get_adapter(adapter_id)
    suffix = path.suffix.lower()

    if ad.pak_centric:
        # Documentación excluida en adaptadores pak_centric (no hereda a generic)
        if _is_doc(name, parts):
            return FileClassification(
                path, rel, ContentKind.DOCUMENTATION, note="no se copia al destino del juego"
            )
        installable_suffixes = (
            IOSTORE_SUFFIXES if ad.iostore_sidecars else UE4_INSTALLABLE_SUFFIXES
        )
        if suffix in installable_suffixes:
            multi = len(pak_names) > 1
            chosen_stem = Path(chosen_pak).stem.lower() if chosen_pak else ""
            file_stem = Path(name).stem.lower()

            if suffix == ".pak":
                if multi and chosen_pak and name.lower() != chosen_pak.lower():
                    return FileClassification(
                        path,
                        rel,
                        ContentKind.VARIANT_ALT,
                        dest_rel=name,
                        note="variante no seleccionada",
                    )
                if multi and not chosen_pak:
                    return FileClassification(
                        path,
                        rel,
                        ContentKind.VARIANT_ALT,
                        dest_rel=name,
                        note="pendiente de elección",
                    )
                note = "UE5 IoStore pak → ~mods" if ad.iostore_sidecars else "UE4 pak → ~mods"
                return FileClassification(
                    path, rel, ContentKind.INSTALLABLE, dest_rel=name, note=note
                )

            # .utoc / .ucas: solo si coinciden con la variante .pak elegida
            if multi and not chosen_pak:
                return FileClassification(
                    path,
                    rel,
                    ContentKind.VARIANT_ALT,
                    dest_rel=name,
                    note="sidecar pendiente de variante .pak",
                )
            if chosen_stem and file_stem != chosen_stem:
                return FileClassification(
                    path,
                    rel,
                    ContentKind.VARIANT_ALT,
                    dest_rel=name,
                    note="sidecar de otra variante",
                )
            if not chosen_stem and multi:
                return FileClassification(
                    path, rel, ContentKind.VARIANT_ALT, dest_rel=name, note="sidecar sin variante"
                )
            return FileClassification(
                path,
                rel,
                ContentKind.INSTALLABLE,
                dest_rel=name,
                note="UE5 IoStore sidecar → ~mods",
            )
        if _is_special(rel, name) or suffix in {".dll", ".asi", ".exe"}:
            return FileClassification(
                path,
                rel,
                ContentKind.SPECIAL_DEST,
                note="requiere destino fuera de Paks/~mods",
            )
        if suffix in {".txt", ".md", ".uplugin", ".lua"}:
            return FileClassification(
                path,
                rel,
                ContentKind.DOCUMENTATION
                if suffix in {".txt", ".md"}
                else ContentKind.UNKNOWN,
                note="excluido / pendiente en adaptador pak_centric",
            )
        return FileClassification(
            path,
            rel,
            ContentKind.UNKNOWN,
            note=f"no instalable por defecto en {adapter_id}",
        )

    # generic_folder: no hereda filtros FF7R (copia casi todo; docs también).
    # Variantes .pak: misma regla de elección que el motor de ofertas.
    if suffix == ".pak" and pak_names:
        multi = len(pak_names) > 1
        if multi and chosen_pak and name.lower() != chosen_pak.lower():
            return FileClassification(
                path, rel, ContentKind.VARIANT_ALT, dest_rel=name, note="variante no seleccionada"
            )
        if multi and not chosen_pak:
            return FileClassification(
                path, rel, ContentKind.VARIANT_ALT, dest_rel=name, note="pendiente de elección"
            )
        return FileClassification(
            path, rel, ContentKind.INSTALLABLE, dest_rel=name, note="generic_folder pak"
        )
    note = "generic_folder"
    if _is_doc(name, parts):
        note = "documentación (generic: se copia; aviso informativo)"
    if _is_special(rel, name):
        note = "posible destino especial (aviso; generic lo copia)"
    return FileClassification(
        path, rel, ContentKind.INSTALLABLE, dest_rel=rel, note=note
    )


def classify_mod(mod: ModEntry, adapter_id: str) -> ModClassification:
    root = Path(mod.stage_path)
    out = ModClassification(
        folder=mod.folder,
        name=mod.name,
        adapter_id=adapter_id,
        pak_names=list(mod.paks),
    )
    if not root.is_dir():
        return out

    pak_names = sorted({p.name for p in root.rglob("*.pak")})
    out.pak_names = pak_names
    multi = len(pak_names) > 1 or mod.multi
    chosen = mod.pak_elegido or (pak_names[0] if len(pak_names) == 1 else "")
    if mod.usar and multi and not mod.pak_elegido:
        out.variant_pending = True

    for f in root.rglob("*"):
        if not f.is_file():
            continue
        fc = classify_file(
            f,
            root,
            adapter_id=adapter_id,
            chosen_pak=chosen or None,
            pak_names=pak_names,
        )
        if fc.kind == ContentKind.SKIP:
            continue
        out.files.append(fc)
        if fc.kind == ContentKind.INSTALLABLE:
            out.installable.append(fc.rel)
        elif fc.kind == ContentKind.DOCUMENTATION:
            out.documentation.append(fc.rel)
        elif fc.kind == ContentKind.SPECIAL_DEST:
            out.special.append(fc.rel)
        elif fc.kind == ContentKind.VARIANT_ALT:
            out.variant_alts.append(fc.rel)
        elif fc.kind == ContentKind.UNKNOWN:
            out.unknown.append(fc.rel)

    out.has_installable = bool(out.installable)
    return out


def classify_library(
    mods: list[ModEntry], adapter_id: str
) -> dict[str, ModClassification]:
    return {m.folder: classify_mod(m, adapter_id) for m in mods}


def is_offer_allowed(
    path: Path,
    stage_root: Path,
    *,
    adapter_id: str,
    chosen_pak: str | None,
    pak_names: list[str],
) -> tuple[bool, ContentKind, str]:
    """True si collect_offers debe incluir el archivo como oferta de instalación."""
    fc = classify_file(
        path,
        stage_root,
        adapter_id=adapter_id,
        chosen_pak=chosen_pak,
        pak_names=pak_names,
    )
    return fc.kind == ContentKind.INSTALLABLE, fc.kind, fc.note
