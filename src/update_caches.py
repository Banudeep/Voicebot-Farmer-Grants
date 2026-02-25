import asyncio
import sys
import subprocess
from pathlib import Path
import os
from datetime import datetime

# Path setup
SRC_DIR = Path(__file__).parent
ROOT_DIR = SRC_DIR.parent
CACHE_SCRIPTS_DIR = ROOT_DIR / "cache" / "scripts"

def run_script(script_path, description):
    """Run a python script using subprocess."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Script: {script_path}")
    print(f"{'='*60}\n")
    
    try:
        # Use the same python interpreter
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            cwd=ROOT_DIR,  # Run from root so path resolution is consistent
            text=True
        )
        print(f"\n✅ Successfully completed: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running {description}: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error running {description}: {e}")
        return False

async def update_usda_tools():
    """Update USDA reports cache using the tool module."""
    print(f"\n{'='*60}")
    print(f"Running: USDA Reports Cache Update")
    print(f"{'='*60}\n")
    
    try:
        sys.path.append(str(SRC_DIR))
        from mcp_tools.usda_tools import fetch_all_reports
        
        print("Fetching all USDA reports...")
        reports = await fetch_all_reports()
        print(f"✅ Successfully cached {len(reports)} USDA reports")
        return True
    except Exception as e:
        print(f"\n❌ Error updating USDA reports: {e}")
        return False

async def main():
    print(f"Starting Cache Update Process at {datetime.now().isoformat()}")
    print(f"Root Directory: {ROOT_DIR}")
    
    results = {}
    
    # 1. Update Form Metadata
    # metadata_script = SRC_DIR / "scraper" / "extract_metadata.py"
    # results["Form Metadata"] = run_script(metadata_script, "Form Metadata Extraction")
    
    # 2. Update USDA Reports
    # results["USDA Reports"] = await update_usda_tools()
    
    # 3. Update FSA Programs
    # fsa_script = CACHE_SCRIPTS_DIR / "scrape_fsa_programs.py"
    # if fsa_script.exists():
    #     results["FSA Programs"] = run_script(fsa_script, "FSA Programs Scraper")
    # else:
    #     print(f"⚠️ Script not found: {fsa_script}")
    #     results["FSA Programs"] = False

    # 4. Update Service Centers
    # sc_script = CACHE_SCRIPTS_DIR / "scrape_service_centers.py"
    # if sc_script.exists():
    #     results["Service Centers"] = run_script(sc_script, "Service Centers Scraper")
    # else:
    #     print(f"⚠️ Script not found: {sc_script}")
    #     results["Service Centers"] = False

    # 5. Update News
    # news_script = CACHE_SCRIPTS_DIR / "scrape_news_deep.py"
    # if news_script.exists():
    #     results["State News"] = run_script(news_script, "State News Scraper")
    # else:
    #     print(f"⚠️ Script not found: {news_script}")
    #     results["State News"] = False
        
    # 6. Update RD Programs
    rd_script = CACHE_SCRIPTS_DIR / "scrape_rd_programs.py"
    if rd_script.exists():
        results["RD Programs"] = run_script(rd_script, "Rural Development Programs Scraper")
    else:
        print(f"⚠️ Script not found: {rd_script}")
        results["RD Programs"] = False

    # 7. Update Program Deadlines
    deadlines_script = CACHE_SCRIPTS_DIR / "scrape_program_deadlines.py"
    if deadlines_script.exists():
        results["Program Deadlines"] = run_script(deadlines_script, "Program Deadlines Scraper")
    else:
        print(f"⚠️ Script not found: {deadlines_script}")
        results["Program Deadlines"] = False

    # Summary
    print(f"\n{'='*60}")
    print("Update Summary")
    print(f"{'='*60}")
    all_success = True
    for job, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"{job}: {status}")
        if not success:
            all_success = False
            
    if all_success:
        print("\n✨ All caches updated successfully!")
    else:
        print("\n⚠️ Some updates failed. Check logs above.")

if __name__ == "__main__":
    asyncio.run(main())
