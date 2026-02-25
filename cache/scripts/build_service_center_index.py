"""
Build RAG embeddings index for Service Center data

Creates searchable embeddings from the scraped service center data
so the voicebot can semantically search for county contacts.

Output: cache/service_centers_index.json
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Paths
BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"

# Input/Output
SERVICE_CENTERS_PATH = CACHE_DIR / "service_centers_all.json"
SERVICE_CENTERS_SAMPLE = CACHE_DIR / "service_centers_full.json"  # Fallback to sample data
OUTPUT_PATH = CACHE_DIR / "service_centers_index.json"

# Embedding model
EMBED_MODEL = "text-embedding-3-small"


def load_service_centers() -> Dict[str, Any]:
    """Load service center data"""
    if SERVICE_CENTERS_PATH.exists():
        path = SERVICE_CENTERS_PATH
    elif SERVICE_CENTERS_SAMPLE.exists():
        path = SERVICE_CENTERS_SAMPLE
    else:
        raise FileNotFoundError("No service center data found. Run scraper first.")
    
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def create_chunks(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create text chunks from service center data for embedding"""
    chunks = []
    
    for key, county_data in data.get("counties", {}).items():
        if "error" in county_data:
            continue  # Skip failed scrapes
        
        state_code = county_data.get("state_code", "")
        county_name = county_data.get("county", "")
        url = county_data.get("url", "")
        
        # Build searchable text
        text_parts = [
            f"{county_name}, {state_code}",
            f"{county_name} County {state_code} USDA service center"
        ]
        
        # Add addresses
        addresses = county_data.get("addresses", [])
        if addresses:
            text_parts.append(f"Address: {addresses[0]}")
        
        # Add contact emails
        emails = county_data.get("emails", [])
        if emails:
            # Filter out generic emails
            specific_emails = [e for e in emails if not any(
                x in e.lower() for x in ["general", "servicedesk", "homeloans"]
            )]
            if specific_emails:
                text_parts.append(f"Contact: {', '.join(specific_emails[:3])}")
        
        # Add phones
        phones = county_data.get("phones", [])
        if phones:
            # Filter out obviously wrong numbers
            valid_phones = [p for p in phones if len(p.replace("-", "").replace(".", "")) == 10]
            if valid_phones:
                text_parts.append(f"Phone: {valid_phones[0]}")
        
        # Add agencies
        agencies = county_data.get("agencies", [])
        if agencies:
            text_parts.append(f"Agencies: {', '.join(agencies)}")
        
        text = " | ".join(text_parts)
        
        chunks.append({
            "key": key,
            "state_code": state_code,
            "county": county_name,
            "url": url,
            "text": text,
            "emails": emails[:5],
            "phones": phones[:3],
            "addresses": addresses[:2]
        })
    
    return chunks


def build_embeddings(chunks: List[Dict[str, Any]], batch_size: int = 100) -> List[Dict[str, Any]]:
    """Build embeddings for all chunks"""
    if not HAS_OPENAI:
        print("⚠️ OpenAI not installed, skipping embeddings")
        return chunks
    
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY not set, skipping embeddings")
        return chunks
    
    client = OpenAI(api_key=api_key)
    
    print(f"📊 Creating embeddings for {len(chunks)} chunks...")
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["text"] for c in batch]
        
        response = client.embeddings.create(
            model=EMBED_MODEL,
            input=texts
        )
        
        for j, embedding_data in enumerate(response.data):
            chunks[i+j]["embedding"] = embedding_data.embedding
        
        print(f"  Processed {min(i+batch_size, len(chunks))}/{len(chunks)}")
    
    return chunks


def main():
    print("=" * 60)
    print("Service Center RAG Index Builder")
    print("=" * 60)
    
    # Load data
    print("\n📂 Loading service center data...")
    data = load_service_centers()
    print(f"  Found {len(data.get('counties', {}))} counties")
    
    # Create chunks
    print("\n📝 Creating chunks...")
    chunks = create_chunks(data)
    print(f"  Created {len(chunks)} chunks")
    
    # Build embeddings
    print("\n🔧 Building embeddings...")
    chunks_with_embeddings = build_embeddings(chunks)
    
    # Save index
    index = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_chunks": len(chunks_with_embeddings),
            "model": EMBED_MODEL
        },
        "chunks": chunks_with_embeddings
    }
    
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    
    print(f"\n✅ Saved index to {OUTPUT_PATH}")
    
    # Print sample
    print("\n📊 Sample chunks:")
    for chunk in chunks[:3]:
        print(f"  • {chunk['key']}: {chunk['text'][:80]}...")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
