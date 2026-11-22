"""Tests for the process-to-unit source (/proc/<pid>/cgroup)."""
from src.services.discovery import SourceError
from src.services.discovery.cgroups import (
    SOURCE,
    Unattributed,
    UnitRef,
    parse_cgroup,
    read_cgroup,
)


def test_system_service(fixture_text):
    assert parse_cgroup(fixture_text("cgroup-system-unit.txt")) == UnitRef(
        scope="system", unit="finance-tracker.service", uid=None
    )


def test_user_service_keeps_uid(fixture_text):
    assert parse_cgroup(fixture_text("cgroup-user-unit.txt")) == UnitRef(
        scope="user", unit="groceries-web.service", uid=1000
    )


def test_tmux_scope_under_user_manager_is_unattributed(fixture_text):
    result = parse_cgroup(fixture_text("cgroup-tmux-scope.txt"))
    assert isinstance(result, Unattributed)
    assert result.path.endswith(".scope")


def test_docker_proxy_maps_to_docker_service(fixture_text):
    # The docker published-port map, not this result, is what names the
    # container; this only records where the process really lives.
    assert parse_cgroup(fixture_text("cgroup-docker-proxy.txt")) == UnitRef(
        scope="system", unit="docker.service", uid=None
    )


def test_user_manager_itself_is_unattributed():
    result = parse_cgroup("0::/user.slice/user-1000.slice/user@1000.service/init.scope\n")
    assert isinstance(result, Unattributed)


def test_init_scope_and_session_scope_are_unattributed():
    assert parse_cgroup("0::/init.scope\n") == Unattributed(path="/init.scope")
    assert isinstance(
        parse_cgroup("0::/user.slice/user-1000.slice/session-5.scope\n"), Unattributed
    )


def test_template_instance_inside_a_sub_slice():
    assert parse_cgroup("0::/system.slice/system-getty.slice/getty@tty1.service\n") == UnitRef(
        scope="system", unit="getty@tty1.service", uid=None
    )


def test_runner_reads_proc_file(tmp_path, fixture_text):
    (tmp_path / "1631").mkdir()
    (tmp_path / "1631" / "cgroup").write_text(fixture_text("cgroup-user-unit.txt"))
    assert read_cgroup(1631, proc_root=str(tmp_path)) == UnitRef(
        scope="user", unit="groceries-web.service", uid=1000
    )


def test_runner_error_when_process_is_gone(tmp_path):
    result = read_cgroup(424242, proc_root=str(tmp_path))
    assert isinstance(result, SourceError)
    assert result.source == SOURCE
