from amr_exploration.blacklist import Blacklist


def test_first_failure_does_not_blacklist_when_limit_is_two():
    blacklist = Blacklist(
        radius=0.4,
        failure_limit=2,
    )

    result = blacklist.record_failure(
        1.0,
        2.0,
    )

    assert result is False
    assert blacklist.contains(
        1.0,
        2.0,
    ) is False


def test_second_failure_blacklists_same_area():
    blacklist = Blacklist(
        radius=0.4,
        failure_limit=2,
    )

    blacklist.record_failure(
        1.0,
        2.0,
    )

    result = blacklist.record_failure(
        1.05,
        2.02,
    )

    assert result is True

    assert blacklist.contains(
        1.1,
        2.1,
    ) is True


def test_far_position_is_not_blacklisted():
    blacklist = Blacklist(
        radius=0.4,
        failure_limit=1,
    )

    blacklist.record_failure(
        1.0,
        2.0,
    )

    assert blacklist.contains(
        2.0,
        2.0,
    ) is False


def test_failure_count_is_shared_inside_same_region():
    blacklist = Blacklist(
        radius=0.4,
        failure_limit=3,
    )

    blacklist.record_failure(
        1.0,
        2.0,
    )

    blacklist.record_failure(
        1.1,
        2.1,
    )

    assert blacklist.failure_count(
        1.05,
        2.05,
    ) == 2


def test_clear_removes_blacklist_and_failure_history():
    blacklist = Blacklist(
        radius=0.4,
        failure_limit=1,
    )

    blacklist.record_failure(
        1.0,
        2.0,
    )

    blacklist.clear()

    assert blacklist.contains(
        1.0,
        2.0,
    ) is False

    assert blacklist.failure_count(
        1.0,
        2.0,
    ) == 0
