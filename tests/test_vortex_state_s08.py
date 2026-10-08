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

S08 — fiabilidad estado Vortex: histórico / desconocido / no tratar backup como actual.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.inventory import ModEntry  # noqa: E402
from app.core.vortex_sync import (  # noqa: E402
    VortexReliability,
    apply_vortex_enablement,
    format_vortex_status_report,
    probe_vortex_enable_state,
)


def _mod(folder: str, *, usar: bool = False) -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=[],
        multi=False,
        on_disk=False,
        stage_path=str(Path("x") / folder),
        usar=usar,
    )


def _write_hourly(roaming: Path, *, game_id: str, enabled: dict[str, bool]) -> Path:
    backup_dir = roaming / "temp" / "state_backups_full"
    backup_dir.mkdir(parents=True, exist_ok=True)
    mod_state = {
        folder: {"enabled": en} for folder, en in enabled.items()
    }
    obj = {
        "persistent": {
            "profiles": {
                "prof1": {
                    "gameId": game_id,
                    "name": "Default",
                    "lastActivated": 100,
                    "modState": mod_state,
                }
            }
        }
    }
    path = backup_dir / "hourly.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


class VortexStateS08Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.roaming = self.base / "Vortex"
        self.mods = self.base / "mods"
        self.mods.mkdir(parents=True)
        self.roaming.mkdir(parents=True)

    def tearDown(self):
        self._td.cleanup()

    def test_unknown_without_backup_or_live(self):
        snap = probe_vortex_enable_state(
            "finalfantasy7remake",
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        self.assertEqual(snap.reliability, VortexReliability.UNKNOWN)
        self.assertEqual(snap.ui_current_label, "Estado Vortex actual no verificado")
        self.assertFalse(snap.enabled_map)
        self.assertIs(snap.deployment_on_disk, False)
        self.assertIn("Estado Vortex actual no verificado", snap.message)

    def test_historical_backup_not_marked_current(self):
        _write_hourly(
            self.roaming,
            game_id="finalfantasy7remake",
            enabled={"ModA": True, "ModB": False, "ModC": True},
        )
        snap = probe_vortex_enable_state(
            "finalfantasy7remake",
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        self.assertEqual(snap.reliability, VortexReliability.HISTORICAL_BACKUP)
        self.assertEqual(snap.ui_current_label, "Estado Vortex actual no verificado")
        self.assertTrue(snap.enabled_map["ModA"])
        self.assertFalse(snap.enabled_map["ModB"])
        self.assertEqual(snap.enabled_count, 2)
        self.assertIn("hourly.json", snap.source_kind)
        self.assertIn("Backup histórico", snap.ui_historical_label)
        # La etiqueta de UI actual NUNCA dice que el backup sea el estado vivo
        self.assertEqual(snap.ui_current_label, "Estado Vortex actual no verificado")
        report = format_vortex_status_report(snap)
        self.assertIn("Estado Vortex actual no verificado", report)
        self.assertIn("histórico", report.lower())
        self.assertIn(snap.reliability.value, report)

    def test_live_state_dir_present_still_unverified(self):
        live = self.roaming / "state.v2"
        live.mkdir()
        (live / "CURRENT").write_text("x", encoding="utf-8")
        _write_hourly(
            self.roaming,
            game_id="finalfantasy7remake",
            enabled={"ModA": True},
        )
        snap = probe_vortex_enable_state(
            "finalfantasy7remake",
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        self.assertTrue(snap.live_state_present)
        self.assertFalse(snap.live_state_readable)
        self.assertEqual(snap.reliability, VortexReliability.HISTORICAL_BACKUP)
        self.assertEqual(snap.ui_current_label, "Estado Vortex actual no verificado")
        self.assertIn("LevelDB", snap.message)

    def test_deployment_on_disk_independent(self):
        (self.mods / "vortex.deployment.json").write_text("{}", encoding="utf-8")
        snap = probe_vortex_enable_state(
            "finalfantasy7remake",
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        self.assertTrue(snap.deployment_on_disk)
        self.assertEqual(snap.reliability, VortexReliability.UNKNOWN)
        self.assertIn("Deploy en disco: SÍ", snap.message)
        self.assertIn("no equivale al mapa Enabled", snap.message)

    def test_apply_blocked_without_allow_historical(self):
        _write_hourly(
            self.roaming,
            game_id="ff7",
            enabled={"ModA": True, "ModB": True},
        )
        mods = [_mod("ModA", usar=False), _mod("ModB", usar=False)]
        on, off, msg = apply_vortex_enablement(
            mods, "ff7", roaming=self.roaming, mods_dir=self.mods
        )
        self.assertEqual(on, 0)
        self.assertFalse(mods[0].usar)
        self.assertFalse(mods[1].usar)
        self.assertIn("BLOQUEADA", msg)
        self.assertIn("histórico", msg.lower())

    def test_apply_historical_with_explicit_flag(self):
        _write_hourly(
            self.roaming,
            game_id="ff7",
            enabled={"ModA": True, "ModB": False},
        )
        mods = [_mod("ModA", usar=False), _mod("ModB", usar=True)]
        on, off, msg = apply_vortex_enablement(
            mods,
            "ff7",
            roaming=self.roaming,
            mods_dir=self.mods,
            allow_historical=True,
        )
        self.assertEqual(on, 1)
        self.assertEqual(off, 1)
        self.assertTrue(mods[0].usar)
        self.assertFalse(mods[1].usar)
        self.assertIn("HISTÓRICO", msg.upper())

    def test_missing_game_id(self):
        snap = probe_vortex_enable_state(
            "",
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        # vacío → usa LEGACY o message sin game; forzamos None-like
        snap2 = probe_vortex_enable_state(
            None,
            roaming=self.roaming,
            mods_dir=self.mods,
        )
        # Con legacy puede buscar perfil; sin backup → unknown
        self.assertIn(
            snap2.reliability,
            (VortexReliability.UNKNOWN, VortexReliability.HISTORICAL_BACKUP),
        )


if __name__ == "__main__":
    unittest.main()
