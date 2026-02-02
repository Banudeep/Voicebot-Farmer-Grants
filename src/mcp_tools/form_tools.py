"""
Form Filling Tool for USDA Voicebot (Dynamic Generic Version)

Collects form data via voice, fills PDF (dynamically inspected), and emails to customer.
"""

import json
import smtplib
import os
import io
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject, DictionaryObject, TextStringObject, NumberObject
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Base directory for documents (project root)
DOCUMENT_DIR = Path(__file__).resolve().parent.parent.parent / "Document"

# In-memory storage for form data
# Structure: { form_name: { field_id: value } }
_FORM_DATA = {}

# Cache for form schemas (to track total field count for progress)
# Structure: { form_name: { field_id: {...} } }
_FORM_SCHEMAS_CACHE = {}

# Cache for the exact count of farmer-relevant fields (set by get_form_fields)
# Structure: { form_name: int }
_FARMER_FIELD_COUNT = {}

# Queue for pending form updates to broadcast to UI
# Each item: { 'type': 'form_update', 'form_name': str, 'field_updates': dict, 'action': str }
_PENDING_UPDATES = []


# Track active form session for auto-open/close
_ACTIVE_FORM = None
# Track current session ID for email reference
_CURRENT_SESSION_ID = None

def set_session_id(session_id: str):
    """Set the current session ID for reference in emails."""
    global _CURRENT_SESSION_ID
    _CURRENT_SESSION_ID = session_id
    
def _load_static_descriptions():
    """Load pre-calculated form metadata from scraper output."""
    try:
        metadata_path = Path(__file__).resolve().parent.parent / "scraper" / "form_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load form metadata: {e}")
    return {}

STATIC_FORM_DESCRIPTIONS = _load_static_descriptions()

def _get_available_forms() -> List[str]:
    """List available PDF forms in the Document directory."""
    if not DOCUMENT_DIR.exists():
        return []
    return [f.name for f in DOCUMENT_DIR.glob("*.pdf")]

def _get_form_schema(form_name: str) -> Dict[str, Any]:
    """
    Dynamically extract form fields from the PDF.
    Returns a dict mapping short_names (simplified) to full field data.
    """
    if not HAS_PYPDF:
        return {"error": "pypdf not installed"}
    
    # Check cache first (OPTIMIZATION)
    if form_name in _FORM_SCHEMAS_CACHE:
        return _FORM_SCHEMAS_CACHE[form_name]
    
    pdf_path = DOCUMENT_DIR / form_name
    if not pdf_path.exists():
        # Help the LLM self-correct by listing actual available forms
        available = [f.name for f in DOCUMENT_DIR.glob("*.pdf")]
        return {
            "error": f"Form '{form_name}' not found. Available forms: {', '.join(available)}",
            "available_forms": available
        }

    try:
        reader = PdfReader(str(pdf_path))
        fields = reader.get_fields()
        
        schema = {}
        if fields:
            for field_name, field_data in fields.items():
                # Skip non-terminal fields if necessary, or just include all
                field_type = field_data.get('/FT', '')
                tooltip = field_data.get('/TU', '')  # Help text
                
                # Create a simple ID for the LLM to use if the PDF name is complex
                # For now, we use the actual PDF field name as the ID, 
                # but we could simplify it if needed.
                schema[field_name] = {
                    "type": field_type,
                    "description": tooltip or field_name,
                    "full_name": field_name
                }
        
        # Cache the schema for progress tracking
        _FORM_SCHEMAS_CACHE[form_name] = schema
        return schema
    except Exception as e:
        return {"error": f"Failed to read form schemas: {e}"}

def _get_form_data(form_name: str) -> dict:
    """Get current form data for a specific form"""
    if form_name not in _FORM_DATA:
        _FORM_DATA[form_name] = {}
    return _FORM_DATA[form_name]

def _get_form_progress(form_name: str) -> Dict[str, int]:
    """Get form filling progress: filled count vs total farmer-relevant fields.
    
    Uses the cached count from get_form_fields to ensure the total matches
    exactly what the voicebot asks the farmer.
    """
    form_data = _get_form_data(form_name)
    filled = len(form_data)
    
    # Use cached farmer field count (set by get_form_fields)
    # This ensures the counter matches exactly what the voicebot asks
    total = _FARMER_FIELD_COUNT.get(form_name, filled + 5)  # Fallback if not yet cached
    
    return {"filled": filled, "total": max(total, filled)}


def get_active_form_state() -> Dict[str, Any]:
    """Get the current active form state for session restore.
    
    Called when a client reconnects to restore the form panel if a form was active.
    """
    if not _ACTIVE_FORM:
        return None
    
    form_data = _get_form_data(_ACTIVE_FORM)
    return {
        'type': 'form_panel',
        'action': 'open',
        'form_name': _ACTIVE_FORM,
        'fields': dict(form_data)
    }

async def list_available_forms() -> Dict[str, Any]:
    """List all forms available for filling."""
    forms = _get_available_forms()
    return {
        "success": True,
        "forms": forms,
        "count": len(forms) 
    }

async def get_form_fields(form_name: str) -> Dict[str, Any]:
    """
    Get the list of fields for a specific form so the AI knows what to ask for.
    Also opens the form panel in the UI.
    """
    global _ACTIVE_FORM
    
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}
    
    # Open the form panel immediately when form fields are requested
    # This shows the PDF viewer as soon as the first question is about to be asked
    if _ACTIVE_FORM != form_name:
        _ACTIVE_FORM = form_name
        form_data = _get_form_data(form_name)
        progress = _get_form_progress(form_name)
        _PENDING_UPDATES.append({
            'type': 'form_panel',
            'action': 'open',
            'form_name': form_name,
            'fields': dict(form_data),  # Existing fields (if any)
            'progress': progress  # {filled: N, total: M}
        })
    
    # Use shared helper to get farmer-relevant fields
    fields_summary = _get_farmer_fields(schema, form_name)
    
    # Cache the count so progress bar shows the exact same number
    _FARMER_FIELD_COUNT[form_name] = len(fields_summary)
            
    return {
        "success": True,
        "form_name": form_name,
        "fields": fields_summary,
        "total_fields": len(fields_summary)
    }

def _get_farmer_fields(schema: Dict[str, Any], form_name: str = None) -> List[Dict[str, Any]]:
    """
    Extract only the fields relevant to the farmer, filtering out office use, signatures, etc.
    Also categorizes fields for summary.
    
    If form_name is provided and has 'curated_fields' in STATIC_FORM_DESCRIPTIONS,
    use that curated list instead of applying heuristics.
    """
    # Check for curated fields in form metadata (for complex forms like BCAP-1)
    if form_name and form_name in STATIC_FORM_DESCRIPTIONS:
        form_meta = STATIC_FORM_DESCRIPTIONS[form_name]
        curated = form_meta.get("curated_fields", [])
        
        if curated:
            # Use the curated field list directly from metadata
            fields_summary = []
            for field_def in curated:
                fid = field_def.get("field_id")
                if fid and fid in schema:
                    fields_summary.append({
                        "field_id": fid,
                        "description": field_def.get("label", schema[fid].get('description', fid)),
                        "type": "text",
                        "category": field_def.get("category", "General Information")
                    })
            return fields_summary
    
    # Default behavior: apply heuristics
    fields_summary = []
    for fid, data in schema.items():
        # Only show TEXT fields (/Tx)
        # This simplifies the form for the voice agent and prevents the 'Button' crash
        if data['type'] == '/Tx': 
            desc_lower = (data['description'] or "").lower()
            id_lower = fid.lower()
            
            # 1. EXCLUSION LIST (Expanded)
            skip_keywords = [
                # General office use
                "office use", "official use", "agency use only", "for fsa use",
                # Signature fields not for farmer (bot handles sending, not signing on screen usually, or user signs later)
                "signature of ccc", "signature of representative", 
                "signature of nrcs", "signature of coc", "signature of sed",
                "nrcs employee", "coc signature", "sed/dd", "date signed", "signature date",
                # Administrative sections
                "date received", "approved by", "disapproved", "remarks", "reviewer",
                "date returned", "date referred", "fsa completes", "state code", "county code",
                # PART sections often reserved
                "part b", "part c", "part d",
                "nrcs information", "coc and concurrences", "mitigation plan",
                # Concurrence fields
                "concur", "technical concurrence"
            ]
            
            if any(k in desc_lower for k in skip_keywords) or any(k in id_lower for k in skip_keywords):
                continue

            # 2. CATEGORIZATION
            category = "General Information"
            
            # Heuristics for keywords
            if any(k in id_lower or k in desc_lower for k in ["name", "address", "phone", "email", "zip", "contact", "producer"]):
                category = "Contact Information"
            elif any(k in id_lower or k in desc_lower for k in ["ssn", "tax", "social security", "identification", "id number"]):
                category = "Identification"
            elif any(k in id_lower or k in desc_lower for k in ["farm", "tract", "crop", "acre", "commodity", "livestock", "land"]):
                category = "Farm Details"
            elif any(k in id_lower or k in desc_lower for k in ["date", "year"]):
                category = "Dates"
                
            fields_summary.append({
                "field_id": fid,
                "description": data['description'],
                "type": "text",
                "category": category
            })
    return fields_summary

async def get_form_summary(form_name: str) -> Dict[str, Any]:
    """
    Get a summary of the form to present to the user BEFORE starting.
    Uses pre-calculated static descriptions for speed.
    """
    # Check if we have a static description for this form
    if form_name in STATIC_FORM_DESCRIPTIONS:
        desc = STATIC_FORM_DESCRIPTIONS[form_name]
        
        # Build category summary string
        cat_summaries = []
        if "categories" in desc:
            for cat, num in desc["categories"].items():
                if num > 0:
                    cat_summaries.append(f"{cat} ({num} fields)")
        
        cat_text = ", ".join(cat_summaries)
        count = desc.get("field_count", 0)
        estimated_time = desc.get("estimated_time", "unknown")
        
        message = (f"This form requires information about: {cat_text}. "
                   f"There are {count} questions in total, which should take about {estimated_time}.")
                   
        return {
            "success": True,
            "form_name": form_name,
            "total_fields": count,
            "categories": desc.get("categories", {}),
            "estimated_time": estimated_time,
            "message": message,
            "note": "These counts exclude office-use sections (pre-calculated)."
        }

    # Fallback to dynamic inspection if not in static list
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}
    
    # Get only the fields the farmer needs to fill
    farmer_fields = _get_farmer_fields(schema)
    count = len(farmer_fields)
    
    # Group by category
    categories = {}
    for f in farmer_fields:
        cat = f.get('category', 'General Information')
        if cat not in categories:
            categories[cat] = 0
        categories[cat] += 1
        
    # Build descriptive message
    cat_summaries = []
    for cat, num in categories.items():
        if num > 0:
            cat_summaries.append(f"{cat} ({num} fields)")
    
    cat_text = ", ".join(cat_summaries)
    
    # Estimate time: ~30 seconds per field (conservative estimate)
    estimated_minutes = max(1, round(count * 0.5))
    
    message = (f"This form requires information about: {cat_text}. "
               f"There are {count} questions in total, which should take about {estimated_minutes} minutes.")

    return {
        "success": True,
        "form_name": form_name,
        "total_fields": count,
        "categories": categories,
        "estimated_time": f"{estimated_minutes} minutes",
        "message": message,
        "note": "These counts exclude office-use sections."
    }

async def fill_form_field(
    form_name: str,
    field_id: str,
    value: str
) -> Dict[str, Any]:
    """
    Store a value for a specific form field.
    """
    global _ACTIVE_FORM
    
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}

    if field_id not in schema:
        # Fuzzy matching or error? Strict for now.
        return {
            "success": False,
            "error": f"Invalid field_id '{field_id}'. Use get_form_fields to see valid IDs."
        }

    # Normalize voice input before validation (fixes common transcription errors)
    normalized_value = _normalize_voice_input(value, field_id)
    
    # Validate input
    validation_error = _validate_field_input(field_id, normalized_value, schema.get(field_id, {}))
    if validation_error:
        return {
            "success": False,
            "error": validation_error,
            "validation_failed": True,
            "original_value": value,
            "normalized_value": normalized_value
        }

    form_data = _get_form_data(form_name)
    
    # Check if this is a new form session (for auto-open)
    is_new_session = _ACTIVE_FORM != form_name
    if is_new_session:
        _ACTIVE_FORM = form_name
        # Queue panel open event with all current fields
        _PENDING_UPDATES.append({
            'type': 'form_panel',
            'action': 'open',
            'form_name': form_name,
            'fields': dict(form_data)  # Existing fields (if any)
        })
    
    # Update the field with normalized value
    form_data[field_id] = normalized_value
    
    # Queue update for UI broadcast with progress
    progress = _get_form_progress(form_name)
    _PENDING_UPDATES.append({
        'type': 'form_update',
        'form_name': form_name,
        'field_updates': {field_id: normalized_value},
        'progress': progress  # {filled: N, total: M}
    })
    
    # Auto-save the PDF to disk so user can see progress
    saved_filename = f"filled_{form_name}"
    try:
        pdf_bytes = _fill_pdf_dynamic(form_name, form_data)
        output_path = DOCUMENT_DIR / saved_filename
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        save_status = f" (Progress saved to {saved_filename})"
    except Exception as e:
        save_status = f" (Auto-save failed: {str(e)})"
    
    # Include original vs normalized if they differ
    result = {
        "success": True,
        "form_name": form_name,
        "field_id": field_id,
        "value": normalized_value,
        "status": "saved" + save_status
    }
    if normalized_value != value:
        result["original_input"] = value
        result["was_normalized"] = True
    
    return result

def _normalize_voice_input(value: str, field_id: str) -> str:
    """
    Normalize voice transcription input to fix common speech-to-text issues.
    Returns the cleaned/normalized value.
    """
    normalized = str(value).strip()
    field_id_lower = field_id.lower()
    
    # Remove common voice artifacts/fillers
    filler_words = [
        r'\b(um|uh|uhh|umm|er|ah|ahh|hmm|hm)\b',
        r'\b(like|you know|i mean|so|well|actually)\b',
        r'\b(wait wait wait|wait wait|wait a second|hold on)\b',
        r'\b(let me think|let me see)\b'
    ]
    for pattern in filler_words:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    normalized = ' '.join(normalized.split())
    
    # Name field normalization (for spelled-out names)
    name_field_keywords = ['name', 'applicant', 'producer', 'contact', 'first', 'last', 'middle']
    if any(kw in field_id_lower for kw in name_field_keywords) and 'email' not in field_id_lower:
        # Strip common prefixes people say before spelling
        name_prefix_patterns = [
            r"^(it's spelled|that's spelled|spelled|it's|that's|my name is|the name is)\s*",
            r"^(sure|yes|okay|ok)[,.]?\s*",
        ]
        for pattern in name_prefix_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        normalized = normalized.strip()
        
        # Check if this looks like spelled-out letters (single letters with spaces)
        # Pattern: "J O H N" or "j o h n" or "J. O. H. N."
        words = normalized.split()
        
        # NATO phonetic alphabet mapping
        nato_alphabet = {
            'alfa': 'A', 'alpha': 'A', 'bravo': 'B', 'charlie': 'C', 'delta': 'D',
            'echo': 'E', 'foxtrot': 'F', 'golf': 'G', 'hotel': 'H', 'india': 'I',
            'juliet': 'J', 'juliett': 'J', 'kilo': 'K', 'lima': 'L', 'mike': 'M',
            'november': 'N', 'oscar': 'O', 'papa': 'P', 'quebec': 'Q', 'romeo': 'R',
            'sierra': 'S', 'tango': 'T', 'uniform': 'U', 'victor': 'V', 'whiskey': 'W',
            'xray': 'X', 'x-ray': 'X', 'yankee': 'Y', 'zulu': 'Z'
        }
        
        # Check for NATO phonetic spelling (e.g., "Juliet Oscar Hotel November")
        nato_letters = []
        is_nato = False
        for word in words:
            word_lower = word.lower().strip('.,')
            if word_lower in nato_alphabet:
                nato_letters.append(nato_alphabet[word_lower])
                is_nato = True
            elif len(word) == 1 and word.isalpha():
                nato_letters.append(word.upper())
        
        if is_nato and len(nato_letters) >= 2:
            # This is NATO phonetic spelling, join the letters
            normalized = ''.join(nato_letters).title()
        elif len(words) >= 2:
            # Check if all words are single letters (regular spelling)
            single_letters = [w.strip('.').upper() for w in words if len(w.strip('.')) == 1 and w.strip('.').isalpha()]
            if len(single_letters) == len(words) and len(single_letters) >= 2:
                # All words are single letters - join them
                normalized = ''.join(single_letters).title()
        
        # Final cleanup - ensure proper title case
        if normalized and len(normalized) > 1:
            normalized = normalized.title()
    
    # Email-specific corrections - use semantic detection instead of field keywords
    # Detect email patterns semantically: looks for "word at/@ domain dot/. extension"
    def _looks_like_email(text: str) -> bool:
        """Detect if text semantically looks like an email address."""
        text_lower = text.lower()
        
        # Already contains @ symbol
        if '@' in text:
            return True
        
        # Common spoken email patterns
        # Pattern: "something at something dot something"
        spoken_email_pattern = r'\b\w+\s+(at|@)\s+\w+\s+(dot|\.)\s+\w+'
        if re.search(spoken_email_pattern, text_lower):
            return True
        
        # Common email domains mentioned (even without "at")
        common_domains = ['gmail', 'yahoo', 'hotmail', 'outlook', 'icloud', 'aol', 'protonmail', 'mail', 'email']
        common_tlds = ['dot com', 'dot org', 'dot net', 'dot gov', 'dot edu', '.com', '.org', '.net', '.gov', '.edu']
        
        has_domain = any(domain in text_lower for domain in common_domains)
        has_tld = any(tld in text_lower for tld in common_tlds)
        
        # If text contains a domain AND a TLD pattern, it's likely an email
        if has_domain and has_tld:
            return True
        
        # Check for "at" followed by domain-like word
        if ' at ' in text_lower and has_domain:
            return True
        
        return False
    
    if _looks_like_email(normalized):
        # First, strip common preceding phrases from voice input
        # These patterns match phrases that users typically say before their email
        email_prefix_patterns = [
            r"^(my email is|my email address is|my email's|email is|the email is)\s*",
            r"^(it's|its|it is|that's|that is|that would be)\s*",
            r"^(you can reach me at|reach me at|contact me at)\s*",
            r"^(sure|yes|yeah|ok|okay)[,.]?\s*(it's|its|it is|that's|my email is)?\s*",
            r"^(i can be reached at|send it to)\s*",
        ]
        for pattern in email_prefix_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Clean up any leading/trailing whitespace after prefix removal
        normalized = normalized.strip()
        
        # Common voice transcription fixes for email
        email_corrections = [
            (r'\s+at\s+', '@'),                    # "john at gmail" -> "john@gmail"
            (r'\s+dot\s+', '.'),                   # "gmail dot com" -> "gmail.com"
            (r'@gmail@gmail', '@gmail'),           # "gmail at gmail" duplication fix
            (r'@(\w+)@', r'@\1.'),                 # Repeated @ symbol -> single @ and dot
            (r'(\w)@(\w+)\.(\w+)@.*', r'\1@\2.\3'), # Strip trailing @ duplicates
            (r'\s+', ''),                          # Remove all spaces in email
        ]
        for pattern, replacement in email_corrections:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
        # Common domain typos from voice
        domain_fixes = {
            'gmailcom': 'gmail.com',
            'yahoocom': 'yahoo.com',
            'hotmailcom': 'hotmail.com',
            'outlookcom': 'outlook.com',
        }
        for typo, fix in domain_fixes.items():
            if typo in normalized.lower():
                normalized = re.sub(typo, fix, normalized, flags=re.IGNORECASE)
    
    # Phone number normalization
    if "phone" in field_id_lower or "tel" in field_id_lower:
        # Extract just the digits
        digits = re.sub(r'\D', '', normalized)
        if len(digits) == 10:
            # Format as (XXX) XXX-XXXX
            normalized = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            # US number with country code
            normalized = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    
    # SSN normalization
    if "ssn" in field_id_lower or "social" in field_id_lower or "security" in field_id_lower:
        digits = re.sub(r'\D', '', normalized)
        if len(digits) == 9:
            # Format as XXX-XX-XXXX
            normalized = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    
    # ZIP code normalization
    if "zip" in field_id_lower or "postal" in field_id_lower:
        digits = re.sub(r'\D', '', normalized)
        if len(digits) == 5:
            normalized = digits
        elif len(digits) == 9:
            # ZIP+4 format
            normalized = f"{digits[:5]}-{digits[5:]}"
    
    return normalized


def _validate_field_input(field_id: str, value: str, field_metadata: dict) -> Optional[str]:
    """
    Validate input value against field type and semantic rules.
    Returns error message string if invalid, None if valid.
    """
    field_id_lower = field_id.lower()
    value_str = str(value).strip()
    
    # 1. Semantic Check: Address vs Email
    # If field asks for "Address" but user provides an Email
    if "address" in field_id_lower and "email" not in field_id_lower:
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        if re.match(email_pattern, value_str):
            return (f"Invalid input: You provided an email address ('{value_str}'), but the field '{field_id}' "
                    "appears to require a physical address. Please ask the user for their street address.")

    # 2. Email Format Validation
    if "email" in field_id_lower:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, value_str):
            return (f"Invalid email format: '{value_str}'. Please provide a valid email address "
                    "(e.g., name@example.com). Ask the user to spell out their email clearly.")

    # 3. Phone Number Validation
    if "phone" in field_id_lower or "tel" in field_id_lower:
        # Extract digits to validate
        digits = re.sub(r'\D', '', value_str)
        if len(digits) < 10:
            return (f"Invalid phone number: '{value_str}'. Phone numbers must have at least 10 digits. "
                    "Please ask the user for their complete phone number including area code.")
        if len(digits) > 11:
            return (f"Invalid phone number: '{value_str}'. Too many digits ({len(digits)}). "
                    "Please verify the phone number with the user.")

    # 4. ZIP Code Validation
    if "zip" in field_id_lower or "postal" in field_id_lower:
        digits = re.sub(r'\D', '', value_str)
        if len(digits) not in [5, 9]:
            return (f"Invalid ZIP code: '{value_str}'. US ZIP codes must be 5 digits (e.g., 12345) "
                    "or 9 digits for ZIP+4 (e.g., 12345-6789). Please ask the user for their ZIP code.")

    # 5. SSN / Tax ID Validation
    if "ssn" in field_id_lower or "social" in field_id_lower or "security" in field_id_lower or "tax" in field_id_lower:
        digits = re.sub(r'\D', '', value_str)
        if len(digits) != 9:
            return (f"Invalid SSN/Tax ID: '{value_str}'. Social Security Numbers must have exactly 9 digits "
                    "(format: XXX-XX-XXXX). Please ask the user to provide all 9 digits.")
        # Check for obviously invalid SSNs (all zeros in any group)
        if digits[:3] == '000' or digits[3:5] == '00' or digits[5:] == '0000':
            return (f"Invalid SSN: '{value_str}'. This appears to be an invalid Social Security Number. "
                    "Please verify with the user.")

    # 6. Date Format and Range Validation
    if "date" in field_id_lower or "dob" in field_id_lower:
        # Allow MM/DD/YYYY or M/D/YYYY
        date_pattern = r'^(0?[1-9]|1[0-2])[\/\-](0?[1-9]|[12][0-9]|3[01])[\/\-](\d{4})$'
        match = re.match(date_pattern, value_str)
        if not match:
            return (f"Invalid date format: '{value_str}'. Dates must be in MM/DD/YYYY format (e.g., 05/21/2024). "
                    "Please ask the user to provide the date in this format.")
        
        # Parse and validate date range
        try:
            month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            input_date = datetime(year, month, day)
            current_year = datetime.now().year
            
            # Date of Birth specific validation
            if "dob" in field_id_lower or "birth" in field_id_lower:
                if year > current_year:
                    return (f"Invalid date of birth: '{value_str}'. Birth year cannot be in the future. "
                            "Please verify the year with the user.")
                if year < 1900:
                    return (f"Invalid date of birth: '{value_str}'. Birth year seems too old (before 1900). "
                            "Please verify with the user.")
                age = current_year - year
                if age > 120:
                    return (f"Invalid date of birth: '{value_str}'. This would make the person over 120 years old. "
                            "Please verify the date with the user.")
            else:
                # General date validation
                if year < 1900:
                    return (f"Invalid date: '{value_str}'. Year seems too old. Please verify with the user.")
                if year > current_year + 10:
                    return (f"Invalid date: '{value_str}'. Year is too far in the future. Please verify with the user.")
        except ValueError:
            return (f"Invalid date: '{value_str}'. This is not a valid calendar date. "
                    "Please verify with the user.")

    # 7. Type Check: Checkboxes / Buttons
    field_type = field_metadata.get('type', '')
    if field_type == '/Btn':
        # Checkboxes usually accept Yes/No, On/Off, True/False, or '1'/'0'
        valid_booleans = ['yes', 'no', 'true', 'false', 'on', 'off', '1', '0']
        if value_str.lower() not in valid_booleans:
            return (f"Invalid value for checkbox/button '{field_id}': '{value_str}'. "
                    f"Please provide one of: {', '.join(valid_booleans)}")

    # Passed all checks
    return None

async def get_form_status(form_name: str) -> Dict[str, Any]:
    """Get current form completion status."""
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}

    form_data = _get_form_data(form_name)
    
    # Just return what we have filled. Let the LLM decide if it's done.
    # We won't enforce a "100% complete" check because many PDF fields are optional or for office use.
    
    return {
        "success": True,
        "form_name": form_name,
        "filled_fields_count": len(form_data),
        "filled_fields": list(form_data.keys()),
        "message": "Form data saved. You can continue filling or send email if done."
    }

def _fill_pdf_dynamic(form_name: str, form_data: dict) -> bytes:
    """Fill the PDF template with form data using dynamic schema."""
    if not HAS_PYPDF:
        raise RuntimeError("pypdf not installed")
    
    pdf_path = DOCUMENT_DIR / form_name
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF {form_name} not found")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    
    writer.clone_reader_document_root(reader)
    
    # Enable NeedAppearances to force viewers to re-render text
    try:
        catalog = writer.root_object
        if "/AcroForm" not in catalog:
            writer.root_object.update({NameObject("/AcroForm"): DictionaryObject()})
        
        acroform = writer.root_object["/AcroForm"]
        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    except Exception as e:
        print(f"Warning: Could not set NeedAppearances: {e}")
    
    # Create update dict
    update_dict = {}
    for k, v in form_data.items():
        update_dict[k] = v
        
    if update_dict:
        # Update values
        writer.update_page_form_field_values(writer.pages[0], update_dict)
        
        # Post-processing: Enforce auto-font size on updated fields
        # This iterates through page annotations to find the fields we just updated
        try:
            for page in writer.pages:
                if "/Annots" in page:
                    for annot in page["/Annots"]:
                        obj = annot.get_object()
                        # specific logic for text fields (Tx)
                        if obj.get("/FT") == "/Tx":
                            # Set default appearance to auto-size (0 Tf) -> "/Helv 0 Tf 0 g"
                            # This fixes cutoff issues by shrinking text to fit
                            obj.update({
                                NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g")
                            })
                            # Also ensure MultiLine is set if it's a long text field (bit 13)
                            # We conserve existing flags but ensure bit 13 is set if it looks like a note
                            flags = obj.get("/Ff", 0)
                            if isinstance(flags, int):
                                # If it's the "Request for good faith" field (heuristic) or long text
                                if "circumstances" in str(obj.get("/TU", "")).lower() or len(str(form_data.get(obj.get("/T"), ""))) > 50:
                                    flags = flags | 4096  # Set MultiLine
                                    obj.update({
                                        NameObject("/Ff"): NumberObject(flags)
                                    })
        except Exception as e:
            print(f"Warning: Could not update field properties: {e}")
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()

async def send_form_email(
    recipient_email: str,
    form_name: str
) -> Dict[str, Any]:
    """
    Fill the PDF with collected data and email to customer.
    """
    form_data = _get_form_data(form_name)
    
    if not form_data:
        return {
            "success": False,
            "error": "No form data collected."
        }
    
    # Get SMTP settings
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user)
    
    if not smtp_user or not smtp_password:
        return {
            "success": False,
            "error": "Email not configured. Set SMTP_USER and SMTP_PASSWORD in .env"
        }
    
    
    # Get form info or use defaults
    if form_name in STATIC_FORM_DESCRIPTIONS:
        form_info = STATIC_FORM_DESCRIPTIONS[form_name]
    else:
        form_info = {
            "title": f"USDA Form: {form_name}",
            "purpose": "This form has been completed with your information for USDA program participation.",
            "next_steps": "Please review the attached form and submit it to your local USDA Service Center."
        }
    
    # Count filled fields
    filled_count = len(form_data)
    
    # Get current date
    current_date = datetime.now().strftime("%B %d, %Y")
    
    try:
        # Fill PDF
        pdf_bytes = _fill_pdf_dynamic(form_name, form_data)
        
        # Try to find farmer's name for greeting
        farmer_name = None
        
        # Patterns that explicitly ask for name (prioritize full name fields)
        full_name_patterns = ['full name', 'producer name', 'applicant name', 'your name', 'farmer name']
        # Combined name+address fields (need to extract name portion)
        name_address_patterns = ['name and address']
        
        # Get schema to check field descriptions
        schema = _get_form_schema(form_name)
        
        def extract_name_from_value(value: str, is_combined_field: bool = False) -> str:
            """Extract name from field value, handling combined name+address fields."""
            value_str = str(value).strip()
            
            if is_combined_field:
                # For combined "Name and Address" fields, name is usually the first part before comma
                # Example: "Arcita S., Sendo Rd., Mount Jackson, VA 22842" -> "Arcita S."
                parts = value_str.split(',')
                if parts:
                    # Take first part as name, but verify it doesn't look like a street
                    first_part = parts[0].strip()
                    # Skip if it looks like a street address (contains numbers or road keywords)
                    road_keywords = ['rd', 'road', 'st', 'street', 'ave', 'avenue', 'blvd', 'drive', 'dr', 'lane', 'ln', 'way', 'court', 'ct']
                    if not any(char.isdigit() for char in first_part):
                        first_lower = first_part.lower()
                        if not any(kw in first_lower for kw in road_keywords):
                            return first_part.title()
                return None
            
            return value_str.title()
        
        for key, value in form_data.items():
            if not value or len(str(value)) < 2:
                continue
            
            key_lower = key.lower()
            description = ''
            if isinstance(schema, dict) and key in schema:
                description = schema[key].get('description', '').lower()
            
            # First, check for explicit full name fields (highest priority)
            if any(pattern in key_lower for pattern in full_name_patterns) or \
               any(pattern in description for pattern in full_name_patterns):
                farmer_name = extract_name_from_value(value, is_combined_field=False)
                if farmer_name:
                    break
            
            # Then, check for combined name+address fields
            if any(pattern in key_lower for pattern in name_address_patterns) or \
               any(pattern in description for pattern in name_address_patterns):
                farmer_name = extract_name_from_value(value, is_combined_field=True)
                if farmer_name:
                    break
        
        # Only include name in greeting if we found a valid name
        greeting = f"Greetings {farmer_name}," if farmer_name else "Greetings,"

        # Create email with HTML and plain text versions
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"USDA Form Submission: {form_info['title']}"
        msg["From"] = sender_email
        msg["To"] = recipient_email
        
        # Plain text version
        plain_body = f"""
USDA GRANTS ASSISTANT
Form Submission Confirmation
Date: {current_date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{greeting}

Thank you for using the USDA Voice Assistant to complete your form. Your submission has been processed successfully.

FORM DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Form: {form_info['title']}
Fields Completed: {filled_count}
Date Submitted: {current_date}
Session ID: {_CURRENT_SESSION_ID or 'Not available'}

ABOUT THIS FORM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{form_info['purpose']}

NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{form_info['next_steps']}

IMPORTANT REMINDERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Review the attached PDF to ensure all information is accurate
• Keep a copy of this form for your records
• Contact your local USDA Service Center if you have questions
• Find your local office at: https://www.farmers.gov/service-locator

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This form was completed using the USDA Voice Assistant.
For questions about your submission, contact your local USDA Service Center.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        msg.attach(MIMEText(plain_body, "plain"))
        
        # Attach PDF
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        filename = f"Filled_{form_name}"
        pdf_attachment.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(pdf_attachment)
        
        # Send
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        
        # NOTE: We intentionally do NOT clear form data here.
        # This allows users to resend to a corrected email if needed.
        # Form data will be cleared when the session ends or user starts a new form.
        
        return {
            "success": True,
            "message": f"Form {form_name} sent to {recipient_email}. Let me know if you need to resend to a different address."
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send: {str(e)}"
        }


async def send_all_forms_email(
    recipient_email: str
) -> Dict[str, Any]:
    """
    Send ALL filled forms in a single email.
    Collects all forms that have data and sends them together.
    """
    # Find all forms with data
    forms_with_data = []
    for form_name, form_data in _FORM_DATA.items():
        if form_data:  # Has at least one field filled
            forms_with_data.append(form_name)
    
    if not forms_with_data:
        return {
            "success": False,
            "error": "No forms have been filled yet."
        }
    
    # Get SMTP settings
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user)
    
    if not smtp_user or not smtp_password:
        return {
            "success": False,
            "error": "Email not configured. Set SMTP_USER and SMTP_PASSWORD in .env"
        }
    
    # Reuse the static form descriptions loaded at module start
    # Each form entry has 'title', 'purpose', etc.
    
    current_date = datetime.now().strftime("%B %d, %Y")
    
    try:
        # Create email
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"USDA Form Submission: {len(forms_with_data)} Form(s) Attached"
        msg["From"] = sender_email
        msg["To"] = recipient_email
        
        # Build form summary for the email body
        form_summary_lines = []
        for i, form_name in enumerate(forms_with_data, 1):
            form_info = STATIC_FORM_DESCRIPTIONS.get(form_name, {"title": form_name, "purpose": "USDA form"})
            fields_count = len(_FORM_DATA.get(form_name, {}))
            form_summary_lines.append(f"{i}. {form_info['title']}\n   Fields Completed: {fields_count}\n   Purpose: {form_info['purpose']}")
        
        forms_summary = "\n\n".join(form_summary_lines)
        
        # Plain text body
        plain_body = f"""
USDA GRANTS ASSISTANT
Form Submission Confirmation
Date: {current_date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dear Farmer,

Thank you for using the USDA Voice Assistant. Your form submissions have been processed successfully.

FORMS INCLUDED IN THIS EMAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{forms_summary}

NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Review each attached PDF to ensure all information is accurate
• Submit these forms to your local USDA Service Center
• Keep copies of these forms for your records
• Find your local office at: https://www.farmers.gov/service-locator

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This email was generated by the USDA Voice Assistant.
For questions, contact your local USDA Service Center.

USDA is an equal opportunity provider, employer, and lender.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        msg.attach(MIMEText(plain_body, "plain"))
        
        # Attach all PDFs
        for form_name in forms_with_data:
            form_data = _FORM_DATA.get(form_name, {})
            pdf_bytes = _fill_pdf_dynamic(form_name, form_data)
            pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            filename = f"Filled_{form_name}"
            pdf_attachment.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(pdf_attachment)
        
        # Send
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        return {
            "success": True,
            "message": f"{len(forms_with_data)} form(s) sent to {recipient_email}: {', '.join(forms_with_data)}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send: {str(e)}"
        }

def cleanup_session_files():
    """
    Clean up temporary filled form files created during the session.
    Deletes all files matching 'filled_*.pdf' in the Document directory.
    """
    try:
        if not DOCUMENT_DIR.exists():
            return
            
        print(f"🧹 Cleaning up session files in {DOCUMENT_DIR}...")
        count = 0
        for file_path in DOCUMENT_DIR.glob("filled_*.pdf"):
            try:
                file_path.unlink()
                count += 1
                print(f"   Deleted: {file_path.name}")
            except Exception as e:
                print(f"   Failed to delete {file_path.name}: {e}")
        
        if count > 0:
            print(f"✓ Removed {count} temporary form file(s)")
        else:
            print("   No temporary files found to clean up")
            
    except Exception as e:
        print(f"⚠️ Error during file cleanup: {e}")

# --- UI Panel Support ---

def get_pending_form_updates() -> list:
    """
    Get and clear pending form updates for broadcasting to UI.
    Called after each LLM response to send updates to the frontend.
    """
    global _PENDING_UPDATES
    updates = _PENDING_UPDATES.copy()
    _PENDING_UPDATES = []
    return updates

async def update_form_field_from_ui(
    form_name: str,
    field_id: str,
    value: str
) -> Dict[str, Any]:
    """
    Update a form field from the UI panel (manual edit).
    Does NOT queue an update back to UI (to avoid loops).
    """
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}

    if field_id not in schema:
        return {
            "success": False,
            "error": f"Invalid field_id '{field_id}'."
        }

    form_data = _get_form_data(form_name)
    form_data[field_id] = value
    
    # Auto-save the PDF
    try:
        pdf_bytes = _fill_pdf_dynamic(form_name, form_data)
        output_path = DOCUMENT_DIR / f"filled_{form_name}"
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
    except Exception:
        pass  # Silently fail auto-save for UI edits
    
    return {"success": True, "field_id": field_id, "value": value}

def get_current_form_state() -> Dict[str, Any]:
    """Get current form state for initial panel load."""
    global _ACTIVE_FORM
    if not _ACTIVE_FORM:
        return {"active": False}
    
    form_data = _get_form_data(_ACTIVE_FORM)
    return {
        "active": True,
        "form_name": _ACTIVE_FORM,
        "fields": dict(form_data)
    }

# --- Tool Definitions ---

LIST_FORMS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_available_forms",
        "description": "List all PDF forms available for filling.",
        "parameters": {"type": "object", "properties": {}}
    }
}

GET_FORM_FIELDS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_form_fields",
        "description": "Get the list of fields (schema) for a specific form.",
        "parameters": {
            "type": "object",
            "properties": {
                "form_name": {
                    "type": "string",
                    "description": "Exact name of the form file (e.g. 'AD-1069.pdf'). MUST be one of the files returned by list_available_forms(). Do NOT invent form names like 'prices'."
                }
            },
            "required": ["form_name"]
        }
    }
}

FILL_FORM_FIELD_TOOL = {
    "type": "function",
    "function": {
        "name": "fill_form_field",
        "description": "Store a value for a form field.",
        "parameters": {
            "type": "object",
            "properties": {
                "form_name": {
                    "type": "string",
                    "description": "Name of the form file"
                },
                "field_id": {
                    "type": "string",
                    "description": "The exact field ID from get_form_fields"
                },
                "value": {
                    "type": "string",
                    "description": "Value to enter"
                }
            },
            "required": ["form_name", "field_id", "value"]
        }
    }
}

GET_FORM_STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_form_status",
        "description": "Check filling progress for a form.",
        "parameters": {
            "type": "object",
            "properties": {
                "form_name": {
                    "type": "string",
                    "description": "Name of the form file"
                }
            },
            "required": ["form_name"]
        }
    }
}

SEND_FORM_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "send_form_email",
        "description": "Fill a single PDF form and email it to the customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_email": {
                    "type": "string",
                    "description": "Customer's email address"
                },
                "form_name": {
                    "type": "string",
                    "description": "Name of the form file"
                }
            },
            "required": ["recipient_email", "form_name"]
        }
    }
}

SEND_ALL_FORMS_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "send_all_forms_email",
        "description": "Send ALL filled forms in a single email. Use this when user wants to receive multiple forms together instead of separately.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_email": {
                    "type": "string",
                    "description": "Customer's email address"
                }
            },
            "required": ["recipient_email"]
        }
    }
}

GET_FORM_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_form_summary",
        "description": "Get a summary of the form (field count, estimated time) to present to the user BEFORE starting.",
        "parameters": {
            "type": "object",
            "properties": {
                "form_name": {
                    "type": "string",
                    "description": "Name of the form file"
                }
            },
            "required": ["form_name"]
        }
    }
}

# --- Chat Summary Email ---
# Storage for chat messages (set by web_voice_agent)
_CHAT_MESSAGES = []

def set_chat_messages(messages: list):
    """Set the current session's chat messages for email summary."""
    global _CHAT_MESSAGES
    _CHAT_MESSAGES = messages

def _generate_transcript_pdf(messages: list, summary_text: str = None) -> bytes:
    """Generate a formatted PDF transcript using ReportLab."""
    if not HAS_REPORTLAB:
        return None
        
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = styles["Heading1"]
    title_style.alignment = 1  # Center
    story.append(Paragraph("USDA Voice Assistant - Conversation Transcript", title_style))
    story.append(Spacer(1, 12))
    
    # Date/Time
    date_str = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    story.append(Paragraph(f"Date: {date_str}", styles["Normal"]))
    if _CURRENT_SESSION_ID:
        story.append(Paragraph(f"Session ID: {_CURRENT_SESSION_ID}", styles["Normal"]))
    story.append(Spacer(1, 24))
    
    # Summary Section
    if summary_text:
        story.append(Paragraph("Summary", styles["Heading2"]))
        # Split bullets if present
        for line in summary_text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), styles["Normal"]))
        story.append(Spacer(1, 24))
    
    # Transcript
    story.append(Paragraph("Full Transcript", styles["Heading2"]))
    story.append(Spacer(1, 12))
    
    # Define styles for chat bubbles
    user_style = ParagraphStyle(
        'UserStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        textColor=colors.black,
        backColor=colors.Color(0.9, 0.95, 1), # Light Blue
        borderPadding=10,
        spaceBefore=6,
        spaceAfter=15,
        borderRadius=8
    )
    
    assistant_style = ParagraphStyle(
        'AssistantStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        textColor=colors.black,
        backColor=colors.Color(0.95, 0.95, 0.95), # Light Grey
        borderPadding=10,
        spaceBefore=6,
        spaceAfter=15,
        borderRadius=8
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        spaceAfter=8
    )
    
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        timestamp = msg.get('timestamp', '')
        
        # Format time
        time_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%I:%M %p")
            except:
                pass
        
        if role == "user":
            header_text = f"<b>You</b> • {time_str}" if time_str else "<b>You</b>"
            style = user_style
        else: # assistant or other
            header_text = f"<b>USDA Assistant</b> • {time_str}" if time_str else "<b>USDA Assistant</b>"
            style = assistant_style
            
        story.append(Paragraph(header_text, header_style))
        story.append(Paragraph(content, style))
        story.append(Spacer(1, 6))
        
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

async def send_chat_summary(
    recipient_email: str,
    summary_text: str = None
) -> Dict[str, Any]:
    """
    Send the conversation history to the user's email.
    Includes a PDF transcript attachment.
    """
    if not _CHAT_MESSAGES:
        return {
            "success": False,
            "error": "No conversation history to send."
        }
    
    # Get SMTP settings
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user)
    
    if not smtp_user or not smtp_password:
        return {
            "success": False,
            "error": "Email not configured. Set SMTP_USER and SMTP_PASSWORD in .env"
        }
    
    current_date = datetime.now().strftime("%B %d, %Y")
    
    try:
        # Create email
        msg = MIMEMultipart("mixed") # mixed content for attachments
        msg["Subject"] = f"Your USDA Assistant Conversation Summary - {current_date}"
        msg["From"] = sender_email
        msg["To"] = recipient_email
        
        # Message Body
        body_text = f"""
USDA GRANTS ASSISTANT
Conversation Summary
Date: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Thank you for using the USDA Voice Assistant! 

Find your conversation transcript attached as a PDF for your records.

"""
        if summary_text:
            body_text += f"""
SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{summary_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
        body_text += """
NEXT STEPS
• Review the attached PDF transcript
• Contact your local USDA Service Center for follow-up questions
• Find your local office at: https://www.farmers.gov/service-locator

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USDA is an equal opportunity provider, employer, and lender.
"""
        msg.attach(MIMEText(body_text, "plain"))
        
        # Parse Chat History for Plain Text fallback (optional) or just use PDF
        # Generating PDF
        if HAS_REPORTLAB:
            pdf_bytes = _generate_transcript_pdf(_CHAT_MESSAGES, summary_text)
            if pdf_bytes:
                pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
                pdf_attachment.add_header(
                    "Content-Disposition", 
                    "attachment", 
                    filename=f"USDA_Conversation_{current_date.replace(' ', '_').replace(',', '')}.pdf"
                )
                msg.attach(pdf_attachment)
            else:
                 msg.attach(MIMEText("\n[Error: Could not generate PDF transcript]", "plain"))
        else:
            msg.attach(MIMEText("\n[Note: PDF generation unavailable]", "plain"))
            
        
        # Send
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        return {
            "success": True,
            "message": f"Chat summary and PDF transcript sent to {recipient_email}!"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send: {str(e)}"
        }

SEND_CHAT_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "send_chat_summary",
        "description": "Send a summary and transcript of the conversation to user's email. Use when user wants to save the info or says goodbye.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_email": {
                    "type": "string",
                    "description": "User's email address"
                },
                "summary_text": {
                    "type": "string",
                    "description": "A concise 3-5 bullet point summary of what was discussed, decisions made, and follow-up items. GENERATE THIS YOURSELF based on the conversation history."
                }
            },
            "required": ["recipient_email", "summary_text"]
        }
    }
}

FORM_TOOLS = [
    LIST_FORMS_TOOL,
    GET_FORM_FIELDS_TOOL,
    FILL_FORM_FIELD_TOOL,
    GET_FORM_STATUS_TOOL,
    SEND_FORM_EMAIL_TOOL,
    SEND_ALL_FORMS_EMAIL_TOOL,
    GET_FORM_SUMMARY_TOOL,
    SEND_CHAT_SUMMARY_TOOL
]

FORM_TOOL_FUNCTIONS = {
    "list_available_forms": list_available_forms,
    "get_form_fields": get_form_fields,
    "fill_form_field": fill_form_field,
    "get_form_status": get_form_status,
    "send_form_email": send_form_email,
    "send_all_forms_email": send_all_forms_email,
    "get_form_summary": get_form_summary,
    "send_chat_summary": send_chat_summary
}

