"""
Build embeddings index for farmers.gov grants RAG system.

Similar to corn_guide_tools pattern, this creates searchable embeddings
for all grant information to enable semantic search queries.
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


EMBED_MODEL = os.getenv("GRANTS_EMBED_MODEL", "text-embedding-3-small")

BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

GRANTS_DATA_PATH = CACHE_DIR / "farmers_grants_comprehensive.json"
INDEX_PATH = CACHE_DIR / "farmers_grants_index.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@dataclass
class GrantChunk:
    """A searchable chunk of grant information"""
    id: str
    grant_id: str
    grant_name: str
    chunk_type: str  # 'overview', 'eligibility', 'funding', 'application', 'deadline'
    text: str
    embedding: List[float]
    metadata: Dict[str, Any]


def _create_grant_chunks(grants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Create searchable chunks from grant data.
    Each grant is split into multiple chunks for better retrieval.
    """
    chunks = []
    chunk_id = 0
    
    for grant in grants:
        grant_id = grant['id']
        grant_name = grant['name']
        acronym = grant.get('acronym', '')
        agency = grant.get('agency', 'USDA')
        program_type = grant.get('program_type', '')
        
        # Chunk 1: Overview
        overview_text = f"{grant_name} ({acronym})\n"
        overview_text += f"Agency: {agency}\n"
        overview_text += f"Program Type: {program_type}\n"
        overview_text += f"Description: {grant.get('description', '')}\n"
        
        # Add keywords
        if grant.get('keywords'):
            overview_text += f"Keywords: {', '.join(grant['keywords'])}\n"
        
        # Add beneficiaries
        if grant.get('beneficiaries'):
            overview_text += f"Beneficiaries: {', '.join(grant['beneficiaries'])}\n"
        
        chunks.append({
            "id": f"{grant_id}_overview_{chunk_id}",
            "grant_id": grant_id,
            "grant_name": grant_name,
            "chunk_type": "overview",
            "text": overview_text,
            "metadata": {
                "agency": agency,
                "program_type": program_type,
                "acronym": acronym
            }
        })
        chunk_id += 1
        
        # Chunk 2: Deadline Information
        deadline_info = grant.get('deadline_info', {})
        deadline_text = f"{grant_name} - Deadline Information\n"
        deadline_text += f"Deadline Type: {deadline_info.get('type', 'unknown')}\n"
        
        if deadline_info.get('national_deadline'):
            deadline_text += f"National Deadline: {deadline_info['national_deadline']}\n"
        
        if deadline_info.get('description'):
            deadline_text += f"{deadline_info['description']}\n"
        
        if deadline_info.get('has_state_variations'):
            deadline_text += "State-specific deadlines may vary. Contact local USDA Service Center.\n"
        
        if deadline_info.get('loss_years'):
            deadline_text += f"Covers losses from: {', '.join(deadline_info['loss_years'])}\n"
        
        chunks.append({
            "id": f"{grant_id}_deadline_{chunk_id}",
            "grant_id": grant_id,
            "grant_name": grant_name,
            "chunk_type": "deadline",
            "text": deadline_text,
            "metadata": {
                "agency": agency,
                "deadline": deadline_info.get('national_deadline'),
                "deadline_type": deadline_info.get('type')
            }
        })
        chunk_id += 1
        
        # Chunk 3: Eligibility
        if grant.get('eligibility'):
            eligibility = grant['eligibility']
            eligibility_text = f"{grant_name} - Eligibility Requirements\n"
            
            if eligibility.get('description'):
                eligibility_text += f"{eligibility['description']}\n"
            
            if eligibility.get('producer_types'):
                eligibility_text += f"Producer Types: {', '.join(eligibility['producer_types'])}\n"
            
            if eligibility.get('eligible_commodities'):
                eligibility_text += f"Eligible Commodities: {', '.join(eligibility['eligible_commodities'])}\n"
            
            if eligibility.get('eligible_crops'):
                eligibility_text += f"Eligible Crops: {', '.join(eligibility['eligible_crops'])}\n"
            
            if eligibility.get('underserved_categories'):
                eligibility_text += f"Special consideration for: {', '.join(eligibility['underserved_categories'])}\n"
            
            if eligibility.get('land_ownership'):
                eligibility_text += f"Land Ownership: {eligibility['land_ownership']}\n"
            
            if eligibility.get('income_limits'):
                eligibility_text += "Income limits apply. "
                if eligibility.get('agi_limit'):
                    eligibility_text += f"AGI limit: ${eligibility['agi_limit']}\n"
            
            if eligibility.get('qualifying_events'):
                eligibility_text += f"Qualifying Events: {', '.join(eligibility['qualifying_events'])}\n"
            
            chunks.append({
                "id": f"{grant_id}_eligibility_{chunk_id}",
                "grant_id": grant_id,
                "grant_name": grant_name,
                "chunk_type": "eligibility",
                "text": eligibility_text,
                "metadata": {
                    "agency": agency,
                    "producer_types": eligibility.get('producer_types', [])
                }
            })
            chunk_id += 1
        
        # Chunk 4: Funding Information
        if grant.get('funding'):
            funding = grant['funding']
            funding_text = f"{grant_name} - Funding Information\n"
            
            if funding.get('description'):
                funding_text += f"{funding['description']}\n"
            
            if funding.get('cost_share_percentage'):
                funding_text += f"Cost Share: {funding['cost_share_percentage']}%\n"
            
            if funding.get('maximum_payment'):
                funding_text += f"Maximum Payment: {funding['maximum_payment']}\n"
            
            if funding.get('advance_payment_available'):
                funding_text += "Advance payments available.\n"
            
            if funding.get('underserved_premium'):
                funding_text += "Higher payment rates available for beginning farmers, socially disadvantaged, veterans, and limited resource producers.\n"
            
            if funding.get('payment_structure'):
                funding_text += f"Payment Structure: {funding['payment_structure']}\n"
            
            if funding.get('payment_calculation'):
                funding_text += f"Payment Calculation: {funding['payment_calculation']}\n"
            
            chunks.append({
                "id": f"{grant_id}_funding_{chunk_id}",
                "grant_id": grant_id,
                "grant_name": grant_name,
                "chunk_type": "funding",
                "text": funding_text,
                "metadata": {
                    "agency": agency,
                    "has_cost_share": funding.get('cost_share_percentage') is not None
                }
            })
            chunk_id += 1
        
        # Chunk 5: Application Process
        if grant.get('application'):
            application = grant['application']
            app_text = f"{grant_name} - Application Process\n"
            
            if application.get('description'):
                app_text += f"{application['description']}\n"
            
            if application.get('process'):
                app_text += f"Process: {application['process']}\n"
            
            if application.get('submission_method'):
                app_text += f"Submission Methods: {', '.join(application['submission_method'])}\n"
            
            if application.get('required_forms'):
                forms = application['required_forms']
                form_ids = [f.get('form_id') or f for f in forms if f]
                if form_ids:
                    app_text += f"Required Forms: {', '.join(form_ids)}\n"
            
            if application.get('approval_process'):
                app_text += f"Approval Process: {application['approval_process']}\n"
            
            chunks.append({
                "id": f"{grant_id}_application_{chunk_id}",
                "grant_id": grant_id,
                "grant_name": grant_name,
                "chunk_type": "application",
                "text": app_text,
                "metadata": {
                    "agency": agency
                }
            })
            chunk_id += 1
        
        # Chunk 6: Special Initiatives (if any)
        if grant.get('special_initiatives'):
            for initiative in grant['special_initiatives']:
                init_text = f"{grant_name} - {initiative['name']}\n"
                init_text += f"{initiative.get('description', '')}\n"
                
                if initiative.get('additional_funding'):
                    init_text += "Provides additional funding opportunities.\n"
                
                chunks.append({
                    "id": f"{grant_id}_initiative_{chunk_id}",
                    "grant_id": grant_id,
                    "grant_name": grant_name,
                    "chunk_type": "special_initiative",
                    "text": init_text,
                    "metadata": {
                        "agency": agency,
                        "initiative_name": initiative['name']
                    }
                })
                chunk_id += 1
    
    return chunks


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Get embeddings for a list of texts using OpenAI embeddings."""
    embeddings: List[List[float]] = []
    batch_size = 64
    
    print(f"   Embedding {len(texts)} chunks...")
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        for item in resp.data:
            embeddings.append(item.embedding)
        print(f"   Progress: {min(i + batch_size, len(texts))}/{len(texts)}")
    
    return embeddings


def build_index():
    """Build embeddings index from grants data"""
    print("🔨 Building grants embeddings index...\n")
    
    # Load grants data
    if not GRANTS_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Grants data not found at {GRANTS_DATA_PATH}. "
            "Run build_grants_database.py first."
        )
    
    print(f"   Loading grants data from {GRANTS_DATA_PATH}")
    with GRANTS_DATA_PATH.open('r', encoding='utf-8') as f:
        data = json.load(f)
    
    grants = data['grants']
    print(f"   Loaded {len(grants)} grants")
    
    # Create chunks
    print(f"   Creating searchable chunks...")
    raw_chunks = _create_grant_chunks(grants)
    print(f"   Created {len(raw_chunks)} chunks")
    
    # Generate embeddings
    texts = [c["text"] for c in raw_chunks]
    embeds = _embed_texts(texts)
    
    # Build index
    print(f"   Building index...")
    chunks: List[GrantChunk] = []
    for c, e in zip(raw_chunks, embeds):
        chunks.append(
            GrantChunk(
                id=c["id"],
                grant_id=c["grant_id"],
                grant_name=c["grant_name"],
                chunk_type=c["chunk_type"],
                text=c["text"],
                embedding=e,
                metadata=c["metadata"]
            )
        )
    
    index = {
        "model": EMBED_MODEL,
        "grants_data_path": str(GRANTS_DATA_PATH),
        "total_grants": len(grants),
        "total_chunks": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }
    
    # Save index
    print(f"   Saving index to {INDEX_PATH}")
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f)
    
    print(f"\n✅ Index built successfully!")
    print(f"   📁 File: {INDEX_PATH}")
    print(f"   📊 Total grants: {len(grants)}")
    print(f"   📦 Total chunks: {len(chunks)}")
    print(f"   🔍 Embedding model: {EMBED_MODEL}")
    
    return index


if __name__ == "__main__":
    build_index()
