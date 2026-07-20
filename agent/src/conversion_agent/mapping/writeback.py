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

import shutil
import zipfile

from lxml import etree

from .model import CrosswalkWorkbook

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
        if not target.startswith("xl/"):
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
        return str(self.xf_cache[key])


def _set_cell(sheet_root, row_idx: int, col_idx: int, text: str,
              cloner: _StyleCloner | None, kind: str) -> None:
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
        except Exception:
            pass  # keep the value; lose only the color


def write(model: CrosswalkWorkbook, out_path: str, overwrite: bool = False) -> dict:
    # overwrite=True deliberately replaces previously written proposal values
    # and notes (revision runs); human review still happens on the output.
    written = {"auto": 0, "llm": 0}
    edits_by_sheet: dict[str, list[tuple[int, int, str, str]]] = {}
    for sec in model.sections:
        for row_idx, prop in sec.proposals.items():
            kind = "llm" if prop.method == "llm" else "auto"
            row = next(r for r in sec.rows if r.row_idx == row_idx)
            for col, value, existing in zip(sec.dst_cols, prop.dest, row.existing):
                if not value or (existing.strip() and not overwrite):
                    continue  # skip empty dests; overwrite only on revision runs
                edits_by_sheet.setdefault(sec.tab, []).append((row_idx, col, value, kind))
            if sec.notes_col and prop.note:
                edits_by_sheet.setdefault(sec.tab, []).append(
                    (row_idx, sec.notes_col, prop.note, kind))
            # (notes for overwritten rows are replaced below via overwrite flag)
            written[kind] += 1

    src_zip = zipfile.ZipFile(model.path)
    paths = _sheet_paths(src_zip)
    sheet_docs = {}
    for tab, edits in edits_by_sheet.items():
        sheet_docs[paths[tab]] = (tab, edits)

    try:
        cloner = _StyleCloner(src_zip.read("xl/styles.xml"))
    except Exception:
        cloner = None

    # Pass 1: apply every cell edit (this may append styles to the cloner),
    # so styles.xml is complete before anything is serialized.
    replacements: dict[str, bytes] = {}
    for path, (tab, edits) in sheet_docs.items():
        root = etree.fromstring(src_zip.read(path))
        for row_idx, col, value, kind in edits:
            _set_cell(root, row_idx, col, value, cloner, kind)
        replacements[path] = etree.tostring(root, xml_declaration=True,
                                           encoding="UTF-8", standalone=True)
    if cloner is not None:
        replacements["xl/styles.xml"] = etree.tostring(
            cloner.root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # Pass 2: write the package, copying every untouched entry byte-for-byte.
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src_zip.infolist():
            out.writestr(item, replacements.get(item.filename) or src_zip.read(item.filename))
    src_zip.close()
    return written
