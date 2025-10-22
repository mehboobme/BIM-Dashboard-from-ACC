"""
Complete Power BI Setup - BOTH Dashboards
1. Progress Report (Model Properties)
2. Issues Dashboard (Issues + 3D Viewer)

Usage: python run_all.py
"""

import subprocess
import sys
import os
import time

def print_header(message):
    """Print formatted header"""
    print("\n" + "="*70)
    print(f"  {message}")
    print("="*70 + "\n")

def run_command(description, command, required=True):
    """Run a command and handle errors"""
    print(f"▶️  {description}...")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=False,
            text=True
        )
        print(f"✅ {description} - Complete\n")
        return True
    except subprocess.CalledProcessError as e:
        if required:
            print(f"❌ {description} - Failed!")
            print(f"   Error: {e}")
            print(f"\n💡 Tip: Run 'python {command.split()[1]}' separately to see detailed error")
            return False
        else:
            print(f"⚠️  {description} - Skipped (optional)\n")
            return True

def check_file_exists(filepath, description):
    """Check if required file exists"""
    if os.path.exists(filepath):
        print(f"✅ Found: {description}")
        return True
    else:
        print(f"❌ Missing: {description} ({filepath})")
        return False

def main():
    print_header("🚀 COMPLETE POWER BI SETUP - TWO DASHBOARDS")
    print("Dashboard 1: Progress Report (Model Properties)")
    print("Dashboard 2: Issues Tracking (Issues + 3D Viewer)")
    
    # Check required files
    print_header("Checking Required Files")
    required_files = {
        'main.py': 'Model data extractor',
        'config.py': 'Configuration',
        'create_viewer_integration.py': 'Integration layer',
        'acc_issues_fetcher_simple.py': 'Issues fetcher',
        'unified_acc_server.py': 'Unified server',
        '.env': 'Environment variables'
    }
    
    all_files_present = True
    for file, desc in required_files.items():
        if not check_file_exists(file, desc):
            all_files_present = False
    
    if not all_files_present:
        print("\n❌ Some required files are missing!")
        print("   Please ensure all files are in the same directory.")
        sys.exit(1)
    
    print("\n✅ All required files present!")
    
    # Step 1: Extract model data for Progress Report
    print_header("STEP 1/4: Extract Model Properties")
    print("This creates data for Progress Report dashboard")
    print("Estimated time: 2-5 minutes depending on model size\n")
    
    if not run_command(
        "Extracting model properties from APS",
        f"{sys.executable} main.py --full",
        required=True
    ):
        print("\n❌ Model extraction failed!")
        print("\n💡 Troubleshooting:")
        print("   1. Check your .env file has correct credentials")
        print("   2. Verify VERSION_URN is correct")
        print("   3. Run: python diagnose_model.py")
        print("   4. Check config.py has the clean_version_urn() fix")
        
        response = input("\n❓ Continue without model data? (Issues dashboard will still work) [y/N]: ")
        if response.lower() != 'y':
            sys.exit(1)
        else:
            print("\n⚠️  Continuing without model properties...")
            print("   Progress Report dashboard will not be available")
            print("   Issues dashboard will work normally")
    
    # Step 2: Create integration tables
    print_header("STEP 2/4: Create Integration Layer")
    print("This links issues to 3D model elements\n")
    
    if not run_command(
        "Creating viewer integration tables",
        f"{sys.executable} create_viewer_integration.py",
        required=False
    ):
        print("⚠️  Integration creation skipped")
        print("   This is optional - issues will still work")
    
    # Step 3: Test issues fetcher
    print_header("STEP 3/4: Verify Issues Access")
    print("Testing connection to ACC Issues API\n")
    
    print("▶️  Testing issues fetcher...")
    try:
        from acc_issues_fetcher_simple import fetch_all_issues
        issues = fetch_all_issues()
        print(f"✅ Successfully connected! Found {len(issues)} issues\n")
    except Exception as e:
        print(f"⚠️  Issues test failed: {e}")
        print("   Server will use direct API calls instead\n")
    
    # Step 4: Start server
    print_header("STEP 4/4: Starting Unified Server")
    print("Server provides ALL data for both dashboards\n")
    
    print("="*70)
    print("✅ SETUP COMPLETE - SERVER STARTING!")
    print("="*70)
    
    print("\n📊 POWER BI CONNECTIONS:")
    print("\n   🏗️  DASHBOARD 1: Progress Report")
    print("      Get Data → Web:")
    print("      • Elements:   http://localhost:5000/api/elements")
    print("      • Quantities: http://localhost:5000/api/quantities")
    print("      • Levels:     http://localhost:5000/api/levels")
    print("      • Types:      http://localhost:5000/api/types")
    
    print("\n   🔧 DASHBOARD 2: Issues Tracking")
    print("      Get Data → Web:")
    print("      • Issues:     http://localhost:5000/api/issues")
    print("      3D Viewer:")
    print("      • HTML:       http://localhost:5000")
    
    print("\n   ⚡ QUICK START (Single Endpoint):")
    print("      • All Data:   http://localhost:5000/api/powerbi")
    
    print("\n🎨 WHAT YOU'LL BUILD:")
    print("   Page 1: Progress Report")
    print("      • Element counts by type/level")
    print("      • Quantities (area, volume, length)")
    print("      • Progress charts")
    print("      • Material schedules")
    
    print("   Page 2: Issues Dashboard")
    print("      • Issue tracking table")
    print("      • Status KPIs")
    print("      • 3D model viewer")
    print("      • Interactive slicers")
    
    print("\n" + "="*70)
    print("⚡ Server starting on port 5000...")
    print("   Keep this window open!")
    print("   Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    # Start server (runs until Ctrl+C)
    try:
        subprocess.run(
            f"{sys.executable} unified_acc_server.py",
            shell=True,
            check=True
        )
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("🛑 Server stopped by user")
        print("="*70)
        print("\n✅ To restart: python run_all.py")
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Setup interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)