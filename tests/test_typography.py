from rozprava.typography import (
    NBSP,
    THIN_NBSP,
    clip,
    count,
    cz_date,
    cz_date_long,
    cz_number,
    cz_percent,
    czech_initial,
    czech_sort_key,
    highlight,
    nbsp,
    plural,
)


def test_one_letter_words_bind_to_the_next_word():
    assert nbsp("A jeho cílem je v okamžiku s právem") == (
        f"A{NBSP}jeho cílem je v{NBSP}okamžiku s{NBSP}právem"
    )


def test_chained_one_letter_words():
    assert nbsp("a v okamžiku") == f"a{NBSP}v{NBSP}okamžiku"


def test_letters_inside_words_and_abbreviations_are_left_alone():
    assert nbsp("pan Kupka Martin") == "pan Kupka Martin"
    assert nbsp("U.S. a") == "U.S. a"


def test_numbers_stay_with_their_noun_and_digit_groups():
    assert nbsp("zhruba 200 000 korun") == f"zhruba 200{NBSP}000{NBSP}korun"
    assert nbsp("zákon č. 427/2011 Sb.") == f"zákon č.{NBSP}427/2011{NBSP}Sb."


def test_nbsp_keeps_length():
    text = "Já v té věci a my všichni kolegové v ODS máme 10 let jasno."
    assert len(nbsp(text)) == len(text)


def test_dates():
    assert cz_date("2026-11-06") == f"6.{NBSP}11.{NBSP}2026"
    assert cz_date_long("2026-11-06") == f"6.{NBSP}listopadu 2026"
    assert cz_date_long("2026-11-06", weekday=True) == f"pátek 6.{NBSP}listopadu 2026"


def test_numbers():
    assert cz_number(45813) == f"45{THIN_NBSP}813"
    assert cz_percent(92.4) == f"92{NBSP}%"
    assert cz_percent(3.5, 1) == f"3,5{NBSP}%"
    assert cz_number(1.57, 2) == "1,57"
    assert cz_number(999) == "999"


def test_plural_and_count():
    assert [plural(n, "projev", "projevy", "projevů") for n in (0, 1, 2, 4, 5, 22)] == [
        "projevů",
        "projev",
        "projevy",
        "projevy",
        "projevů",
        "projevů",
    ]
    assert count(45813, "projev", "projevy", "projevů") == f"45{THIN_NBSP}813{NBSP}projevů"


def test_highlight_marks_terms_without_changing_the_text():
    text = "zavádí automatickou účast zaměstnanců s příspěvkem a opt-out"
    html = str(highlight(text, ["automatickou účast", "opt-out", "opt"]))
    assert '<mark class="term">automatickou účast</mark>' in html
    assert '<mark class="term">opt-out</mark>' in html  # longest term wins
    plain = html.replace('<mark class="term">', "").replace("</mark>", "")
    assert plain.replace(NBSP, " ") == text


def test_highlight_ignores_accents_like_the_search_and_matches_whole_words():
    text = "Důchodová reforma a reformy důchodů"
    html = str(highlight(text, ["duchodova reforma", "duchod"]))
    assert html.count("<mark") == 1 and "Důchodová reforma</mark>" in html


def test_highlight_is_case_insensitive_and_escapes_html():
    html = str(highlight("Automaticky <b>enrollment</b>", ["automaticky"]))
    assert html.startswith('<mark class="term">Automaticky</mark>')
    assert "&lt;b&gt;" in html


def test_czech_sort_order():
    names = ["Žáček", "Chvojka", "Cibulka", "Čermák", "Hora", "Adámková", "Adamec", "Řehoř", "Rais"]
    assert sorted(names, key=czech_sort_key) == [
        "Adamec",
        "Adámková",
        "Cibulka",
        "Čermák",
        "Hora",
        "Chvojka",
        "Rais",
        "Řehoř",
        "Žáček",
    ]


def test_czech_initials():
    assert [czech_initial(n) for n in ("Čermák", "Chvojka", "Ádámková", "Šťastný")] == [
        "Č",
        "Ch",
        "A",
        "Š",
    ]


def test_clip_cuts_at_word_boundaries_only():
    text = "Já bych jenom chtěla podpořit argumentaci, pana kolegy Papajanovského"
    assert clip(text, 200) == text
    assert clip(text, 45) == "Já bych jenom chtěla podpořit argumentaci"
    assert text.startswith(clip(text, 30))
