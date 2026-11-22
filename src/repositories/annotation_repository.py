"""Data access for annotations."""
from typing import Optional
from sqlalchemy.orm import Session
from src.models.annotation import Annotation

_FIELDS = ("display_name", "description", "hidden", "link_override", "health_path", "primary_port")


class AnnotationRepository:
    """Get, upsert, list, hide and delete annotations by identity key."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, identity_key: str) -> Optional[Annotation]:
        return self.session.query(Annotation).filter_by(identity_key=identity_key).first()

    def list(self) -> list[Annotation]:
        return self.session.query(Annotation).order_by(Annotation.identity_key).all()

    def upsert(self, identity_key: str, **fields) -> Annotation:
        unknown = set(fields) - set(_FIELDS)
        if unknown:
            raise TypeError(f"Unknown annotation fields: {sorted(unknown)}")
        annotation = self.get(identity_key)
        if annotation is None:
            annotation = Annotation(identity_key=identity_key)
            self.session.add(annotation)
        for name, value in fields.items():
            setattr(annotation, name, value)
        self.session.commit()
        self.session.refresh(annotation)
        return annotation

    def delete(self, identity_key: str) -> bool:
        annotation = self.get(identity_key)
        if annotation is None:
            return False
        self.session.delete(annotation)
        self.session.commit()
        return True

    def set_hidden(self, identity_key: str, hidden: bool) -> Annotation:
        return self.upsert(identity_key, hidden=hidden)
