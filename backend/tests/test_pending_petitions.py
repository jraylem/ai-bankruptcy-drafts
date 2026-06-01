from src.chatbot.pending_petitions import PendingPetitionResolutionService


class FakeRow:
    def __init__(self, **mapping):
        self._mapping = mapping


def test_select_auto_target_candidate_allows_unique_exact_name_match():
    candidates = [
        {
            "session_id": "case-1",
            "confidence": "exact_name",
            "score": 100,
            "is_strong_match": False,
        },
        {
            "session_id": "case-2",
            "confidence": "partial_name",
            "score": 70,
            "is_strong_match": False,
        },
    ]

    selected = PendingPetitionResolutionService._select_auto_target_candidate(candidates)

    assert selected is not None
    assert selected["session_id"] == "case-1"


def test_select_auto_target_candidate_rejects_ambiguous_strong_matches():
    candidates = [
        {
            "session_id": "case-1",
            "confidence": "exact_name_ssn",
            "score": 225,
            "is_strong_match": True,
        },
        {
            "session_id": "case-2",
            "confidence": "exact_name_ssn",
            "score": 215,
            "is_strong_match": True,
        },
    ]

    selected = PendingPetitionResolutionService._select_auto_target_candidate(candidates)

    assert selected is None


def test_select_documents_to_replace_keeps_non_petition_docs():
    target_documents = [
        FakeRow(
            id="schedule-doc",
            filename="schedule_a.pdf",
            original_filename="Schedule A.pdf",
            file_path="/tmp/schedule_a.pdf",
        ),
        FakeRow(
            id="petition-doc",
            filename="updated_petition.pdf",
            original_filename="Updated Petition.pdf",
            file_path="/tmp/updated_petition.pdf",
        ),
    ]

    selected = PendingPetitionResolutionService._select_documents_to_replace(target_documents)

    assert [row._mapping["id"] for row in selected] == ["petition-doc"]
