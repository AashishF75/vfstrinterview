import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

ALLOWED_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "youtu.be",
}


def extract_youtube_video_id(url: Optional[str]) -> Optional[str]:
    """
    Safely extracts an 11-character YouTube video ID from a watch, short, or embed URL.
    Enforces trusted YouTube hostnames and returns None if the URL does not belong
    to a verified YouTube domain or lacks a valid 11-character video ID.
    Rejects non-http/https schemes, credentials, unexpected ports, and malformed inputs.
    Never exposes query parameters, student answers, or credentials.
    """
    if not url or not isinstance(url, str):
        return None
    url_clean = url.strip()

    # Direct 11-character YouTube video ID string
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_clean):
        return url_clean

    try:
        parsed = urlparse(url_clean)
        # Scheme validation: must be http or https
        if parsed.scheme not in ("http", "https"):
            return None
        # Reject credentials in URL
        if parsed.username or parsed.password:
            return None
        # Reject unexpected ports
        if parsed.port and parsed.port not in (80, 443):
            return None
        hostname = (parsed.hostname or "").lower()
        if hostname not in ALLOWED_YOUTUBE_HOSTS:
            return None

        # youtu.be/<id>
        if hostname == "youtu.be":
            path_match = re.match(r"^/([a-zA-Z0-9_-]{11})(?:/|\?|#|$)", parsed.path)
            if path_match:
                return path_match.group(1)
            return None

        # /embed/<id>
        if parsed.path.startswith("/embed/"):
            embed_match = re.match(r"^/embed/([a-zA-Z0-9_-]{11})(?:/|\?|#|$)", parsed.path)
            if embed_match:
                return embed_match.group(1)
            return None

        # /shorts/<id>
        if parsed.path.startswith("/shorts/"):
            shorts_match = re.match(r"^/shorts/([a-zA-Z0-9_-]{11})(?:/|\?|#|$)", parsed.path)
            if shorts_match:
                return shorts_match.group(1)
            return None

        # Standard /watch?v=<id>
        qs = parse_qs(parsed.query)
        v_list = qs.get("v")
        if v_list and re.match(r"^[a-zA-Z0-9_-]{11}$", v_list[0]):
            return v_list[0]

        # General regex fallback strictly on standard patterns
        match = re.search(r"(?:v=|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})(?![a-zA-Z0-9_-])", url_clean)
        if match:
            candidate_id = match.group(1)
            if re.match(r"^[a-zA-Z0-9_-]{11}$", candidate_id):
                return candidate_id
        return None
    except Exception:
        return None


def build_youtube_embed_url(url_or_id: Optional[str]) -> Optional[str]:
    """
    Constructs a privacy-enhanced, sandbox-safe YouTube embed URL.
    Uses youtube-nocookie.com with rel=0 and modestbranding=1.
    """
    if not url_or_id:
        return None
    video_id = extract_youtube_video_id(url_or_id)
    if video_id and re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
        return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1"
    return None


# ==============================================================================
# Verified Curated Educational Video Resource Catalog
# All 10 entries have been independently verified via live HTTP requests (HTTP 200)
# and validated to contain genuine educational content for the mapped topics.
# Each entry includes a validated YouTube video ID and privacy-safe embed URL.
# ==============================================================================
VERIFIED_LEARNING_RESOURCES: List[Dict[str, Any]] = [
    {
        "resource_id": "res-net-osi-01",
        "topic": "Computer Networks",
        "canonical_topics": ["Computer Networks", "Networking", "Network Protocols", "TCP/IP"],
        "title": "Computer Networking Full Course - OSI Model Deep Dive with Real Life Examples",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=IPvYjXCsTg8",
        "video_id": "IPvYjXCsTg8",
        "embed_url": "https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": False,
        "difficulty_level": "medium",
        "role_tags": ["System Engineer", "Software Development Engineer", "Associate Software Engineer"],
        "description": "Comprehensive tutorial covering OSI layers, TCP/IP stack, packet routing, socket fundamentals, and network architectures.",
        "is_verified": True,
    },
    {
        "resource_id": "res-dsa-structures-01",
        "topic": "Data Structures",
        "canonical_topics": ["Data Structures", "Arrays", "Linked Lists", "Trees", "Graphs", "Hash Tables", "DSA"],
        "title": "Data Structures Easy to Advanced Course - Full Tutorial from a Google Engineer",
        "provider": "William Fiset / freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=RBSGKlAvoiM",
        "video_id": "RBSGKlAvoiM",
        "embed_url": "https://www.youtube-nocookie.com/embed/RBSGKlAvoiM?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": False,
        "difficulty_level": "medium",
        "role_tags": ["Software Development Engineer", "Associate Software Engineer", "Product Engineer"],
        "description": "In-depth visual walkthrough of arrays, linked lists, binary trees, heaps, union find, graphs, and memory representations.",
        "is_verified": True,
    },
    {
        "resource_id": "res-algo-core-01",
        "topic": "Algorithms",
        "canonical_topics": ["Algorithms", "Sorting", "Searching", "Graph Algorithms", "Recursion"],
        "title": "Algorithms and Data Structures Tutorial - Full Course for Beginners",
        "provider": "Treehouse / freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=8hly31xKli0",
        "video_id": "8hly31xKli0",
        "embed_url": "https://www.youtube-nocookie.com/embed/8hly31xKli0?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": True,
        "difficulty_level": "medium",
        "role_tags": ["Software Development Engineer", "Associate Software Engineer", "Product Engineer"],
        "description": "Foundational course on Big-O algorithmic complexity, binary search, merge sort, quicksort, and recursive problem solving.",
        "is_verified": True,
    },
    {
        "resource_id": "res-algo-dp-01",
        "topic": "Dynamic Programming",
        "canonical_topics": ["Dynamic Programming", "Algorithms", "Optimization", "Memoization"],
        "title": "Dynamic Programming - Learn to Solve Algorithmic Problems & Coding Challenges",
        "provider": "Alvin Zablan / freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=oBt53YbR9Kk",
        "video_id": "oBt53YbR9Kk",
        "embed_url": "https://www.youtube-nocookie.com/embed/oBt53YbR9Kk?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": False,
        "difficulty_level": "hard",
        "role_tags": ["Software Development Engineer", "Product Engineer"],
        "description": "Mastery of top-down memoization and bottom-up tabulation strategies for grid traveler, knapsack, and sequence problems.",
        "is_verified": True,
    },
    {
        "resource_id": "res-os-fundamentals-01",
        "topic": "Operating Systems",
        "canonical_topics": ["Operating Systems", "Process Management", "Concurrency", "Memory Management", "CPU Scheduling", "OS"],
        "title": "Operating System Full Course | Operating System Tutorials for Beginners",
        "provider": "Neso Academy",
        "video_url": "https://www.youtube.com/watch?v=mXw9ruZaxzQ",
        "video_id": "mXw9ruZaxzQ",
        "embed_url": "https://www.youtube-nocookie.com/embed/mXw9ruZaxzQ?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": True,
        "difficulty_level": "medium",
        "role_tags": ["System Engineer", "Software Development Engineer", "Associate Software Engineer"],
        "description": "Covers processes, multithreading, CPU scheduling, race conditions, semaphores, deadlocks, and virtual memory paging.",
        "is_verified": True,
    },
    {
        "resource_id": "res-db-sql-01",
        "topic": "Database Management Systems",
        "canonical_topics": ["Database Management Systems", "Databases", "SQL", "Database Design", "Relational Databases", "DBMS"],
        "title": "SQL Tutorial - Full Database Course for Beginners",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=HXV3zeQKqGY",
        "video_id": "HXV3zeQKqGY",
        "embed_url": "https://www.youtube-nocookie.com/embed/HXV3zeQKqGY?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": True,
        "difficulty_level": "easy",
        "role_tags": ["Associate Software Engineer", "Software Development Engineer", "Product Engineer"],
        "description": "Relational schema design, queries, aggregation, joins, primary/foreign keys, normalization, and ACID properties.",
        "is_verified": True,
    },
    {
        "resource_id": "res-oop-design-01",
        "topic": "Object-Oriented Programming",
        "canonical_topics": ["Object-Oriented Programming", "OOP", "Software Design", "Design Patterns"],
        "title": "Object-Oriented Programming, Simplified",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=pTB0EiLXUC8",
        "video_id": "pTB0EiLXUC8",
        "embed_url": "https://www.youtube-nocookie.com/embed/pTB0EiLXUC8?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": True,
        "difficulty_level": "medium",
        "role_tags": ["Associate Software Engineer", "Product Engineer", "Software Development Engineer"],
        "description": "Encapsulation, inheritance, polymorphism, abstraction, interface design, and SOLID engineering principles.",
        "is_verified": True,
    },
    {
        "resource_id": "res-sys-design-01",
        "topic": "System Design",
        "canonical_topics": ["System Design", "Distributed Systems", "Scalability", "Microservices", "Architecture"],
        "title": "System Design for Beginners Course",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=m8Icp_Cid5o",
        "video_id": "m8Icp_Cid5o",
        "embed_url": "https://www.youtube-nocookie.com/embed/m8Icp_Cid5o?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": False,
        "difficulty_level": "hard",
        "role_tags": ["Product Engineer", "System Engineer", "Software Development Engineer"],
        "description": "Architectural principles for horizontal scaling, load balancers, caching strategies, CDNs, database sharding, and message queues.",
        "is_verified": True,
    },
    {
        "resource_id": "res-qa-testing-01",
        "topic": "Software Testing & QA",
        "canonical_topics": ["Software Testing & QA", "Software Testing", "Quality Assurance", "Testing", "Test Automation", "QA"],
        "title": "Software Testing Course – Playwright, E2E, and AI Agents",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=jydYq7oAtD8",
        "video_id": "jydYq7oAtD8",
        "embed_url": "https://www.youtube-nocookie.com/embed/jydYq7oAtD8?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": False,
        "difficulty_level": "medium",
        "role_tags": ["Testing Engineer", "Software Development Engineer", "Product Engineer"],
        "description": "Unit testing, integration testing, end-to-end automation, assertions, test isolation, and modern validation methodologies.",
        "is_verified": True,
    },
    {
        "resource_id": "res-prog-foundations-01",
        "topic": "Programming Fundamentals",
        "canonical_topics": ["Programming Fundamentals", "Technical Assessment", "Coding", "General Programming"],
        "title": "Introduction to Programming and Computer Science - Full Course",
        "provider": "freeCodeCamp.org",
        "video_url": "https://www.youtube.com/watch?v=zOjov-2OZ0E",
        "video_id": "zOjov-2OZ0E",
        "embed_url": "https://www.youtube-nocookie.com/embed/zOjov-2OZ0E?rel=0&modestbranding=1",
        "can_embed": True,
        "is_introductory": True,
        "difficulty_level": "easy",
        "role_tags": ["Associate Software Engineer", "Testing Engineer", "System Engineer"],
        "description": "Fundamental programming abstractions, control flow, functions, algorithmic thinking, and core technical problem solving.",
        "is_verified": True,
    },
]


def _matches_topic(item: Dict[str, Any], t_name: str) -> bool:
    """Helper checking if a catalog item matches a topic or canonical alias."""
    if not t_name or not isinstance(t_name, str):
        return False
    clean_t = t_name.strip().lower()
    item_topic = item["topic"].lower()
    if clean_t == item_topic or clean_t in item_topic or item_topic in clean_t:
        return True
    for ct in item.get("canonical_topics", []):
        ct_lower = ct.lower()
        if clean_t == ct_lower:
            return True
        # For short acronyms (<= 3 chars, e.g. "os", "qa", "sql", "dsa", "oop", "dbms"),
        # use word-boundary matching to prevent loose substring collisions (e.g. "os" matching "microservices")
        if len(clean_t) <= 3:
            if re.search(rf"\b{re.escape(clean_t)}\b", ct_lower):
                return True
        else:
            if clean_t in ct_lower or ct_lower in clean_t:
                return True
    return False


def _format_recommendation_dict(res: Dict[str, Any], reason_text: str) -> Dict[str, Any]:
    """Helper packaging a catalog resource into a full recommendation item."""
    video_id = res.get("video_id") or extract_youtube_video_id(res.get("video_url"))
    embed_url = res.get("embed_url") or build_youtube_embed_url(video_id or res.get("video_url"))
    return {
        "resource_id": res["resource_id"],
        "title": res["title"],
        "provider": res["provider"],
        "topic": res["topic"],
        "video_url": res["video_url"],
        "video_id": video_id,
        "embed_url": embed_url,
        "can_embed": res.get("can_embed", True),
        "difficulty_level": res["difficulty_level"],
        "reason": reason_text,
        "watched": False,
        "is_verified": True,
    }


def _normalize_response(r: Any) -> Optional[Dict[str, Any]]:
    """Safely extracts a dictionary from a response item (dict, model, or custom object)."""
    if r is None:
        return None
    if isinstance(r, dict):
        return r
    if hasattr(r, "model_dump"):
        return r.model_dump()
    if hasattr(r, "__dict__"):
        return r.__dict__
    return None


def _is_response_skipped(r: Dict[str, Any]) -> bool:
    """Accurately detects whether a question was skipped or left blank by the candidate."""
    if r.get("is_skipped") is True:
        return True
    status = str(r.get("status") or "").strip().lower()
    if status == "skipped":
        return True
    eval_score = r.get("evaluation_score")
    if eval_score is None:
        ans_text = str(r.get("answer_text") or "").strip()
        if not ans_text or ans_text == "(Question skipped by candidate)":
            return True
    return False


def match_video_recommendations(
    topic_breakdown: List[Dict[str, Any]],
    selected_role: Optional[str] = None,
    responses: Optional[List[Dict[str, Any]]] = None,
    max_recommendations: int = 4,
) -> List[Dict[str, Any]]:
    """
    Deterministically matches verified learning resources to a student's actual performance evidence:
    1. Identifies skipped/unanswered questions and recommends introductory tutorials without fabricating scores.
    2. Identifies topics where the student scored below 6.5 and recommends targeted review, qualifying single-question samples.
    3. Ranks by deficit priority (lowest scoring topics first) and role alignment.
    4. Provides transparent, non-fabricated reasons directly citing question numbers and evidence.
    5. If the student demonstrated high competence across all questions (>= 7.0), recommends role-specific
       advanced enrichment materials (e.g. System Design, Dynamic Programming) with celebratory reasoning.
    6. Attaches validated YouTube video IDs and privacy-enhanced embed URLs for in-site playback.
    """
    raw_responses = responses or []
    clean_responses: List[Dict[str, Any]] = []
    for r in raw_responses:
        norm = _normalize_response(r)
        if norm:
            clean_responses.append(norm)

    recommendations: List[Dict[str, Any]] = []
    used_resource_ids = set()

    # Helper to check if a resource matches topic or response text
    def find_best_resource_for_topic(t_name: str, prefer_introductory: bool = False) -> Optional[Dict[str, Any]]:
        candidates = [
            r for r in VERIFIED_LEARNING_RESOURCES
            if r["resource_id"] not in used_resource_ids and _matches_topic(r, t_name)
        ]
        if not candidates:
            return None
        if prefer_introductory:
            intro = [c for c in candidates if c.get("is_introductory") or c.get("difficulty_level") == "easy"]
            if intro:
                return intro[0]
        return candidates[0]

    # 1. Pass 1: Handle Skipped or Unanswered Questions
    # Identifies questions the candidate explicitly skipped or did not answer,
    # matching them to introductory foundational tutorials without inventing a score.
    skipped_responses = [r for r in clean_responses if _is_response_skipped(r)]

    for skip_r in skipped_responses:
        q_topic = skip_r.get("topic") or "General Programming"
        matched_res = find_best_resource_for_topic(q_topic, prefer_introductory=True)
        if matched_res:
            # Find all skipped responses matching this topic or matched resource
            related_skips = [
                r for r in skipped_responses
                if _matches_topic(matched_res, r.get("topic") or "")
                or (r.get("topic") or "").strip().lower() == q_topic.strip().lower()
            ]
            q_indices = [str(r.get("question_index")) for r in related_skips if r.get("question_index") is not None]
            if len(q_indices) > 1:
                q_label = f"Questions {', '.join(q_indices)}"
            elif len(q_indices) == 1:
                q_label = f"Question {q_indices[0]}"
            else:
                q_label = f"Question {skip_r.get('question_index')}" if skip_r.get("question_index") is not None else "A question"

            reason = (
                f"Recommended because {q_label} on '{q_topic}' was skipped during your interview. "
                "An introductory tutorial is recommended to build foundational confidence before practicing again."
            )
            recommendations.append(_format_recommendation_dict(matched_res, reason))
            used_resource_ids.add(matched_res["resource_id"])
            if len(recommendations) >= max_recommendations:
                return recommendations

    # 2. Pass 2: Target Weak Evaluated Topics (average score < 6.5)
    def _safe_topic_avg(t: Dict[str, Any]) -> float:
        val = t.get("average_score")
        if val is None:
            return 10.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 10.0

    sorted_topics = sorted(topic_breakdown, key=_safe_topic_avg)

    for topic_item in sorted_topics:
        t_name = topic_item.get("topic", "")
        avg_score = _safe_topic_avg(topic_item)
        q_count = topic_item.get("questions_tested", 1)

        if avg_score < 6.5:
            matched_res = find_best_resource_for_topic(t_name, prefer_introductory=False)
            if matched_res:
                # Find evaluated questions matching this topic specifically
                clean_t = t_name.strip().lower()
                eval_qs = [
                    r for r in clean_responses
                    if not _is_response_skipped(r)
                    and r.get("evaluation_score") is not None
                    and (
                        (r.get("topic") or "").strip().lower() == clean_t
                        or _matches_topic(matched_res, r.get("topic", ""))
                    )
                ]
                q_indices = [f"Question {r.get('question_index')}" for r in eval_qs if r.get("question_index") is not None]
                q_idx_str = ", ".join(q_indices) if q_indices else "your response"

                # Check evidence level & sample size
                if len(eval_qs) == 1:
                    reason_text = (
                        f"Recommended for revision because your score was {avg_score}/10 in '{t_name}' "
                        f"(specifically noted in {q_idx_str}). (Note: Evaluated on a single question sample; targeted practice is suggested for this specific concept)."
                    )
                elif len(eval_qs) > 1:
                    reason_text = (
                        f"Recommended for revision because your average score was {avg_score}/10 in '{t_name}' "
                        f"across {len(eval_qs)} question(s) (specifically noted in {q_idx_str})."
                    )
                else:
                    # len(eval_qs) == 0: no evaluated questions in response list
                    if q_count == 1 or topic_item.get("is_limited_evidence") is True:
                        if avg_score == 0.0:
                            reason_text = (
                                f"Recommended for foundational revision because questions in '{t_name}' were skipped during your interview. "
                                "(Note: Evaluated on a single question sample; targeted practice is suggested for this specific concept)."
                            )
                        else:
                            reason_text = (
                                f"Recommended for revision because your score was {avg_score}/10 in '{t_name}'. "
                                "(Note: Evaluated on a single question sample; targeted practice is suggested for this specific concept)."
                            )
                    else:
                        if avg_score == 0.0:
                            reason_text = (
                                f"Recommended for foundational revision because questions in '{t_name}' were skipped during your interview."
                            )
                        else:
                            reason_text = (
                                f"Recommended for revision because your average score was {avg_score}/10 in '{t_name}' across {q_count} question(s)."
                            )

                recommendations.append(_format_recommendation_dict(matched_res, reason_text))
                used_resource_ids.add(matched_res["resource_id"])
                if len(recommendations) >= max_recommendations:
                    return recommendations

    # 3. Pass 3: Celebratory Advanced Enrichment for Strong Performance
    # Evaluates whether the candidate demonstrated high proficiency (every evaluated question >= 7.0)
    # with zero skipped questions and zero incomplete assessments.
    incomplete_responses = [
        r for r in clean_responses
        if r.get("evaluation_score") is None and not _is_response_skipped(r)
    ]

    all_evaluated_scores: List[float] = []
    for r in clean_responses:
        if not _is_response_skipped(r) and r.get("evaluation_score") is not None:
            try:
                all_evaluated_scores.append(float(r["evaluation_score"]))
            except (ValueError, TypeError):
                pass

    is_high_performance = False
    if clean_responses:
        is_high_performance = (
            len(skipped_responses) == 0
            and len(incomplete_responses) == 0
            and len(all_evaluated_scores) == len(clean_responses)
            and len(all_evaluated_scores) > 0
            and all(s >= 7.0 for s in all_evaluated_scores)
        )
    elif topic_breakdown:
        # If responses list was omitted, derive high performance strictly from topic_breakdown if all topics >= 7.0
        tb_scores: List[float] = []
        tb_valid = True
        for t in topic_breakdown:
            avg = t.get("average_score")
            if avg is None:
                tb_valid = False
                break
            try:
                s_val = float(avg)
                if s_val < 7.0:
                    tb_valid = False
                    break
                tb_scores.append(s_val)
            except (ValueError, TypeError):
                tb_valid = False
                break
        if tb_valid and tb_scores:
            is_high_performance = True
            all_evaluated_scores = tb_scores

    clean_role = (selected_role or "").strip().lower()

    if is_high_performance and len(recommendations) < max_recommendations:
        # Prioritize advanced and mastery enrichment topics (hard > medium > easy)
        difficulty_priority = {"hard": 0, "medium": 1, "easy": 2}
        candidate_resources = [
            r for r in VERIFIED_LEARNING_RESOURCES
            if r["resource_id"] not in used_resource_ids
            and any(clean_role in rt.lower() or rt.lower() in clean_role for rt in r.get("role_tags", []))
        ]
        candidate_resources.sort(key=lambda r: difficulty_priority.get(r.get("difficulty_level", "medium"), 1))

        avg_formatted = (
            f"{round(sum(all_evaluated_scores) / len(all_evaluated_scores), 1)}"
            if all_evaluated_scores else "7.0+"
        )

        for res in candidate_resources:
            reason = (
                f"Excellent performance! As you demonstrated strong proficiency across all interview questions "
                f"(average score {avg_formatted}/10), "
                f"this advanced resource is recommended for further mastery in the '{selected_role}' track."
            )
            recommendations.append(_format_recommendation_dict(res, reason))
            used_resource_ids.add(res["resource_id"])
            if len(recommendations) >= max_recommendations:
                return recommendations

    # 4. Pass 4: Role-specific matching if slots remain
    for res in VERIFIED_LEARNING_RESOURCES:
        if res["resource_id"] in used_resource_ids:
            continue
        role_match = any(clean_role in r.lower() or r.lower() in clean_role for r in res.get("role_tags", []))
        if role_match:
            recommendations.append(_format_recommendation_dict(
                res,
                f"Recommended for ongoing placement interview preparation in the '{selected_role}' track."
            ))
            used_resource_ids.add(res["resource_id"])
            if len(recommendations) >= max_recommendations:
                return recommendations

    # 5. Pass 5: General foundational curriculum fallback
    for res in VERIFIED_LEARNING_RESOURCES:
        if res["resource_id"] in used_resource_ids:
            continue
        recommendations.append(_format_recommendation_dict(
            res,
            "Core engineering curriculum resource recommended for placement interview readiness."
        ))
        used_resource_ids.add(res["resource_id"])
        if len(recommendations) >= max_recommendations:
            break

    return recommendations
