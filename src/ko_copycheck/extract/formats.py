"""Format readers: txt, docx, hwpx, pdf. Run these inside the sandboxed worker."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

SUPPORTED = (".txt", ".docx", ".hwpx", ".pdf")


class ExtractError(Exception):
    """A file cannot be read. ``code`` is a short machine-readable reason."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Limits:
    """Resource limits applied to every input file."""

    max_file_bytes: int = 50 * 1024 * 1024
    max_unzipped_bytes: int = 200 * 1024 * 1024
    max_zip_entries: int = 5000


def extract_file(path: str, limits: Limits | None = None) -> str:
    """Return the plain text of ``path``; raise :class:`ExtractError` on failure."""
    limits = limits or Limits()
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        hint = " (binary .hwp is not supported; save as .hwpx or .pdf)" if ext == ".hwp" else ""
        raise ExtractError("unsupported", f"unsupported file type {ext or '(none)'}{hint}")
    size = p.stat().st_size
    if size > limits.max_file_bytes:
        raise ExtractError("too_large", f"{size} bytes exceeds the {limits.max_file_bytes} byte limit")
    if ext == ".txt":
        return read_txt(p)
    if ext == ".pdf":
        return read_pdf(p)
    check_zip_budget(p, limits)
    return read_docx(p) if ext == ".docx" else read_hwpx(p)


def read_txt(path: Path) -> str:
    """Decode a text file: UTF-16 with BOM, UTF-8 (with or without BOM), then CP949."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def check_zip_budget(path: Path, limits: Limits) -> None:
    """Refuse zip containers that expand beyond the limits.

    Declared sizes in a zip header can lie, so every member is really decompressed in
    small chunks and the *actual* byte count is checked.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > limits.max_zip_entries:
                raise ExtractError("too_large", f"{len(infos)} zip entries exceed {limits.max_zip_entries}")
            total = 0
            for info in infos:
                with zf.open(info) as fh:
                    while chunk := fh.read(1 << 20):
                        total += len(chunk)
                        if total > limits.max_unzipped_bytes:
                            raise ExtractError(
                                "too_large", f"unzipped size exceeds {limits.max_unzipped_bytes} bytes"
                            )
    except zipfile.BadZipFile as exc:
        raise ExtractError("corrupt", f"not a valid zip container: {exc}") from exc


def read_docx(path: Path) -> str:
    """Paragraphs and table cells of a .docx, in document order."""
    from docx import Document  # imported lazily: only the worker needs it

    try:
        doc = Document(str(path))
    except Exception as exc:  # python-docx raises several error types
        raise ExtractError("corrupt", f"cannot open docx: {exc}") from exc
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            lines.extend(cell.text for cell in row.cells)
    return "\n".join(lines)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hwpx_section_order(zf: zipfile.ZipFile) -> list[str]:
    """Section part names in reading order: content.hpf spine, else numeric order."""
    members = set(zf.namelist())
    names = [n for n in members if re.search(r"(^|/)section\d+\.xml$", n)]
    try:
        root = ET.fromstring(zf.read("Contents/content.hpf"))
    except (KeyError, ET.ParseError):
        root = None
    if root is not None:
        manifest = {el.get("id"): el.get("href") for el in root.iter() if _local(el.tag) == "item"}
        spine = [el.get("idref") for el in root.iter() if _local(el.tag) == "itemref"]
        ordered = []
        for idref in spine:
            href = manifest.get(idref)
            if not href:
                continue
            found = next((c for c in (href, f"Contents/{href}") if c in members), None)
            if found and re.search(r"section\d+\.xml$", found):
                ordered.append(found)
        if ordered:
            return ordered
    return sorted(names, key=lambda n: int(re.search(r"section(\d+)\.xml$", n).group(1)))  # type: ignore[union-attr]


def _collect_text(el: ET.Element, out: list[str]) -> None:
    """Depth-first text of an OWPML element: <t> text, line breaks, paragraph ends."""
    name = _local(el.tag)
    if name == "t":
        out.append(el.text or "")
        for child in el:
            if _local(child.tag) == "lineBreak":
                out.append("\n")
            elif _local(child.tag) == "tab":
                out.append("\t")
            out.append(child.tail or "")
        return
    for child in el:
        _collect_text(child, out)
    if name == "p":
        out.append("\n")


def read_hwpx(path: Path) -> str:
    """Body text of a .hwpx (OWPML zip), sections in spine order."""
    try:
        with zipfile.ZipFile(path) as zf:
            sections = _hwpx_section_order(zf)
            if not sections:
                raise ExtractError("corrupt", "no Contents/section*.xml found; is this a real .hwpx?")
            out: list[str] = []
            for name in sections:
                _collect_text(ET.fromstring(zf.read(name)), out)
    except zipfile.BadZipFile as exc:
        raise ExtractError("corrupt", f"not a valid hwpx (zip) file: {exc}") from exc
    except ET.ParseError as exc:
        raise ExtractError("corrupt", f"broken XML in hwpx: {exc}") from exc
    return "".join(out)


def read_pdf(path: Path) -> str:
    """Text layer of a PDF. Scanned PDFs have none; that is reported as an error."""
    from pypdf import PdfReader  # imported lazily: only the worker needs it

    try:
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ExtractError("corrupt", f"cannot read pdf: {exc}") from exc
    if len(text.strip()) < 5:
        raise ExtractError("no_text", "no text layer found (scanned PDF? OCR is not supported)")
    return text
