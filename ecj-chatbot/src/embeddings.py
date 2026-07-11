"""
EuGH Case Law Embeddings Module

This module handles creating and managing vector embeddings for case law documents.
"""

import json
from pathlib import Path
from typing import Iterator

import sys

try:
    import chromadb
    from chromadb.config import Settings
except Exception as e:
    if "unable to infer type" in str(e) or "ConfigError" in str(e):
        print(
            f"\nERROR: chromadb is incompatible with Python {sys.version_info.major}.{sys.version_info.minor}.\n"
            "This is a known pydantic/chromadb compatibility issue.\n"
            "Please use Python 3.11-3.13, or upgrade chromadb:\n"
            "  pip install --upgrade chromadb\n"
        )
    raise

from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from data_acquisition import CaseLawDocument, load_documents_from_disk


# Default embedding model - multilingual for German/English support
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Alternative models:
# - "sentence-transformers/distiluse-base-multilingual-cased-v2" (faster)
# - "intfloat/multilingual-e5-large" (higher quality)
# - "deutsche-telekom/gbert-large-paraphrase-cosine" (German-optimized)


class CaseLawVectorStore:
    """
    Vector store for EuGH case law documents using ChromaDB.
    """

    def __init__(
        self,
        persist_directory: str | Path,
        collection_name: str = "ecj_case_law",
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        """
        Initialize the vector store.

        Args:
            persist_directory: Directory for ChromaDB persistence
            collection_name: Name of the ChromaDB collection
            embedding_model: HuggingFace model name for embeddings
            chunk_size: Size of text chunks in characters
            chunk_overlap: Overlap between chunks
        """

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize embedding model
        print(f"Loading embedding model: {embedding_model}")
        self.embedding_model = SentenceTransformer(embedding_model)

        # Initialize ChromaDB in embedded/local mode.
        # Do not switch to HttpClient without first addressing CVE-2026-45829
        # (unauthenticated RCE in the ChromaDB Python server, unpatched
        # upstream). See SECURITY.md.
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "EuGH Case Law Vector Store"}
        )

    def _chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """

        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings
                for sep in ['. ', '.\n', '? ', '!\n']:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep != -1:
                        end = start + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.chunk_overlap

        return chunks

    def add_document(self, doc: CaseLawDocument) -> int:
        """
        Add a case law document to the vector store.

        Args:
            doc: CaseLawDocument to add

        Returns:
            Number of chunks added
        """

        # Chunk the document text
        chunks = self._chunk_text(doc.text)

        # Prepare data for ChromaDB
        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc.celex}_chunk_{i}"

            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "celex": doc.celex,
                "title": doc.title[:500] if doc.title else "",  # Truncate for metadata
                "date": doc.date,
                "case_number": doc.case_number or "",
                "court": doc.court,
                "document_type": doc.document_type,
                "eurlex_url": doc.eurlex_url,
                "curia_url": doc.curia_url or "",
                "ecli": doc.ecli or "",
                "language": getattr(doc, 'language', 'DE'),  # Document language
                "chunk_index": i,
                "total_chunks": len(chunks)
            })

        # Add to ChromaDB
        if ids:
            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )

        return len(chunks)

    def add_documents_batch(
        self,
        documents: Iterator[CaseLawDocument],
        batch_size: int = 100
    ) -> int:
        """
        Add multiple documents to the vector store.

        Args:
            documents: Iterator of CaseLawDocument objects
            batch_size: Number of documents to process before committing

        Returns:
            Total number of chunks added
        """

        total_chunks = 0

        for doc in tqdm(documents, desc="Indexing documents"):
            try:
                chunks_added = self.add_document(doc)
                total_chunks += chunks_added
            except Exception as e:
                print(f"Failed to index {doc.celex}: {e}")

        print(f"Indexed {total_chunks} chunks total")
        return total_chunks

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_dict: dict | None = None
    ) -> list[dict]:
        """
        Search for relevant case law chunks.

        Args:
            query: Search query
            n_results: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of search results with metadata
        """

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_dict
        )

        search_results = []

        if results and results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                result = {
                    "text": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None
                }
                search_results.append(result)

        return search_results

    def get_unique_cases(self, results: list[dict]) -> list[dict]:
        """
        Deduplicate results to get unique cases.

        Args:
            results: Search results

        Returns:
            List of unique cases with their best-matching chunks
        """

        seen_celex = {}

        for result in results:
            celex = result['metadata'].get('celex', '')
            if celex and celex not in seen_celex:
                seen_celex[celex] = result

        return list(seen_celex.values())

    def get_collection_stats(self) -> dict:
        """Get statistics about the collection."""

        count = self.collection.count()

        return {
            "total_chunks": count,
            "collection_name": self.collection.name,
            "persist_directory": str(self.persist_directory)
        }


def build_index_from_data_dir(
    data_dir: Path,
    index_dir: Path,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
) -> CaseLawVectorStore:
    """
    Build a vector store index from downloaded case law data.

    Args:
        data_dir: Directory containing JSON case documents
        index_dir: Directory for the vector store
        embedding_model: Embedding model to use

    Returns:
        Initialized CaseLawVectorStore
    """

    store = CaseLawVectorStore(
        persist_directory=index_dir,
        embedding_model=embedding_model
    )

    documents = load_documents_from_disk(data_dir)
    store.add_documents_batch(documents)

    stats = store.get_collection_stats()
    print(f"Index built: {stats}")

    return store


if __name__ == "__main__":
    # Example: Build index from downloaded data
    base_dir = Path(__file__).parent.parent

    data_dir = base_dir / "data" / "cases"
    index_dir = base_dir / "data" / "index"

    if data_dir.exists() and any(data_dir.glob("*.json")):
        store = build_index_from_data_dir(data_dir, index_dir)

        # Test search
        results = store.search("Datenschutz Grundrechte")
        print(f"\nSearch results for 'Datenschutz Grundrechte':")
        for r in results[:3]:
            print(f"  - {r['metadata'].get('celex')}: {r['text'][:200]}...")
    else:
        print(f"No data found in {data_dir}. Run data_acquisition.py first.")
