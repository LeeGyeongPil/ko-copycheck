"""Create docx, hwpx, pdf and zip-bomb files at test time (nothing binary is committed)."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(str(path))
    return path


def make_hwpx(path: Path, sections: list[list[str]], spine_order: list[int] | None = None) -> Path:
    """Minimal OWPML zip. ``spine_order`` lists section indexes in reading order."""
    order = spine_order if spine_order is not None else list(range(len(sections)))
    ns = 'xmlns:hs="urn:hwpx:section" xmlns:hp="urn:hwpx:paragraph"'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        items = "".join(f'<opf:item id="s{i}" href="Contents/section{i}.xml" media-type="application/xml"/>' for i in range(len(sections)))
        spine = "".join(f'<opf:itemref idref="s{i}"/>' for i in order)
        zf.writestr(
            "Contents/content.hpf",
            f'<?xml version="1.0"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
            f"<opf:manifest>{items}</opf:manifest><opf:spine>{spine}</opf:spine></opf:package>",
        )
        for i, paras in enumerate(sections):
            body = "".join(f"<hp:p><hp:run><hp:t>{escape(t)}</hp:t></hp:run></hp:p>" for t in paras)
            zf.writestr(f"Contents/section{i}.xml", f'<?xml version="1.0"?><hs:sec {ns}>{body}</hs:sec>')
    return path


def make_pdf(path: Path, line: str) -> Path:
    """One-page PDF with a single ASCII text line (enough to exercise the reader)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def make_zip_bomb(path: Path, unzipped_bytes: int = 5 * 1024 * 1024) -> Path:
    """A small zip whose single member expands to ``unzipped_bytes`` of zeros."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", b"\0" * unzipped_bytes)
    return path
