from pricing.match import title_matches


def test_hyphen_and_space_variants_match():
    assert title_matches("Sony WH 1000XM4 schwarz", "sony wh-1000xm4", ())
    assert title_matches("SONY WH-1000XM4", "sony wh-1000xm4", ())


def test_split_capacity_matches():
    assert title_matches("Sabrent Rocket NVMe 4.0 1 TB", "1TB Sabrent Rocket", ())


def test_word_order_does_not_matter():
    assert title_matches("Rocket Sabrent 1TB", "Sabrent Rocket 1TB", ())


def test_all_tokens_required():
    assert not title_matches("Sabrent Rocket 2TB", "Sabrent Rocket 1TB", ())


def test_wrong_model_is_rejected():
    assert not title_matches("Sony WH-1000XM3", "sony wh-1000xm4", ())


def test_exclude_matches_whole_word():
    assert not title_matches("Sabrent Rocket Nano 1TB", "Sabrent Rocket 1TB", ("Nano",))


def test_exclude_does_not_hit_substring():
    assert title_matches("Sabrent Rocket Professional 1TB", "Sabrent Rocket 1TB", ("pro",))


def test_exclude_is_normalised():
    assert not title_matches("Sabrent Rocket 4 Plus 1TB", "Sabrent Rocket 1TB", ("-PLUS",))


def test_empty_tokens_are_dropped():
    assert title_matches("Sabrent Rocket", "Sabrent - Rocket", ("--", ""))


def test_query_tokens_match_as_substring_known_risk():
    assert title_matches("Seagate 21TB HDD", "1tb", ())
