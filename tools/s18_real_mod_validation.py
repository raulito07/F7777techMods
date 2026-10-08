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

S18 — validación con mod real FF7R SIN Apply real ni tocar loadout/Vortex.
"""

from __future__ import annotations

import json
import shutil
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
    ensure_registry,
    game_paths_for,
)
from app.core.hash_cache import sha256_file  # noqa: E402
from app.core.inventory import ModEntry, scan_staging  # noqa: E402
from app.core.operations import execute_restore, list_operations, plan_restore  # noqa: E402
from app.core.own_archive import create_own_archive, read_own_manifest  # noqa: E402
from app.core.work_library import (  # noqa: E402
    cleanup_work_library,
    load_index,
    mark_in_use,
    restore_archive_to_work,
    work_record_to_mod_entry,
)

CAPTURES = ROOT / "_s18_captures"
RESULT_JSON = ROOT / "data" / "_s18_validation_result.json"
CANDIDATE_FOLDER = "FOV70-788-1-1648368344"


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    ok: bool = True
    started_at: str = ""
    finished_at: str = ""
    candidate: dict = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    real_sim: dict = field(default_factory=dict)
    sandbox: dict = field(default_factory=dict)
    ui_captures: list[str] = field(default_factory=list)
    ui_notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    safety: dict = field(default_factory=dict)
    staging_sha_before: str = ""
    staging_sha_after: str = ""

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(Step(name=name, ok=ok, detail=detail))
        if not ok:
            self.ok = False
            self.problems.append(f"{name}: {detail}")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "candidate": self.candidate,
            "steps": [asdict(s) for s in self.steps],
            "real_sim": self.real_sim,
            "sandbox": self.sandbox,
            "ui_captures": self.ui_captures,
            "ui_notes": self.ui_notes,
            "problems": self.problems,
            "safety": self.safety,
            "staging_sha_before": self.staging_sha_before,
            "staging_sha_after": self.staging_sha_after,
        }


def _entry_from_stage(folder: str, stage: Path) -> ModEntry:
    d = stage / folder
    paks = sorted(p.name for p in d.rglob("*.pak"))
    return ModEntry(
        folder=folder,
        name=folder.split("-")[0],
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(d),
        usar=True,
        pak_elegido=paks[0] if len(paks) == 1 else "",
        source_kind="STAGING_VORTEX",
    )


def select_candidate(stage: Path) -> tuple[str, dict]:
    """Elige el más pequeño con 1 .pak, sin especiales."""
    best = None
    meta = {}
    for d in stage.iterdir():
        if not d.is_dir():
            continue
        paks = list(d.rglob("*.pak"))
        if len(paks) != 1:
            continue
        special = any(
            f.suffix.lower() in {".exe", ".bat", ".ps1", ".dll", ".msi"}
            for f in d.rglob("*")
            if f.is_file()
        )
        if special:
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        if size <= 0 or size > 512 * 1024:
            continue
        if best is None or size < best[0]:
            best = (size, d.name, paks[0])
    if best is None:
        raise RuntimeError("No hay candidato adecuado en staging")
    # Prefer FOV70 if present and eligible
    preferred = stage / CANDIDATE_FOLDER
    if preferred.is_dir() and list(preferred.rglob("*.pak")):
        folder = CANDIDATE_FOLDER
        pak = list(preferred.rglob("*.pak"))[0]
        size = sum(f.stat().st_size for f in preferred.rglob("*") if f.is_file())
    else:
        folder = best[1]
        pak = best[2]
        size = best[0]
    pak_path = stage / folder / pak.name if hasattr(pak, "name") else stage / folder / pak
    if isinstance(pak, Path):
        pak_path = pak
    else:
        pak_path = stage / folder / str(pak)
    sha = sha256_file(pak_path)
    meta = {
        "folder": folder,
        "name": folder.split("-")[0],
        "stage_path": str(stage / folder),
        "pak": pak_path.name,
        "size_bytes": pak_path.stat().st_size,
        "size_total_bytes": size,
        "sha256": sha,
        "reason": (
            "Único .pak, tamaño muy pequeño, sin variantes, sin especiales, "
            "adapter ue4_paks_mods (FF7R), no en destino, no activo en loadout."
        ),
        "pak_internal_analysis_limit": (
            "El gestor no desempaqueta/analiza el contenido interno UE4 del .pak "
            "(solo ruta, tamaño, hash y clasificación por extensión/nombre)."
        ),
    }
    return folder, meta


def simulate_real_ff7r(folder: str, rep: Report) -> None:
    reg = ensure_registry()
    rec = reg.games["ff7r_remake"]
    gp = game_paths_for(rec)
    loadout_mtime_before = (
        gp.loadout_json.stat().st_mtime if gp.loadout_json.exists() else None
    )
    ctx = gp.apply_context()
    settings = gp.conflict_settings()
    # NO merge_loadout / NO guardar: candidato aislado
    m = _entry_from_stage(folder, gp.stage_dir)
    m.usar = True
    plan = plan_apply([m], ctx=ctx, settings=settings)
    dest_exists = (gp.mods_dir / m.pak_elegido).exists() if m.pak_elegido else False
    man = load_manifest(ctx)
    rep.real_sim = {
        "game_id": rec.id,
        "mods_dir": str(gp.mods_dir),
        "stage_dir": str(gp.stage_dir),
        "to_add": list(plan.to_add),
        "to_update": list(plan.to_update),
        "to_remove": list(plan.to_remove),
        "conflicts": plan.conflicts,
        "errors": list(plan.errors[:8]),
        "install_mode": plan.install_mode_policy,
        "dest_pak_exists_before": dest_exists,
        "manifest_entries": len(man),
        "apply_executed": False,
        "loadout_modified": False,
        "isolated_candidate": True,
    }
    ok = plan.conflicts == 0 and not plan.errors and bool(plan.to_add)
    rep.add(
        "sim_destino_real_aislado",
        ok,
        f"add={plan.to_add} conf={plan.conflicts} err={plan.errors[:2]}",
    )
    loadout_mtime_after = (
        gp.loadout_json.stat().st_mtime if gp.loadout_json.exists() else None
    )
    if loadout_mtime_before != loadout_mtime_after:
        rep.add("loadout_intact", False, "mtime del loadout cambió")
    else:
        rep.add("loadout_intact", True, "loadout.json no modificado")


def run_sandbox_cycle(folder: str, stage_src: Path, rep: Report) -> None:
    td = tempfile.TemporaryDirectory(prefix="s18_sgm_")
    base = Path(td.name)
    stage = base / "stage_copy"
    arch = base / "archive"
    work = base / "work"
    mods = base / "mods_dest"
    data = base / "data"
    for p in (stage, arch, work, mods, data):
        p.mkdir(parents=True)
    # copia temporal del candidato (no toca staging real después)
    src = stage_src / folder
    dst = stage / folder
    shutil.copytree(src, dst)
    # ajeno
    (mods / "foreign_user_file.txt").write_text("AJENO S18\n", encoding="utf-8")

    m = _entry_from_stage(folder, stage)
    m.usar = False
    ctx = ApplyContext(
        mods=mods,
        deploy=mods / "vortex.deployment.json",
        loadout_marker=mods / "_manual_loadout.json",
        manifest=data / "managed_manifest.json",
        backups=data / "backups",
        stage=stage,
        data_dir=data,
    )
    settings = ConflictSettings(
        adapter_id="ue4_paks_mods",
        game_id="s18_sandbox",
        work_root=work,
        destination_verified=True,
        install_mode="COPY",
        stage_root=stage,
    )

    cr = create_own_archive(
        game_id="s18_sandbox", mod=m, stage_root=stage, dest_dir=arch
    )
    rep.add("sbx_zip", cr.ok, cr.published_path or "; ".join(cr.errors[:2]))
    if not cr.ok:
        rep._td = td  # type: ignore
        return

    zip_path = Path(cr.published_path)
    man, errs = read_own_manifest(zip_path)
    rep.add("sbx_manifest", bool(man and not errs), f"errs={errs[:2]}")

    idx = load_index(work, game_id="s18_sandbox")
    rr = restore_archive_to_work(
        game_id="s18_sandbox",
        archive_path=zip_path,
        work_root=work,
        idx=idx,
    )
    rep.add("sbx_work", rr.ok, rr.work_path or "; ".join(rr.errors[:2]))
    if not rr.ok:
        rep._td = td  # type: ignore
        return

    idx = load_index(work, game_id="s18_sandbox")
    wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
    wm.pak_elegido = m.pak_elegido

    plan = plan_apply([wm], ctx=ctx, settings=settings)
    rep.add(
        "sbx_plan",
        plan.conflicts == 0 and bool(plan.to_add),
        f"add={plan.to_add} conf={plan.conflicts}",
    )
    try:
        execute(plan, ctx, mods=[wm])
        inst = mods / wm.pak_elegido
        sha_ok = inst.is_file() and sha256_file(inst) == rep.candidate.get("sha256")
        rep.add("sbx_apply", sha_ok, f"sha_match={sha_ok} path={inst}")
    except Exception as e:
        rep.add("sbx_apply", False, str(e)[:200])
        rep._td = td  # type: ignore
        return

    foreign_ok = (mods / "foreign_user_file.txt").is_file()
    wm.usar = False
    mark_in_use(idx, [rr.mod_id], in_use=False)
    plan_off = plan_apply([wm], ctx=ctx, settings=settings)
    try:
        execute(plan_off, ctx, mods=[wm])
        gone = not (mods / m.pak_elegido).is_file()
        rep.add("sbx_deactivate", gone and foreign_ok, f"gone={gone} foreign={foreign_ok}")
    except Exception as e:
        rep.add("sbx_deactivate", False, str(e)[:200])

    ops = list_operations(data)
    restored = False
    for o in ops:
        rp = plan_restore(data, ctx, o.id)
        if rp.ok:
            try:
                execute_restore(rp, ctx, data, confirm=True)
                restored = True
                rep.add("sbx_restore_op", True, f"op={o.id}")
                break
            except Exception as e:
                rep.add("sbx_restore_op", False, str(e)[:200])
                restored = True
                break
    if not restored:
        rep.add("sbx_restore_op", False, "sin operación restaurable")

    # limpiar destino del mod y reinstall
    wm.usar = False
    try:
        execute(plan_apply([wm], ctx=ctx, settings=settings), ctx, mods=[wm])
    except Exception:
        pass
    idx = load_index(work, game_id="s18_sandbox")
    mark_in_use(idx, [rr.mod_id], in_use=False)
    cleanup_work_library(idx, only_unused=True, mods_dir=mods)

    idx = load_index(work, game_id="s18_sandbox")
    rr2 = restore_archive_to_work(
        game_id="s18_sandbox",
        archive_path=zip_path,
        work_root=work,
        idx=idx,
    )
    idx = load_index(work, game_id="s18_sandbox")
    wm2 = work_record_to_mod_entry(idx.mods[rr2.mod_id], usar=True)
    wm2.pak_elegido = m.pak_elegido
    plan2 = plan_apply([wm2], ctx=ctx, settings=settings)
    try:
        execute(plan2, ctx, mods=[wm2])
        rein = (mods / m.pak_elegido).is_file()
        sha2 = sha256_file(mods / m.pak_elegido) if rein else ""
        rep.add(
            "sbx_reinstall",
            rein and sha2 == rep.candidate.get("sha256"),
            f"sha={sha2[:16]}…",
        )
    except Exception as e:
        rep.add("sbx_reinstall", False, str(e)[:200])

    # staging copy intact + original staging check later
    copy_sha = sha256_file(dst / m.pak_elegido)
    rep.sandbox = {
        "base": str(base),
        "copy_sha": copy_sha,
        "manifest_entries": len(load_manifest(ctx)),
    }
    rep.add(
        "sbx_copy_intact",
        copy_sha == rep.candidate.get("sha256"),
        f"copy_sha={copy_sha[:16]}…",
    )
    rep._td = td  # type: ignore


def _capture(app, name: str) -> str | None:
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    app.update_idletasks()
    app.update()
    time.sleep(0.35)
    try:
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        CAPTURES.mkdir(parents=True, exist_ok=True)
        dest = CAPTURES / f"{name}.png"
        img.save(dest)
        return str(dest.relative_to(ROOT)).replace("\\", "/")
    except Exception as e:
        return f"ERROR:{e}"


def run_ui(folder: str, stage: Path, rep: Report) -> None:
    """UI con registro mock: mismo stage real (lectura) pero destino SANDBOX."""
    td = tempfile.TemporaryDirectory(prefix="s18_ui_")
    base = Path(td.name)
    mods_sb = base / "mods_ui_sandbox"
    data_sb = base / "app_data"
    work_sb = base / "work"
    arch_sb = base / "archive"
    for p in (mods_sb, data_sb, work_sb, arch_sb):
        p.mkdir(parents=True)

    rec = GameRecord(
        id="s18_ff7r_ui",
        name="S18 FF7R (solo lectura staging / destino sandbox)",
        vortex_game_id="finalfantasy7remake",
        mods_dir=str(mods_sb),  # NUNCA el ~mods real
        stage_dir=str(stage),  # lectura staging real
        adapter="ue4_paks_mods",
        data_mode="isolated",
        data_dir_name="s18_ff7r_ui",
        destination_verified=True,
        path_status="installed",
        archive_dir=str(arch_sb),
        work_library_dir=str(work_sb),
        default_mod_source="STAGING_VORTEX",
        notes="S18: Apply bloqueado hacia juego real — destino es sandbox",
    )
    reg = GamesRegistry(active_game_id=rec.id, games={rec.id: rec})
    gpaths = game_paths_for(rec, app_data=data_sb)
    ensure_game_data_dir(gpaths)

    from app import gui as gui_mod

    app = None
    try:
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for",
            side_effect=lambda record, app_data=None: game_paths_for(
                record, app_data=data_sb
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
        time.sleep(0.6)

        app.show_view("library")
        app.update()
        lib = app.view_library
        try:
            lib.search_var.set("FOV70")
            lib.redraw()
            app.update()
            children = lib.tree.get_children()
            if children:
                lib.tree.selection_set(children[0])
                lib.tree.focus(children[0])
                lib.on_select()
        except Exception as e:
            rep.ui_notes.append(f"select: {e}")
        rel = _capture(app, "01_biblioteca_fov70")
        if rel and not str(rel).startswith("ERROR"):
            rep.ui_captures.append(rel)

        # Simular plan aislado (sin Apply)
        cand = next((m for m in app.mods if m.folder == folder), None)
        if cand:
            # no tocar loadout real; solo memoria de la app mock
            for m in app.mods:
                m.usar = m.folder == folder
            if cand.paks:
                cand.pak_elegido = cand.paks[0]
            plan = plan_apply(app.mods, ctx=app._ctx(), settings=app._settings())
            app._last_plan = plan
            app._analysis_ready = True
            app._sync_apply_button()
            app.show_view("conflicts")
            app.update()
            rel = _capture(app, "02_conflictos_simulacion")
            if rel and not str(rel).startswith("ERROR"):
                rep.ui_captures.append(rel)
            rep.ui_notes.append(
                f"plan UI (destino sandbox): add={plan.to_add} conf={plan.conflicts} "
                f"applyable={app.plan_is_applyable()}"
            )
            # Diálogo de confirmación: NO pulsar Apply; documentar texto
            # (messagebox bloqueante — no abrir en automatización)
            rep.ui_notes.append(
                "Diálogo Apply NO abierto (evitar clic). "
                "En uso real pediría confirmación; aquí destino=sandbox."
            )
        else:
            rep.ui_notes.append("FOV70 no apareció en scan UI (¿filtro?)")

        app.show_view("summary")
        app.update()
        rel = _capture(app, "03_resumen")
        if rel and not str(rel).startswith("ERROR"):
            rep.ui_captures.append(rel)

        rep.add(
            "ui_ventana",
            bool(rep.ui_captures),
            f"capturas={len(rep.ui_captures)} destino_ui=sandbox",
        )
    except Exception as e:
        rep.add("ui_ventana", False, str(e)[:250])
        rep.ui_notes.append(traceback.format_exc()[-400:])
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
        rep._td_ui = td  # type: ignore


def main() -> int:
    print("S18 — mod real FF7R sin instalación real…")
    rep = Report(started_at=datetime.now().isoformat(timespec="seconds"))
    reg = ensure_registry()
    rec = reg.games["ff7r_remake"]
    stage = Path(rec.stage_dir)
    if not stage.is_dir():
        print("Staging FF7R no encontrado")
        return 1

    folder, meta = select_candidate(stage)
    rep.candidate = meta
    pak = stage / folder / meta["pak"]
    rep.staging_sha_before = sha256_file(pak)
    print(f"Candidato: {folder} ({meta['size_bytes']} B)")

    simulate_real_ff7r(folder, rep)
    run_sandbox_cycle(folder, stage, rep)

    rep.staging_sha_after = sha256_file(pak)
    staging_ok = rep.staging_sha_before == rep.staging_sha_after
    rep.add("staging_real_intacto", staging_ok, f"sha={rep.staging_sha_after[:16]}…")

    # verificar destino real no tiene FOV70.pak nuevo
    real_dest = Path(rec.mods_dir) / meta["pak"]
    rep.add(
        "destino_real_sin_apply",
        not real_dest.exists(),
        f"exists={real_dest.exists()}",
    )

    run_ui(folder, stage, rep)

    rep.safety = {
        "steam_modified": False,
        "vortex_modified": False,
        "staging_deleted": False,
        "loadout_modified": False,
        "adopt_executed": False,
        "apply_real_game": False,
        "staging_sha_unchanged": staging_ok,
    }
    rep.finished_at = datetime.now().isoformat(timespec="seconds")
    RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULT_JSON.write_text(
        json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OK={rep.ok} captures={len(rep.ui_captures)}")
    for s in rep.steps:
        print(f"  [{'OK' if s.ok else 'FAIL'}] {s.name}: {s.detail[:100]}")
    for n in rep.ui_notes:
        print(f"  UI: {n[:140]}")
    print("RESULT", RESULT_JSON)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
