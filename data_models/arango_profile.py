from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class SegmentRef(BaseModel):
    id: str
    name: str


class ArangoProfile(BaseModel):
    model_config = ConfigDict(
        extra="ignore"   # ✅ silently ignore unexpected fields
    )

    profile_id: Optional[str] = None

    primaryEmail: Optional[EmailStr] = None
    primaryPhone: Optional[str] = None

    firstName: Optional[str] = None
    lastName: Optional[str] = None

    jobTitles: List[str] = Field(default_factory=list)
    inSegments: List[SegmentRef] = Field(default_factory=list)
    

    @classmethod
    def from_arango(cls, doc: Dict[str, Any]) -> "ArangoProfile":
        return cls(
            profile_id=doc.get("_key"),
            primaryEmail=doc.get("primaryEmail"),
            primaryPhone=doc.get("primaryPhone"),
            firstName=doc.get("firstName"),
            lastName=doc.get("lastName"),
            jobTitles=doc.get("jobTitles", []),
            inSegments=[
                SegmentRef(id=s["id"], name=s["name"])
                for s in doc.get("inSegments", [])
                if isinstance(s, dict) and "id" in s and "name" in s
            ]
        )

    def to_arango(self) -> Dict[str, Any]:
        """
        Rehydrate back into an ArangoDB document.
        Only writes known, intentional fields.
        """
        doc = self.raw.copy()

        if self.profile_id is not None:
            doc["_key"] = self.profile_id
        if self.primaryEmail is not None:
            doc["primaryEmail"] = self.primaryEmail
        if self.primaryPhone is not None:
            doc["primaryPhone"] = self.primaryPhone
        if self.firstName is not None:
            doc["firstName"] = self.firstName
        if self.lastName is not None:
            doc["lastName"] = self.lastName

        doc["jobTitles"] = self.jobTitles
        doc["inSegments"] = [
            {"id": s.id, "name": s.name} for s in self.inSegments
        ]

        return doc
