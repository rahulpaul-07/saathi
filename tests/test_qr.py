"""The QR image for the rider link."""

import re

from saathi.qr import join_qr_svg


def test_the_svg_is_a_self_contained_image_without_scripts() -> None:
    svg = join_qr_svg("https://saathi.example/rider.html?code=ABC234").decode()
    assert svg.startswith("<svg")
    assert not re.search(r"<script|href=|onload", svg)


def test_different_links_give_different_codes() -> None:
    first = join_qr_svg("https://saathi.example/rider.html?code=ABC234")
    second = join_qr_svg("https://saathi.example/rider.html?code=XYZ789")
    assert first != second
