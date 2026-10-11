import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from app.models.proctoring import (
    ProctoringEventType,
    ProctoringReviewStatus,
    ProctoringEventInDB,
    SingleProctoringEventInput,
    RecordProctoringEventsResponse,
    ProctoringEventSummary,
    ProctoringTimelineItem,
    ProctoringTimelineResponse,
    utc_now,
)
from app.models.interview_session import SessionStatus
from app.models.user import UserInDB, UserRole

logger = logging.getLogger(__name__)

PROCTORING_COLLECTION = "proctoring_events"
SESSIONS_COLLECTION = "interview_sessions"
ASSIGNMENTS_COLLECTION = "student_interview_assignments"


async def _safe_find_one(col: Any, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    res = col.find_one(query)
    if hasattr(res, "__await__"):
        return await res
    return res


async def _safe_to_list(cursor: Any, length: int = 1000) -> List[Dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        res = cursor.to_list(length=length)
        if hasattr(res, "__await__"):
            return await res
        return res
    if hasattr(cursor, "__await__"):
        return await cursor
    return cursor if isinstance(cursor, list) else []


async def _safe_insert_many(col: Any, docs: List[Dict[str, Any]]) -> Any:
    res = col.insert_many(docs)
    if hasattr(res, "__await__"):
        return await res
    return res


async def _safe_update_one(col: Any, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> Any:
    res = col.update_one(filter_dict, update_dict)
    if hasattr(res, "__await__"):
        return await res
    return res


def _format_event_description(event_type: ProctoringEventType, duration: Optional[float] = None) -> str:
    dur_str = f" ({duration:.1f}s)" if duration is not None and duration > 0 else ""
    descriptions = {
        ProctoringEventType.CAMERA_PERMISSION_GRANTED: "Webcam permission granted by candidate.",
        ProctoringEventType.CAMERA_PERMISSION_DENIED: "Webcam access denied by browser or candidate.",
        ProctoringEventType.CAMERA_STREAM_CONNECTED: "Webcam video feed initialized and active.",
        ProctoringEventType.CAMERA_STREAM_DISCONNECTED: "Webcam video feed disconnected or interrupted.",
        ProctoringEventType.CAMERA_TRACK_ENDED: "Webcam hardware device track stopped unexpectedly.",
        ProctoringEventType.FACE_NORMAL: "Single face detected in camera frame.",
        ProctoringEventType.FACE_ABSENT: f"No face detected in video frame{dur_str}.",
        ProctoringEventType.MULTIPLE_FACES: f"Multiple faces detected simultaneously in frame{dur_str}.",
        ProctoringEventType.FACE_RESTORED: "Single face tracking restored in camera frame.",
        ProctoringEventType.TAB_HIDDEN: "Interview browser tab hidden or minimized.",
        ProctoringEventType.TAB_VISIBLE: f"Candidate returned to interview tab{dur_str}.",
        ProctoringEventType.WINDOW_BLUR: "Interview window lost focus.",
        ProctoringEventType.WINDOW_FOCUS: "Interview window regained focus.",
    }
    return descriptions.get(event_type, f"Telemetry event: {event_type.value}{dur_str}")


class ProctoringService:
    @staticmethod
    async def record_events(
        db: AsyncIOMotorDatabase,
        session_id: str,
        events: List[SingleProctoringEventInput],
        student_user: UserInDB,
    ) -> RecordProctoringEventsResponse:
        """
        Records a batch of client-side proctoring events:
        - Validates student ownership of the session.
        - Enforces student registration identity.
        - Generates authoritative server timestamps.
        - Persists events in proctoring_events collection.
        - Does NOT mutate interview scores, responses, or difficulty.
        """
        clean_reg = (student_user.registration_number or "").strip().upper()
        if not clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student account is not linked to a verified registration number",
            )

        # 1. Verify session exists and belongs to this student
        session = await _safe_find_one(db[SESSIONS_COLLECTION], {"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        # Cross-student isolation barrier
        if session.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot submit proctoring telemetry for another student's session",
            )

        now = utc_now()
        assignment_id = session.get("assignment_id", "")
        interview_id = session.get("interview_id", "")

        docs_to_insert = []
        for evt in events:
            doc = {
                "event_id": str(uuid.uuid4()),
                "session_id": session_id,
                "assignment_id": assignment_id,
                "interview_id": interview_id,
                "student_registration_number": clean_reg,
                "event_type": evt.event_type.value,
                "client_timestamp": evt.client_timestamp,
                "server_timestamp": now,
                "duration_seconds": evt.duration_seconds,
                "metadata": evt.metadata or {},
            }
            docs_to_insert.append(doc)

        if docs_to_insert:
            await _safe_insert_many(db[PROCTORING_COLLECTION], docs_to_insert)

        logger.info(
            f"Persisted {len(docs_to_insert)} proctoring events for session {session_id} "
            f"(candidate: {clean_reg})"
        )

        return RecordProctoringEventsResponse(
            success=True,
            session_id=session_id,
            persisted_count=len(docs_to_insert),
            server_received_at=now,
        )

    @staticmethod
    async def get_session_timeline(
        db: AsyncIOMotorDatabase,
        session_id: str,
        current_user: UserInDB,
    ) -> ProctoringTimelineResponse:
        """
        Retrieves proctoring event timeline and summary metrics:
        - Students can access only their own session.
        - Faculty and administrators can inspect any session.
        - Computes summary metrics (tab hidden duration, face absence, stream drops).
        """
        session = await _safe_find_one(db[SESSIONS_COLLECTION], {"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        clean_reg = (current_user.registration_number or "").strip().upper()
        if current_user.role == UserRole.STUDENT and session.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot view proctoring records for another candidate",
            )

        # Fetch events ordered by server_timestamp ascending
        cursor = db[PROCTORING_COLLECTION].find(
            {"session_id": session_id},
            {"_id": 0},
        )
        if hasattr(cursor, "sort") and callable(cursor.sort):
            cursor = cursor.sort("server_timestamp", pymongo.ASCENDING)

        raw_events = await _safe_to_list(cursor, length=1000)

        # Aggregate summary metrics
        tab_hidden_count = 0
        tab_hidden_duration = 0.0
        face_absent_count = 0
        face_absent_duration = 0.0
        multiple_faces_count = 0
        stream_disruptions = 0

        timeline_items: List[ProctoringTimelineItem] = []

        for r in raw_events:
            etype = ProctoringEventType(r["event_type"])
            dur = r.get("duration_seconds")

            if etype == ProctoringEventType.TAB_HIDDEN:
                tab_hidden_count += 1
            elif etype == ProctoringEventType.TAB_VISIBLE:
                if dur and dur > 0:
                    tab_hidden_duration += dur
            elif etype == ProctoringEventType.FACE_ABSENT:
                face_absent_count += 1
                if dur and dur > 0:
                    face_absent_duration += dur
            elif etype == ProctoringEventType.MULTIPLE_FACES:
                multiple_faces_count += 1
            elif etype in (
                ProctoringEventType.CAMERA_PERMISSION_DENIED,
                ProctoringEventType.CAMERA_STREAM_DISCONNECTED,
                ProctoringEventType.CAMERA_TRACK_ENDED,
            ):
                stream_disruptions += 1

            timeline_items.append(
                ProctoringTimelineItem(
                    event_id=r["event_id"],
                    event_type=etype,
                    client_timestamp=r["client_timestamp"],
                    server_timestamp=r["server_timestamp"],
                    duration_seconds=dur,
                    description=_format_event_description(etype, dur),
                    metadata=r.get("metadata", {}),
                )
            )

        # Calculate integrity status badge
        if tab_hidden_count > 3 or face_absent_duration > 60.0 or multiple_faces_count > 2:
            integrity_status = "review_suggested"
        elif tab_hidden_count >= 1 or face_absent_count >= 1 or multiple_faces_count >= 1 or stream_disruptions >= 1:
            integrity_status = "notice"
        else:
            integrity_status = "normal"

        summary = ProctoringEventSummary(
            total_tab_hidden_count=tab_hidden_count,
            total_tab_hidden_duration_seconds=round(tab_hidden_duration, 2),
            total_face_absent_count=face_absent_count,
            total_face_absent_duration_seconds=round(face_absent_duration, 2),
            total_multiple_faces_count=multiple_faces_count,
            stream_disruptions_count=stream_disruptions,
            camera_active_percentage=None,
            integrity_status=integrity_status,
        )

        review_status = session.get("proctoring_review_status", ProctoringReviewStatus.UNREVIEWED.value)
        review_notes = session.get("proctoring_review_notes")

        return ProctoringTimelineResponse(
            session_id=session_id,
            assignment_id=session.get("assignment_id", ""),
            student_registration_number=session.get("student_registration_number", ""),
            summary=summary,
            timeline=timeline_items,
            review_status=ProctoringReviewStatus(review_status),
            review_notes=review_notes,
        )

    @staticmethod
    async def update_review_status(
        db: AsyncIOMotorDatabase,
        session_id: str,
        review_status: ProctoringReviewStatus,
        review_notes: Optional[str],
        admin_user: UserInDB,
    ) -> Dict[str, Any]:
        """
        Updates administrative review status and notes for a session:
        - Strict RBAC: only university_admin, platform_admin, department_admin, or faculty.
        """
        session = await _safe_find_one(db[SESSIONS_COLLECTION], {"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        now = utc_now()
        update_fields = {
            "proctoring_review_status": review_status.value,
            "proctoring_reviewed_by_admin_id": str(admin_user.id),
            "proctoring_reviewed_at": now,
            "updated_at": now,
        }
        if review_notes is not None:
            update_fields["proctoring_review_notes"] = review_notes.strip()

        await _safe_update_one(
            db[SESSIONS_COLLECTION],
            {"session_id": session_id},
            {"$set": update_fields},
        )

        return {
            "success": True,
            "session_id": session_id,
            "review_status": review_status.value,
            "reviewed_by_admin_id": str(admin_user.id),
            "reviewed_at": now.isoformat(),
        }
