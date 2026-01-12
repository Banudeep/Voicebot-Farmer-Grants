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

# Try to import pypdf for PDF form filling
try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Base directory for documents
DOCUMENT_DIR = Path(__file__).parent.parent / "Document"

# In-memory storage for form data
# Structure: { form_name: { field_id: value } }
_FORM_DATA = {}

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
    
    pdf_path = DOCUMENT_DIR / form_name
    if not pdf_path.exists():
        return {"error": f"Form {form_name} not found"}

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
        return schema
    except Exception as e:
        return {"error": f"Failed to read form schemas: {e}"}

def _get_form_data(form_name: str) -> dict:
    """Get current form data for a specific form"""
    if form_name not in _FORM_DATA:
        _FORM_DATA[form_name] = {}
    return _FORM_DATA[form_name]

def _clear_form_data(form_name: str):
    """Clear form data after sending"""
    if form_name in _FORM_DATA:
        _FORM_DATA[form_name] = {}

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
    """
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}
    
    # simplify for the LLM
    fields_summary = []
    for fid, data in schema.items():
        # Only show TEXT fields (/Tx) to avoid pypdf checkbox/radio button issues (/Btn causes /AP crashes)
        # This simplifies the form for the voice agent and prevents the 'Button' crash
        if data['type'] == '/Tx': 
            # Filter out "Office Use" fields so the AI doesn't ask the farmer for them
            desc_lower = (data['description'] or "").lower()
            id_lower = fid.lower()
            
            # Keywords indicating fields NOT for the farmer
            skip_keywords = [
                "office use", "official use", "agency use only", 
                "signature of ccc", "signature of representative", 
                "date received", "coc signature", "approved by",
                "disapproved", "remarks", "reviewer"
            ]
            
            if any(k in desc_lower for k in skip_keywords) or any(k in id_lower for k in skip_keywords):
                continue
                
            fields_summary.append({
                "field_id": fid,
                "description": data['description'],
                "type": "text"
            })
            
    return {
        "success": True,
        "form_name": form_name,
        "fields": fields_summary,
        "total_fields": len(fields_summary)
    }

async def fill_form_field(
    form_name: str,
    field_id: str,
    value: str
) -> Dict[str, Any]:
    """
    Store a value for a specific form field.
    """
    schema = _get_form_schema(form_name)
    if "error" in schema:
        return {"success": False, "error": schema["error"]}

    if field_id not in schema:
        # Fuzzy matching or error? Strict for now.
        return {
            "success": False,
            "error": f"Invalid field_id '{field_id}'. Use get_form_fields to see valid IDs."
        }

    form_data = _get_form_data(form_name)
    form_data[field_id] = value
    
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
    
    return {
        "success": True,
        "form_name": form_name,
        "field_id": field_id,
        "value": value,
        "status": "saved" + save_status
    }

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
    
    # Create update dict directly since we stick to direct field_id mapping now
    # Checkbox handling might need 'Yes'/'No' or '/On' check, simple string for now
    update_dict = {}
    for k, v in form_data.items():
        update_dict[k] = v
        
    if update_dict:
        writer.update_page_form_field_values(writer.pages[0], update_dict)
    
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
    
    try:
        # Fill PDF
        pdf_bytes = _fill_pdf_dynamic(form_name, form_data)
        
        # Create email
        msg = MIMEMultipart()
        msg["Subject"] = f"Your filled form: {form_name}"
        msg["From"] = sender_email
        msg["To"] = recipient_email
        
        body = f"""
Hello,

Please find attached your filled copy of {form_name}.

Completed via USDA Voice Assistant.
"""
        msg.attach(MIMEText(body, "plain"))
        
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
        
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        _clear_form_data(form_name)
        
        # Cleanup: Delete the auto-saved filled PDF
        filled_filename = f"filled_{form_name}"
        filled_path = DOCUMENT_DIR / filled_filename
        if filled_path.exists():
            try:
                filled_path.unlink()
            except Exception as e:
                # Log but don't fail the user request
                print(f"Warning: Failed to delete clean up {filled_filename}: {e}")
        
        return {
            "success": True,
            "message": f"Form {form_name} sent to {recipient_email}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send: {str(e)}"
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
                    "description": "Name of the form file (e.g. AD-1069.pdf)"
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
        "description": "Fill the PDF and email it.",
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

FORM_TOOLS = [
    LIST_FORMS_TOOL,
    GET_FORM_FIELDS_TOOL,
    FILL_FORM_FIELD_TOOL,
    GET_FORM_STATUS_TOOL,
    SEND_FORM_EMAIL_TOOL
]

FORM_TOOL_FUNCTIONS = {
    "list_available_forms": list_available_forms,
    "get_form_fields": get_form_fields,
    "fill_form_field": fill_form_field,
    "get_form_status": get_form_status,
    "send_form_email": send_form_email
}
