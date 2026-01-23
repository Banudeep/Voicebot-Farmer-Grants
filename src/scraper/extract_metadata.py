import asyncio
import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List

# Add src to path to import existing tools
current_dir = Path(__file__).parent
src_dir = current_dir.parent
sys.path.append(str(src_dir))

# Import extraction logic
from mcp_tools.form_tools import _get_available_forms, _get_form_schema

def classify_field(field: Dict[str, Any], form_name: str) -> str:
    """Classify a field as 'Farmer' or 'Official' based on ID and Description."""
    desc = (field.get("description") or "").lower()
    fid = field.get("id", "").lower()
    
    # 1. SPECIAL CASE: AD-1069 - Part A only
    if "ad1069" in form_name.lower() or "ad-1069" in form_name.lower():
        # Heuristic: Part B is usually explicitly labeled or follows Part A
        # For this specific form, we want items 2-10 approx.
        # Exclude signatures and FSA sections
        if "fsa use" in desc or "nrcs use" in desc:
            return "Official"
        if "part b" in desc:
            return "Official"

    # 2. STRONG Indicators of Official Use
    official_keywords = [
        "office use", "official use", "agency use", "fsa use", "nrcs use",
        "contracting officer", "cotr", "coc adjusted", "coc use", "coc signature",
        "approved by", "signature of ccc", "signature of nrcs", "signature of approving",
        "date received", "date returned", "date referred", "date signed", "signature date",
        "application number", "contract number", "order number",
        "fiscal year", "recording state", "recording county",
        "weighted county yield", "weighted insurance",
        "reviewer", "remarks", "disapproved", "action completion",
        "vendor", "contractor", "payment due", "amount due",
        "state code", "county code"
    ]
    
    # Specific ID patterns for official use
    official_id_patterns = [
        r"coc", r"adjust", r"offic", r"signature", r"dateLbl", r"confNbr", r"custNameLbl"
    ]

    for k in official_keywords:
        if k in desc:
            return "Official"
            
    for p in official_id_patterns:
        if re.search(p, fid):
            # Double check description doesn't say "Enter your name" or "Producer"
            if "enter your" not in desc and "producer" not in desc and "applicant" not in desc:
                return "Official"

    # 3. Indicators of Farmer Use
    farmer_keywords = [
        "producer", "enter your", "applicant", "participant", "request",
        "farm number", "tract number", "telephone", "address", 
        "email", "social security", "tax id", "ssn", "ein",
        "crop", "acres", "production", "livestock", "quantity", 
        "inventory", "sales", "revenue", "commodity",
        "date of birth", "zip code"
    ]
    
    for k in farmer_keywords:
        if k in desc:
            return "Farmer"

    # 4. Fallback
    # If description is very short or looks like a label "A.", "B.", it's likely noise/official
    if len(desc) < 5:
        return "Official"
        
    return "Farmer" # Tentative Default

def get_category(field: Dict[str, Any]) -> str:
    """Categorize a Farmer field."""
    desc = (field.get("description") or "").lower()
    fid = field.get("id", "").lower()
    
    if any(x in desc or x in fid for x in ["name", "address", "phone", "email", "zip", "contact", "city", "state"]):
        return "Contact Information"
    elif any(x in desc or x in fid for x in ["ssn", "tax", "security", "identification", "id number", "ein"]):
        return "Identification"
    elif any(x in desc or x in fid for x in ["farm", "tract", "crop", "acre", "commodity", "livestock", "production", "land", "yield"]):
        return "Farm Details"
    elif any(x in desc or x in fid for x in ["date", "year", "month"]):
        return "Dates"
    
    return "General Information"

async def main():
    print("Starting Form Analysis...")
    forms = _get_available_forms()
    print(f"Found {len(forms)} forms: {forms}")
    
    static_descriptions = {}
    
    # Titles and Purposes (Manually curated or extracted could be improved)
    # Using the existing knowledge base for titling
    metadata_db = {
        "AD-2100.pdf": {
            "title": "AD-2100: Request for Information or Documentation",
            "purpose": "Request for additional information/documentation from program participants.",
            "next_steps": "Submit to your local USDA Service Center."
        },
        "AD-3117.pdf": {
            "title": "AD-3117: Conservation Program Application",
            "purpose": "Application for USDA conservation programs (CSP, EQIP, etc.).",
            "next_steps": "Submit to NRCS office. Site visit may be required."
        },
        "AD1069.pdf": {
            "title": "AD-1069: Request for Good Faith Relief",
            "purpose": "Application for relief from Wetland Conservation (WC) violations (Part A only).",
            "next_steps": "Complete Part A and submit to your local FSA office. NRCS will complete Part B."
        },
        "BCAP-1.pdf": {
            "title": "BCAP-1: Biomass Crop Assistance Program Application",
            "purpose": "Application for Biomass Crop Assistance Program.",
            "next_steps": "Submit to FSA office with land eligibility docs."
        }
    }

    for form_name in forms:
        try:
            print(f"Processing {form_name}...")
            schema = _get_form_schema(form_name)
            if "error" in schema:
                print(f"  Error reading {form_name}: {schema['error']}")
                continue
            
            farmer_fields = []
            
            for fid, data in schema.items():
                if data['type'] == '/Tx': # Text fields only
                    field_obj = {
                        "id": fid,
                        "description": data.get('description', ''),
                        "name": data.get('name', '')
                    }
                    
                    classification = classify_field(field_obj, form_name)
                    
                    if classification == "Farmer":
                        category = get_category(field_obj)
                        farmer_fields.append({**field_obj, "category": category})
            
            count = len(farmer_fields)
            estimated_minutes = max(1, round(count * 0.5))
            
            # Categorize counts
            cat_counts = {}
            for f in farmer_fields:
                c = f["category"]
                cat_counts[c] = cat_counts.get(c, 0) + 1
            
            # Merge with metadata
            base_meta = metadata_db.get(form_name, {
                "title": f"USDA Form: {form_name}",
                "purpose": "USDA Program Form",
                "next_steps": "Submit to USDA Service Center."
            })
            
            static_descriptions[form_name] = {
                **base_meta,
                "field_count": count,
                "estimated_time": f"{estimated_minutes} minutes",
                "categories": cat_counts
            }
            
        except Exception as e:
            print(f"  Failed to process {form_name}: {e}")

    # Output valid Python dictionary string for easy copy-pasting
    print("\n\n# COPY THIS INTO form_tools.py")
    print("STATIC_FORM_DESCRIPTIONS = " + json.dumps(static_descriptions, indent=4))
    
    # Also save to JSON file in scraper dir
    output_path = current_dir / "form_metadata.json"
    with open(output_path, "w") as f:
        json.dump(static_descriptions, f, indent=4)
    print(f"\nSaved metadata to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
