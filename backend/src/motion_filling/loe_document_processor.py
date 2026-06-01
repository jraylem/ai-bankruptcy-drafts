"""
LOE Supporting Document Processor

Handles processing of supporting documents (PDF, DOCX, images) for
Letter of Explanation generation.
- Extracts text from PDFs and DOCX files
- Uses Claude Vision API for image analysis
- Stores documents temporarily in Redis for LOE generation
- Stores documents permanently in vectorstore when requested
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Optional

import anthropic
import redis
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document

from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD
from ..tasks.redis_client import make_sync_redis


LOE_DOCS_PREFIX = "loe_docs:"
LOE_DOCS_TTL = 3600  # 1 hour TTL for temporary storage


_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = make_sync_redis()
    return _redis_client


def _get_media_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        return mime_type
    ext = Path(file_path).suffix.lower()
    mime_map = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    return mime_map.get(ext, 'application/octet-stream')


def analyze_image_with_claude_vision(image_path: str) -> str:
    """
    Use Claude Vision API to analyze an image (bank statement, receipt, etc.)

    Args:
        image_path: Path to the image file

    Returns:
        Extracted text and analysis from the image
    """
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        media_type = _get_media_type(image_path)

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": """Analyze this document image and extract all relevant information.
Focus on:
- Dates (transaction dates, statement dates, due dates)
- Amounts (transaction amounts, totals, balances)
- Names (account holder, payee, institution names)
- Account/reference numbers
- Any explanatory text or notes

Format your response as a structured summary that can be used as supporting evidence in a legal letter.
Be precise with numbers, dates, and amounts - these details matter for legal documentation."""
                    }
                ],
            }]
        )

        return response.content[0].text

    except Exception as e:
        print(f"[error] analyze_image_with_claude_vision: {e}")
        return f"[Error extracting image content: {str(e)}]"


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using PyPDFLoader.

    Args:
        file_path: Path to the PDF file

    Returns:
        Extracted text content
    """
    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        return "\n\n".join(doc.page_content for doc in documents)
    except Exception as e:
        print(f"[error] extract_text_from_pdf: {e}")
        return f"[Error extracting PDF content: {str(e)}]"


def extract_text_from_docx(file_path: str) -> str:
    """
    Extract text from a DOCX file using Docx2txtLoader.

    Args:
        file_path: Path to the DOCX file

    Returns:
        Extracted text content
    """
    try:
        loader = Docx2txtLoader(file_path)
        documents = loader.load()
        return "\n\n".join(doc.page_content for doc in documents)
    except Exception as e:
        print(f"[error] extract_text_from_docx: {e}")
        return f"[Error extracting DOCX content: {str(e)}]"


def process_single_document(file_path: str, filename: str) -> dict:
    """
    Process a single document and extract its content.

    Args:
        file_path: Path to the file
        filename: Original filename

    Returns:
        Dict with type, filename, and extracted content
    """
    ext = Path(file_path).suffix.lower()

    if ext == '.pdf':
        content = extract_text_from_pdf(file_path)
        doc_type = 'pdf'
    elif ext in ('.docx', '.doc'):
        content = extract_text_from_docx(file_path)
        doc_type = 'docx'
    elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
        content = analyze_image_with_claude_vision(file_path)
        doc_type = 'image'
    else:
        content = f"[Unsupported file type: {ext}]"
        doc_type = 'unknown'

    return {
        'type': doc_type,
        'filename': filename,
        'content': content
    }


def process_loe_supporting_docs(
    file_paths: list[tuple[str, str]],
    session_id: str,
    task_id: str,
    store_permanently: bool = False
) -> dict:
    """
    Process multiple supporting documents for LOE generation.

    Args:
        file_paths: List of tuples (file_path, original_filename)
        session_id: Session identifier
        task_id: Task identifier
        store_permanently: Whether to store in vectorstore for future access

    Returns:
        Dict with success status, processed count, and any errors
    """
    processed_docs = []
    errors = []

    for file_path, filename in file_paths:
        try:
            doc = process_single_document(file_path, filename)
            processed_docs.append(doc)
        except Exception as e:
            errors.append({
                'filename': filename,
                'error': str(e)
            })

    # Store in Redis for immediate LOE generation
    if processed_docs:
        store_docs_in_redis(session_id, task_id, processed_docs)

    # Store in vectorstore if user wants permanent storage
    if store_permanently and processed_docs:
        store_docs_in_vectorstore(session_id, processed_docs)

    return {
        'success': len(errors) == 0,
        'processed_count': len(processed_docs),
        'errors': errors if errors else None
    }


def _redis_key(session_id: str, task_id: str) -> str:
    return f"{LOE_DOCS_PREFIX}{session_id}:{task_id}"


def store_docs_in_redis(session_id: str, task_id: str, docs_content: list[dict]) -> bool:
    """
    Store processed document content in Redis for LOE generation.

    Args:
        session_id: Session identifier
        task_id: Task identifier
        docs_content: List of processed document dicts

    Returns:
        True if stored successfully
    """
    try:
        r = _get_redis()
        key = _redis_key(session_id, task_id)
        r.setex(key, LOE_DOCS_TTL, json.dumps(docs_content))
        return True
    except Exception as e:
        print(f"[error] store_docs_in_redis: {e}")
        return False


def retrieve_docs_from_redis(session_id: str, task_id: str) -> Optional[list[dict]]:
    """
    Retrieve processed document content from Redis.

    Args:
        session_id: Session identifier
        task_id: Task identifier

    Returns:
        List of processed document dicts, or None if not found
    """
    try:
        r = _get_redis()
        key = _redis_key(session_id, task_id)
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"[error] retrieve_docs_from_redis: {e}")
        return None


def cleanup_temp_docs(session_id: str, task_id: str) -> bool:
    """
    Remove temporary document content from Redis after LOE generation.

    Args:
        session_id: Session identifier
        task_id: Task identifier

    Returns:
        True if cleaned up successfully
    """
    try:
        r = _get_redis()
        key = _redis_key(session_id, task_id)
        r.delete(key)
        return True
    except Exception as e:
        print(f"[error] cleanup_temp_docs: {e}")
        return False


def store_docs_in_vectorstore(session_id: str, docs_content: list[dict]) -> dict:
    """
    Store processed documents in vectorstore for permanent access.
    Creates embeddings and stores in loe_supporting_{session_id} collection.

    Args:
        session_id: Session identifier
        docs_content: List of processed document dicts

    Returns:
        Dict with success status and chunk count
    """
    from ..chatbot.vectorestore import process_and_store_documents, get_vectorstore

    collection_name = f"loe_supporting_{session_id}"

    # Convert processed docs to LangChain Document objects
    documents = []
    for doc in docs_content:
        documents.append(Document(
            page_content=doc['content'],
            metadata={
                'doc_type': 'loe_supporting',
                'source': 'user_upload',
                'filename': doc['filename'],
                'file_type': doc['type'],
                'session_id': session_id
            }
        ))

    # Initialize vectorstore for this collection
    get_vectorstore(collection_name)

    # Process and store with embeddings
    result = process_and_store_documents(documents, collection_name)

    return result
