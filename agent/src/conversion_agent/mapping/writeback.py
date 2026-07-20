"""Write proposals back into a copy of the client's workbook — surgically.

The tool-generated workbooks carry x14 extension data validations (cascading
INDIRECT/VLOOKUP dropdowns) that openpyxl silently strips on save. So we never
round-trip the file through a library: we edit only the target cells inside
the worksheet XML at the zip level and copy every other byte of the package
unchanged — dropdowns, defined names, hidden tabs, and the LookupSpec survive
intact.

Values are written as inline strings with xml:space="preserve" (several
configured pick-list values carry trailing spaces that must survive
byte-exact). Fill colors are applied by cloning each cell's existing style
with a new fill, appended to styles.xml; if styles editing fails for any
reason, values are still written and only the coloring is skipped.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from conversion_agent.core.errors import OutputError

from .model import CellEdit, CrosswalkWorkbook, WriteReport

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKGREL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_XML = "http://www.w3.org/XML/1998/namespace"

FILL_RGB = {"auto": "FFC6EFCE", "llm": "FFFFEB9C"}  # green / yellow


def _col_letter(col: int) -> str:
    out = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def _cell_ref_col(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n


def _sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    wb = etree.fromstring(zf.read("xl/workbook.xml"))
    rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    target_by_id = {r.get("Id"): r.get("Target")
                    for r in rels.findall(f"{{{NS_PKGREL}}}Relationship")}
    out = {}
    for sheet in wb.findall(f"{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
        target = target_by_id[sheet.get(f"{{{NS_REL}}}id")]
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        out[sheet.get("name")] = target
    return out


class _StyleCloner:
    """Clone existing cell styles with a solid fill appended to styles.xml."""

    def __init__(self, styles_xml: bytes):
        self.root = etree.fromstring(styles_xml)
        self.fills = self.root.find(f"{{{NS_MAIN}}}fills")
        self.cellxfs = self.root.find(f"{{{NS_MAIN}}}cellXfs")
        self.fill_ids: dict[str, int] = {}
        self.xf_cache: dict[tuple[str, str], int] = {}
        self.changed = False

    def _fill_id(self, kind: str) -> int:
        if kind not in self.fill_ids:
            fill = etree.SubElement(self.fills, f"{{{NS_MAIN}}}fill")
            pf = etree.SubElement(fill, f"{{{NS_MAIN}}}patternFill",
                                  patternType="solid")
            etree.SubElement(pf, f"{{{NS_MAIN}}}fgColor", rgb=FILL_RGB[kind])
            etree.SubElement(pf, f"{{{NS_MAIN}}}bgColor", indexed="64")
            self.fill_ids[kind] = len(self.fills) - 1
            self.fills.set("count", str(len(self.fills)))
        return self.fill_ids[kind]

    def styled(self, base_s: str, kind: str) -> str:
        key = (base_s, kind)
        if key not in self.xf_cache:
            xfs = self.cellxfs.findall(f"{{{NS_MAIN}}}xf")
            base = xfs[int(base_s)] if base_s.isdigit() and int(base_s) < len(xfs) else xfs[0]
            clone = etree.fromstring(etree.tostring(base))
            clone.set("fillId", str(self._fill_id(kind)))
            clone.set("applyFill", "1")
            self.cellxfs.append(clone)
            self.cellxfs.set("count", str(len(self.cellxfs)))
            self.xf_cache[key] = len(self.cellxfs) - 1
            self.changed = True
        return str(self.xf_cache[key])


def _set_cell(sheet_root, row_idx: int, col_idx: int, text: str,
              cloner: _StyleCloner | None, kind: str, warnings: list[str]) -> None:
    sheet_data = sheet_root.find(f"{{{NS_MAIN}}}sheetData")
    row = None
    for r in sheet_data.findall(f"{{{NS_MAIN}}}row"):
        if r.get("r") == str(row_idx):
            row = r
            break
    if row is None:
        row = etree.SubElement(sheet_data, f"{{{NS_MAIN}}}row", r=str(row_idx))
    ref = f"{_col_letter(col_idx)}{row_idx}"
    cell = None
    for c in row.findall(f"{{{NS_MAIN}}}c"):
        if c.get("r") == ref:
            cell = c
            break
    if cell is None:
        cell = etree.Element(f"{{{NS_MAIN}}}c", r=ref)
        pos = 0
        for i, c in enumerate(row.findall(f"{{{NS_MAIN}}}c")):
            if _cell_ref_col(c.get("r", "")) < col_idx:
                pos = i + 1
        row.insert(pos, cell)
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop("t", None)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS_MAIN}}}is")
    t_el = etree.SubElement(is_el, f"{{{NS_MAIN}}}t")
    t_el.text = text
    t_el.set(f"{{{NS_XML}}}space", "preserve")
    if cloner is not None:
        try:
            cell.set("s", cloner.styled(cell.get("s", "0"), kind))
        except Exception as exc:
            warnings.append(f"Style not applied to {ref}: {type(exc).__name__}: {exc}")


def _write_package(
    model: CrosswalkWorkbook, out_path: Path, *, overwrite: bool
) -> tuple[WriteReport, tuple[CellEdit, ...]]:
    """Create a surgically edited package at ``out_path`` for later verification."""
    deterministic_rows = 0
    model_rows = 0
    destination_cells = 0
    note_cells = 0
    edits_by_sheet: dict[str, list[tuple[int, int, str, str]]] = {}
    for sec in model.sections:
        for row_idx, prop in sec.proposals.items():
            kind = "llm" if prop.method == "llm" else "auto"
            row = next(r for r in sec.rows if r.row_idx == row_idx)
            row_written = False
            for col, value, existing in zip(sec.dst_cols, prop.dest, row.existing):
                if not value or (existing.strip() and not overwrite):
                    continue  # skip empty dests; overwrite only on revision runs
                edits_by_sheet.setdefault(sec.tab, []).append((row_idx, col, value, kind))
                destination_cells += 1
                row_written = True
            if sec.notes_col and prop.note:
                edits_by_sheet.setdefault(sec.tab, []).append(
                    (row_idx, sec.notes_col, prop.note, kind)
                )
                note_cells += 1
                row_written = True
            if row_written:
                if kind == "llm":
                    model_rows += 1
                else:
                    deterministic_rows += 1

    warnings: list[str] = []
    with zipfile.ZipFile(model.path) as source_zip:
        paths = _sheet_paths(source_zip)
        sheet_docs = {
            paths[tab]: edits for tab, edits in edits_by_sheet.items()
        }
        try:
            cloner = _StyleCloner(source_zip.read("xl/styles.xml"))
        except Exception as exc:
            cloner = None
            warnings.append(f"Style cloning disabled: {type(exc).__name__}: {exc}")

        replacements: dict[str, bytes] = {}
        expected_edits: list[CellEdit] = []
        for path, edits in sheet_docs.items():
            root = etree.fromstring(source_zip.read(path))
            for row_idx, col, value, kind in edits:
                _set_cell(root, row_idx, col, value, cloner, kind, warnings)
                expected_edits.append(CellEdit(path, f"{_col_letter(col)}{row_idx}", value))
            replacements[path] = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
        if cloner is not None and cloner.changed:
            replacements["xl/styles.xml"] = etree.tostring(
                cloner.root, xml_declaration=True, encoding="UTF-8", standalone=True
            )

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as output_zip:
            for item in source_zip.infolist():
                output_zip.writestr(
                    item, replacements.get(item.filename) or source_zip.read(item.filename)
                )

    return (
        WriteReport(
            deterministic_rows=deterministic_rows,
            model_rows=model_rows,
            destination_cells=destination_cells,
            note_cells=note_cells,
            warnings=tuple(warnings),
        ),
        tuple(expected_edits),
    )


def verify_output(source: Path, output: Path, expected_edits: tuple[CellEdit, ...]) -> None:
    """Confirm that only intended worksheet values changed before publication."""
    with zipfile.ZipFile(source) as source_zip, zipfile.ZipFile(output) as output_zip:
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/styles.xml"}
        if not required <= set(output_zip.namelist()):
            raise OutputError("Output is missing required workbook package parts.")
        for name in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if source_zip.read(name) != output_zip.read(name):
                raise OutputError(f"Protected workbook part changed unexpectedly: {name}")
        edits_by_sheet: dict[str, list[CellEdit]] = {}
        for edit in expected_edits:
            edits_by_sheet.setdefault(edit.sheet_path, []).append(edit)
        for sheet_path, edits in edits_by_sheet.items():
            source_root = etree.fromstring(source_zip.read(sheet_path))
            output_root = etree.fromstring(output_zip.read(sheet_path))
            source_ext = source_root.find(f"{{{NS_MAIN}}}extLst")
            output_ext = output_root.find(f"{{{NS_MAIN}}}extLst")
            source_ext_xml = b"" if source_ext is None else etree.tostring(source_ext)
            output_ext_xml = b"" if output_ext is None else etree.tostring(output_ext)
            if source_ext_xml != output_ext_xml:
                raise OutputError(f"Data-validation extensions changed: {sheet_path}")
            cells = {cell.get("r"): cell for cell in output_root.findall(f".//{{{NS_MAIN}}}c")}
            for edit in edits:
                cell = cells.get(edit.cell_ref)
                text = "" if cell is None else "".join(cell.itertext())
                if text != edit.value:
                    raise OutputError(
                        f"Expected {edit.sheet_path}!{edit.cell_ref}={edit.value!r}, got {text!r}"
                    )


def write(model: CrosswalkWorkbook, out_path: str, overwrite: bool = False) -> WriteReport:
    # overwrite=True deliberately replaces previously written proposal values
    # and notes (revision runs); human review still happens on the output.
    source = Path(model.path).resolve()
    output = Path(out_path).resolve()
    if source == output:
        raise OutputError("Output path must not be the input workbook.")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        report, expected_edits = _write_package(model, temporary, overwrite=overwrite)
        verify_output(source, temporary, expected_edits)
        os.replace(temporary, output)
        return report
    except OutputError:
        raise
    except Exception as exc:
        raise OutputError(f"Could not write verified workbook {output}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
