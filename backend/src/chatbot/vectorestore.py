from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredFileLoader
)

from typing import List, Dict, Any, Optional
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text

from ..config import settings
from ..ai_models import MODEL_EMBEDDINGS

# Initialize embeddings
embeddings = OpenAIEmbeddings(model=MODEL_EMBEDDINGS, api_key=settings.OPENAI_API_KEY)

"""
Vectorstore instances are maintained per collection to allow session-scoped storage
without reusing a single global collection.
"""
collection_vectorstores: Dict[str, PGVector] = {}

def get_vectorstore(collection_name: str = "bankruptcy_knowledge"):
    """Get or initialize a PGVector instance for the given collection name."""
    if collection_name in collection_vectorstores:
        return collection_vectorstores[collection_name]
    try:
        vs = PGVector(
            connection=settings.VECTORSTORE_URL,
            embeddings=embeddings,
            collection_name=collection_name
        )
        collection_vectorstores[collection_name] = vs
        print(f"✅ Vectorstore initialized for collection: {collection_name}")
        return vs
    except Exception as e:
        print(f"❌ Failed to initialize vectorstore for '{collection_name}': {e}")
        raise

# Initialize text splitter
# Using smaller chunk_size to ensure we stay well under the 8192 token limit
# 500 characters ≈ 125-200 tokens (safe margin)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

def process_and_store_documents(documents: List[Document], collection_name: str = "bankruptcy_knowledge") -> Dict[str, Any]:
    """
    Process a list of documents and store them in the pgvector database.
    
    Args:
        documents: List of Document objects to process and store
        collection_name: Name of the collection in the vectorstore
        
    Returns:
        Dictionary containing processing results and statistics
    """
    if not documents:
        return {
            "success": True,
            "message": "No documents to store",
            "processed_count": 0,
            "stored_count": 0
        }
    
    try:
        # Get or initialize the vectorstore
        collection_vectorstore = get_vectorstore(collection_name)
        
        # Process documents
        processed_docs = []
        failed_docs = []
        
        for i, doc in enumerate(documents):
            try:
                # Split the document into chunks
                splits = text_splitter.split_documents([doc])
                
                # Add metadata to track source
                for split in splits:
                    if not split.metadata:
                        split.metadata = {}
                    split.metadata.update({
                        "source": doc.metadata.get("source", f"document_{i}"),
                        "document_type": doc.metadata.get("document_type", "unknown"),
                        "chunk_index": len(processed_docs),
                        "total_chunks": len(splits)
                    })
                
                processed_docs.extend(splits)
                
            except Exception as e:
                print(f"Error processing document {i+1}: {str(e)}")
                failed_docs.append({
                    "index": i,
                    "error": str(e),
                    "document": doc
                })
        
        if not processed_docs:
            return {
                "success": False,
                "error": "No documents were successfully processed",
                "processed_count": 0,
                "stored_count": 0,
                "failed_docs": failed_docs
            }
        
        # Store processed documents in vectorstore with batching
        # to avoid exceeding token limits
        try:
            batch_size = 50  # Process 50 chunks at a time
            stored_count = 0

            for i in range(0, len(processed_docs), batch_size):
                batch = processed_docs[i:i + batch_size]
                collection_vectorstore.add_documents(batch)
                stored_count += len(batch)
                print(f"Stored batch {i//batch_size + 1}: {len(batch)} chunks")

            return {
                "success": True,
                "processed_count": len(documents),
                "stored_count": stored_count,
                "collection_name": collection_name,
                "chunk_size": 500,
                "chunk_overlap": 100,
                "failed_docs": failed_docs if failed_docs else None
            }
            
        except Exception as e:
            print(f"Error storing documents in vectorstore: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to store documents: {str(e)}",
                "processed_count": len(documents),
                "stored_count": 0,
                "failed_docs": failed_docs
            }
            
    except Exception as e:
        print(f"Error in process_and_store_documents: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "processed_count": 0,
            "stored_count": 0
        }

def process_uploaded_file(file_path: str, file_type: str, collection_name: str = "bankruptcy_knowledge") -> Dict[str, Any]:
    """
    Process an uploaded file and store it in the vectorstore.

    Args:
        file_path: Path to the uploaded file
        file_type: Type of file (pdf, docx, txt, etc.)
        collection_name: Name of the collection to store in

    Returns:
        Dictionary containing processing results
    """
    try:
        # Load the document based on file type
        if file_type.lower() == "pdf":
            loader = PyPDFLoader(file_path)
        elif file_type.lower() in ["docx", "doc"]:
            loader = Docx2txtLoader(file_path)
        elif file_type.lower() == "txt":
            loader = TextLoader(file_path)
        else:
            # Try unstructured loader for other file types
            loader = UnstructuredFileLoader(file_path)

        # Load the document
        documents = loader.load()

        # Add metadata about the source file
        for doc in documents:
            doc.metadata.update({
                "source": file_path,
                "document_type": file_type.lower(),
                "filename": os.path.basename(file_path)
            })

        # Process and store the documents
        result = process_and_store_documents(documents, collection_name)
        
        # Clean up the temporary file if it was created
        if os.path.exists(file_path) and file_path.startswith(tempfile.gettempdir()):
            os.remove(file_path)
        
        return result
        
    except Exception as e:
        print(f"Error processing uploaded file {file_path}: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to process file: {str(e)}",
            "file_path": file_path,
            "file_type": file_type
        }

def search_vectorstore(query: str, collection_name: str = "bankruptcy_knowledge", k: int = 2) -> List[Document]:
    """
    Search the vectorstore for relevant documents.
    
    Args:
        query: Search query string
        collection_name: Name of the collection to search in
        k: Number of results to return
        
    Returns:
        List of relevant documents
    """
    try:
        collection_vectorstore = get_vectorstore(collection_name)
        
        results = collection_vectorstore.similarity_search(query, k=k)
        return results
        
    except Exception as e:
        print(f"Error searching vectorstore: {str(e)}")
        return []

def clear_collection(collection_name: str) -> Dict[str, Any]:
    """Clear all vectors from a specific collection name.

    This uses direct SQL deletion to remove all documents from the given collection.
    If the collection does not exist, this becomes a no-op.
    """
    try:
        # Use direct SQL deletion to ensure all embeddings are removed
        engine = create_engine(settings.VECTORSTORE_URL)
        
        with engine.connect() as conn:
            # First, check if collection exists and get its UUID
            check_query = text("""
                SELECT uuid FROM langchain_pg_collection 
                WHERE name = :collection_name
            """)
            result = conn.execute(check_query, {"collection_name": collection_name})
            collection_row = result.fetchone()
            
            if not collection_row:
                # Collection doesn't exist, nothing to clear
                print(f"⚠️ Collection '{collection_name}' does not exist, nothing to clear")
                return {"success": True, "collection_name": collection_name, "deleted_count": 0}
            
            collection_uuid = collection_row[0]
            
            # Count chunks before deletion for logging
            count_query = text("""
                SELECT COUNT(*) FROM langchain_pg_embedding 
                WHERE collection_id = :collection_id
            """)
            count_result = conn.execute(count_query, {"collection_id": collection_uuid})
            chunk_count = count_result.scalar() or 0
            
            # Delete all embeddings for this collection
            delete_query = text("""
                DELETE FROM langchain_pg_embedding 
                WHERE collection_id = :collection_id
            """)
            conn.execute(delete_query, {"collection_id": collection_uuid})
            conn.commit()
            
            print(f"✅ Cleared collection '{collection_name}': deleted {chunk_count} chunks")
            return {
                "success": True, 
                "collection_name": collection_name, 
                "deleted_count": chunk_count
            }
    except Exception as e:
        print(f"❌ Error clearing collection '{collection_name}': {e}")
        return {"success": False, "error": str(e), "collection_name": collection_name}


def delete_by_metadata(collection_name: str, doc_type: str) -> Dict[str, Any]:
    """Delete embeddings matching a specific doc_type from a collection.

    This allows updating a single document type without affecting others
    in the same collection.
    """
    try:
        engine = create_engine(settings.VECTORSTORE_URL)

        with engine.connect() as conn:
            check_query = text("""
                SELECT uuid FROM langchain_pg_collection WHERE name = :name
            """)
            result = conn.execute(check_query, {"name": collection_name})
            row = result.fetchone()

            if not row:
                return {"success": True, "deleted_count": 0, "message": "Collection does not exist"}

            collection_uuid = row[0]

            count_query = text("""
                SELECT COUNT(*) FROM langchain_pg_embedding
                WHERE collection_id = :collection_id
                AND cmetadata->>'doc_type' = :doc_type
            """)
            count_result = conn.execute(count_query, {
                "collection_id": collection_uuid,
                "doc_type": doc_type
            })
            chunk_count = count_result.scalar() or 0

            delete_query = text("""
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = :collection_id
                AND cmetadata->>'doc_type' = :doc_type
            """)
            conn.execute(delete_query, {
                "collection_id": collection_uuid,
                "doc_type": doc_type
            })
            conn.commit()

            print(f"✅ Deleted {chunk_count} chunks with doc_type='{doc_type}' from '{collection_name}'")
            return {"success": True, "deleted_count": chunk_count, "doc_type": doc_type}

    except Exception as e:
        print(f"❌ Error deleting by metadata from '{collection_name}': {e}")
        return {"success": False, "error": str(e)}


def store_generated_motion(session_id: str, doc_type: str, content: str, filename: str) -> Dict[str, Any]:
    """Store a generated motion/document in the vectorstore.

    Replaces any existing document of the same doc_type for this session.

    Args:
        session_id: Session ID
        doc_type: Document type (e.g., 'objection_to_claim', 'motion_to_extend')
        content: Full text content of the document
        filename: Original filename

    Returns:
        Dictionary with success status and stored chunk count
    """
    from datetime import datetime
    from langchain_core.documents import Document

    collection_name = f"generated_motions_{session_id}"

    delete_result = delete_by_metadata(collection_name, doc_type)
    if not delete_result.get("success"):
        print(f"⚠️ Warning: Failed to clear previous {doc_type}: {delete_result.get('error')}")

    doc = Document(
        page_content=content,
        metadata={
            "doc_type": doc_type,
            "source": "generated_motion",
            "filename": filename,
            "session_id": session_id,
            "generated_at": datetime.now().isoformat(),
        }
    )

    result = process_and_store_documents([doc], collection_name)

    if result.get("success"):
        print(f"✅ Stored generated {doc_type} for session {session_id}: {result.get('stored_count')} chunks")
    else:
        print(f"❌ Failed to store {doc_type}: {result.get('error')}")

    return result


def load_bankruptcy_knowledge():
    """
    Load bankruptcy knowledge documents from the bankruptcy_knowledge folder into the vectorstore.
    This function processes all documents in the folder and stores them for future retrieval.
    """
    # Test database connection first
    try:
        knowledge_vectorstore = get_vectorstore("bankruptcy_knowledge")
    except Exception as e:
        return {
            "success": False,
            "error": f"Database connection failed: {e}",
            "processed_count": 0,
            "stored_count": 0
        }
    
    # Get the bankruptcy_knowledge directory path
    knowledge_dir = Path("bankruptcy_knowledge")
    
    if not knowledge_dir.exists():
        return {
            "success": False,
            "error": "Bankruptcy knowledge directory not found",
            "processed_count": 0,
            "stored_count": 0
        }
    
    # Get all files in bankruptcy_knowledge directory
    files = list(knowledge_dir.glob("*"))
    
    if not files:
        return {
            "success": False,
            "error": "No files found in bankruptcy_knowledge directory",
            "processed_count": 0,
            "stored_count": 0
        }
    
    # Process each file
    total_processed = 0
    total_stored = 0
    failed_files = []
    
    for file_path in files:
        file_type = file_path.suffix.lower().lstrip('.')
        
        try:
            # Process the file
            result = process_uploaded_file(str(file_path), file_type, "bankruptcy_knowledge")
            
            if result['success']:
                total_processed += result['processed_count']
                total_stored += result['stored_count']
            else:
                failed_files.append({
                    "file": file_path.name,
                    "error": result.get('error', 'Unknown error')
                })
                
        except Exception as e:
            failed_files.append({
                "file": file_path.name,
                "error": str(e)
            })
    
    return {
        "success": total_processed > 0,
        "total_files": len(files),
        "processed_count": total_processed,
        "stored_count": total_stored,
        "failed_files": failed_files if failed_files else None,
        "collection_name": "bankruptcy_knowledge"
    }

def get_all_claims_sorted(collection_name: str) -> List[Document]:
    """
    Retrieve all claim documents from the collection and sort them by claim number in descending order.
    Parses the claim number from "History / Documents{NUMBER}" pattern in the claim text.
    
    Args:
        collection_name: Name of the collection to retrieve claims from
        
    Returns:
        List of documents sorted by claim number (slot) in descending order
    """
    try:
        import re
        # Create a database connection using the vectorstore URL
        engine = create_engine(settings.VECTORSTORE_URL)
        
        with engine.connect() as conn:
            # Query to get all documents from the collection that have History / Documents
            query = text("""
                SELECT 
                    e.document,
                    e.cmetadata
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = :collection_name
                  AND e.document LIKE '%History / Documents%'
            """)
            
            result = conn.execute(query, {"collection_name": collection_name})
            rows = result.fetchall()
            
            documents = []
            for row in rows:
                doc = Document(
                    page_content=row[0],
                    metadata=row[1]
                )
                documents.append(doc)
            
            # Sort documents by extracting claim number from "History / Documents{NUMBER}" pattern
            def extract_claim_number(doc: Document) -> int:
                # Try to extract number from "History / Documents6-" or "History / Documents6"
                text = doc.page_content
                match = re.search(r'History / Documents(\d+)', text)
                if match:
                    return int(match.group(1))
                return 0
            
            # Filter out documents without claim numbers (return 0)
            filtered_docs = [doc for doc in documents if extract_claim_number(doc) > 0]
            
            # Sort by claim number in descending order (6, 5, 4, 3, 2, 1)
            filtered_docs.sort(key=extract_claim_number, reverse=True)
            
            return filtered_docs
            
    except Exception as e:
        print(f"Error retrieving all claims: {str(e)}")
        return []

if __name__ == "__main__":
    # For loading knowledge base
    load_bankruptcy_knowledge()