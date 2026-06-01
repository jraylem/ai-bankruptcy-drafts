"""
Structured payload extractors using LangChain's with_structured_output().

Replaces ReAct agent per-field extraction with single LLM calls that
guarantee Pydantic schema validation.
"""

from typing import Type, TypeVar, Optional
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD
from ..chatbot.vectorestore import search_vectorstore
from .schemas import (
    MOTION_SCHEMAS,
    USER_INPUT_FIELDS,
    CertificateOfServicePayload,
    OrderSustainingPayload,
)

T = TypeVar('T', bound=BaseModel)

EXTRACTION_SYSTEM_PROMPT = """You are a legal document extraction assistant specializing in bankruptcy cases.

Extract ALL requested fields from the provided bankruptcy petition and court email data.
Follow these rules strictly:

1. For case numbers: Use format XX-XXXXX-XXX where XXX is the judge's initials (e.g., "25-14980-PDR")
2. For dates: Use format MM/DD/YYYY or write out as "Month Day, Year"
3. For names: Use the full legal name as written in documents
4. For court districts: Extract the full district name (e.g., "Northern District of Florida")
5. For chapters: Extract just the number (7, 11, 12, or 13)

If a field cannot be found in the provided context:
- Return "N/A" for string fields
- Leave optional fields as null

Be precise and extract verbatim text when possible. Do not invent or guess information."""

SERVICE_EXTRACTION_PROMPT = """You are a legal document extraction assistant.

Extract certificate of service fields from the bankruptcy court data.
Find the trustee name, trustee email, US trustee email, and related service information.

If a field cannot be found, return "N/A" for required string fields."""


# Called by: all extractor subclasses (same file) via super().__init__();
#            get_extractor() (same file) as fallback for unmapped motion types
class StructuredPayloadExtractor:
    """
    Extracts motion payloads using LangChain's with_structured_output().

    This replaces the ReAct agent approach where each field required
    2-3 LLM calls. Now we make 1-2 calls total with guaranteed schema.
    """

    def __init__(self, session_id: str, model: str = CLAUDE_MODEL_STANDARD):
        """Initialize extractor with session context.

        Args:
            session_id: Active session identifier; used to target per-session vectorstore collections.
            model: Claude model name to use for extraction.
        """
        self.session_id = session_id
        self.llm = ChatAnthropic(
            model=model,
            temperature=0,
            api_key=settings.ANTHROPIC_API_KEY,
        )

    def _get_petition_context(self) -> str:
        """Get context from bankruptcy petition vectorstore"""
        collection = f"bankruptcy_knowledge_{self.session_id}"
        try:
            docs = search_vectorstore(
                query="debtor name case number court district petition date chapter filing",
                collection_name=collection,
                k=10
            )
            if docs:
                return "\n---\n".join([doc.page_content for doc in docs])
            return "No petition data available."
        except Exception as e:
            print(f"Error getting petition context: {e}")
            return "Error retrieving petition data."

    def _get_gmail_context(self) -> str:
        """Get context from Gmail/court email vectorstore"""
        collection = f"gmail_{self.session_id}"
        try:
            docs = search_vectorstore(
                query="case number chapter judge trustee dismissal date docket entry meeting creditors",
                collection_name=collection,
                k=10
            )
            if docs:
                return "\n---\n".join([doc.page_content for doc in docs])
            return "No court email data available."
        except Exception as e:
            print(f"Error getting gmail context: {e}")
            return "No court email data available."

    def _get_dismissed_context(self) -> str:
        """Get context from dismissed case vectorstore (for Motion Extend)"""
        collection = f"gmail_dismissed_{self.session_id}"
        try:
            docs = search_vectorstore(
                query="case number judge initial docket entry dismissal order",
                collection_name=collection,
                k=5
            )
            if docs:
                return "\n---\n".join([doc.page_content for doc in docs])
            return "No dismissed case data available."
        except Exception as e:
            return "No dismissed case data available."

    def _get_combined_context(self, include_dismissed: bool = False) -> str:
        """Combine all context sources into a single string"""
        petition_ctx = self._get_petition_context()
        gmail_ctx = self._get_gmail_context()

        context = f"""=== BANKRUPTCY PETITION DATA ===
{petition_ctx}

=== COURT EMAIL DATA ===
{gmail_ctx}"""

        if include_dismissed:
            dismissed_ctx = self._get_dismissed_context()
            context += f"""

=== DISMISSED CASE DATA ===
{dismissed_ctx}"""

        return context

    def _create_extraction_chain(self, schema: Type[T]):
        """Create a chain with structured output for the given schema"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("user", "Extract all fields for {motion_type} from the following documents:\n\n{context}")
        ])
        return prompt | self.llm.with_structured_output(schema)

    def extract_motion_payload(self, motion_type: str) -> BaseModel:
        """
        Extract motion payload using structured output.

        ONE LLM call extracts ALL fields with guaranteed Pydantic schema.
        This replaces 10+ ReAct agent invocations.

        Args:
            motion_type: Motion type key (e.g., "extend", "modify", "claim").

        Returns:
            Populated Pydantic model instance for the given motion type.

        Raises:
            ValueError: If motion_type is not in MOTION_SCHEMAS.
        """
        schema = MOTION_SCHEMAS.get(motion_type)
        if not schema:
            raise ValueError(f"Unknown motion type: {motion_type}")

        include_dismissed = motion_type == "extend"
        context = self._get_combined_context(include_dismissed=include_dismissed)

        chain = self._create_extraction_chain(schema)

        result = chain.invoke({
            "motion_type": motion_type.replace("-", " ").title(),
            "context": context
        })

        return result

    def extract_service_payload(self, motion_type: str) -> CertificateOfServicePayload:
        """Extract certificate of service payload using dedicated service functions.

        Args:
            motion_type: Motion type key; used to derive the motion context label.

        Returns:
            Populated CertificateOfServicePayload.

        Raises:
            RuntimeError: If the underlying service call fails.
        """
        import json
        from .orchestrator import get_motion_context

        motion_context = get_motion_context(motion_type) # Get the whole Motion Name

        # motion_context = motion_type.replace("-", " ").title()

        # Calls: gmail/service.py → generate_payload_service_for_session_gmail()
        from ..gmail.service import generate_payload_service_for_session_gmail
        result = generate_payload_service_for_session_gmail(
            self.session_id,
            motion_context=motion_context
        )

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Service extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return CertificateOfServicePayload(**payload_data)

    def extract_order_sustaining_payload(self, claim_payload: dict) -> OrderSustainingPayload:
        """Build order sustaining objection payload from an already-extracted claim payload.

        Args:
            claim_payload: Dict of fields from a MotionClaimPayload extraction.

        Returns:
            Populated OrderSustainingPayload derived from the claim data.
        """
        return OrderSustainingPayload(
            DebtorName=claim_payload.get("DebtorName", "N/A"),
            CaseNo=claim_payload.get("CaseNumber", "N/A"),
            Chapter=claim_payload.get("Chapter", "N/A"),
            SlotNumb=claim_payload.get("Slot", "N/A"),
            Creditor=claim_payload.get("ClaimantName", "N/A"),
            CalendarDate="N/A",
            Docket="N/A",
        )

    def extract_all(
        self,
        motion_type: str,
        include_service: bool = True,
        include_order_sustaining: bool = False
    ) -> dict:
        """Extract all payloads for a motion in one call.

        Args:
            motion_type: Motion type key.
            include_service: Whether to also extract the certificate of service payload.
            include_order_sustaining: Whether to extract order sustaining payload (claim only).

        Returns:
            Dict with keys: motion_payload, service_payload, order_sustaining_payload, errors.
        """
        result = {
            "motion_payload": None,
            "service_payload": None,
            "order_sustaining_payload": None,
            "errors": []
        }

        try:
            motion_payload = self.extract_motion_payload(motion_type)
            result["motion_payload"] = motion_payload.model_dump()
        except ExtractionNeedsInputError as e:
            return {
                "status": "needs_input",
                "missing_field": e.missing_field,
                "missing_fields": e.missing_fields,
                "message": e.message,
                "partial_payload": e.partial_payload,
                "motion_payload": None,
                "service_payload": None,
                "order_sustaining_payload": None,
                "errors": [],
            }
        except Exception as e:
            result["errors"].append(f"Motion extraction failed: {str(e)}")
            return result

        if include_service:
            try:
                service_payload = self.extract_service_payload(motion_type)
                service_dict = service_payload.model_dump()
                # Inherit matching fields from motion_payload where service has no real value
                if result["motion_payload"]:
                    for key, value in service_dict.items():
                        if value in ("N/A", "", None) and key in result["motion_payload"]:
                            motion_value = result["motion_payload"][key]
                            if motion_value not in ("N/A", "", None):
                                service_dict[key] = motion_value
                result["service_payload"] = service_dict
            except Exception as e:
                result["errors"].append(f"Service extraction failed: {str(e)}")

        if include_order_sustaining and motion_type == "claim" and result["motion_payload"]:
            try:
                order_payload = self.extract_order_sustaining_payload(result["motion_payload"])
                result["order_sustaining_payload"] = order_payload.model_dump()
            except Exception as e:
                result["errors"].append(f"Order sustaining extraction failed: {str(e)}")

        return result


class ExtractionNeedsInputError(Exception):
    """Raised when extraction requires user input to continue."""

    def __init__(
        self,
        missing_field: str,
        message: str,
        partial_payload: dict = None,
        missing_fields: list = None,
    ):
        self.missing_field = missing_field
        self.missing_fields = missing_fields or []
        self.message = message
        self.partial_payload = partial_payload or {}
        super().__init__(message)


# Called by: get_extractor() (same file) when motion_type == "extend"
class ExtendMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Extend (Revamped).

    Uses the new GmailMotionExtendAgent with:
    - Dismissed case extraction from petition page 3, item 9
    - Gmail search for Order Dismissing Case email
    - AI recommendations for user input fields

    Gmail only - no CourtDrive support for extend.
    """

    def __init__(self, session_id: str, prefilled: dict = None):
        super().__init__(session_id)
        self.prefilled = prefilled or {}

    def extract_motion_payload(self, motion_type: str = "extend") -> BaseModel:  # noqa: ARG002
        import json
        from ..gmail.service import generate_payload_extend_for_session_gmail
        from .schemas import MotionExtendPayload

        result = generate_payload_extend_for_session_gmail(self.session_id, prefilled=self.prefilled)

        if result.get("status") == "needs_input":
            raise ExtractionNeedsInputError(
                missing_field=result.get("missing_field"),
                message=result.get("message"),
                partial_payload=result.get("partial_payload"),
                missing_fields=result.get("missing_fields"),
            )

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Extend extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionExtendPayload(**payload_data)

    def extract_payload_with_recommendations(self) -> dict:
        """
        Extract payload AND AI recommendations for the new extend flow.

        Returns:
            {
                "status": "success" | "needs_input" | "failed",
                "payload": MotionExtendPayload or None,
                "recommendations": {...} or None,
                "missing_field": str (if needs_input),
                "message": str,
            }
        """
        import json
        from ..gmail.service import generate_payload_extend_with_recommendations_for_session_gmail
        from .schemas import MotionExtendPayload

        result = generate_payload_extend_with_recommendations_for_session_gmail(self.session_id)

        if result.get("status") == "needs_input":
            return {
                "status": "needs_input",
                "missing_field": result.get("missing_field"),
                "message": result.get("message"),
                "partial_payload": result.get("partial_payload"),
            }

        if result.get("status") != "success":
            return {
                "status": "failed",
                "error": result.get("error", "Extend extraction failed"),
                "message": result.get("message", "Error during extraction"),
            }

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return {
            "status": "success",
            "payload": MotionExtendPayload(**payload_data),
            "recommendations": result.get("recommendations"),
        }


# Called by: get_extractor() (same file) when motion_type == "claim"
class ClaimMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Objection to Claim.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    Gmail uses extract_all_claim_fields_for_session() for multi-claimant support.
    CourtDrive uses generate_payload_objection_claim_for_session().
    """

    def extract_motion_payload(self, motion_type: str = "claim") -> BaseModel:  # noqa: ARG002
        from datetime import datetime
        from .schemas import MotionClaimPayload

        # Calls: gmail/tools/objection_claim.py → extract_all_claim_fields_for_session()
        from ..gmail.tools.objection_claim import extract_all_claim_fields_for_session

        claim_fields = extract_all_claim_fields_for_session(self.session_id)

        context = self._get_combined_context()
        chain = self._create_extraction_chain(MotionClaimPayload)

        base_result = chain.invoke({
            "motion_type": "Objection to Claim",
            "context": context
        })

        return MotionClaimPayload(
            DebtorName=base_result.DebtorName,
            CaseNumber=base_result.CaseNumber,
            Slot=claim_fields.get("slot", "N/A"),
            ClaimantName=claim_fields.get("claimant_name", "N/A"),
            ClaimAmount=claim_fields.get("claim_amount", "N/A"),
            Date=datetime.now().strftime("%B %d, %Y"),
            Basis="N/A"
        )


# Called by: get_extractor() (same file) when motion_type == "order-value"
class OrderValueExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion to Value Personal Property.

    Delegates to generate_order_value_payload_for_session_gmail() which handles:
    - GmailOrderValueAgent for base field extraction
    - GmailHearingExtractAgent for DocketNumber/TrusteeCalendar from hearing email
    - DateFiled from Voluntary Petition email
    - U.S. prime rate lookup for Percent
    - Value1/Value2/PriceYes/PriceNo from Proof of Claim email
    """

    def extract_motion_payload(self, motion_type: str = "order-value") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_order_value_payload_for_session_gmail()
        from ..gmail.service import generate_order_value_payload_for_session_gmail
        from .schemas import OrderValuePayload

        result = generate_order_value_payload_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order value extraction failed"))

        payload_data = result.get("order_value_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderValuePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-extend"
class OrderExtendExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion to Extend Automatic Stay.

    Delegates to generate_order_extend_payload_for_session_gmail() which derives
    DebtorName/CaseNumber/Chapter from the motion extend payload and DocketMotion
    from the certificate of service payload.

    Note: service returns `granted` as string "N/A" and includes extra `expedited`
    field — both are normalized before constructing the Pydantic model.
    """

    def extract_motion_payload(self, motion_type: str = "order-extend") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_order_extend_payload_for_session_gmail()
        from ..gmail.service import generate_order_extend_payload_for_session_gmail
        from .schemas import OrderExtendPayload

        result = generate_order_extend_payload_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order extend extraction failed"))

        payload_data = result.get("order_extend_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        # Normalize: remove extra field, coerce granted to bool
        payload_data.pop("expedited", None)
        granted_raw = payload_data.get("granted", True)
        payload_data["granted"] = granted_raw is True or str(granted_raw).lower() in ("true", "1", "yes")

        return OrderExtendPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-withdraw"
class OrderWithdrawExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion to Withdraw as Counsel.

    Delegates to generate_payload_withdraw_from_hearing_for_session_gmail() which
    extracts base fields via GmailMotionWithdrawAgent and enriches with DocketNumber
    and TrusteeCalendar from the latest 'Notice of Hearing' email.
    """

    def extract_motion_payload(self, motion_type: str = "order-withdraw") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_withdraw_from_hearing_for_session_gmail()
        from ..gmail.service import generate_payload_withdraw_from_hearing_for_session_gmail
        from .schemas import OrderWithdrawPayload

        result = generate_payload_withdraw_from_hearing_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order withdraw extraction failed"))

        payload_data = result.get("order_withdraw_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderWithdrawPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-waive"
class OrderWaiveExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion to Waive Filing Fee.

    Delegates to generate_payload_waive_from_hearing_for_session_gmail() which
    extracts base fields via GmailMotionWaiveAgent and enriches with DocketNumber
    and TrusteeCalendar from the latest 'Notice of Hearing' email.
    """

    def extract_motion_payload(self, motion_type: str = "order-waive") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_waive_from_hearing_for_session_gmail()
        from ..gmail.service import generate_payload_waive_from_hearing_for_session_gmail
        from .schemas import OrderWaivePayload

        result = generate_payload_waive_from_hearing_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order waive extraction failed"))

        payload_data = result.get("order_waive_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderWaivePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "modify"
class ModifyMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Modify Plan.

    Dual-source: Supports both Gmail and CourtDrive extraction.

    Supports three modification types:
    - delinquent: Debtor fell behind on plan payments
    - creditor_alteration: Creditor(s) altered terms
    - both: Combination of delinquent and creditor alteration
    """

    def __init__(self, session_id: str, model: str = CLAUDE_MODEL_STANDARD, modification_type: str = "delinquent"):
        super().__init__(session_id, model)
        self.modification_type = modification_type

    def extract_motion_payload(self, motion_type: str = "modify") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import MotionModifyPayload

        # Calls: gmail/service.py → generate_payload_modify_for_session_gmail()
        from ..gmail.service import generate_payload_modify_for_session_gmail
        result = generate_payload_modify_for_session_gmail(
            self.session_id,
            modification_type=self.modification_type
        )

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Modify extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionModifyPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "value"
class ValueMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Value Personal Property.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "value") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import MotionValuePayload

        # Calls: gmail/service.py → generate_payload_value_for_session_gmail()
        from ..gmail.service import generate_payload_value_for_session_gmail
        result = generate_payload_value_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Value extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionValuePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "withdraw"
class WithdrawMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Withdraw as Counsel.

    Gmail only extraction.
    """

    def extract_motion_payload(self, motion_type: str = "withdraw") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_withdraw_for_session_gmail()
        from ..gmail.service import generate_payload_withdraw_for_session_gmail
        from .schemas import MotionWithdrawPayload

        result = generate_payload_withdraw_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Withdraw extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionWithdrawPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "waive"
class WaiveMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Waive Filing Fee.

    Gmail only extraction.
    """

    def extract_motion_payload(self, motion_type: str = "waive") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_waive_for_session_gmail()
        from ..gmail.service import generate_payload_waive_for_session_gmail
        from .schemas import MotionWaivePayload

        result = generate_payload_waive_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Waive extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionWaivePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "delay"
class DelayMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion for Delay.

    Gmail only extraction.
    """

    def extract_motion_payload(self, motion_type: str = "delay") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_delay_for_session_gmail()
        from ..gmail.service import generate_payload_delay_for_session_gmail
        from .schemas import MotionDelayPayload

        result = generate_payload_delay_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Delay extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionDelayPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "reinstate"
class ReinstateMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Motion to Reinstate.

    Gmail only extraction.
    """

    def extract_motion_payload(self, motion_type: str = "reinstate") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_payload_reinstate_for_session_gmail()
        from ..gmail.service import generate_payload_reinstate_for_session_gmail
        from .schemas import MotionReinstatePayload

        result = generate_payload_reinstate_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Reinstate extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionReinstatePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "suggestion"
class SuggestionMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Suggestion of Bankruptcy.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "suggestion") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import MotionSuggestionPayload

        # Calls: gmail/service.py → generate_payload_suggestion_for_session_gmail()
        from ..gmail.service import generate_payload_suggestion_for_session_gmail
        result = generate_payload_suggestion_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Suggestion extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionSuggestionPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "loe"
class LOEMotionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Letter of Explanation.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "loe") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import MotionLOEPayload

        # Calls: gmail/service.py → generate_payload_LOE_for_session_gmail()
        from ..gmail.service import generate_payload_LOE_for_session_gmail
        result = generate_payload_LOE_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "LOE extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionLOEPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "ex-parte-extension"
class ExParteExtensionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Ex Parte Motion for Extension.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "ex-parte-extension") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import MotionExParteExtensionPayload

        # Calls: gmail/service.py → generate_payload_ex_parte_extension_for_session_gmail()
        from ..gmail.service import generate_payload_ex_parte_extension_for_session_gmail
        result = generate_payload_ex_parte_extension_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Ex parte extension extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return MotionExParteExtensionPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "objection-sustain"
class OrderSustainingObjectionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order Sustaining Objection to Claim.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "objection-sustain") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import OrderSustainingPayload

        # Calls: gmail/service/order_sustaining_objection.py → generate_payload_objection_sustain_for_session_gmail()
        from ..gmail.service import generate_payload_objection_sustain_for_session_gmail
        result = generate_payload_objection_sustain_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order sustaining objection extraction failed"))

        payload_data = result.get("order_sustaining_objection_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderSustainingPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-extension"
class OrderExtensionExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion for Extension.

    Delegates to generate_order_extension_payload_for_session_gmail() which handles:
    - GmailOrderExtensionAgent for DebtorName/CaseNumber/ChapterNumber
    - GmailHearingExtractAgent for DocketNumber from hearing email
    - DateFiledPlusFourteen from Voluntary Petition email + 14 business days
    """

    def extract_motion_payload(self, motion_type: str = "order-extension") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service.py → generate_order_extension_payload_for_session_gmail()
        from ..gmail.service import generate_order_extension_payload_for_session_gmail
        from .schemas import OrderMotionExtensionPayload

        result = generate_order_extension_payload_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order extension extraction failed"))

        payload_data = result.get("order_extension_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderMotionExtensionPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-reinstate"
class OrderReinstateExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion to Reinstate.

    Delegates to generate_payload_reinstate_from_hearing_for_session_gmail() which
    extracts base fields via GmailOrderReinstateAgent and enriches with DocketNumber
    and TrusteeCalendar from the latest 'Notice of Hearing' email.
    """

    def extract_motion_payload(self, motion_type: str = "order-reinstate") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service/order_reinstate.py → generate_payload_reinstate_from_hearing_for_session_gmail()
        from ..gmail.service import generate_payload_reinstate_from_hearing_for_session_gmail
        from .schemas import OrderReinstatePayload

        result = generate_payload_reinstate_from_hearing_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order reinstate extraction failed"))

        payload_data = result.get("order_reinstate_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderReinstatePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "notice-withdraw"
class NoticeWithdrawExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Notice of Withdrawal.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    """

    def extract_motion_payload(self, motion_type: str = "notice-withdraw") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import NoticeWithdrawPayload

        # Calls: gmail/service.py → generate_payload_notice_withdraw_for_session_gmail()
        from ..gmail.service import generate_payload_notice_withdraw_for_session_gmail
        result = generate_payload_notice_withdraw_for_session_gmail(self.session_id)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Notice withdraw extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return NoticeWithdrawPayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "certificate-of-service"
class CertificateOfServiceExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Certificate of Service.

    Dual-source: Supports both Gmail and CourtDrive extraction.
    Delegates to generate_payload_service_for_session_gmail() (gmail)
    or generate_payload_service_for_session() (courtdrive).
    """

    def extract_motion_payload(self, motion_type: str = "N/A") -> BaseModel:  # noqa: ARG002
        import json
        from .schemas import CertificateOfServicePayload

        # Calls: gmail/service/cert_service.py → generate_payload_service_for_session_gmail()
        from ..gmail.service import generate_payload_service_for_session_gmail
        # Set Motion Type to N/A since it will ask input from users
        motion_type = "N/A"
        result = generate_payload_service_for_session_gmail(
            self.session_id,
            motion_context=motion_type,
        )

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Certificate of service extraction failed"))

        payload_data = result.get("payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return CertificateOfServicePayload(**payload_data)


# Called by: get_extractor() (same file) when motion_type == "order-delay"
class OrderDelayExtractor(StructuredPayloadExtractor):
    """
    Specialized extractor for Order on Motion for Delay.

    Delegates to generate_order_delay_payload_for_session_gmail() which handles:
    - GmailOrderDelayAgent for DebtorName/CaseNumber/ChapterNumber
    - GmailHearingExtractAgent for DocketNumber from Motion to Delay email
    - OldDischargeability, OldDischargeabilityDatePlus30, WhyExtensionNeeded, WithMotion: N/A (placeholder)
    """

    def extract_motion_payload(self, motion_type: str = "order-delay") -> BaseModel:  # noqa: ARG002
        import json
        # Calls: gmail/service/order_delay.py → generate_order_delay_payload_for_session_gmail()
        from ..gmail.service import generate_order_delay_payload_for_session_gmail
        from .schemas import OrderMotionDelayPayload

        result = generate_order_delay_payload_for_session_gmail(self.session_id)
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Order delay extraction failed"))

        payload_data = result.get("order_delay_payload")
        if isinstance(payload_data, str):
            payload_data = json.loads(payload_data)

        return OrderMotionDelayPayload(**payload_data)


# Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
def get_extractor(
    session_id: str,
    motion_type: str,
    modification_type: str = "delinquent",
    prefilled: dict = None,
) -> StructuredPayloadExtractor:
    """Return the appropriate extractor subclass for the given motion type.

    Args:
        session_id: Active session identifier.
        motion_type: Motion type key (e.g., "extend", "claim", "order-value").
        modification_type: For motion to modify - 'delinquent', 'creditor_alteration', or 'both'.
        prefilled: Optional dict with pre-filled values from user input (for resume).

    Returns:
        Instantiated StructuredPayloadExtractor subclass for the motion type,
        or a base StructuredPayloadExtractor if the type is not in the map.
    """
    EXTRACTOR_MAP = {
        "extend": ExtendMotionExtractor,
        "modify": ModifyMotionExtractor,
        "value": ValueMotionExtractor,
        "withdraw": WithdrawMotionExtractor,
        "waive": WaiveMotionExtractor,
        "delay": DelayMotionExtractor,
        "reinstate": ReinstateMotionExtractor,
        "claim": ClaimMotionExtractor,
        "suggestion": SuggestionMotionExtractor,
        "loe": LOEMotionExtractor,
        "ex-parte-extension": ExParteExtensionExtractor,
        "order-extend": OrderExtendExtractor,
        "order-value": OrderValueExtractor,
        "order-extension": OrderExtensionExtractor,
        "order-delay": OrderDelayExtractor,
        "order-withdraw": OrderWithdrawExtractor,
        "order-waive": OrderWaiveExtractor,
        "order-reinstate": OrderReinstateExtractor,
        "objection-sustain": OrderSustainingObjectionExtractor,
        "notice-withdraw": NoticeWithdrawExtractor,
        "certificate-of-service": CertificateOfServiceExtractor,
    }
    extractor_cls = EXTRACTOR_MAP.get(motion_type, StructuredPayloadExtractor)

    # Special handling for ModifyMotionExtractor which needs modification_type
    if motion_type == "modify":
        return extractor_cls(session_id, modification_type=modification_type)

    # Special handling for ExtendMotionExtractor which needs prefilled
    if motion_type == "extend":
        return extractor_cls(session_id, prefilled=prefilled)

    return extractor_cls(session_id)
