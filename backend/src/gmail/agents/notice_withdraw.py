from typing import Optional, Dict, Any, List
import re
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    notice_withdraw_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_NOTICE_WITHDRAW_GMAIL,
)
from ...chatbot.vectorestore import search_vectorstore


# Called by: service.generate_payload_notice_withdraw_for_session_gmail (L2)
#   -> routes/service_stream.py
class GmailNoticeWithdrawAgent:
    """
    Gmail-backed Notice to Withdraw Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_notice_withdraw, case_number_notice_withdraw
    - Gmail vectorstore (gmail_<session_id>) for:
      chapter_notice_withdraw, judge_notice_withdraw, document_title_notice_withdraw

    Output payload shape matches the CourtDrive-based NoticeWithdrawAgent payload.
    """

    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()

        self.llm = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
        )

        self.pdf_fields = ["debtor_name_notice_withdraw", "case_number_notice_withdraw"]
        self.gmail_fields = [
            "chapter_notice_withdraw",
            "judge_notice_withdraw",
            "document_title_notice_withdraw",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_notice_withdraw": "Your full name Debtor 1",
            "case_number_notice_withdraw": "Case number if known",
            "chapter_notice_withdraw": "chapter case details",
            "judge_notice_withdraw": "Judge",
            # CourtDrive-style retrieval hint (works well for docket notice emails too)
            "document_title_notice_withdraw": "Filed by Debtor",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_document_title_by_document_number(self, document_number: int) -> str:
        """
        Deterministically extract DocumentTitle from Gmail email text.

        Expected email pattern:
        - Document Number: <n>
          Docket Text:
          <TITLE> Filed by Debtor ...
        """
        if not self.session_id:
            return "N/A"

        try:
            gmail_collection = f"gmail_{self.session_id}"
            # Retrieval: broaden query because email text may use tabs/newlines and may not include all tokens in one chunk.
            queries = [
                f"Document Number {document_number}",
                f"Document Number: {document_number}",
                f"Doc No {document_number}",
                f"Entry Number {document_number}",
                f"Docket Text Document Number {document_number}",
                f"Docket Text: Document Number: {document_number}",
                # CourtDrive-style anchor text commonly present in the docket line
                f"Filed by Debtor Document Number {document_number}",
                f"Filed by Debtor Document Number: {document_number}",
                f"Filed by Debtor {document_number}",
            ]

            all_docs = []
            seen = set()
            for q in queries:
                for d in search_vectorstore(q, collection_name=gmail_collection, k=50) or []:
                    key = (d.metadata.get("id") if isinstance(getattr(d, "metadata", None), dict) else None) or d.page_content
                    if key in seen:
                        continue
                    seen.add(key)
                    all_docs.append(d)

            if not all_docs:
                return "N/A"

            import re

            # Combine text across chunks to handle chunk boundary splits.
            combined = "\n".join((d.page_content or "") for d in all_docs)

            num_pat = re.compile(
                r"(?:Document\s*Number|Doc(?:ument)?\s*No\.?|Document\s*#|Entry\s*Number)\s*[:#]?\s*(\d+)",
                re.IGNORECASE,
            )

            # Require the specific document number to be present somewhere in retrieved text.
            found_match = False
            for m in num_pat.finditer(combined):
                try:
                    if int(m.group(1)) == int(document_number):
                        found_match = True
                        break
                except Exception:
                    continue
            if not found_match:
                return "N/A"

            # Robust anchor: due to vectorstore chunk ordering, "Docket Text:" and the actual docket
            # line may not be adjacent in the combined string. We therefore:
            # 1) Find occurrences of the target Document Number.
            # 2) From each occurrence, look ahead for "Docket Text:".
            # 3) From there, pick the first non-empty line that contains "Filed by Debtor".
            #
            # This prevents mistakenly capturing headers like "Case Name:" as the docket line.
            docnum_pat = re.compile(
                rf"(?:Document\s*Number|Doc(?:ument)?\s*No\.?|Document\s*#|Entry\s*Number)\s*[:#]?\s*{int(document_number)}\b",
                re.IGNORECASE,
            )
            docket_label_pat = re.compile(r"Docket\s*Text\s*:?", re.IGNORECASE)

            def _extract_title_from_docket_line(line: str) -> str:
                if not line:
                    return "N/A"
                # Must look like a docket text line, not a header.
                if not re.search(r"\bFiled\s+by\s+Debtor\b", line, flags=re.IGNORECASE):
                    return "N/A"
                title_local = re.split(
                    r"\s+Filed\s+by\b", line, maxsplit=1, flags=re.IGNORECASE
                )[0].strip()
                if not title_local:
                    return "N/A"
                # Guardrail: never allow obvious NOE headers as "titles".
                if re.match(r"^(Case\s+Name|Case\s+Number|Document\s+Number|Docket\s+Text)\s*:?\s*$", title_local, flags=re.IGNORECASE):
                    return "N/A"
                return title_local

            for dm in docnum_pat.finditer(combined):
                start = dm.start()
                window = combined[start : start + 2500]  # generous lookahead window
                lm = docket_label_pat.search(window)
                if not lm:
                    continue
                after = window[lm.end() :]
                after_lines = [ln.strip() for ln in after.splitlines()]
                # find first meaningful line that contains Filed by Debtor
                for ln in after_lines[:40]:
                    if not ln:
                        continue
                    title_candidate = _extract_title_from_docket_line(ln)
                    if title_candidate != "N/A":
                        return title_candidate

            # If we can't confidently parse, fail closed.
            return "N/A"
        except Exception:
            return "N/A"

    def _extract_document_title_from_noe_email(
        self,
        case_number_prefix: Optional[str] = None,
        debtor_name: Optional[str] = None,
    ) -> str:
        """
        Deterministically extract DocumentTitle from a Notice of Electronic Filing (NOE) email.

        This is a fallback when docket_number is not provided.

        Expected pattern in the email:
        Docket Text:
        <TITLE> Filed by Debtor ...
        """
        if not self.session_id:
            return "N/A"

        try:
            import re

            gmail_collection = f"gmail_{self.session_id}"
            queries = [
                "Notice of Electronic Filing Docket Text",
                "Docket Text:",
                "Docket Text Filed by Debtor",
                "Filed by Debtor",
            ]

            docs = []
            seen = set()
            for q in queries:
                for d in search_vectorstore(q, collection_name=gmail_collection, k=25) or []:
                    key = (
                        (d.metadata.get("id") if isinstance(getattr(d, "metadata", None), dict) else None)
                        or d.page_content
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    docs.append(d)

            if not docs:
                return "N/A"

            combined = "\n".join((d.page_content or "") for d in docs)
            combined_lower = combined.lower()

            # Optional anchoring to reduce picking the wrong NOE when multiple exist.
            if case_number_prefix:
                cn = case_number_prefix.strip()
                if cn and cn.lower() not in combined_lower:
                    # If our top retrieved docs don't even mention the case, extraction is unreliable.
                    # Still proceed, but only via strict pattern matching.
                    pass

            # Find docket text line(s) associated with "Docket Text:"
            # Prefer the first non-empty line after the label that also contains "Filed by Debtor".
            lines = [ln.strip() for ln in combined.splitlines()]
            docket_lines = []
            for i, ln in enumerate(lines):
                if re.match(r"^Docket\s*Text\s*:?\s*$", ln, flags=re.IGNORECASE):
                    # next non-empty line
                    for j in range(i + 1, min(i + 6, len(lines))):
                        cand = lines[j].strip()
                        if cand:
                            docket_lines.append(cand)
                            break
                else:
                    m = re.match(r"^Docket\s*Text\s*:?\s*(.+)$", ln, flags=re.IGNORECASE)
                    if m:
                        docket_lines.append((m.group(1) or "").strip())

            # Also consider any line that contains "Filed by Debtor" (some chunks omit "Docket Text:" label)
            for ln in lines:
                if re.search(r"\bFiled\s+by\s+Debtor\b", ln, flags=re.IGNORECASE):
                    docket_lines.append(ln.strip())

            # Filter down to candidates that look like the docket text line.
            candidates = []
            for dl in docket_lines:
                if not dl:
                    continue
                if not re.search(r"\bFiled\s+by\s+Debtor\b", dl, flags=re.IGNORECASE):
                    continue
                candidates.append(dl)

            if not candidates:
                return "N/A"

            def score(line: str) -> int:
                s = 0
                if case_number_prefix and case_number_prefix.strip():
                    if case_number_prefix.strip().lower() in line.lower():
                        s += 3
                if debtor_name and debtor_name.strip():
                    # loose match: any token from debtor name present
                    tokens = [t for t in re.split(r"\s+", debtor_name.strip()) if len(t) >= 3]
                    hit = sum(1 for t in tokens if t.lower() in line.lower())
                    s += min(hit, 3)
                return s

            candidates.sort(key=score, reverse=True)
            best = candidates[0]

            title = re.split(r"\s+Filed\s+by\b", best, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            return title if title else "N/A"
        except Exception:
            return "N/A"

    def _extract_all_filed_motions(self) -> List[Dict[str, str]]:
        """
        Extract all motions filed by debtor from Gmail.
        Filter: "Filed by Debtor" AND "(Van Horn, Chad)" in docket text.

        Returns list of:
        {
            "docket_number": "6",
            "document_title": "Verified Motion to Extend the Automatic Stay"
        }
        """
        if not self.session_id:
            return []

        try:
            gmail_collection = f"gmail_{self.session_id}"

            queries = [
                "Filed by Debtor Van Horn Chad",
                "Filed by Debtor (Van Horn, Chad)",
                "Docket Text Filed by Debtor",
                "Notice of Electronic Filing Filed by Debtor",
            ]

            all_docs = []
            seen_content = set()
            for q in queries:
                for d in search_vectorstore(q, collection_name=gmail_collection, k=100) or []:
                    content_hash = hash(d.page_content[:200] if d.page_content else "")
                    if content_hash in seen_content:
                        continue
                    seen_content.add(content_hash)
                    all_docs.append(d)

            if not all_docs:
                return []

            combined = "\n".join((d.page_content or "") for d in all_docs)

            filed_motions = []
            seen_dockets = set()

            doc_num_pat = re.compile(
                r"(?:Document\s*Number|Doc(?:ument)?\s*No\.?|Document\s*#|Entry\s*Number)\s*[:#]?\s*(\d+)",
                re.IGNORECASE,
            )

            lines = combined.splitlines()

            for i, line in enumerate(lines):
                if not re.search(r"\bFiled\s+by\s+Debtor\b", line, flags=re.IGNORECASE):
                    continue
                if not re.search(r"\(Van\s*Horn,?\s*Chad\)", line, flags=re.IGNORECASE):
                    continue

                title = re.split(r"\s+Filed\s+by\b", line, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                if not title or re.match(r"^(Case\s+Name|Case\s+Number|Document\s+Number|Docket\s+Text)\s*:?\s*$", title, flags=re.IGNORECASE):
                    continue

                docket_number = None
                search_window = "\n".join(lines[max(0, i-15):i+5])
                for m in doc_num_pat.finditer(search_window):
                    try:
                        docket_number = m.group(1)
                        break
                    except Exception:
                        continue

                if docket_number and docket_number not in seen_dockets:
                    seen_dockets.add(docket_number)
                    filed_motions.append({
                        "docket_number": docket_number,
                        "document_title": title
                    })

            filed_motions.sort(key=lambda x: int(x["docket_number"]) if x["docket_number"].isdigit() else 0)

            print(f"Found {len(filed_motions)} filed motions for withdrawal")
            for m in filed_motions:
                print(f"  Docket #{m['docket_number']}: {m['document_title']}")

            return filed_motions

        except Exception as e:
            print(f"Error extracting filed motions: {e}")
            return []

    def _extract_single_field(self, field_name: str, query: str, docket_number: Optional[int] = None) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = notice_withdraw_gmail_tool(session_id=self.session_id)
                field_tool = None

                for tool in tools:
                    if tool.name == f"extract_{field_name}":
                        field_tool = tool
                        break

                if not field_tool:
                    return f"Tool for {field_name} not found"

                prompt = INDIVIDUAL_FIELD_PROMPTS_NOTICE_WITHDRAW_GMAIL[field_name]

                agent_executor = create_react_agent(
                    tools=[field_tool],
                    model=self.llm,
                    prompt=prompt,
                )

                response = agent_executor.invoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Return ONLY the extracted value for: {field_name}. Query: {query}. No explanation. No summaries. No markdown. Return only the value(s) or N/A.",
                            }
                        ]
                    },
                    config={
                        "configurable": {
                            "thread_id": f"{self.session_id}_{field_name}_{attempt}"
                        },
                        "recursion_limit": 50,
                    },
                )

                ai_response = ""
                if "messages" in response:
                    ai_messages = []
                    for message in response["messages"]:
                        if hasattr(message, "content") and hasattr(message, "__class__"):
                            if "AIMessage" in str(message.__class__):
                                ai_messages.append(message.content)
                    if ai_messages:
                        ai_response = ai_messages[-1].strip()

                if ai_response and ai_response != "N/A":
                    return ai_response
                elif attempt < max_retries:
                    print(f"  Retrying {field_name} (attempt {attempt + 1})...")
                    continue
                else:
                    return "N/A"

            except Exception as e:
                if "recursion limit" in str(e).lower() and attempt < max_retries:
                    print(
                        f"  Recursion error for {field_name}, retrying with different approach..."
                    )
                    query = f"{field_name}"
                    continue
                else:
                    print(f"Error extracting {field_name}: {str(e)}")
                    if attempt < max_retries:
                        continue
                    return "N/A"

        return "N/A"

    def extract_payload(self, user_hint: Optional[str] = None, docket_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Extract notice to withdraw payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Gmail-backed sequential field extraction for notice to withdraw...")
            if docket_number is not None:
                print(f"Using docket number for document title extraction: {docket_number}")

            pdf_results: Dict[str, str] = {}
            print("Extracting petition (PDF) fields...")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query, docket_number)
                pdf_results[field] = result
                print(f"    {field}: {result}")

            gmail_results: Dict[str, str] = {}
            print("Extracting Gmail-backed fields...")
            for field in self.gmail_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                if field == "document_title_notice_withdraw" and docket_number is not None:
                    # Avoid LLM hallucination: deterministically parse Document Number + Docket Text block.
                    result = self._extract_document_title_by_document_number(docket_number)
                    # IMPORTANT: If user provided docket_number but we cannot match it to a
                    # "Document Number" in the NOE email, fail closed to "N/A" (do not
                    # fall back to other docket entries).
                elif field == "document_title_notice_withdraw":
                    # Fallback: deterministically parse NOE "Docket Text:" line (prevents "Case Name" hallucination).
                    case_number_prefix = (pdf_results.get("case_number_notice_withdraw") or "").strip()
                    debtor_name = (pdf_results.get("debtor_name_notice_withdraw") or "").strip()
                    result = self._extract_document_title_from_noe_email(
                        case_number_prefix=case_number_prefix or None,
                        debtor_name=debtor_name or None,
                    )
                else:
                    result = self._extract_single_field(field, query, docket_number)
                gmail_results[field] = result
                print(f"    {field}: {result}")

            judge_initial = gmail_results.get("judge_notice_withdraw", "N/A")
            case_number = pdf_results.get("case_number_notice_withdraw", "N/A")

            combined_case_number = case_number
            if judge_initial != "N/A" and judge_initial and case_number != "N/A" and case_number:
                combined_case_number = f"{case_number}-{judge_initial}"

            filed_motions = self._extract_all_filed_motions()
            available_docket_numbers = "\n".join([m["docket_number"] for m in filed_motions])
            available_document_titles = "\n".join([m["document_title"] for m in filed_motions])

            final_payload = {
                "DebtorName": pdf_results.get("debtor_name_notice_withdraw", "N/A"),
                "CaseNumberJudge": combined_case_number,
                "Chapter": gmail_results.get("chapter_notice_withdraw", "N/A"),
                "ECFNumber": "N/A",
                "DocumentTitle": gmail_results.get("document_title_notice_withdraw", "N/A"),
                "AvailableDocketNumbers": available_docket_numbers,
                "AvailableDocumentTitles": available_document_titles,
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Gmail-backed notice withdraw payload: {final_payload}")
            print(
                f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)"
            )

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_notice_withdraw_agent_sequential",
                "field_results": extracted_fields,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Gmail Notice withdraw payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_notice_withdraw_agent_sequential",
            }

