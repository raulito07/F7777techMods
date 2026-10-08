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

Herramienta puntual para aplicar/actualizar cabeceras PI (GPL v3).
No forma parte del runtime de la aplicación.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

try:
    from app.version import __version__ as VERSION
except Exception:
    VERSION = "0.1.0"

OLD_MARKERS = (
    "F7777techMods — Gestor multijuego de mods.",
    "F7777techMods — Gestor multijuego de mods.",
)
MARKER = "F7777techMods — Gestor multijuego de mods."
HEADER_BODY = f"""F7777techMods — Gestor multijuego de mods.
Versión: {VERSION}
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
junto con este programa. Si no, vea <https://www.gnu.org/licenses/>."""

PROPRIETARY_SNIPPETS = (
    "Todos los derechos reservados.",
    "Queda prohibida su reproducción, distribución o modificación",
    "sin autorización expresa del titular de los derechos.",
)


def split_coding_and_rest(text: str):
    lines = text.splitlines(keepends=True)
    i = 0
    prefix = []
    if lines and lines[0].startswith("#!"):
        prefix.append(lines[0])
        i = 1
    if i < len(lines) and re.match(r"^[ \t\f]*#.*?coding[:=]", lines[i]):
        prefix.append(lines[i])
        i += 1
    return "".join(prefix), "".join(lines[i:])


def extract_existing_docstring(rest: str):
    rest_l = rest.lstrip("\n")
    if rest_l.startswith('"""') or rest_l.startswith("'''"):
        q = rest_l[:3]
        end = rest_l.find(q, 3)
        if end == -1:
            return None, rest
        body = rest_l[3:end]
        after = rest_l[end + 3 :]
        if after.startswith("\n"):
            after = after[1:]
        return body, after
    return None, rest


def strip_old_pi(cleaned: str) -> str:
    for marker in OLD_MARKERS:
        if marker in cleaned:
            idx = cleaned.find(marker)
            cleaned = cleaned[idx + len(marker) :]
            break
    # Cortar bloque PI antiguo (propietario o GPL previo)
    for end_mark in (
        "sin autorización expresa del titular de los derechos.",
        "vea <https://www.gnu.org/licenses/>.",
        "vea <https://www.gnu.org/licenses/>",
    ):
        if end_mark in cleaned:
            cleaned = cleaned.split(end_mark, 1)[1]
            break
    for snip in PROPRIETARY_SNIPPETS:
        cleaned = cleaned.replace(snip, "")
    return cleaned.strip()


def rebuild_doc_body(old_doc: str | None) -> str:
    extra = ""
    if old_doc is not None:
        cleaned = strip_old_pi(old_doc.strip())
        if cleaned and MARKER not in cleaned:
            extra = "\n\n" + cleaned
    return HEADER_BODY + extra


def process_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    original = text
    if "F7777techMods — Gestor multijuego de mods." in text:
        text = text.replace(
            "F7777techMods — Gestor multijuego de mods.", MARKER
        )
    text = text.replace("F7777techMods", "F7777techMods")

    prefix, rest = split_coding_and_rest(text)
    if "# -*- coding" not in prefix and "coding:" not in prefix:
        prefix = "# -*- coding: utf-8 -*-\n" + prefix

    old_doc, rest_after = extract_existing_docstring(rest)
    needs_pi = old_doc is not None and (
        any(m in old_doc for m in OLD_MARKERS)
        or "Four Seven Tech" in old_doc[:400]
        or "Todos los derechos reservados" in old_doc
        or "GNU" in old_doc[:800]
    )
    if needs_pi:
        new_body = rebuild_doc_body(old_doc)
        new_body = re.sub(
            r"Versión:\s*[^\n]+",
            f"Versión: {VERSION}",
            new_body,
            count=1,
        )
        new_doc = '"""\n' + new_body + '\n"""\n'
        rest_after = rest_after.lstrip("\n")
        new_text = prefix
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += new_doc + "\n" + rest_after
    elif MARKER not in text[:1500]:
        new_doc = '"""\n' + HEADER_BODY + '\n"""\n'
        rest_after = rest.lstrip("\n")
        new_text = prefix
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += new_doc + "\n" + rest_after
    else:
        new_text = text

    if not new_text.endswith("\n"):
        new_text += "\n"
    if new_text == original:
        return "skipped"
    path.write_text(new_text, encoding="utf-8")
    return "updated"


def main():
    files = []
    for base in (ROOT / "app", ROOT / "tests", ROOT / "legacy", ROOT / "tools"):
        if base.exists():
            files.extend(sorted(base.rglob("*.py")))

    updated, skipped = [], []
    for path in files:
        rel = str(path.relative_to(ROOT))
        if path.name == "version.py":
            skipped.append(f"{rel} (central)")
            continue
        status = process_file(path)
        if status == "updated":
            updated.append(rel)
        else:
            skipped.append(rel)

    print("UPDATED", len(updated))
    for u in updated:
        print(" +", u)
    print("SKIPPED", len(skipped))


if __name__ == "__main__":
    main()
