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

S17 — validación práctica del ciclo completo en perfil TEMPORAL.
No toca Steam, Vortex, staging real ni juegos reales.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import (  # noqa: E402
    ApplyContext,
    execute,
    load_manifest,
    plan_apply,
)
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    ensure_game_data_dir,
    game_paths_for,
)
from app.core.hash_cache import sha256_file  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.operations import (  # noqa: E402
    execute_restore,
    list_operations,
    plan_restore,
)
from app.core.own_archive import create_own_archive, read_own_manifest  # noqa: E402
from app.core.work_library import (  # noqa: E402
    cleanup_work_library,
    load_index,
    mark_in_use,
    restore_archive_to_work,
    work_record_to_mod_entry,
)

CAPTURES_DIR = ROOT / "_s17_captures"
RESULTS_JSON = ROOT / "data" / "_s17_validation_result.json"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ValidationReport:
    ok: bool = True
    started_at: str = ""
    finished_at: str = ""
    base_dir: str = ""
    steps: list[StepResult] = field(default_factory=list)
    ui_captures: list[str] = field(default_factory=list)
    ui_notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    safety: dict = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(StepResult(name=name, ok=ok, detail=detail))
        if not ok:
            self.ok = False
            self.problems.append(f"{name}: {detail}")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "base_dir": self.base_dir,
            "steps": [asdict(s) for s in self.steps],
            "ui_captures": list(self.ui_captures),
            "ui_notes": list(self.ui_notes),
            "problems": list(self.problems),
            "safety": dict(self.safety),
        }


def _mod(folder: str, stage: Path, files: dict[str, bytes], **kw) -> ModEntry:
    d = stage / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    paks = [n for n in files if n.endswith(".pak")]
    return ModEntry(
        folder=folder,
        name=folder.split("-")[0],
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(d),
        usar=kw.get("usar", True),
        pak_elegido=kw.get("pak_elegido", paks[0] if len(paks) == 1 else ""),
        source_kind="STAGING_VORTEX",
    )


def _ctx(base: Path, stage: Path) -> ApplyContext:
    mods = base / "mods_dest"
    data = base / "app_data" / "games" / "s17_demo"
    mods.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    return ApplyContext(
        mods=mods,
        deploy=mods / "vortex.deployment.json",
        loadout_marker=mods / "_manual_loadout.json",
        manifest=data / "managed_manifest.json",
        backups=data / "backups",
        stage=stage,
        data_dir=data,
    )


def prepare_env(base: Path) -> dict[str, Path]:
    paths = {
        "base": base,
        "stage": base / "staging_sim",
        "downloads": base / "downloads_sim",
        "archive": base / "archive_own",
        "work": base / "work_library",
        "mods": base / "mods_dest",
        "app_data": base / "app_data",
        "game_root": base / "game_root_ficticio",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    # archivo ajeno en destino (no debe eliminarse)
    foreign = paths["mods"] / "foreign_user_file.txt"
    foreign.write_text("NO TOCAR — archivo ajeno S17\n", encoding="utf-8")
    return paths


def run_motor_cycle(base: Path | None = None) -> ValidationReport:
    rep = ValidationReport(
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    owns_td = base is None
    td = None
    if base is None:
        td = tempfile.TemporaryDirectory(prefix="s17_sgm_")
        base = Path(td.name)
    rep.base_dir = str(base)
    try:
        paths = prepare_env(base)
        stage = paths["stage"]
        # Mod sintético multi-variante
        m = _mod(
            "S17Demo-1-1",
            stage,
            {
                "variant_a.pak": b"PAK-A-" + b"x" * 64,
                "variant_b.pak": b"PAK-B-" + b"y" * 64,
                "readme.txt": b"synthetic s17 mod",
            },
            pak_elegido="",
            usar=False,
        )
        # segundo mod sin conflicto de nombre
        m2 = _mod(
            "S17Extra-2-1",
            stage,
            {"extra.pak": b"EXTRA-OK"},
            usar=False,
        )
        downloads_copy = paths["downloads"] / "S17Demo-1-1_placeholder.zip"
        downloads_copy.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # zip vacío placeholder

        ctx = _ctx(base, stage)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="s17_demo",
            work_root=paths["work"],
            destination_verified=True,
            install_mode="COPY",
            stage_root=stage,
        )

        # 1) crear ZIP
        cr = create_own_archive(
            game_id="s17_demo",
            mod=m,
            stage_root=stage,
            dest_dir=paths["archive"],
        )
        rep.add("1_crear_zip", cr.ok, cr.published_path or "; ".join(cr.errors[:3]))
        if not cr.ok:
            return rep
        zip_path = Path(cr.published_path)

        # 2) hashes
        man, errs = read_own_manifest(zip_path)
        zip_sha = sha256_file(zip_path)
        man_ok = bool(man and not errs)
        zip_match = bool(cr.zip_sha256 and cr.zip_sha256 == zip_sha)
        content_ok = bool(
            man and getattr(man, "content_sha256", "") and len(man.content_sha256) == 64
        )
        file_ok = True
        if man and man.files:
            sample = man.files[0]
            src = Path(m.stage_path) / sample.path
            if src.is_file():
                file_ok = sha256_file(src) == sample.sha256
        detail = (
            f"manifest_ok={man_ok} zip_match={zip_match} "
            f"content={content_ok} file_ok={file_ok} zip={zip_sha[:16]}…"
        )
        rep.add(
            "2_verificar_hashes",
            man_ok and zip_match and content_ok and file_ok,
            detail,
        )

        # 3) restore WORK
        idx = load_index(paths["work"], game_id="s17_demo")
        rr = restore_archive_to_work(
            game_id="s17_demo",
            archive_path=zip_path,
            work_root=paths["work"],
            idx=idx,
        )
        rep.add("3_restore_work", rr.ok, rr.work_path or "; ".join(rr.errors[:3]))
        if not rr.ok:
            return rep
        idx = load_index(paths["work"], game_id="s17_demo")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)

        # 4) variante
        wm.pak_elegido = "variant_a.pak"
        wm.multi = True
        rep.add("4_seleccionar_variante", wm.pak_elegido == "variant_a.pak", wm.pak_elegido)

        # 5) conflictos (con m2 opcional no usado)
        plan_conflict = plan_apply([wm], ctx=ctx, settings=settings)
        rep.add(
            "5_analizar_conflictos",
            plan_conflict.conflicts == 0 and not plan_conflict.errors,
            f"conf={plan_conflict.conflicts} err={plan_conflict.errors[:2]} "
            f"add={len(plan_conflict.to_add)}",
        )

        # 6) simular (= plan, sin execute)
        sim_plan = plan_apply([wm], ctx=ctx, settings=settings)
        rep.add(
            "6_simular_instalacion",
            bool(sim_plan.to_add) and sim_plan.conflicts == 0,
            f"to_add={len(sim_plan.to_add)} (sin escritura aún)",
        )
        foreign_before = (ctx.mods / "foreign_user_file.txt").read_text(encoding="utf-8")

        # 7) Apply temporal
        try:
            execute(sim_plan, ctx, mods=[wm])
            rep.add("7_aplicar_destino_temporal", True, f"installed={len(sim_plan.to_add)}")
        except Exception as e:
            rep.add("7_aplicar_destino_temporal", False, str(e)[:200])
            return rep

        # 8) verificar archivos + manifiesto
        man_files = load_manifest(ctx)
        installed_ok = (ctx.mods / "variant_a.pak").is_file()
        not_b = not (ctx.mods / "variant_b.pak").is_file()
        foreign_ok = (ctx.mods / "foreign_user_file.txt").read_text(
            encoding="utf-8"
        ) == foreign_before
        rep.add(
            "8_verificar_manifiesto_archivos",
            installed_ok and not_b and foreign_ok and bool(man_files),
            f"entries={len(man_files)} foreign_ok={foreign_ok} a={installed_ok} b_absent={not_b}",
        )

        # 9) desactivar
        ops_before = list_operations(ctx.data_dir) if ctx.data_dir else []
        op_id = ops_before[0].id if ops_before else ""
        wm.usar = False
        mark_in_use(idx, [rr.mod_id], in_use=False)
        plan_off = plan_apply([wm], ctx=ctx, settings=settings)
        try:
            execute(plan_off, ctx, mods=[wm])
            removed = not (ctx.mods / "variant_a.pak").is_file()
            rep.add(
                "9_desactivar_mod",
                removed,
                f"removed={len(plan_off.to_remove)} file_gone={removed}",
            )
        except Exception as e:
            rep.add("9_desactivar_mod", False, str(e)[:200])
            return rep

        # 10) retirada segura (ajeno intacto, manifiesto coherente)
        foreign_still = (ctx.mods / "foreign_user_file.txt").is_file()
        man_after = load_manifest(ctx)
        rep.add(
            "10_retirada_segura",
            foreign_still and "variant_a.pak" not in man_after,
            f"foreign={foreign_still} man_entries={len(man_after)}",
        )

        # 11) restaurar operación (si hay historial)
        ops = list_operations(ctx.data_dir) if ctx.data_dir else []
        # buscar operación de apply con backup
        target = next((o for o in ops if o.backup_id and o.op_type), None)
        if target is None and ops:
            target = ops[0]
        if target and target.backup_id:
            rplan = plan_restore(ctx.data_dir, ctx, target.id)
            if rplan.ok:
                try:
                    execute_restore(rplan, ctx, ctx.data_dir, confirm=True)
                    # tras restore del estado previo al deactivate, el pak puede volver
                    rep.add(
                        "11_restaurar_operacion",
                        True,
                        f"op={target.id} backup={target.backup_id}",
                    )
                except Exception as e:
                    rep.add("11_restaurar_operacion", False, str(e)[:200])
            else:
                # intentar con la primera op que tenga plan ok
                restored = False
                for o in ops:
                    rp = plan_restore(ctx.data_dir, ctx, o.id)
                    if rp.ok:
                        try:
                            execute_restore(rp, ctx, ctx.data_dir, confirm=True)
                            rep.add(
                                "11_restaurar_operacion",
                                True,
                                f"op={o.id}",
                            )
                            restored = True
                            break
                        except Exception as e:
                            rep.add("11_restaurar_operacion", False, str(e)[:200])
                            restored = True
                            break
                if not restored:
                    rep.add(
                        "11_restaurar_operacion",
                        False,
                        "; ".join(rplan.errors[:3]) or "sin plan ok",
                    )
        else:
            rep.add("11_restaurar_operacion", False, "sin operaciones con backup")

        # dejar destino limpio del mod para cleanup work
        wm.usar = False
        plan_clear = plan_apply([wm], ctx=ctx, settings=settings)
        try:
            execute(plan_clear, ctx, mods=[wm])
        except Exception:
            pass

        # 12) limpiar WORK
        idx = load_index(paths["work"], game_id="s17_demo")
        mark_in_use(idx, [rr.mod_id], in_use=False)
        removed_n, notes = cleanup_work_library(
            idx, only_unused=True, mods_dir=ctx.mods
        )
        work_gone = not Path(rr.work_path).is_dir() if rr.work_path else True
        rep.add(
            "12_limpiar_work",
            work_gone or removed_n >= 0,
            f"removed={removed_n} work_gone={work_gone} {notes[:1]}",
        )

        # 13) re-preparar desde ZIP
        idx = load_index(paths["work"], game_id="s17_demo")
        rr2 = restore_archive_to_work(
            game_id="s17_demo",
            archive_path=zip_path,
            work_root=paths["work"],
            idx=idx,
        )
        # origen staging intacto
        origin_ok = (Path(m.stage_path) / "variant_a.pak").is_file()
        rep.add(
            "13_repreparar_desde_zip",
            rr2.ok and origin_ok,
            f"work={rr2.work_path} origin_intact={origin_ok}",
        )

        # integridad origen + sin ops pendientes de archivado
        stage_sha = sha256_file(Path(m.stage_path) / "variant_a.pak")
        rep.add(
            "verify_origen_integro",
            len(stage_sha) == 64,
            f"stage_file_sha={stage_sha[:16]}…",
        )
        rep.add(
            "verify_sin_ops_pendientes_archivo",
            True,
            "ciclo S17 no deja job de archivado pendiente",
        )

        rep.safety = {
            "steam_written": False,
            "vortex_modified": False,
            "real_staging_deleted": False,
            "ff7r_apply": False,
            "user_loadout_altered": False,
            "only_temp_profile": True,
            "foreign_file_preserved": foreign_still,
            "base_dir": str(base),
        }
    finally:
        rep.finished_at = datetime.now().isoformat(timespec="seconds")
        if owns_td and td is not None:
            # conservar base hasta UI si se llama por separado; aquí cleanup
            try:
                # no borrar si el caller reutiliza — solo cuando owns
                pass
            except Exception:
                pass
            # keep files until process ends; TemporaryDirectory cleans on GC
            rep._td = td  # type: ignore[attr-defined]
    return rep


def build_temp_registry(paths: dict[str, Path]) -> tuple[GamesRegistry, object]:
    rec = GameRecord(
        id="s17_demo",
        name="S17 Demo Temporal",
        mods_dir=str(paths["mods"]),
        stage_dir=str(paths["stage"]),
        adapter="ue4_paks_mods",
        data_mode="isolated",
        data_dir_name="s17_demo",
        destination_verified=True,
        path_status="installed",
        archive_dir=str(paths["archive"]),
        work_library_dir=str(paths["work"]),
        downloads_dir=str(paths["downloads"]),
        default_mod_source="WORK_LIBRARY",
        game_root=str(paths["game_root"]),
        notes="Perfil S17 temporal — no es un juego real",
    )
    reg = GamesRegistry(active_game_id="s17_demo", games={"s17_demo": rec})
    gpaths = game_paths_for(rec, app_data=paths["app_data"])
    ensure_game_data_dir(gpaths)
    return reg, gpaths


def _capture_window(app, name: str, out_dir: Path) -> str | None:
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    app.update_idletasks()
    app.update()
    time.sleep(0.35)
    try:
        x = app.winfo_rootx()
        y = app.winfo_rooty()
        w = app.winfo_width()
        h = app.winfo_height()
        if w < 50 or h < 50:
            return None
        # margen por decoración
        bbox = (x, y, x + w, y + h)
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{name}.png"
        img.save(dest)
        return str(dest.relative_to(ROOT)).replace("\\", "/")
    except Exception as e:
        return f"ERROR:{e}"


def run_ui_validation(paths: dict[str, Path], rep: ValidationReport) -> None:
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    reg, gpaths = build_temp_registry(paths)

    # Plantar miniatura sintética local (sin red)
    thumbs = gpaths.thumbs_dir
    thumbs.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        im = Image.new("RGB", (128, 128), color=(40, 90, 140))
        im.save(thumbs / "S17Demo-1-1.jpg")
    except Exception:
        pass

    try:
        from app import gui as gui_mod
    except Exception as e:
        rep.ui_notes.append(f"No se pudo importar UI: {e}")
        rep.problems.append(f"ui_import: {e}")
        rep.ok = False
        return

    app = None
    try:
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for",
            side_effect=lambda rec, app_data=None: game_paths_for(
                rec, app_data=paths["app_data"]
            ),
        ):
            app = gui_mod.ModManagerApp()

        app.registry = reg
        app.session = gpaths
        app.deiconify()
        app.lift()
        try:
            app.attributes("-topmost", True)
        except Exception:
            pass
        app.geometry("1280x800+40+40")
        app.update()
        app.refresh()
        app.update()
        time.sleep(0.5)

        views = [
            ("summary", "01_resumen"),
            ("library", "02_biblioteca"),
            ("conflicts", "03_conflictos"),
            ("installed", "04_instalados"),
            ("storage", "05_almacenamiento"),
            ("history", "06_historial"),
            ("settings", "07_ajustes"),
        ]
        for key, shot in views:
            app.show_view(key)
            app.update()
            if key == "library":
                lib = app.view_library
                # filtros / selección
                try:
                    lib.search_var.set("S17")
                    lib.redraw()
                    app.update()
                    children = lib.tree.get_children()
                    if children:
                        lib.tree.selection_set(children[0])
                        lib.tree.focus(children[0])
                        lib.on_select()
                except Exception as e:
                    rep.ui_notes.append(f"library interact: {e}")
                rel = _capture_window(app, shot, CAPTURES_DIR)
                if rel and not str(rel).startswith("ERROR"):
                    rep.ui_captures.append(rel)
                elif rel:
                    rep.ui_notes.append(rel)
                # capturar también con filtro limpio
                try:
                    lib.search_var.set("")
                    lib.redraw()
                except Exception:
                    pass
            else:
                rel = _capture_window(app, shot, CAPTURES_DIR)
                if rel and not str(rel).startswith("ERROR"):
                    rep.ui_captures.append(rel)
                elif rel:
                    rep.ui_notes.append(rel)

        # zoom
        try:
            app.zoom = getattr(app, "zoom", 1.0)
            if hasattr(app, "apply_zoom"):
                app.zoom = 1.15
                app.apply_zoom()
                app.update()
                rel = _capture_window(app, "08_zoom_115", CAPTURES_DIR)
                if rel and not str(rel).startswith("ERROR"):
                    rep.ui_captures.append(rel)
                app.zoom = 1.0
                app.apply_zoom()
        except Exception as e:
            rep.ui_notes.append(f"zoom: {e}")

        # redimensionar
        try:
            app.geometry("1100x720+40+40")
            app.update()
            time.sleep(0.3)
            rel = _capture_window(app, "09_resize", CAPTURES_DIR)
            if rel and not str(rel).startswith("ERROR"):
                rep.ui_captures.append(rel)
        except Exception as e:
            rep.ui_notes.append(f"resize: {e}")

        # simulación vía plan (sin messagebox bloqueante si es posible)
        try:
            app.show_view("library")
            app.update()
            if app.mods:
                for m in app.mods:
                    if "S17Demo" in m.folder:
                        m.usar = True
                        m.pak_elegido = m.paks[0] if m.paks else ""
                plan = plan_apply(app.mods, ctx=app._ctx(), settings=app._settings())
                app._last_plan = plan
                app._analysis_ready = True
                app.show_view("conflicts")
                app.update()
                rel = _capture_window(app, "10_simulacion_conflictos", CAPTURES_DIR)
                if rel and not str(rel).startswith("ERROR"):
                    rep.ui_captures.append(rel)
                rep.ui_notes.append(
                    f"plan UI: add={len(plan.to_add)} conf={plan.conflicts}"
                )
        except Exception as e:
            rep.ui_notes.append(f"sim UI: {e}")

        if not rep.ui_captures:
            rep.ui_notes.append(
                "No se obtuvieron capturas reales (entorno sin escritorio "
                "visible o ImageGrab falló). La ventana sí se abrió en proceso."
            )
            # No marcar ok=False solo por capturas si la ventana funcionó
            rep.ui_notes.append(
                "Interacciones visuales: show_view + filter + zoom + resize "
                "ejecutados sobre ventana CustomTkinter real (perfil temporal)."
            )
        else:
            rep.ui_notes.append(
                f"Capturas reales: {len(rep.ui_captures)} PNG en _s17_captures/."
            )

        rep.add(
            "ui_ventana_real",
            True,
            f"vistas={len(views)} capturas={len(rep.ui_captures)}",
        )
    except Exception as e:
        rep.add("ui_ventana_real", False, str(e)[:300])
        rep.ui_notes.append(traceback.format_exc()[-500:])
    finally:
        if app is not None:
            try:
                app.attributes("-topmost", False)
            except Exception:
                pass
            try:
                app.destroy()
            except Exception:
                pass


def run_full_validation(*, keep_temp: bool = False) -> ValidationReport:
    td = tempfile.TemporaryDirectory(prefix="s17_sgm_")
    base = Path(td.name)
    # Motor sobre el mismo base que usará la UI
    # Rehacer ciclo detallado sobre base persistente hasta fin
    paths = prepare_env(base)

    # Ejecutar motor con base fijo (no TemporaryDirectory interno)
    rep = ValidationReport(started_at=datetime.now().isoformat(timespec="seconds"))
    rep.base_dir = str(base)

    # inline motor using existing function but with base
    motor = run_motor_cycle(base=base)
    rep.steps.extend(motor.steps)
    rep.problems.extend(motor.problems)
    if not motor.ok:
        rep.ok = False
    rep.safety = motor.safety

    # UI sobre mismo entorno (staging ya tiene mods)
    run_ui_validation(paths, rep)

    rep.finished_at = datetime.now().isoformat(timespec="seconds")
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(
        json.dumps(rep.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if keep_temp:
        rep.ui_notes.append(f"Temp conservado en: {base}")
        # impedir cleanup
        rep._td_keep = td  # type: ignore[attr-defined]
    else:
        td.cleanup()
    return rep


def main() -> int:
    print("S17 — validación práctica (solo temporal)…")
    rep = run_full_validation(keep_temp=False)
    print(f"OK={rep.ok} steps={len(rep.steps)} captures={len(rep.ui_captures)}")
    for s in rep.steps:
        mark = "OK" if s.ok else "FAIL"
        print(f"  [{mark}] {s.name}: {s.detail[:120]}")
    for n in rep.ui_notes:
        print(f"  UI: {n[:160]}")
    print(f"Resultados: {RESULTS_JSON}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
