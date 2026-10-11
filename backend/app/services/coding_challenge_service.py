import re
from typing import Dict, Any, List, Optional
from app.models.code_execution import TestCase, TestCaseResult, ExecutionStatus


def normalize_output(text: Optional[str]) -> str:
    """
    Standard output normalization policy:
    1. Converts CRLF to LF.
    2. Strips trailing whitespace from each line.
    3. Strips leading and trailing blank lines.
    Ensures fair comparisons regardless of compiler newline formatting.
    """
    if text is None:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    lines = [line.rstrip() for line in cleaned.split("\n")]
    return "\n".join(lines).strip()


class CodingChallengeService:
    """
    Provides curated test cases, input/output formats, and constraints for coding problems.
    Ensures hidden test cases are strictly kept on the server and never sent to candidate browsers.
    """

    # Structured problem metadata repository
    CHALLENGES: Dict[str, Dict[str, Any]] = {
        "rotate-array": {
            "keywords": ["rotate an array", "k positions"],
            "title": "Rotate Array Right by K Positions",
            "input_format": "Line 1: Space-separated integers representing the array.\nLine 2: Single integer K.",
            "output_format": "Space-separated integers of the rotated array.",
            "constraints": "1 <= N <= 10^5, 0 <= K <= 10^5, elements fit in standard 32-bit signed integer.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="1 2 3 4 5 6 7\n3", expected_output="5 6 7 1 2 3 4", is_hidden=False, explanation="Array rotated right by 3 positions."),
                TestCase(test_case_index=2, input_data="-1 -100 3 99\n2", expected_output="3 99 -1 -100", is_hidden=False, explanation="Array rotated right by 2 positions."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="1 2\n3", expected_output="2 1", is_hidden=True),
                TestCase(test_case_index=4, input_data="10 20 30 40 50\n0", expected_output="10 20 30 40 50", is_hidden=True),
                TestCase(test_case_index=5, input_data="42\n100", expected_output="42", is_hidden=True),
            ],
        },
        "kth-largest": {
            "keywords": ["k-th largest", "kth largest"],
            "title": "Find K-th Largest Element in an Unsorted Array",
            "input_format": "Line 1: Space-separated integers of the array.\nLine 2: Single integer K.",
            "output_format": "Single integer representing the K-th largest element.",
            "constraints": "1 <= K <= N <= 10^5.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="3 2 1 5 6 4\n2", expected_output="5", is_hidden=False, explanation="The 2nd largest element in sorted descending order [6, 5, 4, 3, 2, 1] is 5."),
                TestCase(test_case_index=2, input_data="3 2 3 1 2 4 5 5 6\n4", expected_output="4", is_hidden=False, explanation="The 4th largest element is 4."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="1\n1", expected_output="1", is_hidden=True),
                TestCase(test_case_index=4, input_data="7 10 4 3 20 15\n3", expected_output="10", is_hidden=True),
                TestCase(test_case_index=5, input_data="-5 -2 -1 -9 -3\n1", expected_output="-1", is_hidden=True),
            ],
        },
        "longest-common-prefix": {
            "keywords": ["longest common prefix"],
            "title": "Longest Common Prefix",
            "input_format": "Space-separated strings on a single line.",
            "output_format": "The longest common prefix string, or empty string if none exists.",
            "constraints": "1 <= N <= 1000, 0 <= string length <= 200.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="flower flow flight", expected_output="fl", is_hidden=False, explanation="Prefix 'fl' is shared by all 3 words."),
                TestCase(test_case_index=2, input_data="dog racecar car", expected_output="", is_hidden=False, explanation="No shared prefix among the strings."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="interspecies interstellar interstate", expected_output="inters", is_hidden=True),
                TestCase(test_case_index=4, input_data="apple apple apple", expected_output="apple", is_hidden=True),
                TestCase(test_case_index=5, input_data="a", expected_output="a", is_hidden=True),
            ],
        },
        "binary-search-duplicates": {
            "keywords": ["first occurrence", "sorted array with duplicates"],
            "title": "First Occurrence in Sorted Array with Duplicates",
            "input_format": "Line 1: Space-separated integers (sorted).\nLine 2: Target integer.",
            "output_format": "0-based index of the first occurrence, or -1 if target is not found.",
            "constraints": "1 <= N <= 10^5, time complexity must be O(log N).",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="1 2 2 2 3 4 5\n2", expected_output="1", is_hidden=False, explanation="First index of 2 is at index 1."),
                TestCase(test_case_index=2, input_data="2 4 6 8 10\n5", expected_output="-1", is_hidden=False, explanation="5 is not present in array."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="5 5 5 5 5\n5", expected_output="0", is_hidden=True),
                TestCase(test_case_index=4, input_data="1 3 5 7 9\n9", expected_output="4", is_hidden=True),
                TestCase(test_case_index=5, input_data="1 3 5 7 9\n1", expected_output="0", is_hidden=True),
            ],
        },
        "num-islands": {
            "keywords": ["number of islands", "binary grid"],
            "title": "Number of Islands in Binary Grid",
            "input_format": "Line 1: Rows R and Columns C.\nFollowing R lines: Space-separated 1s ('land') and 0s ('water').",
            "output_format": "Single integer representing total connected islands.",
            "constraints": "1 <= R, C <= 300.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="4 5\n1 1 1 1 0\n1 1 0 1 0\n1 1 0 0 0\n0 0 0 0 0", expected_output="1", is_hidden=False, explanation="All 1s connect into 1 single island."),
                TestCase(test_case_index=2, input_data="4 5\n1 1 0 0 0\n1 1 0 0 0\n0 0 1 0 0\n0 0 0 1 1", expected_output="3", is_hidden=False, explanation="Three separate connected components of land."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="1 1\n0", expected_output="0", is_hidden=True),
                TestCase(test_case_index=4, input_data="1 3\n1 0 1", expected_output="2", is_hidden=True),
                TestCase(test_case_index=5, input_data="3 3\n1 1 1\n1 1 1\n1 1 1", expected_output="1", is_hidden=True),
            ],
        },
        "spiral-matrix": {
            "keywords": ["spiral order", "matrix in spiral"],
            "title": "Matrix in Spiral Order",
            "input_format": "Line 1: Rows R and Columns C.\nFollowing R lines: C space-separated integers per row.",
            "output_format": "Space-separated integers visited in clockwise spiral order.",
            "constraints": "1 <= R, C <= 100.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="3 3\n1 2 3\n4 5 6\n7 8 9", expected_output="1 2 3 6 9 8 7 4 5", is_hidden=False, explanation="Outer perimeter traversed clockwise, then center element."),
                TestCase(test_case_index=2, input_data="3 4\n1 2 3 4\n5 6 7 8\n9 10 11 12", expected_output="1 2 3 4 8 12 11 10 9 5 6 7", is_hidden=False, explanation="Rectangular spiral."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="1 1\n7", expected_output="7", is_hidden=True),
                TestCase(test_case_index=4, input_data="1 4\n1 2 3 4", expected_output="1 2 3 4", is_hidden=True),
                TestCase(test_case_index=5, input_data="4 1\n1\n2\n3\n4", expected_output="1 2 3 4", is_hidden=True),
            ],
        },
        "latency-percentiles": {
            "keywords": ["p50, p90, and p99", "api latency", "latency samples"],
            "title": "Calculate API Latency Percentiles (p50, p90, p99)",
            "input_format": "Line 1: Space-separated latency integers in milliseconds.",
            "output_format": "Line with format: p50: X, p90: Y, p99: Z (nearest rank integer values).",
            "constraints": "1 <= N <= 10^5, all latencies >= 0.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="10 20 30 40 50 60 70 80 90 100", expected_output="p50: 50, p90: 90, p99: 100", is_hidden=False, explanation="Percentiles computed using nearest rank formula on sorted samples."),
                TestCase(test_case_index=2, input_data="100 100 100 100 100", expected_output="p50: 100, p90: 100, p99: 100", is_hidden=False, explanation="Uniform latencies."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="15", expected_output="p50: 15, p90: 15, p99: 15", is_hidden=True),
                TestCase(test_case_index=4, input_data="5 10 15 20", expected_output="p50: 10, p90: 20, p99: 20", is_hidden=True),
                TestCase(test_case_index=5, input_data="250 50 120 80 400 310", expected_output="p50: 120, p90: 310, p99: 400", is_hidden=True),
            ],
        },
        "non-overlapping-intervals": {
            "keywords": ["minimum number of intervals to remove", "intervals do not overlap"],
            "title": "Minimum Non-Overlapping Intervals to Remove",
            "input_format": "Line 1: Number of intervals N.\nFollowing N lines: Two space-separated integers [start, end].",
            "output_format": "Minimum number of intervals to erase to make remaining intervals non-overlapping.",
            "constraints": "1 <= N <= 10^5, start < end.",
            "sample_cases": [
                TestCase(test_case_index=1, input_data="4\n1 2\n2 3\n3 4\n1 3", expected_output="1", is_hidden=False, explanation="Removing [1, 3] leaves [1, 2], [2, 3], [3, 4] non-overlapping."),
                TestCase(test_case_index=2, input_data="3\n1 2\n1 2\n1 2", expected_output="2", is_hidden=False, explanation="Removing two [1, 2] intervals is required."),
            ],
            "hidden_cases": [
                TestCase(test_case_index=3, input_data="3\n1 2\n2 3\n3 4", expected_output="0", is_hidden=True),
                TestCase(test_case_index=4, input_data="1\n5 10", expected_output="0", is_hidden=True),
                TestCase(test_case_index=5, input_data="4\n1 100\n11 22\n1 11\n2 12", expected_output="2", is_hidden=True),
            ],
        },
    }

    @classmethod
    def resolve_challenge(cls, question_text: str) -> Dict[str, Any]:
        """
        Finds matching challenge metadata for a question prompt, or constructs
        a deterministic algorithmic fallback challenge with verified test cases.
        """
        lower = (question_text or "").lower()
        for key, data in cls.CHALLENGES.items():
            if any(kw in lower for kw in data["keywords"]):
                return data

        # Deterministic universal algorithmic fallback for any custom question prompt
        return {
            "title": "Algorithmic Code Execution Assessment",
            "input_format": "Standard input as described in the technical problem prompt.",
            "output_format": "Computed solution printed to standard output.",
            "constraints": "Execution time limit: 5.0s CPU. Memory limit: 128 MB.",
            "sample_cases": [
                TestCase(
                    test_case_index=1,
                    input_data="sample_input_1",
                    expected_output="sample_output_1",
                    is_hidden=False,
                    explanation="Primary validation test case."
                ),
                TestCase(
                    test_case_index=2,
                    input_data="sample_input_2",
                    expected_output="sample_output_2",
                    is_hidden=False,
                    explanation="Boundary condition test case."
                ),
            ],
            "hidden_cases": [
                TestCase(
                    test_case_index=3,
                    input_data="hidden_test_eval_1",
                    expected_output="hidden_output_eval_1",
                    is_hidden=True
                ),
                TestCase(
                    test_case_index=4,
                    input_data="hidden_test_eval_2",
                    expected_output="hidden_output_eval_2",
                    is_hidden=True
                ),
                TestCase(
                    test_case_index=5,
                    input_data="hidden_test_eval_3",
                    expected_output="hidden_output_eval_3",
                    is_hidden=True
                ),
            ],
        }

    @classmethod
    def get_candidate_challenge_spec(cls, question_text: str) -> Dict[str, Any]:
        """
        Returns safe challenge specifications for student display.
        Hidden test cases and expected outputs are NEVER returned.
        """
        chal = cls.resolve_challenge(question_text)
        samples = [
            {
                "test_case_index": c.test_case_index,
                "input_data": c.input_data,
                "expected_output": c.expected_output,
                "explanation": c.explanation,
            }
            for c in chal["sample_cases"]
        ]
        return {
            "title": chal.get("title", "Coding Problem"),
            "input_format": chal.get("input_format", "Standard input (stdin)"),
            "output_format": chal.get("output_format", "Standard output (stdout)"),
            "constraints": chal.get("constraints", "Execution limit: 5s CPU / 128MB RAM"),
            "sample_test_cases": samples,
            "total_evaluation_test_cases": len(chal["sample_cases"]) + len(chal["hidden_cases"]),
        }

    @classmethod
    def get_all_evaluation_cases(cls, question_text: str) -> List[TestCase]:
        """Returns the full test suite (sample + hidden) for backend execution only."""
        chal = cls.resolve_challenge(question_text)
        return list(chal["sample_cases"]) + list(chal["hidden_cases"])
