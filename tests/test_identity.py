"""Party swatches, dot-matrix numbers, short titles and catalogue numbers."""

import re
from pathlib import Path

import pytest

from rozprava import dotmatrix
from rozprava.parties import INDEPENDENT, PARTIES, Party, hex_to_oklch, swatches
from rozprava.titles import catalog_number, catalog_slug, reading, short_title

DESIGN = (Path(__file__).resolve().parent.parent / "DESIGN.md").read_text(encoding="utf-8")


def test_oklch_of_known_colours():
    lightness, chroma, hue = hex_to_oklch("#ff0000")
    assert lightness == pytest.approx(0.628, abs=0.002)
    assert chroma == pytest.approx(0.258, abs=0.002)
    assert hue == pytest.approx(29.2, abs=0.3)
    assert hex_to_oklch("#111111")[1] < 0.001


def test_unverified_parties_all_get_the_same_pending_swatch():
    result = swatches()
    assert result[INDEPENDENT].kind == "independent"
    assert {s.kind for abbr, s in result.items() if abbr != INDEPENDENT} == {"pending"}


def test_normalisation_and_hue_collisions():
    sample = {
        "A": Party("A", "A", "#004494"),  # blue
        "B": Party("B", "B", "#034ea2"),  # a near-identical blue: hatched
        "C": Party("C", "C", "#ce0f68"),  # magenta
        "D": Party("D", "D", "#111111"),  # black branding
    }
    result = swatches(sample)
    assert result["A"].css is not None and result["A"].css.startswith("oklch(0.62 0.12 ")
    assert not result["A"].hatched and result["B"].hatched and not result["C"].hatched
    assert result["D"].kind == "achromatic" and result["D"].css == "oklch(0.35 0 0)"


def test_every_term_10_club_has_a_label():
    assert PARTIES["Piráti"].label == "PIRÁTI" and PARTIES[INDEPENDENT].label == "NEZ."


def test_dot_matrix_glyphs_match_design_md():
    block = re.search(r"### 8\.2 Glyph grid.*?```\n(.*?)```", DESIGN, re.S)
    assert block
    spec = dict(line.split(": ", 1) for line in block.group(1).strip().splitlines())
    assert spec == dotmatrix.GLYPHS


def test_dot_matrix_render():
    cols = dotmatrix.columns("43 897")
    # Five glyphs; each but the last advances by a 1-cell gap; the space adds 2 cells.
    assert len(cols) == 5 * 5 + 4 + 2
    svg = str(dotmatrix.render("72", "m", label="72 projevů"))
    assert 'aria-label="72 projevů"' in svg and svg.count("<circle") == 70
    with pytest.raises(ValueError):
        dotmatrix.columns("A1")


def test_short_titles():
    full = (
        "Vládní návrh zákona, kterým se mění zákon č. 427/2011 Sb., o doplňkovém penzijním "
        "spoření, ve znění pozdějších předpisů, a mění a zrušují další související zákony"
    )
    assert short_title(full) == "Novela zákona o doplňkovém penzijním spoření"
    member = "Návrh poslanců Jana Nováka a dalších na vydání zákona, kterým se mění zákon o obcích"
    assert short_title(member) == "Poslanecký návrh: změna zákon o obcích"
    long = "Návrh zákona, kterým se mění některé zákony v oblasti veřejných rozpočtů a daní a cel"
    assert len(short_title(long)) <= 60 and short_title(long).endswith("…")
    assert reading("Novela /sněmovní tisk 285/ - druhé čtení") == "2. čtení"


def test_short_titles_prefer_psp_short_names_written_out():
    assert short_title("…", psp_short="Novela z. o doplňkovém penzijním spoření") == (
        "Novela zákona o doplňkovém penzijním spoření"
    )
    assert (
        short_title("…", psp_short="Novela z. - stavební zákon") == "Novela zákona – stavební zákon"
    )
    assert short_title("…", psp_short="Vl.n.z. o státním rozpočtu ČR na rok 2026") == (
        "Vládní návrh zákona o státním rozpočtu ČR na rok 2026"
    )
    assert short_title("…", tisk=90, psp_short="Vl.n.z., kt. se mění některé z.") == (
        "Změny zákonů v oblasti veřejných rozpočtů"
    )


def test_catalog_numbers():
    assert catalog_number(10, 34, 644, 2) == "10/034/0644/2"
    assert catalog_slug(10, 34, 644, 2) == "10-034-0644-2"
