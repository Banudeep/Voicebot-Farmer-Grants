"""
Build RAG embeddings index for State News data

Creates searchable embeddings from state news articles for semantic search.
Chunks long articles for better retrieval precision.

Output: cache/state_news_index.json
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Paths
BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"

# Input/Output
NEWS_DATA_PATH = CACHE_DIR / "state_news_deep.json"
OUTPUT_PATH = CACHE_DIR / "state_news_index.json"

# Embedding model
EMBED_MODEL = "text-embedding-3-small"

# Chunking config
MAX_CHUNK_CHARS = 1500  # Keep chunks reasonable size for embeddings
OVERLAP_CHARS = 200     # Overlap between chunks for context


def load_news_data() -> Dict[str, Any]:
    """Load state news data"""
    if not NEWS_DATA_PATH.exists():
        raise FileNotFoundError(f"News data not found at {NEWS_DATA_PATH}. Run scraper first.")
    
    with NEWS_DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end in last 20% of chunk
            search_start = end - int(max_chars * 0.2)
            search_text = text[search_start:end]
            
            # Find last sentence boundary
            for pattern in ['. ', '.\n', '? ', '?\n', '! ', '!\n']:
                idx = search_text.rfind(pattern)
                if idx > 0:
                    end = search_start + idx + 1
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start with overlap
        start = end - overlap
        if start <= 0 and len(chunks) > 0:
            break
    
    return chunks


def create_chunks(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create text chunks from news articles for embedding"""
    chunks = []
    
    for state_code, state_data in data.get("states", {}).items():
        state_name = state_data.get("state_name", state_code)
        
        for article in state_data.get("news_items", []):
            headline = article.get("headline", article.get("title", ""))
            full_text = article.get("full_text", "")
            summary = article.get("summary", "")
            url = article.get("url", "")
            date = article.get("date", article.get("listing_date", ""))
            agency = article.get("category", "")
            
            if not headline and not full_text:
                continue
            
            # Build base text for small articles
            if len(full_text) <= MAX_CHUNK_CHARS:
                text = f"{headline}\n\n{full_text}" if full_text else headline
                chunks.append({
                    "state_code": state_code,
                    "state_name": state_name,
                    "headline": headline,
                    "url": url,
                    "date": date,
                    "agency": agency,
                    "text": text,
                    "chunk_index": 0,
                    "total_chunks": 1
                })
            else:
                # Chunk large articles
                article_chunks = chunk_text(full_text)
                for idx, chunk_text_content in enumerate(article_chunks):
                    # Prepend headline to first chunk
                    if idx == 0:
                        text = f"{headline}\n\n{chunk_text_content}"
                    else:
                        text = f"{headline} (continued)\n\n{chunk_text_content}"
                    
                    chunks.append({
                        "state_code": state_code,
                        "state_name": state_name,
                        "headline": headline,
                        "url": url,
                        "date": date,
                        "agency": agency,
                        "text": text,
                        "chunk_index": idx,
                        "total_chunks": len(article_chunks)
                    })
    
    return chunks


def build_embeddings(chunks: List[Dict[str, Any]], batch_size: int = 50) -> List[Dict[str, Any]]:
    """Build embeddings for all chunks"""
    if not HAS_OPENAI:
        print("⚠️ OpenAI not installed, saving without embeddings")
        return chunks
    
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY not set, saving without embeddings")
        return chunks
    
    client = OpenAI(api_key=api_key)
    
    print(f"📊 Creating embeddings for {len(chunks)} chunks...")
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["text"] for c in batch]
        
        try:
            response = client.embeddings.create(
                model=EMBED_MODEL,
                input=texts
            )
            
            for j, embedding_data in enumerate(response.data):
                chunks[i+j]["embedding"] = embedding_data.embedding
            
            print(f"  Processed {min(i+batch_size, len(chunks))}/{len(chunks)}")
        except Exception as e:
            print(f"  Error on batch {i}: {e}")
            continue
    
    return chunks


def main():
    print("=" * 60)
    print("State News RAG Index Builder")
    print("=" * 60)
    
    # Load data
    print("\n📂 Loading news data...")
    data = load_news_data()
    total_states = len(data.get("states", {}))
    total_articles = sum(
        len(s.get("news_items", []))
        for s in data.get("states", {}).values()
    )
    print(f"  Found {total_articles} articles across {total_states} states")
    
    # Create chunks
    print("\n📝 Creating chunks...")
    chunks = create_chunks(data)
    print(f"  Created {len(chunks)} chunks")
    
    # Build embeddings
    print("\n🔧 Building embeddings...")
    chunks_with_embeddings = build_embeddings(chunks)
    
    # Count successful embeddings
    embedded = sum(1 for c in chunks_with_embeddings if c.get("embedding"))
    
    # Save index
    index = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_chunks": len(chunks_with_embeddings),
            "chunks_with_embeddings": embedded,
            "model": EMBED_MODEL,
            "source_file": str(NEWS_DATA_PATH)
        },
        "chunks": chunks_with_embeddings
    }
    
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    
    print(f"\n✅ Saved index to {OUTPUT_PATH}")
    print(f"   Total chunks: {len(chunks_with_embeddings)}")
    print(f"   With embeddings: {embedded}")
    
    # Print sample
    print("\n📊 Sample chunks:")
    for chunk in chunks[:3]:
        print(f"  • [{chunk['state_code']}] {chunk['headline'][:50]}...")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
