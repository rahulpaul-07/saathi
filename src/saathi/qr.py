"""QR code for the rider's join link, as an SVG."""

import io

import segno


def join_qr_svg(url: str) -> bytes:
    """SVG for `url`. Medium error correction keeps the code small enough to scan off a phone."""
    out = io.BytesIO()
    segno.make(url, error="m").save(out, kind="svg", scale=5, border=2, xmldecl=False, nl=False)
    return out.getvalue()
