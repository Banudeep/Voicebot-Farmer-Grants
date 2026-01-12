
import os
from pathlib import Path
from pypdf import PdfReader

def inspect_pdf(filename):
    # Correct path relative to CWD (Voicebot-Cascading)
    path = Path("Document") / filename
    if not path.exists():
        print(f"File not found: {path.absolute()}")
        return

    try:
        reader = PdfReader(str(path))
        fields = reader.get_fields()
        
        print(f"--- Fields for {filename} ---")
        if fields:
            # Sort by name for readability
            for field_name in sorted(list(fields.keys()))[:15]: 
                field_data = fields[field_name]
                print(f"Field: {field_name}")
                print(f"  Type: {field_data.get('/FT')}")
                print(f"  Help/Alt: {field_data.get('/TU')}") 
                # print(f"  Value: {field_data.get('/V')}") # Value might be empty
        else:
            print("No form fields found.")
    except Exception as e:
        print(f"Error reading {filename}: {e}")
    print("\n")

inspect_pdf("AD-1069.pdf")
inspect_pdf("AD-2100.pdf")
inspect_pdf("BCAP-1.pdf")
