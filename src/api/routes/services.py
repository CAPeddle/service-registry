"""Service management API: annotations keyed by identity.

A registration names a service; it is matched against the live inventory and
recorded as that identity's annotation. Edits from the landing page address an
annotation by its identity key directly. Identity keys contain ':' and '/', so
they travel in the JSON body or the query string, never in a path segment.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from src.api.dependencies.services import get_inventory_service
from src.api.schemas.service_schema import AnnotationResponse, AnnotationUpdate, ServiceCreate
from src.models.annotation import Annotation
from src.models.base import get_db
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery.inventory import InventoryRow, InventoryService, parse_identity_key

router = APIRouter()


@router.get("", response_model=List[AnnotationResponse])
def list_annotations(db: Session = Depends(get_db)) -> List[Annotation]:
    """List every annotation."""
    return AnnotationRepository(db).list()


@router.post("", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
def register_service(
    service_data: ServiceCreate,
    db: Session = Depends(get_db),
    inventory: InventoryService = Depends(get_inventory_service),
) -> Annotation:
    """Record a registration as an annotation.

    A name matching a discovered service annotates that service with the
    description and health path. Its base_url is not stored: registrations
    typically send a loopback or old-host URL, and the page builds links from
    the visitor's address. A name matching nothing becomes ``manual:<name>``,
    whose only link is the base_url.
    """
    repo = AnnotationRepository(db)
    name = service_data.name
    key = _match_inventory(inventory.get().rows, name) or _match_annotation(repo, name)
    fields = {"description": service_data.description, "health_path": service_data.health_endpoint}
    if key is None:
        key = f"manual:{name}"
    if key.startswith("manual:"):
        fields["link_override"] = service_data.base_url
    return repo.upsert(key, **fields)


@router.put("/annotation", response_model=AnnotationResponse)
def update_annotation(update: AnnotationUpdate, db: Session = Depends(get_db)) -> Annotation:
    """Create or change the annotation for one identity key; omitted fields are unchanged."""
    fields = update.model_dump(exclude_unset=True)
    key = fields.pop("identity_key")
    return AnnotationRepository(db).upsert(key, **fields)


@router.delete("/annotation", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(
    identity_key: str = Query(..., min_length=1), db: Session = Depends(get_db)
) -> Response:
    """Remove the annotation for one identity key."""
    if not AnnotationRepository(db).delete(identity_key):
        raise HTTPException(status_code=404, detail="Annotation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _names(row: InventoryRow) -> set[str]:
    """The names a registration may use for a discovered row."""
    parts = parse_identity_key(row.identity_key)
    if parts is None:
        return set()
    if parts.prefix in ("system", "user"):
        return {parts.name}
    if parts.prefix == "docker":
        return {parts.name, parts.name.rsplit("/", 1)[-1], row.display_name}
    return set()


def _match_inventory(rows: List[InventoryRow], name: str) -> Optional[str]:
    return next((row.identity_key for row in rows if name in _names(row)), None)


def _match_annotation(repo: AnnotationRepository, name: str) -> Optional[str]:
    return next((a.identity_key for a in repo.list() if a.identity_key.endswith(f":{name}")), None)
