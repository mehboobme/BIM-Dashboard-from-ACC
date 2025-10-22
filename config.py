"""
Configuration file for APS to Power BI pipeline
Complete version with all required settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / 'output'
RAW_DIR = OUTPUT_DIR / 'raw'
CLEANED_DIR = OUTPUT_DIR / 'cleaned'
TRANSFORMED_DIR = OUTPUT_DIR / 'transformed'
REPORTS_DIR = OUTPUT_DIR / 'reports'
LOGS_DIR = BASE_DIR / 'logs'

# Create directories if they don't exist
for directory in [OUTPUT_DIR, RAW_DIR, CLEANED_DIR, TRANSFORMED_DIR, REPORTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# ==================== URN CLEANING FUNCTION ====================
def clean_version_urn(urn):
    """
    Keep the ?version=X parameter for ACC (Autodesk Construction Cloud) files.
    Model Derivative API now supports full version URNs.
    """
    if urn:
        print(f"\nℹ️  URN Verified (version kept): {urn}\n")
    return urn



# ==================== APS CONFIGURATION ====================
APS_CONFIG = {
    'CLIENT_ID': os.getenv('APS_CLIENT_ID'),
    'CLIENT_SECRET': os.getenv('APS_CLIENT_SECRET'),
    'BASE_URL': os.getenv('BASE_URL', 'https://developer.api.autodesk.com'),
    'VERSION_URN': clean_version_urn(os.getenv('VERSION_URN')),  # Keep version param
    'ORIGINAL_URN': os.getenv('ORIGINAL_URN'),  # Keep lineage reference
}



# ==================== FILE PATHS ====================
FILES = {
    # Raw data
    'raw_properties': RAW_DIR / 'model_properties_raw.csv',
    
    # Cleaned data
    'cleaned_properties': CLEANED_DIR / 'model_properties_cleaned.csv',
    
    # Dimension tables
    'dim_elements': TRANSFORMED_DIR / 'dim_elements.csv',
    'dim_levels': TRANSFORMED_DIR / 'dim_levels.csv',
    'dim_types': TRANSFORMED_DIR / 'dim_types.csv',
    
    # Fact tables
    'fact_quantities': TRANSFORMED_DIR / 'fact_quantities.csv',
    'fact_properties': TRANSFORMED_DIR / 'fact_properties.csv',
    
    # Reports
    'validation_report': REPORTS_DIR / 'validation_report.html',
    'summary_report': REPORTS_DIR / 'summary_report.txt',
    
    # Logs
    'log_file': LOGS_DIR / 'pipeline.log',
}


# ==================== LOGGING CONFIGURATION ====================
LOGGING_CONFIG = {
    'level': 'INFO',  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S'
}


# ==================== DATA CLEANING CONFIGURATION ====================
CLEANING_CONFIG = {
    # Columns to drop if they exist
    'columns_to_drop': [
        'properties.__parent__',
        'properties.__internalref__',
        'properties.__instanceof_objid',
    ],
    
    # Handle missing values
    'fill_na_values': {
        'name': 'Unnamed',
        'element_type': 'Unknown',
        'level': 'Unassigned',
    },
    
    # Remove duplicates based on these columns
    'duplicate_subset': ['objectId'],
    
    # Standardize text columns
    'text_columns_to_strip': ['name', 'element_type', 'level', 'category'],
    
    # Remove rows where all values are null
    'drop_empty_rows': True,
}


# ==================== DATA TRANSFORMATION CONFIGURATION ====================
TRANSFORM_CONFIG = {
    # Element dimension
    'element_fields': [
        'objectId',
        'externalId', 
        'name',
        'element_type',
        'category',
        'level',
        'family',
    ],
    
    # Level dimension
    'level_fields': [
        'level',
        'elevation',
    ],
    
    # Type dimension
    'type_fields': [
        'element_type',
        'category',
        'family',
    ],
    
    # Quantity fields to extract
    'quantity_fields': [
        'Volume',
        'Area',
        'Length',
        'Width',
        'Height',
        'Perimeter',
        'Count',
    ],
    
    # Property fields to include in fact table
    'property_fields': [
        'Material',
        'Structural Material',
        'Function',
        'Type Mark',
        'Mark',
        'Comments',
        'Phase Created',
        'Phase Demolished',
    ],
}


# ==================== DATA VALIDATION CONFIGURATION ====================
VALIDATION_CONFIG = {
    # Minimum expected row counts
    'min_row_counts': {
        'dim_elements': 10,
        'dim_levels': 1,
        'dim_types': 1,
        'fact_quantities': 5,
        'fact_properties': 5,
    },
    
    # Required columns for each table
    'required_columns': {
        'dim_elements': ['objectId', 'name', 'element_type'],
        'dim_levels': ['level'],
        'dim_types': ['element_type'],
        'fact_quantities': ['element_id', 'quantity_name', 'quantity_value'],
        'fact_properties': ['element_id', 'property_name', 'property_value'],
    },
    
    # Uniqueness checks
    'unique_constraints': {
        'dim_elements': ['objectId'],
    },
    
    # Not null checks
    'not_null_constraints': {
        'dim_elements': ['objectId', 'name'],
        'fact_quantities': ['element_id', 'quantity_name'],
        'fact_properties': ['element_id', 'property_name'],
    },
}


# ==================== POWER BI CONFIGURATION ====================
POWERBI_CONFIG = {
    # Refresh settings
    'auto_refresh_minutes': 5,
    
    # Data source URLs (for unified server)
    'server_port': 5000,
    'server_host': 'localhost',
    
    # Endpoint URLs
    'endpoints': {
        'issues': 'http://localhost:5000/api/issues',
        'elements': 'http://localhost:5000/api/elements',
        'quantities': 'http://localhost:5000/api/quantities',
        'levels': 'http://localhost:5000/api/levels',
        'types': 'http://localhost:5000/api/types',
        'viewer_control': 'http://localhost:5000/api/viewer-control',
        'powerbi_all': 'http://localhost:5000/api/powerbi',
        'health': 'http://localhost:5000/health',
    },
}


# ==================== VALIDATION FUNCTION ====================
def validate_config():
    """
    Validate configuration settings
    Raises exceptions if critical settings are missing
    """
    errors = []
    
    # Check APS credentials
    if not APS_CONFIG['CLIENT_ID']:
        errors.append("APS_CLIENT_ID not set in .env")
    if not APS_CONFIG['CLIENT_SECRET']:
        errors.append("APS_CLIENT_SECRET not set in .env")
    if not APS_CONFIG['VERSION_URN']:
        errors.append("VERSION_URN not set in .env")
    
    # Check directories exist
    required_dirs = [OUTPUT_DIR, RAW_DIR, CLEANED_DIR, TRANSFORMED_DIR, REPORTS_DIR, LOGS_DIR]
    for directory in required_dirs:
        if not directory.exists():
            errors.append(f"Directory does not exist: {directory}")
    
    if errors:
        error_msg = "\n❌ Configuration Errors:\n" + "\n".join(f"   • {e}" for e in errors)
        raise ValueError(error_msg)
    
    return True


# ==================== DISPLAY CONFIGURATION ====================
def display_config():
    """Display current configuration (for debugging)"""
    print("\n" + "="*70)
    print("CONFIGURATION SUMMARY")
    print("="*70)
    
    print("\n📁 Directories:")
    print(f"   Base: {BASE_DIR}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Raw: {RAW_DIR}")
    print(f"   Cleaned: {CLEANED_DIR}")
    print(f"   Transformed: {TRANSFORMED_DIR}")
    print(f"   Reports: {REPORTS_DIR}")
    print(f"   Logs: {LOGS_DIR}")
    
    print("\n🔐 APS Configuration:")
    print(f"   Client ID: {APS_CONFIG['CLIENT_ID'][:20]}..." if APS_CONFIG['CLIENT_ID'] else "   Client ID: Not set")
    print(f"   Client Secret: {'*' * 20}..." if APS_CONFIG['CLIENT_SECRET'] else "   Client Secret: Not set")
    print(f"   Base URL: {APS_CONFIG['BASE_URL']}")
    print(f"   VERSION_URN: {APS_CONFIG['VERSION_URN'][:60]}..." if APS_CONFIG['VERSION_URN'] else "   VERSION_URN: Not set")
    
    print("\n📊 Output Files:")
    for key, path in FILES.items():
        status = "✓" if path.exists() else "○"
        print(f"   {status} {key}: {path.name}")
    
    print("\n🔧 Logging:")
    print(f"   Level: {LOGGING_CONFIG['level']}")
    print(f"   Log File: {FILES['log_file']}")
    
    print("\n" + "="*70 + "\n")


# ==================== EXPORT CONFIG ====================
__all__ = [
    'APS_CONFIG',
    'FILES',
    'LOGGING_CONFIG',
    'CLEANING_CONFIG',
    'TRANSFORM_CONFIG',
    'VALIDATION_CONFIG',
    'POWERBI_CONFIG',
    'BASE_DIR',
    'OUTPUT_DIR',
    'RAW_DIR',
    'CLEANED_DIR',
    'TRANSFORMED_DIR',
    'REPORTS_DIR',
    'LOGS_DIR',
    'validate_config',
    'display_config',
]


# Run validation on import (optional - comment out if not desired)
if __name__ != "__main__":
    try:
        validate_config()
    except ValueError as e:
        print(e)
        print("\n⚠️  Please fix the configuration errors above")