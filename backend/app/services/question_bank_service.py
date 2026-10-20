import logging
import uuid
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status
from pymongo import UpdateOne, ASCENDING, DESCENDING

from app.models.user import UserInDB, UserRole
from app.models.interview_session import QuestionDifficulty
from app.models.question_bank import (
    StoredQuestionItem,
    QuestionType,
    QuestionPreviewItem,
    QuestionExtractionPreviewResponse,
    QuestionBatchSaveRequest,
    QuestionBatchSaveResponse,
    QuestionBankListResponse,
    QuestionSetSummary,
    QuestionSetListResponse,
    QuestionSetPreviewResponse,
    utc_now,
)
from app.services.question_file_parser import parse_question_file

logger = logging.getLogger(__name__)

QUESTIONS_COLLECTION = "interview_questions"


class QuestionBankService:
    @staticmethod
    def preview_uploaded_file(
        file_bytes: bytes,
        filename: str,
        default_topic: str = "Technical Assessment",
    ) -> QuestionExtractionPreviewResponse:
        """
        Parses an uploaded file (PDF, CSV, JSON, TXT, MD, or ZIP) and produces
        an interactive extraction preview for faculty review and inline correction.
        Validates question fields, flags missing or deficient inputs without discarding them,
        and extracts role metadata if present in structured formats.
        """
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file payload is empty",
            )

        clean_filename = filename.strip()
        lower_name = clean_filename.lower()
        allowed_extensions = (".pdf", ".csv", ".json", ".txt", ".md", ".zip")
        if not lower_name.endswith(allowed_extensions):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{clean_filename}'. Supported formats: PDF, CSV, JSON, TXT, MD, and ZIP.",
            )

        try:
            parsed_raw = parse_question_file(
                file_bytes_or_path=file_bytes,
                filename=clean_filename,
                default_topic=default_topic or "Technical Assessment",
            )
        except Exception as e:
            logger.warning("Failed to parse question file '%s': %s", clean_filename, e)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not extract questions from '{clean_filename}': {str(e)}",
            )

        if not parsed_raw:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No valid question prompts could be identified in '{clean_filename}'. Please ensure questions follow standard format (e.g., 'Q1. [Topic] Question text...').",
            )

        detected_role = None
        preview_items: List[QuestionPreviewItem] = []

        for idx, item in enumerate(parsed_raw, 1):
            q_text = str(item.get("question_text") or "").strip()
            topic = str(item.get("topic") or default_topic or "Technical Assessment").strip()
            role = item.get("role")
            if role and not detected_role:
                detected_role = str(role).strip()

            raw_type = str(item.get("question_type") or "conceptual").strip().lower()
            q_type = QuestionType.CODING if raw_type == "coding" else QuestionType.CONCEPTUAL

            raw_diff = item.get("difficulty")
            diff: Optional[QuestionDifficulty] = None
            if raw_diff:
                try:
                    diff = QuestionDifficulty(str(raw_diff).lower())
                except ValueError:
                    diff = None

            expected_ans = item.get("expected_answer")
            if expected_ans:
                expected_ans = str(expected_ans).strip()

            keywords = item.get("keywords") or []
            if not isinstance(keywords, list):
                keywords = []

            # Validation checks
            errors: List[str] = []
            if len(q_text) < 10:
                errors.append("Question prompt is too short (minimum 10 characters required).")
            if not topic:
                errors.append("Topic is required.")

            is_valid = len(errors) == 0

            preview_items.append(
                QuestionPreviewItem(
                    temp_id=str(uuid.uuid4()),
                    question_text=q_text,
                    question_type=q_type,
                    topic=topic,
                    difficulty=diff,
                    expected_answer=expected_ans,
                    role=role,
                    keywords=keywords,
                    is_valid=is_valid,
                    validation_errors=errors,
                )
            )

        valid_count = sum(1 for p in preview_items if p.is_valid)
        invalid_count = len(preview_items) - valid_count

        return QuestionExtractionPreviewResponse(
            filename=clean_filename,
            total_extracted=len(preview_items),
            valid_count=valid_count,
            invalid_count=invalid_count,
            detected_role=detected_role,
            questions=preview_items,
        )

    @staticmethod
    async def save_confirmed_questions(
        db: AsyncIOMotorDatabase,
        data: QuestionBatchSaveRequest,
        current_user: UserInDB,
    ) -> QuestionBatchSaveResponse:
        """
        Commits verified questions into the interview_questions database collection:
        - Enforces strict multi-tenant institutional isolation (tagged with current_user.institution_id).
        - Enforces department scoping if reviewer is department-constrained.
        - Preserves existing VFSTR question bank records and existing batch imports.
        - Does NOT automatically schedule interviews or assign candidates.
        """
        if current_user.role not in [
            UserRole.PLATFORM_ADMIN,
            UserRole.UNIVERSITY_ADMIN,
            UserRole.DEPARTMENT_ADMIN,
            UserRole.FACULTY,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to manage institution question bank",
            )

        inst_id = (current_user.institution_id or "VFSTR").strip().upper()
        if not inst_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reviewer institutional identity could not be verified.",
            )

        dept = current_user.department or data.target_department
        if current_user.role == UserRole.DEPARTMENT_ADMIN and not dept:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department administrator must have an assigned department scope.",
            )

        valid_questions = [q for q in data.questions if len(q.question_text.strip()) >= 10]
        if not valid_questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid questions to save. All question texts must be at least 10 characters.",
            )

        batch_id = f"batch-upload-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = utc_now()
        target_role = data.role

        docs_to_insert = []
        for idx, q in enumerate(valid_questions, 1):
            clean_text = q.question_text.strip()
            clean_topic = (q.topic or "Technical Assessment").strip()
            q_role = q.role or target_role

            # Generate stable deterministic keyword list if empty
            keywords = q.keywords or [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", clean_text)[:6]]

            doc = {
                "question_id": str(uuid.uuid4()),
                "interview_id": data.interview_id,
                "institution_id": inst_id,
                "department": dept,
                "role": q_role,
                "set_number": None,
                "question_number": idx,
                "question_type": q.question_type.value,
                "topic": clean_topic,
                "difficulty": q.difficulty.value if q.difficulty else None,
                "question_text": clean_text,
                "expected_answer": q.expected_answer.strip() if q.expected_answer else None,
                "keywords": keywords,
                "source_filename": f"institution-upload-{inst_id.lower()}",
                "import_batch_id": batch_id,
                "created_by_user_id": str(current_user.id),
                "created_by_email": current_user.email,
                "created_at": now,
                "updated_at": now,
            }
            docs_to_insert.append(doc)

        coll = db[QUESTIONS_COLLECTION]
        if docs_to_insert:
            res = coll.insert_many(docs_to_insert)
            if hasattr(res, "__await__"):
                await res

        logger.info(
            "Saved %d institution questions for %s (batch: %s) by %s",
            len(docs_to_insert),
            inst_id,
            batch_id,
            current_user.email,
        )

        return QuestionBatchSaveResponse(
            success=True,
            saved_count=len(docs_to_insert),
            batch_id=batch_id,
            institution_id=inst_id,
            interview_id=data.interview_id,
        )

    @staticmethod
    async def list_questions(
        db: AsyncIOMotorDatabase,
        current_user: UserInDB,
        role: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        interview_id: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QuestionBankListResponse:
        """
        Retrieves institution-scoped stored questions with search, role, topic, and difficulty filters.
        Enforces tenant isolation:
        - platform_admin: can view all questions across institutions or filter by institution.
        - university_admin & faculty: views questions belonging to their institution_id,
          plus shared platform questions where institution_id is None or matches VFSTR.
        """
        if current_user.role not in [
            UserRole.PLATFORM_ADMIN,
            UserRole.UNIVERSITY_ADMIN,
            UserRole.DEPARTMENT_ADMIN,
            UserRole.FACULTY,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access institution question bank",
            )

        inst_id = (current_user.institution_id or "VFSTR").strip().upper()
        filter_query: Dict[str, Any] = {}

        if current_user.role != UserRole.PLATFORM_ADMIN:
            # Multi-tenant isolation: reviewer's institution or platform-shared (institution_id is None or matches)
            filter_query["$or"] = [
                {"institution_id": inst_id},
                {"institution_id": None},
                {"institution_id": {"$exists": False}},
            ]
            if current_user.role == UserRole.DEPARTMENT_ADMIN and current_user.department:
                filter_query["$and"] = [
                    {"$or": filter_query.pop("$or")},
                    {"$or": [{"department": current_user.department}, {"department": None}, {"department": {"$exists": False}}]},
                ]

        if role and role.strip():
            filter_query["role"] = role.strip()

        if topic and topic.strip():
            filter_query["topic"] = {"$regex": re.escape(topic.strip()), "$options": "i"}

        if difficulty and difficulty.strip():
            clean_diff = difficulty.strip().lower()
            if clean_diff in ["easy", "medium", "hard"]:
                filter_query["difficulty"] = clean_diff

        if interview_id and interview_id.strip():
            filter_query["interview_id"] = interview_id.strip()

        if search and search.strip():
            clean_search = search.strip()
            search_regex = {"$regex": re.escape(clean_search), "$options": "i"}
            search_clause = [
                {"question_text": search_regex},
                {"topic": search_regex},
                {"role": search_regex},
            ]
            if "$and" in filter_query:
                filter_query["$and"].append({"$or": search_clause})
            elif "$or" in filter_query:
                filter_query["$and"] = [{"$or": filter_query.pop("$or")}, {"$or": search_clause}]
            else:
                filter_query["$or"] = search_clause

        coll = db[QUESTIONS_COLLECTION]
        count_res = coll.count_documents(filter_query)
        total = await count_res if hasattr(count_res, "__await__") else count_res

        cursor = coll.find(filter_query, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(limit)
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=limit)
        elif hasattr(cursor, "__await__"):
            docs = await cursor
        else:
            docs = list(cursor)

        items = [StoredQuestionItem(**d) for d in docs]
        return QuestionBankListResponse(total=total, items=items)

    @staticmethod
    async def validate_question_set_access(
        db: AsyncIOMotorDatabase,
        set_id: str,
        current_user: UserInDB,
    ) -> Dict[str, Any]:
        """
        Validates that the given question set exists and that the user is authorized to access it
        within institutional multi-tenant bounds.
        """
        clean_set_id = (set_id or "").strip()
        if not clean_set_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Question set ID cannot be empty",
            )

        # 1. Platform-shared canonical role sets
        platform_roles = {
            "platform-role-associate-software-engineer": "Associate Software Engineer",
            "platform-role-software-development-engineer": "Software Development Engineer",
            "platform-role-product-engineer": "Product Engineer",
            "platform-role-system-engineer": "System Engineer",
            "platform-role-testing-engineer": "Testing Engineer",
        }
        if clean_set_id in platform_roles:
            return {
                "valid": True,
                "source_type": "platform",
                "role": platform_roles[clean_set_id],
                "set_id": clean_set_id,
            }

        # 2. Institution-scoped custom upload batches
        coll = db[QUESTIONS_COLLECTION]
        sample_doc = await coll.find_one({"import_batch_id": clean_set_id})
        if not sample_doc:
            # Fallback check for single question_id
            sample_doc = await coll.find_one({"question_id": clean_set_id})

        if not sample_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question set '{clean_set_id}' was not found.",
            )

        # Enforce multi-tenant institution isolation
        user_inst = (current_user.institution_id or "VFSTR").strip().upper()
        doc_inst = (sample_doc.get("institution_id") or "VFSTR").strip().upper()

        if current_user.role != UserRole.PLATFORM_ADMIN:
            if doc_inst != user_inst:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Question set '{clean_set_id}' belongs to another institution ({doc_inst}).",
                )
            if current_user.role in [UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY] and current_user.department:
                doc_dept = sample_doc.get("department")
                if doc_dept and doc_dept != current_user.department:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access denied: Question set belongs to another department ({doc_dept}).",
                    )

        return {
            "valid": True,
            "source_type": "institution",
            "set_id": clean_set_id,
            "institution_id": doc_inst,
            "department": sample_doc.get("department"),
            "role": sample_doc.get("role"),
            "sample_doc": sample_doc,
        }

    @staticmethod
    async def list_question_sets(
        db: AsyncIOMotorDatabase,
        current_user: UserInDB,
    ) -> QuestionSetListResponse:
        """
        Discovers and lists all question sets accessible to the current reviewer:
        - 5 standard platform role-based question sets.
        - Verified institution-uploaded batches matching the user's institution scope.
        """
        user_inst = (current_user.institution_id or "VFSTR").strip().upper()

        # 1. Platform Question Sets
        platform_items = [
            QuestionSetSummary(
                set_id="platform-role-associate-software-engineer",
                title="Platform: Associate Software Engineer Pool",
                source_type="platform",
                institution_id="VFSTR",
                role="Associate Software Engineer",
                question_count=375,
                topics=["Technical Assessment", "Coding", "Problem Solving", "Core CS"],
                difficulties=["medium", "easy", "hard"],
                source_filename="Associate_Software_Engineer_Additional_25_Sets.pdf",
            ),
            QuestionSetSummary(
                set_id="platform-role-software-development-engineer",
                title="Platform: Software Development Engineer Pool",
                source_type="platform",
                institution_id="VFSTR",
                role="Software Development Engineer",
                question_count=375,
                topics=["Data Structures", "Algorithms", "System Design", "Concurrency"],
                difficulties=["medium", "hard", "easy"],
                source_filename="Software_Development_Engineer_Additional_25_Sets.pdf",
            ),
            QuestionSetSummary(
                set_id="platform-role-product-engineer",
                title="Platform: Product Engineer Pool",
                source_type="platform",
                institution_id="VFSTR",
                role="Product Engineer",
                question_count=375,
                topics=["Architecture", "Databases", "APIs", "Performance"],
                difficulties=["medium", "easy", "hard"],
                source_filename="Product_Engineer_Additional_25_Sets.pdf",
            ),
            QuestionSetSummary(
                set_id="platform-role-system-engineer",
                title="Platform: System Engineer Pool",
                source_type="platform",
                institution_id="VFSTR",
                role="System Engineer",
                question_count=375,
                topics=["Operating Systems", "Networking", "Linux", "Troubleshooting"],
                difficulties=["medium", "easy", "hard"],
                source_filename="System_Engineer_Additional_25_Sets.pdf",
            ),
            QuestionSetSummary(
                set_id="platform-role-testing-engineer",
                title="Platform: Testing Engineer Pool",
                source_type="platform",
                institution_id="VFSTR",
                role="Testing Engineer",
                question_count=375,
                topics=["QA Automation", "Test Coverage", "Integration", "Security"],
                difficulties=["medium", "easy", "hard"],
                source_filename="Testing_Engineer_Additional_25_Sets.pdf",
            ),
        ]

        # 2. Query institution-scoped batches
        coll = db[QUESTIONS_COLLECTION]
        match_filter: Dict[str, Any] = {
            "import_batch_id": {"$exists": True, "$ne": None},
        }
        if current_user.role != UserRole.PLATFORM_ADMIN:
            match_filter["$or"] = [
                {"institution_id": user_inst},
                {"institution_id": None},
                {"institution_id": {"$exists": False}},
            ]
            if current_user.role == UserRole.DEPARTMENT_ADMIN and current_user.department:
                match_filter["$and"] = [
                    {"$or": match_filter.pop("$or")},
                    {"$or": [{"department": current_user.department}, {"department": None}, {"department": {"$exists": False}}]},
                ]

        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": "$import_batch_id",
                    "question_count": {"$sum": 1},
                    "role": {"$first": "$role"},
                    "topics": {"$addToSet": "$topic"},
                    "difficulties": {"$addToSet": "$difficulty"},
                    "source_filename": {"$first": "$source_filename"},
                    "institution_id": {"$first": "$institution_id"},
                    "department": {"$first": "$department"},
                    "created_at": {"$first": "$created_at"},
                    "created_by_email": {"$first": "$created_by_email"},
                }
            },
            {"$sort": {"created_at": -1}},
        ]

        cursor = coll.aggregate(pipeline)
        if hasattr(cursor, "to_list"):
            batch_docs = await cursor.to_list(length=100)
        elif hasattr(cursor, "__await__"):
            batch_docs = await cursor
        else:
            batch_docs = list(cursor)

        institution_items = []
        for b in batch_docs:
            batch_id = b["_id"]
            if not batch_id or str(batch_id).startswith("batch-role-qbank"):
                continue  # Skip initial platform import batch ID

            title = b.get("role") or b.get("source_filename") or f"Custom Batch ({batch_id[:16]})"
            raw_topics = [t for t in (b.get("topics") or []) if t]
            raw_diffs = [d for d in (b.get("difficulties") or []) if d]

            institution_items.append(
                QuestionSetSummary(
                    set_id=str(batch_id),
                    title=f"{title} (Institution Batch)",
                    source_type="institution",
                    institution_id=b.get("institution_id") or user_inst,
                    department=b.get("department"),
                    role=b.get("role"),
                    question_count=b.get("question_count", 0),
                    topics=raw_topics[:8],
                    difficulties=raw_diffs,
                    source_filename=b.get("source_filename"),
                    created_at=b.get("created_at"),
                    created_by_email=b.get("created_by_email"),
                )
            )

        all_items = institution_items + platform_items
        return QuestionSetListResponse(total=len(all_items), items=all_items)

    @staticmethod
    async def preview_question_set(
        db: AsyncIOMotorDatabase,
        set_id: str,
        current_user: UserInDB,
        limit: int = 50,
    ) -> QuestionSetPreviewResponse:
        """
        Retrieves a detailed preview of questions belonging to a selected question set.
        """
        access = await QuestionBankService.validate_question_set_access(db, set_id, current_user)
        coll = db[QUESTIONS_COLLECTION]

        if access["source_type"] == "platform":
            role_name = access["role"]
            cursor = coll.find({"role": role_name}, {"_id": 0}).limit(limit)
            if hasattr(cursor, "to_list"):
                docs = await cursor.to_list(length=limit)
            elif hasattr(cursor, "__await__"):
                docs = await cursor
            else:
                docs = list(cursor)

            count_res = coll.count_documents({"role": role_name})
            total = await count_res if hasattr(count_res, "__await__") else count_res

            return QuestionSetPreviewResponse(
                set_id=set_id,
                title=f"Platform: {role_name} Pool",
                source_type="platform",
                question_count=total,
                questions=docs,
            )
        else:
            batch_id = access["set_id"]
            cursor = coll.find({"import_batch_id": batch_id}, {"_id": 0}).limit(limit)
            if hasattr(cursor, "to_list"):
                docs = await cursor.to_list(length=limit)
            elif hasattr(cursor, "__await__"):
                docs = await cursor
            else:
                docs = list(cursor)

            count_res = coll.count_documents({"import_batch_id": batch_id})
            total = await count_res if hasattr(count_res, "__await__") else count_res

            title = access.get("role") or access.get("sample_doc", {}).get("source_filename") or f"Custom Batch ({batch_id[:16]})"
            return QuestionSetPreviewResponse(
                set_id=set_id,
                title=f"{title} (Institution Batch)",
                source_type="institution",
                question_count=total,
                questions=docs,
            )
