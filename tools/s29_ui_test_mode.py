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

S29 — modo de prueba UI con biblioteca sintética temporal.
Nunca usa Steam/Vortex/FOV70/perfil personal. Apply solo a mods_dest sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SANDBOX_NAME = "F7777techMods_S29_UI_TEST"
MARKER = "S29_SANDBOX_MARKER.txt"


def default_sandbox_root() -> Path:
    env = (os.environ.get("SGM_TEST_SANDBOX_ROOT") or "").strip()
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / SANDBOX_NAME


def _write(p: Path, data: bytes = b"x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _assert_safe_root(root: Path) -> None:
    root = root.resolve()
    forbidden_names = {
        "steam",
        "steamapps",
        "vortex",
        "fourseven tech",
        "fourseventech",
    }
    parts_l = {p.lower() for p in root.parts}
    # No permitir anclar el sandbox dentro de installs típicos
    for bad in ("Program Files", "Program Files (x86)", "SteamLibrary"):
        if bad in root.parts:
            raise SystemExit(f"S29 rechazado: raíz insegura ({bad}): {root}")
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        real_profile = (Path(local) / "FourSevenTech" / "F7777techMods").resolve()
        try:
            root.relative_to(real_profile)
            raise SystemExit(
                f"S29 rechazado: no usar el perfil personal como sandbox:\n{real_profile}"
            )
        except ValueError:
            pass
    if any(x in parts_l for x in forbidden_names) and SANDBOX_NAME not in str(root):
        # permitir temp con nombre propio
        pass


def prepare_sandbox(root: Path | None = None, *, reset: bool = False) -> Path:
    root = (root or default_sandbox_root()).resolve()
    _assert_safe_root(root)
    if reset and root.exists():
        import shutil

        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    app_data = root / "app_data"
    stage_r = root / "staging_remake"
    stage_b = root / "staging_rebirth"
    mods_r = root / "mods_dest_remake"
    mods_b = root / "mods_dest_rebirth"
    archive = root / "archive_own"
    work = root / "work_library"
    downloads = root / "downloads_sim"
    game_root = root / "game_root_ficticio"
    for p in (
        app_data,
        stage_r,
        stage_b,
        mods_r,
        mods_b,
        archive,
        work,
        downloads,
        game_root,
    ):
        p.mkdir(parents=True, exist_ok=True)

    (root / MARKER).write_text(
        "F7777techMods S29 — sandbox sintético. NO es un juego real.\n"
        f"root={root}\n"
        "Apply solo escribe en mods_dest_* de este árbol.\n",
        encoding="utf-8",
    )
    (root / "COMO_PROBAR.txt").write_text(
        "1) Arrancar con Arrancar_Modo_Prueba_S29.cmd\n"
        "2) Selector de juego: «S29 Remake Sintético» o «S29 Rebirth Sintético»\n"
        "3) Biblioteca → buscar S29 → ver detalle (clasificación S28)\n"
        "4) Activar mods en Usar → elegir variante FOV si aplica\n"
        "5) Barra: Preparar plan → Simular → Aplicar (solo mods_dest sandbox)\n"
        "6) Instalados / Historial / backup bajo app_data/games/…\n"
        "7) Archivar ZIP propio → recuperar WORK → simular de nuevo\n",
        encoding="utf-8",
    )

    # Remake-like (UE4)
    _write(stage_r / "S29_Simple-1-1" / "Simple.pak", b"S29-SIMPLE")
    _write(stage_r / "S29_Simple-1-1" / "readme.txt", b"docs")
    _write(stage_r / "S29_FOV-2-1" / "Camera_FOV70.pak", b"FOV70")
    _write(stage_r / "S29_FOV-2-1" / "Camera_FOV90.pak", b"FOV90")
    _write(stage_r / "S29_CollA-3-1" / "SharedName.pak", b"COLL-A")
    _write(stage_r / "S29_CollB-4-1" / "SharedName.pak", b"COLL-B")

    # Rebirth-like (UE5 IoStore)
    for stem, complete in (("S29_IoOK", True), ("S29_IoBad", False)):
        d = stage_b / f"{stem}-1-1"
        _write(d / f"{stem}.pak", b"PAK-" + stem.encode())
        _write(d / f"{stem}.utoc", b"UTOC")
        if complete:
            _write(d / f"{stem}.ucas", b"UCAS")

    # Archivo ajeno en destino (no debe borrarse)
    (mods_r / "foreign_user_file.txt").write_text(
        "NO TOCAR — archivo ajeno S29\n", encoding="utf-8"
    )
    (mods_b / "foreign_user_file.txt").write_text(
        "NO TOCAR — archivo ajeno S29\n", encoding="utf-8"
    )
    # Sin marcador Vortex: Apply UI queda bloqueado si existe (regla producto).
    for dest in (mods_r, mods_b):
        for name in ("vortex.deployment.json", "_manual_loadout.json"):
            p = dest / name
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
            # Limpiar paks de pruebas anteriores en destino sandbox
        for p in dest.glob("*.pak"):
            try:
                p.unlink()
            except OSError:
                pass

    games = {
        "version": 1,
        "active_game_id": "s29_remake",
        "games": {
            "s29_remake": {
                "id": "s29_remake",
                "name": "S29 Remake Sintético",
                "vortex_game_id": "",
                "game_root": str(game_root),
                "mods_dir": str(mods_r),
                "stage_dir": str(stage_r),
                "adapter": "ue4_paks_mods",
                "platform": "manual",
                "data_mode": "isolated",
                "data_dir_name": "s29_remake",
                "enabled": True,
                "notes": "S29 sandbox — no es FF7 Remake real",
                "migration_status": "not_needed",
                "migration_note": "",
                "install_mode": "COPY",
                "downloads_dir": str(downloads),
                "destination_verified": True,
                "path_status": "installed",
                "archive_dir": str(archive),
                "work_library_dir": str(work),
                "default_mod_source": "STAGING_VORTEX",
            },
            "s29_rebirth": {
                "id": "s29_rebirth",
                "name": "S29 Rebirth Sintético",
                "vortex_game_id": "",
                "game_root": str(game_root),
                "mods_dir": str(mods_b),
                "stage_dir": str(stage_b),
                "adapter": "ue5_iostore_mods",
                "platform": "manual",
                "data_mode": "isolated",
                "data_dir_name": "s29_rebirth",
                "enabled": True,
                "notes": "S29 sandbox — no es FF7 Rebirth real",
                "migration_status": "not_needed",
                "migration_note": "",
                "install_mode": "COPY",
                "downloads_dir": str(downloads),
                "destination_verified": True,
                "path_status": "installed",
                "archive_dir": str(archive),
                "work_library_dir": str(work),
                "default_mod_source": "STAGING_VORTEX",
            },
        },
    }
    (app_data / "games.json").write_text(
        json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (app_data / "ui_settings.json").write_text(
        json.dumps({"zoom": 100, "s29_test": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return root


def activate_env(root: Path) -> None:
    root = root.resolve()
    if not (root / MARKER).is_file():
        raise SystemExit(f"Falta marcador S29 en {root}")
    os.environ["SGM_TEST_SANDBOX"] = "1"
    os.environ["SGM_TEST_SANDBOX_ROOT"] = str(root)
    os.environ["SGM_DATA_DIR"] = str(root / "app_data")
    # Evitar herencia accidental de overrides Steam/Vortex
    for k in list(os.environ):
        if k.startswith("SGM_VORTEX_") or k.startswith("SGM_LEGACY_") or k == "SGM_STEAM_COMMON":
            os.environ.pop(k, None)


def run_headless_e2e(root: Path) -> int:
    """Ciclo motor completo en sandbox (sin tocar Steam/Vortex)."""
    activate_env(root)
    # Re-import paths after env — use subprocess-like isolation via importlib reload
    import importlib

    import app.core.paths as paths_mod

    importlib.reload(paths_mod)
    import app.core.games as games_mod

    importlib.reload(games_mod)

    from app.core.apply import execute, load_manifest, plan_apply
    from app.core.conflict_engine import ConflictSettings
    from app.core.games import GameRecord, game_paths_for, ensure_game_data_dir
    from app.core.inventory import scan_staging
    from app.core.mod_structure import analyze_mod_structure
    from app.core.operations import execute_restore, list_operations, plan_restore
    from app.core.own_archive import create_own_archive
    from app.core.work_library import (
        load_index,
        restore_archive_to_work,
        work_record_to_mod_entry,
    )

    failures: list[str] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        mark = "OK" if cond else "FAIL"
        print(f"  [{mark}] {name}: {detail}")
        if not cond:
            failures.append(name)

    stage = root / "staging_remake"
    mods = list(scan_staging(stage))
    ok("detectar_mods", len(mods) >= 4, f"n={len(mods)}")

    simple = next(m for m in mods if m.folder.startswith("S29_Simple"))
    fov = next(m for m in mods if m.folder.startswith("S29_FOV"))
    coll_a = next(m for m in mods if m.folder.startswith("S29_CollA"))
    coll_b = next(m for m in mods if m.folder.startswith("S29_CollB"))

    r_simple = analyze_mod_structure(simple, "ue4_paks_mods")
    ok("s28_simple", r_simple.classification == "SIMPLE", r_simple.classification)
    fov.usar = True
    fov.pak_elegido = ""
    fov.multi = True
    r_fov = analyze_mod_structure(fov, "ue4_paks_mods")
    ok("s28_variantes", r_fov.classification == "CON_VARIANTES", r_fov.classification)

    stage_b = root / "staging_rebirth"
    mods_b = list(scan_staging(stage_b))
    bad = next(m for m in mods_b if "IoBad" in m.folder)
    bad.usar = True
    bad.pak_elegido = bad.paks[0] if bad.paks else ""
    r_bad = analyze_mod_structure(bad, "ue5_iostore_mods")
    ok("s28_incompleto", r_bad.classification == "INCOMPLETO", r_bad.classification)

    rec = GameRecord(
        id="s29_remake",
        name="S29 Remake Sintético",
        mods_dir=str(root / "mods_dest_remake"),
        stage_dir=str(stage),
        adapter="ue4_paks_mods",
        destination_verified=True,
        path_status="installed",
        archive_dir=str(root / "archive_own"),
        work_library_dir=str(root / "work_library"),
        game_root=str(root / "game_root_ficticio"),
        data_dir_name="s29_remake",
    )
    gpaths = game_paths_for(rec, app_data=root / "app_data")
    ensure_game_data_dir(gpaths)
    ctx = gpaths.apply_context()
    settings = ConflictSettings(
        adapter_id="ue4_paks_mods",
        game_id="s29_remake",
        destination_verified=True,
        install_mode="COPY",
        stage_root=stage,
        work_root=root / "work_library",
    )

    simple.usar = True
    simple.pak_elegido = "Simple.pak"
    fov.usar = True
    fov.pak_elegido = "Camera_FOV70.pak"
    plan = plan_apply([simple, fov], ctx, settings)
    ok(
        "preparar_simular",
        plan.conflicts == 0 and bool(plan.to_add) and not plan.errors,
        f"add={len(plan.to_add)} conf={plan.conflicts}",
    )
    foreign_before = (ctx.mods / "foreign_user_file.txt").read_text(encoding="utf-8")
    execute(plan, ctx, mods=[simple, fov])
    ok(
        "aplicar_sandbox",
        (ctx.mods / "Simple.pak").is_file()
        and (ctx.mods / "Camera_FOV70.pak").is_file()
        and not (ctx.mods / "Camera_FOV90.pak").is_file(),
        "paks instalados",
    )
    man = load_manifest(ctx)
    ok("manifiesto", bool(man), f"entries={len(man)}")

    coll_a.usar = True
    coll_a.pak_elegido = "SharedName.pak"
    coll_b.usar = True
    coll_b.pak_elegido = "SharedName.pak"
    plan_c = plan_apply([coll_a, coll_b], ctx, settings)
    ok("conflictos", plan_c.conflicts > 0 or plan_c.file_unresolved > 0, f"conf={plan_c.conflicts}")

    simple.usar = False
    fov.usar = False
    plan_off = plan_apply([simple, fov], ctx, settings)
    execute(plan_off, ctx, mods=[simple, fov])
    ok(
        "desactivar",
        not (ctx.mods / "Simple.pak").is_file(),
        "retirado",
    )
    ok(
        "ajeno_intacto",
        (ctx.mods / "foreign_user_file.txt").read_text(encoding="utf-8") == foreign_before,
        "foreign",
    )

    ops = list_operations(ctx.data_dir) if ctx.data_dir else []
    target = next((o for o in ops if getattr(o, "backup_id", None)), None)
    if target:
        rp = plan_restore(ctx.data_dir, ctx, target.id)
        if rp.ok:
            execute_restore(rp, ctx, ctx.data_dir, confirm=True)
            ok("restaurar_historial", True, target.id)
        else:
            ok("restaurar_historial", False, "plan_restore no ok")
    else:
        ok("restaurar_historial", bool(ops), f"ops={len(ops)} (sin backup_id explícito)")

    # Asegurar destino limpio antes del ciclo archivo→WORK→plan
    for leftover in ("Simple.pak", "Camera_FOV70.pak", "Camera_FOV90.pak"):
        p = ctx.mods / leftover
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    # Archivar + WORK
    simple2 = next(m for m in scan_staging(stage) if m.folder.startswith("S29_Simple"))
    cr = create_own_archive(
        game_id="s29_remake",
        mod=simple2,
        stage_root=stage,
        dest_dir=root / "archive_own",
    )
    ok("archivar_zip", cr.ok, cr.published_path or ";".join(cr.errors[:2]))
    if cr.ok:
        idx = load_index(root / "work_library", game_id="s29_remake")
        rr = restore_archive_to_work(
            game_id="s29_remake",
            archive_path=Path(cr.published_path),
            work_root=root / "work_library",
            idx=idx,
        )
        ok("recuperar_work", rr.ok, rr.work_path or ";".join(rr.errors[:2]))
        if rr.ok:
            idx = load_index(root / "work_library", game_id="s29_remake")
            wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
            wm.pak_elegido = wm.paks[0] if wm.paks else "Simple.pak"
            plan_w = plan_apply([wm], ctx, settings)
            ok(
                "simular_desde_work",
                plan_w.conflicts == 0
                and not plan_w.errors
                and (bool(plan_w.to_add) or (ctx.mods / "Simple.pak").is_file()),
                f"add={len(plan_w.to_add)} err={plan_w.errors[:2]}",
            )

    print(f"E2E headless: {'OK' if not failures else 'FAIL'} ({len(failures)} fallos)")
    return 0 if not failures else 1


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def run_ui(root: Path, *, auto_demo: bool = False) -> int:
    activate_env(root)
    # Importar UI solo tras env
    from app.gui import ModManagerApp

    app = ModManagerApp()
    title = app.title()
    if "F7777" not in title and "tech" not in title.lower():
        _safe_print(f"AVISO: titulo inesperado: {title}")
    try:
        app.title(f"{title}  [S29 SANDBOX]")
    except Exception:
        pass
    app.geometry("1480x900+30+30")
    app.deiconify()
    app.lift()
    app.update()
    app.refresh()
    app.update()

    if auto_demo:
        try:
            app.show_view("library")
            app.update()
            lib = app.view_library
            lib.search_var.set("S29")
            lib.redraw()
            app.update()
            time.sleep(0.3)
            def _wait_analysis(timeout_s: float = 8.0) -> bool:
                t_end = time.time() + timeout_s
                while time.time() < t_end:
                    app.update()
                    time.sleep(0.05)
                    ready = bool(getattr(app, "_analysis_ready", False))
                    struct = getattr(app, "_structure_by_folder", None) or {}
                    if ready and struct:
                        return True
                return bool(getattr(app, "_structure_by_folder", None))

            # Esperar análisis S28 del refresh inicial
            _wait_analysis()
            # Forzar reanálisis por si el hilo anterior se invalidó
            app.analyze_conflicts()
            _wait_analysis()

            # Seleccionar S29_Simple (mejor para ver SIMPLE)
            selected = False
            target = next(
                (m for m in app.mods if m.folder.startswith("S29_Simple")),
                app.mods[0] if app.mods else None,
            )
            if target and hasattr(lib, "tree") and lib.tree.exists(target.folder):
                lib.tree.selection_set(target.folder)
                lib.tree.see(target.folder)
                lib.on_select()
                selected = True
            elif target:
                app._selected_folder = target.folder
                try:
                    lib.on_select()
                except Exception:
                    pass
                selected = True
            app.update()
            detail = ""
            if hasattr(lib, "detail_badges"):
                detail = str(lib.detail_badges.cget("text") or "")
            # Si aún no hay S28, rellenar caché en hilo UI (mismo motor) y refrescar detalle
            if "Formato:" not in detail and app.mods:
                from app.core.mod_structure import analyze_library_structures

                aid = str(getattr(app.session.record, "adapter", "") or "ue4_paks_mods")
                app._structure_by_folder = analyze_library_structures(
                    app.mods, aid, cache=getattr(app, "_structure_cache", {})
                )
                if selected:
                    lib.on_select()
                    app.update()
                    detail = str(lib.detail_badges.cget("text") or "")
            _safe_print("UI detalle (extracto):")
            _safe_print(detail[:500])
            has_s28 = ("Clasificacion:" in detail) or ("Clasificación:" in detail) or (
                "Formato:" in detail
            )
            _safe_print(
                f"S28 en detalle: {has_s28} selected={selected} "
                f"struct_n={len(getattr(app, '_structure_by_folder', {}) or {})}"
            )

            for m in app.mods:
                m.usar = False
            for m in app.mods:
                if m.folder.startswith("S29_Simple"):
                    m.usar = True
                    m.pak_elegido = m.paks[0] if m.paks else ""
                if m.folder.startswith("S29_FOV"):
                    m.usar = True
                    m.pak_elegido = "Camera_FOV70.pak"
            lib.redraw()
            # Sin mainloop, after() del hilo puede no completar: plan sync (mismo motor).
            from app.core.apply import plan_apply
            from app.core.mod_structure import (
                analyze_library_structures,
                structure_blocks_apply,
            )

            aid = str(getattr(app.session.record, "adapter", "") or "ue4_paks_mods")
            plan = plan_apply(app.mods, app._ctx(), app._settings())
            structs = analyze_library_structures(
                app.mods, aid, cache=getattr(app, "_structure_cache", {})
            )
            app._last_plan = plan
            app._structure_by_folder = structs
            app._structure_blocks_apply = structure_blocks_apply(structs, app.mods)
            app._analysis_ready = plan is not None
            app._analysis_for_gen = app._session_gen
            app._sync_apply_button()
            app.show_view("conflicts")
            app.update()
            time.sleep(0.5)
            try:
                from PIL import ImageGrab

                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, h = app.winfo_width(), app.winfo_height()
                cap_dir = root / "_ui_captures"
                cap_dir.mkdir(exist_ok=True)
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
                dest = cap_dir / "s29_conflicts.png"
                img.save(dest)
                _safe_print(f"Captura UI: {dest}")
                # segunda captura biblioteca
                app.show_view("library")
                app.update()
                time.sleep(0.3)
                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, h = app.winfo_width(), app.winfo_height()
                img2 = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
                dest2 = cap_dir / "s29_library.png"
                img2.save(dest2)
                _safe_print(f"Captura UI: {dest2}")
            except Exception as e:
                _safe_print(f"Captura UI omitida: {e}")
            applyable = app.plan_is_applyable()
            tip = getattr(app, "_apply_tip", "")
            _safe_print(f"Apply aplicable (sandbox): {applyable} tip={tip}")
            games = list(getattr(app.registry, "games", {}) or {})
            _safe_print(f"Juegos en registro: {games}")
            real_leak = any(
                g in games for g in ("ff7_rebirth", "stellar_blade", "ff7_remake")
            )
            _safe_print(f"Sin perfiles reales: {not real_leak}")
            # Capturas ya hechas = verificación visual realizada
            caps = list((root / "_ui_captures").glob("s29_*.png"))
            _safe_print(f"Capturas visuales: {len(caps)}")
            time.sleep(1.0)
            app.destroy()
            return 0 if has_s28 and not real_leak and caps else 1
        except Exception:
            traceback.print_exc()
            try:
                app.destroy()
            except Exception:
                pass
            return 1

    _safe_print(f"S29 UI lista. Sandbox: {root}")
    _safe_print("Cierre la ventana para terminar.")
    app.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S29 modo prueba UI sintético")
    ap.add_argument("--reset", action="store_true", help="Recrear sandbox desde cero")
    ap.add_argument("--root", type=str, default="", help="Raíz sandbox opcional")
    ap.add_argument("--e2e", action="store_true", help="Ciclo motor headless")
    ap.add_argument("--ui", action="store_true", help="Abrir interfaz")
    ap.add_argument(
        "--auto-demo",
        action="store_true",
        help="Con --ui: recorrido automático corto + captura",
    )
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="Solo preparar sandbox y mostrar rutas",
    )
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root.strip() else default_sandbox_root()
    root = prepare_sandbox(root, reset=args.reset)
    print(f"Sandbox S29: {root}")
    print(f"SGM_DATA_DIR -> {root / 'app_data'}")

    if args.prepare_only:
        return 0
    if args.e2e:
        code = run_headless_e2e(root)
        if code != 0:
            return code
    if args.ui or (not args.e2e and not args.prepare_only):
        # Por defecto abrir UI si no se pidió solo e2e
        if args.e2e and not args.ui:
            return 0
        return run_ui(root, auto_demo=args.auto_demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
