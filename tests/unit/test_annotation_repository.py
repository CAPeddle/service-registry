"""Tests for the annotation repository."""
import pytest
from src.repositories.annotation_repository import AnnotationRepository


@pytest.fixture
def repo(db_session):
    yield AnnotationRepository(db_session)


def test_upsert_existing_key_updates_in_place(repo):
    first = repo.upsert("system:nginx.service", display_name="Web", primary_port=80)
    second = repo.upsert(
        "system:nginx.service", display_name="Proxy", link_override="http://z2:8080"
    )

    assert second.id == first.id
    assert len(repo.list()) == 1
    got = repo.get("system:nginx.service")
    assert got.display_name == "Proxy"
    assert got.link_override == "http://z2:8080"
    assert got.primary_port == 80


def test_set_hidden_on_unknown_key_creates_minimal_annotation(repo):
    annotation = repo.set_hidden("docker:media/plex", True)

    assert annotation.identity_key == "docker:media/plex"
    assert annotation.hidden is True
    assert annotation.display_name is None
    assert annotation.link_override is None
    assert repo.get("docker:media/plex") is not None


def test_new_annotation_leaves_hidden_unset(repo):
    annotation = repo.upsert("docker:media/plex", description="Plex")

    assert annotation.hidden is None


def test_delete_removes_the_annotation_and_reports_whether_it_existed(repo):
    repo.upsert("docker:media/plex", description="Plex")

    assert repo.delete("docker:media/plex") is True
    assert repo.get("docker:media/plex") is None
    assert repo.delete("docker:media/plex") is False
