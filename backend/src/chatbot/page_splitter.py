from PyPDF2 import PdfReader
import re

# Footer keywords grouped by logical sections
footer_groups = {
    "Schedule C & D": [
        "Schedule C: The Property You Claim as Exempt",
        "Schedule D: Creditors Who Have Claims Secured by Property"
    ],
    "Schedule I, J & Summary": [
        "Schedule I: Your Income",
        "Schedule J: Your Expenses",
        "Summary of Your Assets and Liabilities and Certain Statistical Information"
    ],
    "Schedule A/B": [
        "Schedule A/B: Property"
    ],
    "Statement of Financial Affairs": [
        "Statement of Financial Affairs for Individuals Filing for Bankruptcy"
    ],
    "Schedule E/F": [
        "Schedule E/F: Creditors Who Have Unsecured Claims"
    ],
    "Schedule G & H": [
        "Schedule G: Executory Contracts and Unexpired Leases",
        "Schedule H: Your Codebtors"
    ]
}

# Create a mapping from individual footer text to group name
footer_to_group = {}
for group_name, footers in footer_groups.items():
    for footer in footers:
        footer_to_group[footer] = group_name

# Create regex pattern for all footers
all_footers = [footer for footers in footer_groups.values() for footer in footers]
footer_pattern = re.compile("|".join(re.escape(f) for f in all_footers), re.IGNORECASE)


def split_pdf_by_footers(pdf_path: str) -> dict:
    """
    Split a PDF into groups based on footer keywords.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary with group names as keys and lists of page numbers as values
    """
    reader = PdfReader(pdf_path)
    
    # Store groups in memory: {group_name: [list_of_page_numbers]}
    groups = {}
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        
        if len(text) < 50:  # Very short text might indicate extraction failure
            print(f"  WARNING: Page {i+1} has very short text: '{text[:100]}...'")
        
        match = footer_pattern.search(text)
        if match:
            footer_text = match.group(0)
            # Map footer to group name
            group_name = footer_to_group.get(footer_text, "Other")
            # Store page number (1-indexed for user-friendly display)
            page_number = i + 1
            groups.setdefault(group_name, []).append(page_number)
        else:
            pass
    
    # Groups processing completed
    return groups


def get_group_text(pdf_path: str, group_name: str, page_numbers: list) -> str:
    """
    Get combined text from all pages in a specific group.
    
    Args:
        pdf_path: Path to the PDF file
        group_name: Name of the group
        page_numbers: List of page numbers in the group
        
    Returns:
        Combined text from all pages in the group
    """
    reader = PdfReader(pdf_path)
    combined_text = ""
    
    for page_num in page_numbers:
        # Convert back to 0-indexed for PdfReader
        page_index = page_num - 1
        page = reader.pages[page_index]
        page_text = page.extract_text() or ""
        combined_text += f"\n--- Page {page_num} ---\n{page_text}"
    
    return combined_text


def process_pdf_and_get_groups(pdf_path: str) -> dict:
    """
    Process a PDF and return both the groups and their combined text.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary with group names as keys and dictionaries containing:
        - page_numbers: List of page numbers
        - text: Combined text from all pages in the group
    """
    groups = split_pdf_by_footers(pdf_path)
    result = {}
    
    for group_name, page_numbers in groups.items():
        result[group_name] = {
            "page_numbers": page_numbers,
            "text": get_group_text(pdf_path, group_name, page_numbers)
        }
    
    return result
