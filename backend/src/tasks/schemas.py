"""
Pydantic schemas for structured LLM output extraction.

These schemas replace ReAct agent per-field extraction with
LangChain's `with_structured_output()` for guaranteed schema validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# Called by: ExtendMotionExtractor (tasks/extractors.py)
class MotionExtendPayload(BaseModel):
    """Structured payload for Motion to Extend Automatic Stay (Revamped)"""
    # Current case info
    court_district: str = Field(description="Court district (e.g., 'Southern District of Florida')")
    court_division: str = Field(default="N/A", description="Court division (e.g., 'Miami Division')")
    petition_date: str = Field(description="Petition filing date")
    debtor_name: str = Field(description="Debtor's full legal name")
    case_no: str = Field(description="Current case number with judge initial")
    chapter: str = Field(description="Bankruptcy chapter (7, 11, 12, or 13)")

    # Dismissed case info (extracted)
    dismissed_case_number: str = Field(description="Prior dismissed case number (e.g., '25-19062')")
    dismissal_date: str = Field(description="Date the prior case was dismissed")
    trustees_reason: str = Field(description="Trustee's reason for dismissal from Docket Text")
    docket_entry_no: str = Field(description="Docket entry number for dismissal order")

    # User input fields (with AI recommendations)
    dismissal_reason: str = Field(default="N/A", description="User-provided dismissal explanation")
    change_in_circum: str = Field(default="N/A", description="User-provided change in circumstances")

    # Extension type selection
    extension_type: str = Field(default="regular", description="'regular' or 'expedite'")

    # Expedite-only field
    petition_date_plus_30: str = Field(default="", description="Petition date + 30 days (for expedite only)")


# Called by: ModifyMotionExtractor (tasks/extractors.py)
class MotionModifyPayload(BaseModel):
    """Structured payload for Motion to Modify Plan"""
    # Common fields (all templates)
    court_district: str = Field(description="Court district")
    court_division: str = Field(description="Court division (e.g., 'Jacksonville')")
    debtor_name: str = Field(description="Debtor's full legal name")
    case_no: str = Field(description="Case number with judge initial")
    chapter: str = Field(description="Bankruptcy chapter")
    confirm_date: str = Field(description="Date plan was confirmed")
    docket_confirm: str = Field(description="Docket number for confirmation order")
    docket_plan: str = Field(description="Docket number for the plan")
    current_date: str = Field(default="", description="Current date (auto-filled)")

    # Type selection (set BEFORE extraction based on user's answer)
    modification_type: str = Field(default="delinquent", description="'delinquent', 'creditor_alteration', or 'both'")

    # Template selection (determined by comparing order emails)
    use_granting_template: bool = Field(default=False, description="True if 'Order on Motion to Modify' is more recent than 'Order Confirming'")

    # Regular (delinquent) fields - extracted only if delinquent/both
    date_delinquent: str = Field(default="N/A", description="Date debtor became delinquent")
    docket_notice: str = Field(default="N/A", description="Docket number for delinquency notice")
    delinquent_reason: str = Field(default="N/A", description="User-provided reason for delinquency")

    # noD (creditor alteration) fields - extracted only if creditor_alteration/both
    creditors: str = Field(default="N/A", description="User-selected creditor names")
    claim_slot: str = Field(default="N/A", description="Computed claim slot format: (POC X & Y)")
    has_have: str = Field(default="has", description="Computed: 'has' (single) or 'have' (multiple)")
    s_plural: str = Field(default="", description="Computed: '' (single) or 's' (multiple)")

    # For UI selection (extracted POC data)
    available_creditors: str = Field(default="", description="JSON array of {creditor_name, claim_number, amount_claimed}")


# Called by: ValueMotionExtractor (tasks/extractors.py)
class MotionValuePayload(BaseModel):
    """Structured payload for Motion to Value Personal Property"""
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    DebtorName: str = Field(description="Debtor's full legal name")
    Creditor: str = Field(description="Secured creditor name")
    CarModel: str = Field(description="Vehicle make, model, and year")
    VinModel: str = Field(description="Vehicle identification number (VIN)")
    Odometer: str = Field(description="Odometer reading/mileage")
    Value: str = Field(description="Current value amount")
    ValueMethod: str = Field(description="Valuation method used (e.g., KBB, NADA)")
    ClaimSlot: str = Field(description="Claim slot/position number")
    Percent: str = Field(description="User percentage")
    Price: str = Field(description="User price")
    WithClaim: str = Field(description="With Proof of Claim or No Proof of Claim")
    DescriptionOfProperty: str = Field(default="N/A", description="User-provided Description of Property")


# Called by: WithdrawMotionExtractor (tasks/extractors.py)
class MotionWithdrawPayload(BaseModel):
    """Structured payload for Motion to Withdraw as Counsel"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    Chapter: str = Field(description="Bankruptcy chapter")
    Judge: str = Field(description="Judge's initials")
    DebtorCurrentAddy: str = Field(description="Debtor's current address")


# Called by: WaiveMotionExtractor (tasks/extractors.py)
class MotionWaivePayload(BaseModel):
    """Structured payload for Motion to Waive Filing Fee"""
    CaseNumber: str = Field(description="Case number with judge initial")
    Chapter: str = Field(description="Bankruptcy chapter")
    DebtorName: str = Field(description="Debtor's full legal name")
    DateOne: str = Field(description="Original filing date formatted")
    DateTwo: str = Field(default="", description="Current date (auto-filled)")
    employment_explanation: str = Field(default="N/A", description="User-provided employment explanation")


# Called by: DelayMotionExtractor (tasks/extractors.py)
class MotionDelayPayload(BaseModel):
    """Structured payload for Motion for Delay"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumb: str = Field(description="Bankruptcy chapter")
    District: str = Field(default="SOUTHERN", description="Court district (e.g., SOUTHERN, MIDDLE, NORTHERN)")
    DateFiled: str = Field(description="Petition filing date")
    ConcludedMeetingDate: str = Field(description="Date meeting of creditors concluded")
    Vehicle: str = Field(description="Vehicle description (year, make, model)")
    VIN: str = Field(description="Vehicle identification number")
    House: str = Field(description="Local property identification number")
    Address: str = Field(description="Property address")
    Creditors: str = Field(description="Creditor names")
    CurrentDate: str = Field(default="", description="Current date (auto-filled)")
    ReasonForDelay: str = Field(default="N/A", description="User-provided reason for delay")
    IfReaffirmation: str = Field(default="N/A", description="User-provided reaffirmation info")
    ReaffirmationNeeded: str = Field(default="N/A", description="Whether reaffirmation needed")
    DelayReasonRecommendations: list = Field(default=[], description="AI-generated delay reason recommendations")


# Called by: ReinstateMotionExtractor (tasks/extractors.py)
class MotionReinstatePayload(BaseModel):
    """Structured payload for Motion to Reinstate"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumb: str = Field(description="Bankruptcy chapter")
    DateFiled: str = Field(description="Petition filing date")
    DismissedDate: str = Field(default="N/A", description="Date case was dismissed")
    DismissalReason: str = Field(default="N/A", description="System-extracted reason for dismissal")
    WhyDismissedDetailed: str = Field(default="N/A", description="User or AI provided detailed dismissal reason")


# Called by: ClaimMotionExtractor (tasks/extractors.py)
class MotionClaimPayload(BaseModel):
    """Structured payload for Objection to Claim"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    Slot: str = Field(description="Claim slot/position number")
    ClaimantName: str = Field(description="Name of the claimant")
    ClaimAmount: str = Field(description="Amount of the claim")
    Date: str = Field(default="", description="Current date (auto-filled)")
    Basis: str = Field(default="N/A", description="User-provided basis for objection")


# Called by: SuggestionMotionExtractor (tasks/extractors.py)
class MotionSuggestionPayload(BaseModel):
    """Structured payload for Suggestion of Bankruptcy"""
    CaseNumber: str = Field(description="Bankruptcy case number with judge initial")
    DebtorName: str = Field(description="Debtor's full legal name")
    Creditor: str = Field(default="N/A", description="Creditor name from legal actions")
    CourtAgency: str = Field(default="N/A", description="Court or agency name from legal actions")
    County: str = Field(default="N/A", description="County the court belongs to")
    CircuitNumber: str = Field(default="N/A", description="Circuit number of the court")
    District: str = Field(default="N/A", description="District")
    BKCaseNumber: str = Field(default="N/A", description="Bankruptcy case number (alternate)")
    DateFiled: str = Field(description="Bankruptcy filing date")


# Called by: LOEMotionExtractor (tasks/extractors.py)
class MotionLOEPayload(BaseModel):
    """Structured payload for Letter of Explanation"""
    Date: str = Field(default="", description="Current date (auto-filled)")
    TrusteeName: str = Field(description="Trustee's name from emails")
    ChapterNumb: str = Field(description="Bankruptcy chapter")
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumb: str = Field(description="Case number with judge initial")
    explanation: str = Field(default="N/A", description="User-provided explanation")
    AttorneyName: str = Field(default="N/A", description="Attorney name (may be auto-filled)")


# Called by: ExParteExtensionExtractor (tasks/extractors.py)
class MotionExParteExtensionPayload(BaseModel):
    """Structured payload for Ex Parte Motion for Extension"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    DateFiled: str = Field(description="Petition filing date")
    DateFiledPlusFourteen: str = Field(default="", description="Date filed + 14 days (auto-calculated)")
    MeetingDate: str = Field(description="Meeting of creditors date")
    CurrentDate: str = Field(default="", description="Current date (auto-filled)")


# Called by: StructuredPayloadExtractor.extract_service_payload() (tasks/extractors.py)
#            — used by all motion extractor subclasses
class CertificateOfServicePayload(BaseModel):
    """Structured payload for Certificate of Service"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    CourtDistrict: str = Field(description="Court district")
    Chapter: str = Field(description="Bankruptcy chapter")
    MotionType: str = Field(description="Type of motion being served")
    TrusteeName: str = Field(description="Trustee's name")
    TrustEmail: str = Field(description="Trustee's email address")
    USTemail: str = Field(description="US Trustee email address")
    CurrentDate: str = Field(default="", description="Current date (auto-filled)")
    IfNoticeofHearing: str = Field(default="", description="Whether notice of hearing included")
    WasOrWere: str = Field(default="was", description="Grammar: 'was' or 'were'")
    DocketMotion: str = Field(default="", description="Docket number for the motion")
    MiscMailListings: str = Field(default="", description="Misc Name and email findings")


# Called by: OrderSustainingObjectionExtractor (tasks/extractors.py)
class OrderSustainingPayload(BaseModel):
    """Structured payload for Order Sustaining Objection to Claim"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    SlotNumb: str = Field(default="N/A", description="Claim slot/position number")
    Creditor: str = Field(description="Creditor/claimant name")
    DocketNumber: str = Field(default="N/A", description="Docket number from Notice of Hearing email")
    TrusteeCalendar: str = Field(default="N/A", description="Hearing date and time from Notice of Hearing email")


# Called by: OrderExtendExtractor (tasks/extractors.py)
class OrderExtendPayload(BaseModel):
    """Structured payload for Order on Motion to Extend"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    Chapter: str = Field(description="Bankruptcy chapter")
    CalendarDate: str = Field(default="N/A", description="User-provided calendar date")
    granted: bool = Field(default=True, description="Whether motion is granted")
    DocketMotion: str = Field(description="User-provided docket motion number or Extracted")
    OptionalConditions: str = Field(default="", description="User-provided optional conditions")
    expedited: str = Field(default="", description="User-provided if Regular or Expedited")

# Called by: OrderWaiveExtractor (tasks/extractors.py)
class OrderWaivePayload(BaseModel):
    """Structured payload for Order on Motion to Waive"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    TrusteeCalendar: str = Field(default="N/A", description="User-provided trustee calendar date/time")
    DocketNumber: str = Field(default="N/A", description="User-provided docket number")


# Called by: OrderWithdrawExtractor (tasks/extractors.py)
class OrderWithdrawPayload(BaseModel):
    """Structured payload for Order on Motion to Withdraw"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    MotionAddress: str = Field(description="Debtor's address")
    TrusteeCalendar: str = Field(default="N/A", description="User-provided trustee calendar date/time")
    DocketMotion: str = Field(default="N/A", description="User-provided docket motion number")
    DocketNumber: str = Field(default="N/A", description="User-provided docket number")


# Called by: OrderValueExtractor (tasks/extractors.py)
class OrderValuePayload(BaseModel):
    """Structured payload for Order on Motion to Value Personal Property"""
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    DebtorName: str = Field(description="Debtor's full legal name")
    Creditor: str = Field(description="Secured creditor name")
    DocketNumber: str = Field(default="N/A", description="User-provided docket number")
    TrusteeCalendar: str = Field(default="N/A", description="User-provided trustee calendar date/time")
    CarModel: str = Field(description="Vehicle make, model, and year")
    VinModel: str = Field(description="Vehicle identification number (VIN)")
    Odometer: str = Field(description="Odometer reading/mileage")
    Value: str = Field(description="Current value amount")
    ClaimSlot: str = Field(description="Claim slot/position number")
    DateFiled: str = Field(default="N/A", description="Petition filing date")
    Value1: str = Field(default="N/A", description="Amount secured (from Proof of Claim)")
    Value2: str = Field(default="N/A", description="Amount unsecured (AmountClaimed - AmountSecured)")
    Percent: str = Field(default="N/A", description="U.S. prime loan rate at time of filing")
    PriceYes: str = Field(default="N/A", description="Total repayment if claim filed")
    PriceNo: str = Field(default="N/A", description="Total repayment if no claim filed")
    WithClaim: str = Field(default="N/A", description="User-provided: whether a proof of claim was filed")
    AmountClaimed: str = Field(default="N/A", description="Amount Claimed")
    AmountSecured:  str = Field(default="N/A", description="Amount Secured")
    FinalPrice: str = Field(default="N/A", description="Total repayment if claim filed or not")


# Called by: OrderExtensionExtractor (tasks/extractors.py)
class OrderMotionExtensionPayload(BaseModel):
    """Structured payload for Order on Motion for Extension"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    DocketNumber: str = Field(default="N/A", description="Docket number from Notice of Hearing")
    DateFiled: str = Field(default="N/A", description="Petition filing date")
    DateFiledPlusFourteen: str = Field(default="N/A", description="Petition filing date + 14 calendar days")


# Called by: OrderDelayExtractor (tasks/extractors.py)
class OrderMotionDelayPayload(BaseModel):
    """Structured payload for Order on Motion for Delay"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    DocketNumber: str = Field(default="N/A", description="Docket number from Motion to Delay email")
    District : str = Field(default="N/A", description="Court District Direction")
    OldDischargeability: str = Field(default="N/A", description="Old dischargeability date")
    OldDischargeabilityDatePlus30: str = Field(default="N/A", description="Old dischargeability date + 30 days")
    WhyExtensionNeeded: str = Field(default="N/A", description="Reason extension is needed")
    WithMotion: bool = Field(default=True, description="True = chips auto-generated from Schedule D; False = user must upload Motion to Delay doc")

# Called by: OrderReinstateExtractor (tasks/extractors.py)
class OrderReinstatePayload(BaseModel):
    """Structured payload for Order on Motion to Reinstate"""
    DebtorName: str = Field(description="Debtor's full legal name")
    CaseNumber: str = Field(description="Case number with judge initial")
    ChapterNumber: str = Field(description="Bankruptcy chapter")
    TrusteeCalendar: str = Field(default="N/A", description="User-provided trustee calendar date/time")
    DocketNumber: str = Field(default="N/A", description="Docket number from Notice of Hearing")
    X1: str = Field(default="N/A", description="User Initiated value for Checkmark - Provision A ")
    X2: str = Field(default="N/A", description="User Initiated value for Checkmark - Provision B ")
    X3: str = Field(default="N/A", description="User Initiated value for Checkmark - Provision C ")


# Called by: NoticeWithdrawExtractor (tasks/extractors.py)
class NoticeWithdrawPayload(BaseModel):
    """Structured payload for Notice of Withdrawal"""
    DebtorName: str = Field(default="N/A", description="Debtor's full legal name")
    CaseNumberJudge: str = Field(default="N/A", description="Case number with judge initial (e.g., 25-12345-JCC)")
    Chapter: str = Field(default="N/A", description="Bankruptcy chapter")
    ECFNumber: str = Field(default="N/A", description="ECF/Docket number")
    DocumentTitle: str = Field(default="N/A", description="Document title from NOE email")
    AvailableDocketNumbers: str = Field(default="", description="Newline-separated docket numbers for dropdown")
    AvailableDocumentTitles: str = Field(default="", description="Newline-separated document titles for dropdown")

    class Config:
        populate_by_name = True


# Called by: StructuredPayloadExtractor (tasks/extractors.py)
MOTION_SCHEMAS = {
    "extend": MotionExtendPayload,
    "modify": MotionModifyPayload,
    "value": MotionValuePayload,
    "withdraw": MotionWithdrawPayload,
    "waive": MotionWaivePayload,
    "delay": MotionDelayPayload,
    "reinstate": MotionReinstatePayload,
    "claim": MotionClaimPayload,
    "suggestion": MotionSuggestionPayload,
    "loe": MotionLOEPayload,
    "ex-parte-extension": MotionExParteExtensionPayload,
    "order-extend": OrderExtendPayload,
    "order-waive": OrderWaivePayload,
    "order-withdraw": OrderWithdrawPayload,
    "order-value": OrderValuePayload,
    "order-extension": OrderMotionExtensionPayload,
    "order-reinstate": OrderReinstatePayload,
    "objection-sustain": OrderSustainingPayload,
    "notice-withdraw": NoticeWithdrawPayload,
    "certificate-of-service": CertificateOfServicePayload,
}

# Called by: pleading_tasks._build_prefilled() (tasks/pleading_tasks.py)
USER_INPUT_FIELDS = {
    # motions
    "extend": ["dismissal_reason", "change_in_circum"],
    "modify": ["delinquent_reason", "creditors", "claim_slot", "has_have", "s_plural"],
    "value": ["Select1", "Select2", "Put1", "Percent1", "Price1", "Put2", "Percent2", "Price2"],
    "withdraw": [],
    "waive": ["employment_explanation"],
    "delay": ["ReasonForDelay", "Explain", "IfReaffirmation", "ReaffirmationNeeded"],
    "reinstate": ["WhyDismissedDetailed"],
    "claim": ["Basis"],
    "suggestion": ["CaseNumber", "Creditor", "County", "CircuitNumber", "DateFiled" ],
    "loe": ["explanation"],
    "ex-parte-extension": [],
    # orders
    "order-extend": ["expedited", "CalendarDate", "DocketMotion", "OptionalConditions"],
    "order-waive": ["TrusteeCalendar", "DocketNumber"],
    "order-withdraw": ["Motion Address", "TrusteeCalendar", "DocketNumber"],
    "order-value": ["Creditor", "DocketNumber", "TrusteeCalendar", "CarModel", "VinModel", "Odometer",
                    "Value", "ClaimSlot", "Percent", "WithClaim", "AmountClaimed", "AmountSecured" ],
    "order-extension": [],
    "order-reinstate": ["X1", "X2", "X3"],
    "order-delay": ["WhyExtensionNeeded"],
    "objection-sustain": ["SlotNumb", "Creditor", "TrusteeCalendar", "DocketNumber"],
    "notice-withdraw": ["ECFNumber", "DocumentTitle"],
    "certificate-of-service": ["MotionType", "IfNoticeofHearing"],
}