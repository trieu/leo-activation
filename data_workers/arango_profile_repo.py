# repositories/arango_profile_repo.py
import logging
from typing import List
from models.profile import CDPProfile, SegmentRef

logger = logging.getLogger(__name__)


class ArangoProfileRepository:
    def __init__(self, db):
        self.db = db

    def resolve_segment_id(self, segment_name: str) -> str | None:
        query = """
        FOR s IN cdp_segment
            FILTER s.name == @name
            RETURN s._key
        """
        cursor = self.db.aql.execute(query, bind_vars={"name": segment_name})
        return next(iter(cursor), None)

    def fetch_profiles_by_segment(self, segment_name: str) -> List[CDPProfile]:
        segment_id = self.resolve_segment_id(segment_name)

        if not segment_id:
            logger.warning(f"[ArangoDB] Segment not found: {segment_name}")
            return []

        query = """
        FOR p IN cdp_profile
            FILTER @segment_id IN p.inSegments[*].id
            FILTER (p.primaryEmail != null AND p.primaryEmail != "")
               OR (p.primaryPhone != null AND p.primaryPhone != "")
            RETURN p
        """

        cursor = self.db.aql.execute(
            query, bind_vars={"segment_id": segment_id}
        )

        profiles: List[CDPProfile] = []

        for doc in cursor:
            profiles.append(
                CDPProfile(
                    ext_id=doc.get("_key"),
                    email=doc.get("primaryEmail"),
                    mobile_number=doc.get("primaryPhone"),
                    first_name=doc.get("firstName"),
                    last_name=doc.get("lastName"),
                    segments=[
                        SegmentRef(id=s["id"], name=s.get("name"))
                        for s in doc.get("inSegments", [])
                    ],
                    data_labels=doc.get("dataLabels", []),
                    raw_attributes=doc,
                )
            )

        logger.info(f"[ArangoDB] Loaded {len(profiles)} profiles")
        return profiles
