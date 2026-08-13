import pytest

from amr_exploration.state import (
    ExplorerSession,
    ExplorerState,
)


def test_initial_state_is_idle():
    session = ExplorerSession()

    assert session.state is ExplorerState.IDLE
    assert session.active_goal_xy is None
    assert session.no_frontier_count == 0


def test_start_navigation_changes_state():
    session = ExplorerSession()

    session.start_navigation((1.0, 2.0))

    assert session.state is ExplorerState.NAVIGATING
    assert session.active_goal_xy == (1.0, 2.0)


def test_success_returns_to_idle():
    session = ExplorerSession()

    session.start_navigation((1.0, 2.0))
    session.navigation_succeeded()

    assert session.state is ExplorerState.IDLE
    assert session.active_goal_xy is None


def test_failure_returns_to_idle():
    session = ExplorerSession()

    session.start_navigation((1.0, 2.0))
    session.navigation_failed()

    assert session.state is ExplorerState.IDLE
    assert session.active_goal_xy is None


def test_three_empty_checks_move_to_done():
    session = ExplorerSession()

    assert session.record_empty_check(3) is False
    assert session.record_empty_check(3) is False
    assert session.record_empty_check(3) is True

    assert session.state is ExplorerState.DONE


def test_candidate_found_resets_empty_counter():
    session = ExplorerSession()

    session.record_empty_check(3)
    session.record_empty_check(3)

    assert session.no_frontier_count == 2

    session.record_candidate_found()

    assert session.no_frontier_count == 0


def test_cannot_start_second_goal_while_navigating():
    session = ExplorerSession()

    session.start_navigation((1.0, 2.0))

    with pytest.raises(RuntimeError):
        session.start_navigation((3.0, 4.0))


def test_reset_returns_session_to_idle():
    session = ExplorerSession()

    session.record_empty_check(1)

    assert session.state is ExplorerState.DONE

    session.reset()

    assert session.state is ExplorerState.IDLE
    assert session.active_goal_xy is None
    assert session.no_frontier_count == 0
