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

S09 — modos de instalación COPY / HARDLINK / AUTO y elegibilidad segura.

La integridad del staging de Vortex tiene prioridad absoluta sobre el ahorro.
Los hardlinks comparten datos físicos: una escritura en destino puede alterar
el origen. Esta protección no puede garantizarse completamente.
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Sufijos tratados como contenedores de solo lectura típicos (candidatos hardlink).
# Configs / DLL / INI → siempre COPY (pueden modificarse en runtime).
PACKAGED_READONLY_SUFFIXES = {
    ".pak",
    ".utoc",
    ".ucas",
    ".ba2",
    ".bsa",
    ".archive",
    ".bun",
    ".far",
}
ALWAYS_COPY_SUFFIXES = {
    ".ini",
    ".cfg",
    ".json",
    ".xml",
    ".txt",
    ".dll",
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".asi",
}


class InstallMode(str, Enum):
    COPY = "COPY"
    HARDLINK = "HARDLINK"
    AUTO = "AUTO"


class InstallMethod(str, Enum):
    COPY = "COPY"
    HARDLINK = "HARDLINK"


@dataclass
class VolumeInfo:
    path: Path
    root: str
    device: int | None
    fs_name: str
    supports_hardlinks: bool | None  # None = desconocido
    note: str = ""


@dataclass
class EligibilityResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    volume_src: VolumeInfo | None = None
    volume_dst: VolumeInfo | None = None
    already_linked: bool = False


@dataclass
class InstallDecision:
    dest_rel: str
    source: Path
    method: InstallMethod
    policy: InstallMode
    reason: str
    size: int = 0
    eligible_hardlink: bool = False
    blocked: bool = False
    already_linked: bool = False


def parse_install_mode(value: str | None) -> InstallMode:
    v = (value or "COPY").strip().upper()
    if v in InstallMode.__members__:
        return InstallMode[v]
    return InstallMode.COPY


def _win_volume_root(path: Path) -> str:
    try:
        import ctypes
        from ctypes import wintypes

        GetVolumePathNameW = ctypes.windll.kernel32.GetVolumePathNameW
        GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        buf = ctypes.create_unicode_buffer(260)
        ok = GetVolumePathNameW(str(path.resolve()), buf, 260)
        if ok:
            return buf.value
    except Exception:
        pass
    # Fallback: unidad
    resolved = path.resolve()
    if resolved.drive:
        return resolved.drive + "\\"
    return str(resolved.anchor or resolved)


def _win_fs_name(root: str) -> tuple[str, bool | None]:
    try:
        import ctypes
        from ctypes import wintypes

        GetVolumeInformationW = ctypes.windll.kernel32.GetVolumeInformationW
        fs_buf = ctypes.create_unicode_buffer(64)
        ok = GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            None,
            0,
            None,
            None,
            None,
            fs_buf,
            64,
        )
        if ok:
            name = (fs_buf.value or "").upper()
            # NTFS sí; exFAT/FAT32 no hardlinks; ReFS sí en versiones modernas (tratar con cautela)
            if name == "NTFS":
                return name, True
            if name in {"FAT32", "FAT", "EXFAT", "CDFS", "UDF"}:
                return name, False
            return name or "UNKNOWN", None
    except Exception:
        pass
    return "UNKNOWN", None


def probe_volume(path: Path) -> VolumeInfo:
    """Inspección de volumen (solo lectura; sin escritura de prueba)."""
    try:
        resolved = path.resolve()
    except OSError:
        return VolumeInfo(
            path=path,
            root="",
            device=None,
            fs_name="UNKNOWN",
            supports_hardlinks=None,
            note="ruta no resoluble",
        )
    device: int | None
    try:
        device = resolved.stat().st_dev if resolved.exists() else (
            resolved.parent.stat().st_dev if resolved.parent.exists() else None
        )
    except OSError:
        device = None

    if os.name == "nt":
        root = _win_volume_root(resolved if resolved.exists() else resolved.parent)
        fs_name, supports = _win_fs_name(root)
        return VolumeInfo(
            path=resolved,
            root=root,
            device=device,
            fs_name=fs_name,
            supports_hardlinks=supports,
            note="" if supports is not None else "soporte hardlink no determinado",
        )

    # POSIX: hardlinks en mismo st_dev suelen OK en ext4/xfs; desconocido en red
    root = str(resolved.anchor or "/")
    return VolumeInfo(
        path=resolved,
        root=root,
        device=device,
        fs_name="POSIX",
        supports_hardlinks=True if device is not None else None,
        note="POSIX: hardlink si mismo dispositivo",
    )


def same_file(a: Path, b: Path) -> bool:
    try:
        if not a.is_file() or not b.is_file():
            return False
        return os.path.samefile(a, b)
    except OSError:
        return False


def link_count(path: Path) -> int:
    try:
        return int(path.stat().st_nlink)
    except OSError:
        return 0


def is_symlink_or_reparse(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return True


def evaluate_hardlink_eligibility(
    source: Path,
    dest: Path,
    *,
    stage_root: Path | None = None,
    mods_root: Path | None = None,
) -> EligibilityResult:
    """Condiciones explícitas. Si hay duda → no elegible."""
    reasons: list[str] = []
    if not source.is_file():
        return EligibilityResult(False, ["origen no es archivo regular"])
    if is_symlink_or_reparse(source):
        return EligibilityResult(False, ["origen es symlink/reparse — bloqueado"])
    if dest.exists() and is_symlink_or_reparse(dest):
        return EligibilityResult(False, ["destino es symlink/reparse — bloqueado"])

    suffix = source.suffix.lower()
    if suffix in ALWAYS_COPY_SUFFIXES:
        return EligibilityResult(False, [f"sufijo {suffix} exige COPY (mutable/runtime)"])
    if suffix not in PACKAGED_READONLY_SUFFIXES:
        return EligibilityResult(
            False,
            [f"sufijo {suffix or '(sin)'} no está en la lista de contenedores de solo lectura"],
        )

    if stage_root is not None:
        try:
            source.resolve().relative_to(stage_root.resolve())
        except ValueError:
            return EligibilityResult(False, ["origen fuera del staging autorizado"])

    if mods_root is not None:
        try:
            # dest puede no existir; validar padre bajo mods
            parent = dest.parent if not dest.exists() else dest
            parent.resolve().relative_to(mods_root.resolve())
        except ValueError:
            return EligibilityResult(False, ["destino fuera de mods_dir autorizado"])

    vol_s = probe_volume(source)
    vol_d = probe_volume(dest.parent if not dest.exists() else dest)
    if vol_s.device is None or vol_d.device is None:
        return EligibilityResult(
            False,
            ["no se pudo determinar el dispositivo/volumen"],
            vol_s,
            vol_d,
        )
    if vol_s.device != vol_d.device:
        return EligibilityResult(
            False,
            ["volúmenes distintos (hardlink imposible)"],
            vol_s,
            vol_d,
        )
    if vol_s.supports_hardlinks is False or vol_d.supports_hardlinks is False:
        return EligibilityResult(
            False,
            [f"FS no soporta hardlinks ({vol_s.fs_name}/{vol_d.fs_name})"],
            vol_s,
            vol_d,
        )
    if vol_s.supports_hardlinks is None or vol_d.supports_hardlinks is None:
        return EligibilityResult(
            False,
            ["soporte de hardlinks desconocido — se exige certeza"],
            vol_s,
            vol_d,
        )

    already = same_file(source, dest) if dest.exists() else False
    if already:
        reasons.append("destino ya es el mismo inode (hardlink existente)")
    else:
        reasons.append("elegible: mismo volumen, FS compatible, contenedor de solo lectura")

    return EligibilityResult(True, reasons, vol_s, vol_d, already_linked=already)


def decide_install_method(
    source: Path,
    dest: Path,
    policy: InstallMode | str,
    *,
    stage_root: Path | None = None,
    mods_root: Path | None = None,
    dest_rel: str = "",
) -> InstallDecision:
    mode = parse_install_mode(policy if isinstance(policy, str) else policy.value)
    size = 0
    try:
        size = source.stat().st_size if source.is_file() else 0
    except OSError:
        pass

    elig = evaluate_hardlink_eligibility(
        source, dest, stage_root=stage_root, mods_root=mods_root
    )

    if mode == InstallMode.COPY:
        return InstallDecision(
            dest_rel=dest_rel,
            source=source,
            method=InstallMethod.COPY,
            policy=mode,
            reason="política COPY",
            size=size,
            eligible_hardlink=elig.ok,
            already_linked=elig.already_linked,
        )

    if mode == InstallMode.HARDLINK:
        if not elig.ok:
            return InstallDecision(
                dest_rel=dest_rel,
                source=source,
                method=InstallMethod.COPY,
                policy=mode,
                reason="HARDLINK bloqueado: " + "; ".join(elig.reasons),
                size=size,
                eligible_hardlink=False,
                blocked=True,
                already_linked=elig.already_linked,
            )
        return InstallDecision(
            dest_rel=dest_rel,
            source=source,
            method=InstallMethod.HARDLINK,
            policy=mode,
            reason="; ".join(elig.reasons),
            size=size,
            eligible_hardlink=True,
            already_linked=elig.already_linked,
        )

    # AUTO: hardlink solo si elegible; si no, COPY
    if elig.ok:
        return InstallDecision(
            dest_rel=dest_rel,
            source=source,
            method=InstallMethod.HARDLINK,
            policy=mode,
            reason="AUTO→HARDLINK: " + "; ".join(elig.reasons),
            size=size,
            eligible_hardlink=True,
            already_linked=elig.already_linked,
        )
    return InstallDecision(
        dest_rel=dest_rel,
        source=source,
        method=InstallMethod.COPY,
        policy=mode,
        reason="AUTO→COPY: " + "; ".join(elig.reasons),
        size=size,
        eligible_hardlink=False,
        already_linked=elig.already_linked,
    )


def install_file_atomic(
    source: Path,
    dest: Path,
    method: InstallMethod,
    *,
    force_copy: bool = False,
) -> InstallMethod:
    """Instala vía temporal + os.replace. Nunca escribe in-place sobre hardlink.

    Backups del gestor deben usar siempre COPY (force_copy / shutil.copy2 aparte).
    """
    use = InstallMethod.COPY if force_copy else method
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and same_file(source, dest):
        return InstallMethod.HARDLINK  # ya enlazado; no tocar

    tmp = dest.with_name(dest.name + f".{uuid.uuid4().hex}.partial")
    try:
        if use == InstallMethod.HARDLINK:
            try:
                if tmp.exists():
                    tmp.unlink()
                os.link(source, tmp)
            except OSError as e:
                # Fallback seguro a copia
                use = InstallMethod.COPY
                shutil.copy2(source, tmp)
                if tmp.stat().st_size != source.stat().st_size:
                    raise OSError(f"Copia incompleta tras fallo hardlink: {e}") from e
        else:
            shutil.copy2(source, tmp)
            if tmp.stat().st_size != source.stat().st_size:
                raise OSError("Copia incompleta")

        # Verificar que tmp no es el mismo path que source
        if same_file(source, tmp) and use == InstallMethod.COPY:
            # copy que resultó samefile sería anómalo
            pass
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    if not dest.is_file() or dest.stat().st_size != source.stat().st_size:
        raise OSError(f"Verificación fallida tras instalar: {dest}")
    return use


def volume_compatibility_report(stage: Path | None, mods: Path) -> str:
    lines = ["=== Compatibilidad de volumen (S09) ==="]
    vm = probe_volume(mods)
    lines.append(
        f"Destino mods: {mods}\n"
        f"  root={vm.root or '?'} FS={vm.fs_name} "
        f"hardlinks={'sí' if vm.supports_hardlinks else ('no' if vm.supports_hardlinks is False else '?')}"
    )
    if stage and stage.exists():
        vs = probe_volume(stage)
        same = (
            vs.device is not None
            and vm.device is not None
            and vs.device == vm.device
        )
        lines.append(
            f"Staging: {stage}\n"
            f"  root={vs.root or '?'} FS={vs.fs_name} "
            f"hardlinks={'sí' if vs.supports_hardlinks else ('no' if vs.supports_hardlinks is False else '?')}"
        )
        lines.append(
            f"Mismo volumen: {'SÍ' if same else 'NO'} "
            f"(hardlink entre stage↔mods "
            f"{'posible si demás condiciones' if same and vs.supports_hardlinks and vm.supports_hardlinks else 'no disponible'})"
        )
    else:
        lines.append("Staging: (no configurado / no existe)")
    lines.append("")
    lines.append(
        "ADVERTENCIA: un hardlink comparte datos físicos. "
        "Cualquier proceso con permiso de escritura en el archivo del juego "
        "podría modificar también el staging. "
        "La protección frente a escrituras externas no puede garantizarse "
        "completamente con hardlinks. Integridad del staging > ahorro de espacio."
    )
    return "\n".join(lines)
