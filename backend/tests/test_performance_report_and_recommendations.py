import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.models.user import UserInDB, UserRole
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.interview_session import (
    QuestionDifficulty,
    SessionStatus,
    EvaluatorMode,
    utc_now,
    TopicPerformanceItem,
    ActionablePriorityItem,
    VideoRecommendationItem,
    StudentPerformanceReportResponse,
)
from app.services.interview_session_service import InterviewSessionService
from app.services.learning_resources import (
    match_video_recommendations,
    VERIFIED_LEARNING_RESOURCES,
    extract_youtube_video_id,
    build_youtube_embed_url,
)


def make_user(uid: str, email: str, role: UserRole, reg_no: str = None) -> UserInDB:
    return UserInDB(
        id=uid,
        email=email,
        role=role,
        hashed_password="hashed_password_sample",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_student_can_retrieve_own_completed_report():
    """
    Verifies that a student can retrieve their own completed performance report with:
    - Overall score, percentage, and performance level.
    - Topic-wise aggregated scores and question counts.
    - Clear honesty markers on single-question topics (limited evidence).
    - Actionable growth priorities with evidence justifications.
    - Verified personalized learning video recommendations with unviewed status.
    """
    now = utc_now()
    assignment_id = "asgn-rep-001"
    session_id = "sess-rep-001"
    interview_id = "int-rep-001"
    student = make_user("u-1", "student@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04001")

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_scorecards = AsyncMock()
    mock_interviews = AsyncMock()
    mock_responses = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
        "university_interviews": mock_interviews,
        "interview_responses": mock_responses,
    }[name]

    # Assignment document
    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "interview_id": interview_id,
        "student_registration_number": "241FA04001",
        "student_email": student.email,
        "selected_role": "Software Development Engineer",
        "status": AssignmentStatus.COMPLETED.value,
        "assigned_at": now - timedelta(hours=2),
    }

    # Session document
    completed_session = {
        "session_id": session_id,
        "assignment_id": assignment_id,
        "interview_id": interview_id,
        "student_registration_number": "241FA04001",
        "selected_role": "Software Development Engineer",
        "session_status": SessionStatus.COMPLETED.value,
        "completed_at": now,
        "final_scorecard_id": "sc-001",
    }
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[completed_session])

    # Scorecard document
    mock_scorecards.find_one.return_value = {
        "scorecard_id": "sc-001",
        "session_id": session_id,
        "interview_id": interview_id,
        "student_registration_number": "241FA04001",
        "overall_score": 6.8,
        "percentage_score": 68.0,
        "performance_level": "Satisfactory",
        "summary_feedback": "Demonstrated solid algorithmic fundamentals but requires revision on network protocols.",
        "difficulty_progression": ["medium", "hard", "medium", "hard", "hard"],
        "strengths_summary": ["Recursion and tree traversals", "Clean code structure"],
        "areas_for_growth": ["Deepen understanding of TCP socket mechanics", "Review memory cache hierarchy"],
        "evaluator_mode": "mock_rule_engine",
        "disclaimer": "Automated technical rubric practice.",
    }

    # Interview parent document
    mock_interviews.find_one.return_value = {
        "interview_id": interview_id,
        "title": "Software Development Engineer Technical Screening",
    }

    # Responses: 3 questions on Data Structures (high), 1 on Computer Networks (low), 1 on Operating Systems (medium)
    responses_list = [
        {
            "response_id": "r1",
            "session_id": session_id,
            "question_index": 1,
            "topic": "Data Structures",
            "difficulty": "medium",
            "question_text": "Explain binary search tree balancing and rotations.",
            "answer_text": "AVL trees rotate left or right to maintain balance factor between -1 and 1.",
            "evaluation_score": 8.0,
            "evaluation_feedback": "Accurate rotation mechanics explained clearly.",
            "strengths": ["Clear rotation logic"],
            "improvements": [],
            "difficulty_adjustment_rationale": "High score; escalated.",
            "question_type": "conceptual",
        },
        {
            "response_id": "r2",
            "session_id": session_id,
            "question_index": 2,
            "topic": "Computer Networks",
            "difficulty": "hard",
            "question_text": "Detail the TCP three-way handshake and SYN-ACK sequence numbers.",
            "answer_text": "Client sends SYN, server sends ACK, then connected.",
            "evaluation_score": 4.0,
            "evaluation_feedback": "Superficial answer. Failed to explain ISN (Initial Sequence Number) exchange or SYN-ACK packets.",
            "strengths": [],
            "improvements": ["Explain TCP flags (SYN, ACK) and sequence number acknowledgment synchronization."],
            "difficulty_adjustment_rationale": "Low score; de-escalated.",
            "question_type": "conceptual",
        },
        {
            "response_id": "r3",
            "session_id": session_id,
            "question_index": 3,
            "topic": "Data Structures",
            "difficulty": "medium",
            "question_text": "Compare Hash Table collision handling strategies: Chaining vs Open Addressing.",
            "answer_text": "Chaining uses linked lists, open addressing probes next slot.",
            "evaluation_score": 7.5,
            "evaluation_feedback": "Good comparison with load factor awareness.",
            "strengths": ["Good probe explanation"],
            "improvements": [],
            "difficulty_adjustment_rationale": "Sufficient score.",
            "question_type": "conceptual",
        },
        {
            "response_id": "r4",
            "session_id": session_id,
            "question_index": 4,
            "topic": "Operating Systems",
            "difficulty": "hard",
            "question_text": "Explain deadlock Coffman conditions and how prevention differs from avoidance.",
            "answer_text": "Four conditions: mutual exclusion, hold and wait, no preemption, circular wait.",
            "evaluation_score": 6.5,
            "evaluation_feedback": "Listed conditions accurately, but did not contrast banker's algorithm avoidance with prevention.",
            "strengths": ["Memorized 4 conditions"],
            "improvements": ["Contrast dynamic Banker's avoidance with static condition elimination."],
            "difficulty_adjustment_rationale": "Maintained hard.",
            "question_type": "conceptual",
        },
        {
            "response_id": "r5",
            "session_id": session_id,
            "question_index": 5,
            "topic": "Data Structures",
            "difficulty": "hard",
            "question_text": "Implement or describe LRU Cache with O(1) get and put.",
            "answer_text": "Combine hash map with doubly linked list.",
            "evaluation_score": 8.0,
            "evaluation_feedback": "Correct doubly linked list plus map design.",
            "strengths": ["O(1) architecture correct"],
            "improvements": [],
            "difficulty_adjustment_rationale": "Final question.",
            "question_type": "conceptual",
        },
    ]
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=responses_list)

    report = await InterviewSessionService.get_performance_report(
        db=mock_db,
        assignment_id=assignment_id,
        user=student,
    )

    assert isinstance(report, StudentPerformanceReportResponse)
    assert report.assignment_id == assignment_id
    assert report.student_registration_number == "241FA04001"
    assert report.overall_score == 6.8
    assert report.performance_level == "Satisfactory"
    assert report.selected_role == "Software Development Engineer"
    assert report.interview_title == "Software Development Engineer Technical Screening"

    # Verify Topic Breakdown Aggregation
    topic_map = {t.topic: t for t in report.topic_breakdown}
    assert "Data Structures" in topic_map
    assert "Computer Networks" in topic_map
    assert "Operating Systems" in topic_map

    # Data Structures: 3 questions, avg = (8.0 + 7.5 + 8.0)/3 = 7.8
    ds_topic = topic_map["Data Structures"]
    assert ds_topic.questions_tested == 3
    assert ds_topic.average_score == 7.8
    assert ds_topic.category == "strength"
    assert ds_topic.is_limited_evidence is False
    assert ds_topic.evidence_level == "sufficient"

    # Computer Networks: 1 question (score 4.0) -> MUST BE FLAGGED AS LIMITED EVIDENCE
    net_topic = topic_map["Computer Networks"]
    assert net_topic.questions_tested == 1
    assert net_topic.average_score == 4.0
    assert net_topic.category == "weakness"
    assert net_topic.is_limited_evidence is True
    assert net_topic.evidence_level == "limited"
    assert "Limited evidence" in net_topic.evidence_note

    # Actionable Priorities: Weakest topic (Computer Networks) must be high priority
    assert len(report.actionable_priorities) > 0
    top_priority = report.actionable_priorities[0]
    assert top_priority.topic == "Computer Networks"
    assert top_priority.priority == "high"
    assert "4.0/10" in top_priority.reason
    assert len(top_priority.actionable_steps) >= 2

    # Video Recommendations: Must recommend verified Computer Networks video
    assert len(report.video_recommendations) > 0
    net_recs = [v for v in report.video_recommendations if v.topic == "Computer Networks"]
    assert len(net_recs) >= 1
    rec = net_recs[0]
    assert rec.is_verified is True
    assert rec.watched is False  # Never claims student watched
    assert "https://www.youtube.com/watch?v=IPvYjXCsTg8" in rec.video_url
    assert "Computer Networks" in rec.reason


@pytest.mark.anyio
async def test_cross_student_idor_rejection():
    """
    Verifies that Student B (241FA04002) is rejected with 403 Forbidden
    when attempting to fetch Student A's (241FA04001) performance report.
    """
    assignment_id = "asgn-rep-001"
    student_b = make_user("u-2", "attacker@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04002")

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
    }[name]

    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "student_registration_number": "241FA04001",  # Belongs to Student A
        "status": AssignmentStatus.COMPLETED.value,
    }

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.get_performance_report(
            db=mock_db,
            assignment_id=assignment_id,
            user=student_b,
        )

    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail


@pytest.mark.anyio
async def test_authorized_institutional_roles_can_retrieve_report():
    """
    Verifies that institutional administrative roles and faculty can inspect
    any student's completed report for monitoring and academic review.
    """
    now = utc_now()
    assignment_id = "asgn-rep-001"
    session_id = "sess-rep-001"
    admin_user = make_user("admin-1", "admin@vfstr.ac.in", UserRole.UNIVERSITY_ADMIN)

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_scorecards = AsyncMock()
    mock_interviews = AsyncMock()
    mock_responses = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
        "university_interviews": mock_interviews,
        "interview_responses": mock_responses,
    }[name]

    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.COMPLETED.value,
    }
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[{
        "session_id": session_id,
        "assignment_id": assignment_id,
        "interview_id": "int-1",
        "session_status": SessionStatus.COMPLETED.value,
    }])
    mock_scorecards.find_one.return_value = {
        "scorecard_id": "sc-1",
        "session_id": session_id,
        "overall_score": 7.0,
        "percentage_score": 70.0,
        "performance_level": "Proficient",
        "summary_feedback": "Good interview.",
    }
    mock_interviews.find_one.return_value = {"title": "Campus Placement Mock"}
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    report = await InterviewSessionService.get_performance_report(
        db=mock_db,
        assignment_id=assignment_id,
        user=admin_user,
    )
    assert report.assignment_id == assignment_id
    assert report.student_registration_number == "241FA04001"


@pytest.mark.anyio
async def test_report_unavailable_for_in_progress_session():
    """
    Verifies that requesting a report for an in-progress session returns 400 Bad Request.
    """
    assignment_id = "asgn-in-prog"
    student = make_user("u-1", "student@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04001")

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
    }[name]

    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.IN_PROGRESS.value,
    }
    # No completed session
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    mock_sessions.find_one.return_value = {
        "assignment_id": assignment_id,
        "session_status": SessionStatus.IN_PROGRESS.value,
    }

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.get_performance_report(
            db=mock_db,
            assignment_id=assignment_id,
            user=student,
        )

    assert exc_info.value.status_code == 400
    assert "still in progress" in exc_info.value.detail


def test_verified_catalog_integrity():
    """
    Verifies that the static educational resource catalog contains verified entries,
    valid URLs starting with https://www.youtube.com/watch?v=, valid 11-char video IDs,
    privacy-enhanced embed URLs, and required metadata.
    """
    assert len(VERIFIED_LEARNING_RESOURCES) == 10
    for res in VERIFIED_LEARNING_RESOURCES:
        assert res["resource_id"].startswith("res-")
        assert res["video_url"].startswith("https://www.youtube.com/watch?v=")
        assert res["is_verified"] is True
        assert len(res["title"]) > 10
        assert len(res["provider"]) > 2
        assert len(res["role_tags"]) >= 1
        assert "video_id" in res and len(res["video_id"]) == 11
        assert "embed_url" in res and res["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")
        assert res["can_embed"] is True


def test_match_video_recommendations_celebratory_enrichment_for_high_scores():
    """
    Verifies that when a student scores high across all tested topics (>= 8.0),
    the recommendation engine provides role-specific enrichment (e.g. System Design)
    without fabricating weaknesses.
    """
    high_perf_topics = [
        {"topic": "Data Structures", "average_score": 9.0, "questions_tested": 3},
        {"topic": "Algorithms", "average_score": 8.5, "questions_tested": 2},
    ]
    recs = match_video_recommendations(
        topic_breakdown=high_perf_topics,
        selected_role="Software Development Engineer",
        responses=[],
        max_recommendations=3,
    )
    assert len(recs) == 3
    for r in recs:
        assert r["watched"] is False
        assert r["is_verified"] is True
        assert len(r["video_url"]) > 10


def test_api_route_report_endpoints():
    """
    Validates FastAPI route endpoints with TestClient:
    - GET /api/student/interviews/reports/{assignment_id}
    - GET /api/interview-rooms/sessions/{session_id}/report
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.security import create_access_token
    from unittest.mock import patch

    client = TestClient(app)
    student = make_user("stu-api-1", "student@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04001")
    token = create_access_token(
        subject=student.id,
        email=student.email,
        role=student.role.value,
        institution_id=student.institution_id,
    )
    headers = {"Authorization": f"Bearer {token}"}

    sample_report_dict = {
        "report_id": "rep-test-1",
        "assignment_id": "asgn-api-1",
        "session_id": "sess-api-1",
        "interview_id": "int-api-1",
        "interview_title": "Test Title",
        "selected_role": "Software Development Engineer",
        "student_registration_number": "241FA04001",
        "student_email": student.email,
        "overall_score": 7.5,
        "percentage_score": 75.0,
        "performance_level": "Proficient",
        "summary_feedback": "Solid work.",
        "evaluator_mode": "gemini",
        "difficulty_progression": ["medium", "hard"],
        "completed_at": utc_now(),
        "topic_breakdown": [
            {
                "topic": "Computer Networks",
                "questions_tested": 1,
                "average_score": 6.0,
                "min_score": 6.0,
                "max_score": 6.0,
                "category": "moderate",
                "is_limited_evidence": True,
                "evidence_level": "limited",
                "evidence_note": "Limited evidence: 1 question.",
            }
        ],
        "actionable_priorities": [
            {
                "topic": "Computer Networks",
                "priority": "medium",
                "average_score": 6.0,
                "reason": "6.0/10 average.",
                "actionable_steps": ["Review TCP/IP."],
            }
        ],
        "video_recommendations": [
            {
                "resource_id": "res-net-osi-01",
                "title": "Computer Networking Full Course",
                "provider": "freeCodeCamp.org",
                "topic": "Computer Networks",
                "video_url": "https://www.youtube.com/watch?v=IPvYjXCsTg8",
                "difficulty_level": "medium",
                "reason": "Targeted revision.",
                "watched": False,
                "is_verified": True,
            }
        ],
        "responses": [],
        "disclaimer": "Automated practice.",
    }

    mock_resp = StudentPerformanceReportResponse(**sample_report_dict)
    mock_db = MagicMock()

    from app.core.database import get_interview_database
    from app.api.deps import get_current_active_user

    app.dependency_overrides[get_current_active_user] = lambda: student
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    try:
        with patch("app.services.interview_session_service.InterviewSessionService.get_performance_report", new_callable=AsyncMock) as mock_get_rep, \
             patch("app.services.interview_session_service.InterviewSessionService.get_performance_report_by_session", new_callable=AsyncMock) as mock_get_sess_rep:

            mock_get_rep.return_value = mock_resp
            mock_get_sess_rep.return_value = mock_resp

            # 1. Test student interview report endpoint
            resp1 = client.get("/api/student/interviews/reports/asgn-api-1", headers=headers)
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["assignment_id"] == "asgn-api-1"
            assert data1["overall_score"] == 7.5
            assert len(data1["video_recommendations"]) == 1

            # 2. Test interview room session report endpoint
            resp2 = client.get("/api/interview-rooms/sessions/sess-api-1/report", headers=headers)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["session_id"] == "sess-api-1"
            assert data2["performance_level"] == "Proficient"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_in_progress_session_does_not_return_earlier_completed_session_report():
    """
    Regression test for Fix 1:
    When an assignment has an older completed session and a newer in-progress session,
    requesting the in-progress session must return HTTP 400 and NEVER return the report
    from the earlier completed session.
    """
    now = utc_now()
    assignment_id = "asgn-multi-sess-1"
    old_session_id = "sess-old-completed"
    new_session_id = "sess-new-in-progress"
    student = make_user("stu-multi", "candidate@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04099")

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_scorecards = AsyncMock()
    mock_interviews = AsyncMock()
    mock_responses = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
        "university_interviews": mock_interviews,
        "interview_responses": mock_responses,
    }[name]

    # Assignment document
    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "interview_id": "int-multi",
        "student_registration_number": "241FA04099",
        "status": AssignmentStatus.IN_PROGRESS.value,
    }

    # Session lookup by ID returns the specific session
    def session_find_one(query, *args, **kwargs):
        sid = query.get("session_id")
        if sid == new_session_id:
            return {
                "session_id": new_session_id,
                "assignment_id": assignment_id,
                "interview_id": "int-multi",
                "student_registration_number": "241FA04099",
                "session_status": SessionStatus.IN_PROGRESS.value,
            }
        elif sid == old_session_id:
            return {
                "session_id": old_session_id,
                "assignment_id": assignment_id,
                "interview_id": "int-multi",
                "student_registration_number": "241FA04099",
                "session_status": SessionStatus.COMPLETED.value,
                "completed_at": now - timedelta(days=1),
                "final_scorecard_id": "sc-old",
            }
        return None

    mock_sessions.find_one = AsyncMock(side_effect=session_find_one)
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[{
        "session_id": old_session_id,
        "assignment_id": assignment_id,
        "interview_id": "int-multi",
        "student_registration_number": "241FA04099",
        "session_status": SessionStatus.COMPLETED.value,
        "completed_at": now - timedelta(days=1),
        "final_scorecard_id": "sc-old",
    }])

    # 1. Requesting the in-progress session MUST raise HTTP 400
    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.get_performance_report_by_session(
            db=mock_db,
            session_id=new_session_id,
            user=student,
        )

    assert exc_info.value.status_code == 400
    assert "still in progress" in exc_info.value.detail
    assert new_session_id in exc_info.value.detail

    # 2. Requesting the older completed session returns the older session's report
    mock_scorecards.find_one.return_value = {
        "scorecard_id": "sc-old",
        "session_id": old_session_id,
        "overall_score": 7.0,
        "percentage_score": 70.0,
        "performance_level": "Proficient",
        "summary_feedback": "Previous completed attempt.",
    }
    mock_interviews.find_one.return_value = {"title": "Campus Assessment"}
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    old_report = await InterviewSessionService.get_performance_report_by_session(
        db=mock_db,
        session_id=old_session_id,
        user=student,
    )
    assert old_report.session_id == old_session_id
    assert old_report.overall_score == 7.0


@pytest.mark.anyio
async def test_topic_acronym_preservation_and_grouping():
    """
    Regression test for Fix 2:
    Preserves industry acronyms (SQL, OS, OOP, DBMS, TCP/IP, DSA, API, REST, QA)
    without turning 'SQL' into 'Sql'.
    Groups questions with different casing (e.g. 'SQL' and 'sql') into the same canonical acronym.
    """
    from app.services.interview_session_service import _format_topic_name

    # Unit checks on acronym preservation
    assert _format_topic_name("SQL") == "SQL"
    assert _format_topic_name("sql") == "SQL"
    assert _format_topic_name("OS") == "OS"
    assert _format_topic_name("os") == "OS"
    assert _format_topic_name("OOP") == "OOP"
    assert _format_topic_name("oop") == "OOP"
    assert _format_topic_name("DBMS") == "DBMS"
    assert _format_topic_name("dbms") == "DBMS"
    assert _format_topic_name("TCP/IP") == "TCP/IP"
    assert _format_topic_name("tcp/ip") == "TCP/IP"
    assert _format_topic_name("DSA") == "DSA"
    assert _format_topic_name("dsa") == "DSA"
    assert _format_topic_name("API") == "API"
    assert _format_topic_name("api") == "API"
    assert _format_topic_name("REST") == "REST"
    assert _format_topic_name("rest") == "REST"
    assert _format_topic_name("QA") == "QA"
    assert _format_topic_name("qa") == "QA"

    # Multiword topics
    assert _format_topic_name("computer networks") == "Computer Networks"
    assert _format_topic_name("operating systems") == "Operating Systems"
    assert _format_topic_name("data structures") == "Data Structures"
    assert _format_topic_name("SQL database optimization") == "SQL Database Optimization"

    # End-to-end report generation with acronyms
    now = utc_now()
    assignment_id = "asgn-acronym-1"
    session_id = "sess-acronym-1"
    student = make_user("stu-acr", "student@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04077")

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_scorecards = AsyncMock()
    mock_interviews = AsyncMock()
    mock_responses = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
        "university_interviews": mock_interviews,
        "interview_responses": mock_responses,
    }[name]

    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "interview_id": "int-acr",
        "student_registration_number": "241FA04077",
        "status": AssignmentStatus.COMPLETED.value,
    }
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[{
        "session_id": session_id,
        "assignment_id": assignment_id,
        "interview_id": "int-acr",
        "session_status": SessionStatus.COMPLETED.value,
        "completed_at": now,
        "final_scorecard_id": "sc-acr",
    }])
    mock_scorecards.find_one.return_value = {
        "scorecard_id": "sc-acr",
        "session_id": session_id,
        "overall_score": 6.0,
        "percentage_score": 60.0,
        "performance_level": "Satisfactory",
        "summary_feedback": "Tested on databases and networking.",
    }
    mock_interviews.find_one.return_value = {"title": "Full Stack Assessment"}

    responses_list = [
        # Two questions on SQL with different casing: "SQL" and "sql"
        {
            "response_id": "r1",
            "session_id": session_id,
            "question_index": 1,
            "topic": "SQL",
            "difficulty": "medium",
            "question_text": "Write a query with group by and having.",
            "answer_text": "SELECT dept, count(*) FROM emp GROUP BY dept HAVING count(*) > 5;",
            "evaluation_score": 8.0,
            "evaluation_feedback": "Correct query.",
            "strengths": [],
            "improvements": [],
            "difficulty_adjustment_rationale": "Escalated.",
            "question_type": "conceptual",
        },
        {
            "response_id": "r2",
            "session_id": session_id,
            "question_index": 2,
            "topic": "sql",
            "difficulty": "hard",
            "question_text": "Explain B-tree indexes vs Hash indexes in PostgreSQL.",
            "answer_text": "B-tree for range queries, Hash for equality.",
            "evaluation_score": 7.0,
            "evaluation_feedback": "Accurate distinction.",
            "strengths": [],
            "improvements": [],
            "difficulty_adjustment_rationale": "Maintained.",
            "question_type": "conceptual",
        },
        # One question on TCP/IP (acronym with slash)
        {
            "response_id": "r3",
            "session_id": session_id,
            "question_index": 3,
            "topic": "tcp/ip",
            "difficulty": "medium",
            "question_text": "Explain TCP flow control and sliding window.",
            "answer_text": "Window size controls unacknowledged bytes.",
            "evaluation_score": 4.5,
            "evaluation_feedback": "Needs more detail on advertised window.",
            "strengths": [],
            "improvements": ["Explain TCP window scaling options and receiver buffer starvation."],
            "difficulty_adjustment_rationale": "De-escalated.",
            "question_type": "conceptual",
        },
        # One question on QA
        {
            "response_id": "r4",
            "session_id": session_id,
            "question_index": 4,
            "topic": "qa",
            "difficulty": "medium",
            "question_text": "Describe boundary value analysis.",
            "answer_text": "Test at the edges of equivalence partitions.",
            "evaluation_score": 7.5,
            "evaluation_feedback": "Good answer.",
            "strengths": [],
            "improvements": [],
            "difficulty_adjustment_rationale": "Maintained.",
            "question_type": "conceptual",
        },
    ]
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=responses_list)

    report = await InterviewSessionService.get_performance_report(
        db=mock_db,
        assignment_id=assignment_id,
        user=student,
    )

    topic_map = {t.topic: t for t in report.topic_breakdown}

    # "SQL" and "sql" MUST be grouped together into "SQL" (count=2, NOT "Sql")
    assert "SQL" in topic_map
    assert "Sql" not in topic_map
    sql_item = topic_map["SQL"]
    assert sql_item.questions_tested == 2
    assert sql_item.average_score == 7.5

    # "tcp/ip" MUST be formatted as "TCP/IP"
    assert "TCP/IP" in topic_map
    assert "Tcp/Ip" not in topic_map
    tcp_item = topic_map["TCP/IP"]
    assert tcp_item.questions_tested == 1
    assert tcp_item.average_score == 4.5
    assert tcp_item.is_limited_evidence is True

    # "qa" MUST be formatted as "QA"
    assert "QA" in topic_map
    assert "Qa" not in topic_map


def test_video_recommendations_skipped_question_handling():
    """
    Phase 4 test:
    Verifies that when a question is skipped or unanswered:
    - An introductory tutorial is matched for that question's topic.
    - No fabricated score (e.g. 0.0) is assigned or cited in the reasoning.
    - The reason clearly explains that Question N on the topic was skipped.
    - Embed URL and YouTube video ID are properly attached.
    """
    responses = [
        {
            "response_id": "r1",
            "question_index": 1,
            "topic": "Data Structures",
            "evaluation_score": 7.5,
            "answer_text": "A binary heap is a complete binary tree...",
            "is_skipped": False,
            "status": "evaluated",
        },
        {
            "response_id": "r2",
            "question_index": 2,
            "topic": "Operating Systems",
            "evaluation_score": None,
            "answer_text": "",
            "is_skipped": True,
            "status": "skipped",
        },
    ]
    topic_breakdown = [
        {"topic": "Data Structures", "average_score": 7.5, "questions_tested": 1},
    ]

    recs = match_video_recommendations(
        topic_breakdown=topic_breakdown,
        selected_role="Software Development Engineer",
        responses=responses,
        max_recommendations=3,
    )

    os_recs = [r for r in recs if r["topic"] == "Operating Systems"]
    assert len(os_recs) >= 1
    os_rec = os_recs[0]
    assert "Question 2" in os_rec["reason"]
    assert "Operating Systems" in os_rec["reason"]
    assert "skipped" in os_rec["reason"]
    assert "introductory tutorial" in os_rec["reason"]
    assert "0.0" not in os_rec["reason"]
    assert os_rec["video_id"] == "mXw9ruZaxzQ"
    assert os_rec["embed_url"] == "https://www.youtube-nocookie.com/embed/mXw9ruZaxzQ?rel=0&modestbranding=1"
    assert os_rec["can_embed"] is True


def test_video_recommendations_insufficient_evidence_qualification():
    """
    Phase 4 test:
    Verifies that single-question topics qualify their recommendation reason
    with a note about the limited sample size to avoid over-generalizing.
    Multi-question topics cite the exact question count.
    """
    responses = [
        {
            "response_id": "r1",
            "question_index": 1,
            "topic": "Computer Networks",
            "evaluation_score": 4.0,
            "answer_text": "TCP is connection oriented.",
            "is_skipped": False,
            "status": "evaluated",
        },
        {
            "response_id": "r2",
            "question_index": 2,
            "topic": "Operating Systems",
            "evaluation_score": 5.0,
            "answer_text": "Deadlock is when processes wait.",
            "is_skipped": False,
            "status": "evaluated",
        },
        {
            "response_id": "r3",
            "question_index": 3,
            "topic": "Operating Systems",
            "evaluation_score": 5.5,
            "answer_text": "Virtual memory uses paging.",
            "is_skipped": False,
            "status": "evaluated",
        },
    ]
    topic_breakdown = [
        {"topic": "Computer Networks", "average_score": 4.0, "questions_tested": 1},
        {"topic": "Operating Systems", "average_score": 5.25, "questions_tested": 2},
    ]

    recs = match_video_recommendations(
        topic_breakdown=topic_breakdown,
        selected_role="Software Development Engineer",
        responses=responses,
        max_recommendations=3,
    )

    # 1. Computer Networks (single question sample)
    net_recs = [r for r in recs if r["topic"] == "Computer Networks"]
    assert len(net_recs) == 1
    assert "single question sample" in net_recs[0]["reason"]
    assert "Question 1" in net_recs[0]["reason"]
    assert "4.0/10" in net_recs[0]["reason"]

    # 2. Operating Systems (two question sample)
    os_recs = [r for r in recs if r["topic"] == "Operating Systems"]
    assert len(os_recs) == 1
    assert "across 2 question(s)" in os_recs[0]["reason"]
    assert "Question 2, Question 3" in os_recs[0]["reason"]


def test_video_recommendations_strong_performance_celebration():
    """
    Phase 4 test:
    Verifies that when a student achieves high scores (all >= 7.0) with zero skipped questions,
    the system presents celebratory advanced enrichment rather than manufacturing deficiencies.
    """
    responses = [
        {
            "response_id": "r1",
            "question_index": 1,
            "topic": "Data Structures",
            "evaluation_score": 8.5,
            "is_skipped": False,
            "status": "evaluated",
        },
        {
            "response_id": "r2",
            "question_index": 2,
            "topic": "Algorithms",
            "evaluation_score": 9.0,
            "is_skipped": False,
            "status": "evaluated",
        },
    ]
    topic_breakdown = [
        {"topic": "Data Structures", "average_score": 8.5, "questions_tested": 1},
        {"topic": "Algorithms", "average_score": 9.0, "questions_tested": 1},
    ]

    recs = match_video_recommendations(
        topic_breakdown=topic_breakdown,
        selected_role="Software Development Engineer",
        responses=responses,
        max_recommendations=3,
    )

    assert len(recs) == 3
    assert any("Excellent performance!" in r["reason"] for r in recs)
    for r in recs:
        assert r["can_embed"] is True
        assert r["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")
        assert len(r["video_id"]) == 11


def test_video_recommendations_unmatched_topic_fallback():
    """
    Phase 4 test:
    Verifies that when a topic does not match any curated resource (e.g. niche or custom topic),
    the recommendation engine falls back to role-aligned resources without error or empty results.
    """
    responses = [
        {
            "response_id": "r1",
            "question_index": 1,
            "topic": "Quantum Computing & Cryptography",
            "evaluation_score": 3.0,
            "is_skipped": False,
            "status": "evaluated",
        }
    ]
    topic_breakdown = [
        {"topic": "Quantum Computing & Cryptography", "average_score": 3.0, "questions_tested": 1}
    ]

    recs = match_video_recommendations(
        topic_breakdown=topic_breakdown,
        selected_role="Software Development Engineer",
        responses=responses,
        max_recommendations=2,
    )

    assert len(recs) == 2
    for r in recs:
        assert r["is_verified"] is True
        assert r["can_embed"] is True
        assert r["video_id"] is not None


def test_safe_youtube_id_extraction_and_embed_url():
    """
    Phase 4 test:
    Verifies that YouTube video ID extraction and embed URL generation:
    - Correctly parses standard watch URLs, short youtu.be URLs, and embed URLs.
    - Strictly rejects non-YouTube URLs, invalid IDs, script injections, and malformed inputs.
    - Constructs privacy-enhanced, nocookie embed URLs with rel=0 and modestbranding=1.
    """
    # 1. Standard watch URL
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=IPvYjXCsTg8") == "IPvYjXCsTg8"
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=IPvYjXCsTg8&t=120s") == "IPvYjXCsTg8"

    # 2. youtu.be short URL
    assert extract_youtube_video_id("https://youtu.be/IPvYjXCsTg8") == "IPvYjXCsTg8"

    # 3. Existing embed URL
    assert extract_youtube_video_id("https://www.youtube.com/embed/IPvYjXCsTg8") == "IPvYjXCsTg8"
    assert extract_youtube_video_id("https://www.youtube-nocookie.com/embed/IPvYjXCsTg8") == "IPvYjXCsTg8"

    # 4. Plain valid 11-char ID
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=8hly31xKli0") == "8hly31xKli0"

    # 5. Invalid / Malicious / Injected URLs
    assert extract_youtube_video_id(None) is None
    assert extract_youtube_video_id("") is None
    assert extract_youtube_video_id("not-a-url") is None
    assert extract_youtube_video_id("https://evil.example.com/watch?v=IPvYjXCsTg8") is None
    assert extract_youtube_video_id("<script>alert(1)</script>") is None
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=short") is None
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=toolongvideoid12345") is None

    # 6. Embed URL constructor
    embed = build_youtube_embed_url("https://www.youtube.com/watch?v=IPvYjXCsTg8")
    assert embed == "https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1"

    # Direct 11-char ID
    embed_direct = build_youtube_embed_url("IPvYjXCsTg8")
    assert embed_direct == "https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1"

    # Invalid input returns None
    assert build_youtube_embed_url(None) is None
    assert build_youtube_embed_url("") is None
    assert build_youtube_embed_url("malicious_id_too_long_or_with_invalid_characters!!!") is None


def test_boundary_scores_and_high_performance_safeguards():
    """
    Hardening test:
    Verifies behavior at score boundaries:
    - 6.49 triggers weak-topic revision (< 6.5)
    - 6.5 does NOT trigger weak-topic revision (< 6.5) and does NOT trigger high-performance (>= 7.0)
    - 6.99 does NOT trigger high-performance enrichment
    - 7.0 triggers high-performance enrichment when all evaluated questions >= 7.0 and zero skipped
    - Incomplete assessment (None evaluation score) or skipped question NEVER triggers high performance
    """
    # 1. Score 6.49: Triggers Pass 2 (Weak evaluated topic)
    recs_649 = match_video_recommendations(
        topic_breakdown=[{"topic": "Data Structures", "average_score": 6.49, "questions_tested": 1}],
        selected_role="Software Development Engineer",
        responses=[{"question_index": 1, "topic": "Data Structures", "evaluation_score": 6.49}],
        max_recommendations=2,
    )
    assert len(recs_649) >= 1
    assert "revision" in recs_649[0]["reason"].lower()
    assert "6.49" in recs_649[0]["reason"]

    # 2. Score 6.5: Does NOT trigger weak topic (< 6.5)
    recs_65 = match_video_recommendations(
        topic_breakdown=[{"topic": "Data Structures", "average_score": 6.5, "questions_tested": 1}],
        selected_role="Software Development Engineer",
        responses=[{"question_index": 1, "topic": "Data Structures", "evaluation_score": 6.5}],
        max_recommendations=2,
    )
    assert len(recs_65) >= 1
    assert "6.5" not in recs_65[0]["reason"]
    assert "Excellent performance!" not in recs_65[0]["reason"]

    # 3. Score 6.99: Below 7.0, does NOT trigger celebratory enrichment
    recs_699 = match_video_recommendations(
        topic_breakdown=[{"topic": "Data Structures", "average_score": 6.99, "questions_tested": 1}],
        selected_role="Software Development Engineer",
        responses=[{"question_index": 1, "topic": "Data Structures", "evaluation_score": 6.99}],
        max_recommendations=2,
    )
    assert len(recs_699) >= 1
    assert not any("Excellent performance!" in r["reason"] for r in recs_699)

    # 4. Score 7.0: Exactly at threshold, triggers celebratory enrichment
    recs_70 = match_video_recommendations(
        topic_breakdown=[{"topic": "Data Structures", "average_score": 7.0, "questions_tested": 1}],
        selected_role="Software Development Engineer",
        responses=[{"question_index": 1, "topic": "Data Structures", "evaluation_score": 7.0}],
        max_recommendations=2,
    )
    assert len(recs_70) >= 1
    assert any("Excellent performance!" in r["reason"] for r in recs_70)

    # 5. Incomplete assessment safeguard: 1 response has score 9.0, but 1 response has evaluation_score = None
    # Must NEVER trigger high performance!
    recs_incomplete = match_video_recommendations(
        topic_breakdown=[
            {"topic": "Data Structures", "average_score": 9.0, "questions_tested": 1},
            {"topic": "Algorithms", "average_score": 7.0, "questions_tested": 1},
        ],
        selected_role="Software Development Engineer",
        responses=[
            {"question_index": 1, "topic": "Data Structures", "evaluation_score": 9.0, "answer_text": "AVL trees"},
            {"question_index": 2, "topic": "Algorithms", "evaluation_score": None, "answer_text": "Draft answer in progress"},
        ],
        max_recommendations=2,
    )
    assert not any("Excellent performance!" in r["reason"] for r in recs_incomplete)

    # 6. Skipped question safeguard: 1 response has score 10.0, but question 2 was skipped
    # Must NEVER trigger high performance!
    recs_skipped = match_video_recommendations(
        topic_breakdown=[{"topic": "Data Structures", "average_score": 10.0, "questions_tested": 1}],
        selected_role="Software Development Engineer",
        responses=[
            {"question_index": 1, "topic": "Data Structures", "evaluation_score": 10.0},
            {"question_index": 2, "topic": "Operating Systems", "is_skipped": True},
        ],
        max_recommendations=2,
    )
    assert not any("Excellent performance!" in r["reason"] for r in recs_skipped)


def test_unanswered_topic_zero_score_fabrication_prevention():
    """
    Hardening test:
    When a student skips all questions in a topic and the topic average is recorded as 0.0,
    the recommendation system must NEVER fabricate a statement claiming the candidate scored 0.0/10.
    """
    responses = [
        {
            "question_index": 1,
            "topic": "Operating Systems",
            "is_skipped": True,
            "answer_text": "",
            "evaluation_score": None,
        }
    ]
    # Topic breakdown indicates 0.0 average score
    topic_breakdown = [
        {
            "topic": "Operating Systems",
            "average_score": 0.0,
            "questions_tested": 1,
            "is_limited_evidence": True,
        }
    ]

    recs = match_video_recommendations(
        topic_breakdown=topic_breakdown,
        selected_role="System Engineer",
        responses=responses,
        max_recommendations=2,
    )

    assert len(recs) >= 1
    os_rec = recs[0]
    assert "0.0/10" not in os_rec["reason"]
    assert "0.0" not in os_rec["reason"]
    assert "Operating Systems" in os_rec["reason"]


def test_strict_url_security_against_credentials_ports_and_deceptive_hosts():
    """
    Hardening test:
    Verifies that extract_youtube_video_id and build_youtube_embed_url reject:
    - Embedded username/password credentials (e.g. https://user:pass@youtube.com/...)
    - Unexpected ports (e.g. https://youtube.com:8443/...)
    - Deceptive subdomains / suffixes (e.g. https://youtube.com.evil.com/...)
    - Non-http/https protocols (javascript:, ftp:, data:)
    - PII or secret query parameters are stripped from embed URLs
    """
    # Deceptive domains
    assert extract_youtube_video_id("https://youtube.com.evil.com/watch?v=IPvYjXCsTg8") is None
    assert extract_youtube_video_id("https://www.youtube.com.attacker.org/embed/IPvYjXCsTg8") is None

    # Embedded credentials
    assert extract_youtube_video_id("https://user:password@www.youtube.com/watch?v=IPvYjXCsTg8") is None

    # Unexpected ports
    assert extract_youtube_video_id("https://www.youtube.com:8080/watch?v=IPvYjXCsTg8") is None
    assert extract_youtube_video_id("https://www.youtube.com:4444/watch?v=IPvYjXCsTg8") is None

    # Dangerous protocols
    assert extract_youtube_video_id("javascript:alert('xss')") is None
    assert extract_youtube_video_id("data:text/html,<script>alert(1)</script>") is None
    assert extract_youtube_video_id("ftp://www.youtube.com/watch?v=IPvYjXCsTg8") is None

    # Embed URL generation strips tokens and PII completely
    dirty_url = "https://www.youtube.com/watch?v=IPvYjXCsTg8&token=secret_jwt_bearer&student_id=241FA04001"
    embed_url = build_youtube_embed_url(dirty_url)
    assert embed_url == "https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1"
    assert "token" not in embed_url
    assert "student_id" not in embed_url
    assert "241FA04001" not in embed_url


def test_acronym_matching_collision_protection():
    """
    Hardening test:
    Verifies that short technical acronyms like 'OS' do not collide with unrelated topics
    such as 'Microservices' in System Design, and that 'SQL' and 'TCP/IP' match accurately.
    """
    from app.services.learning_resources import _matches_topic, VERIFIED_LEARNING_RESOURCES

    os_resource = next(r for r in VERIFIED_LEARNING_RESOURCES if r["resource_id"] == "res-os-fundamentals-01")
    sys_design_resource = next(r for r in VERIFIED_LEARNING_RESOURCES if r["resource_id"] == "res-sys-design-01")

    # "OS" must match Operating Systems
    assert _matches_topic(os_resource, "OS") is True
    assert _matches_topic(os_resource, "os") is True

    # "OS" must NOT match System Design (even though System Design has "Microservices")
    assert _matches_topic(sys_design_resource, "OS") is False
    assert _matches_topic(sys_design_resource, "os") is False

    # "SQL" matches Database
    db_resource = next(r for r in VERIFIED_LEARNING_RESOURCES if r["resource_id"] == "res-db-sql-01")
    assert _matches_topic(db_resource, "SQL") is True
    assert _matches_topic(db_resource, "sql") is True
