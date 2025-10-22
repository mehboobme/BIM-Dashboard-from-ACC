"""
Create integration data for Power BI + 3D Viewer
This links your issues to 3D model elements
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def create_viewer_integration():
    """
    Create integration tables that link Power BI data to 3D viewer
    """
    print("=" * 60)
    print("Creating Power BI + 3D Viewer Integration")
    print("=" * 60)
    
    # Load data
    print("\n1️⃣  Loading data...")
    dim_elements = pd.read_csv(config.FILES['dim_elements'], encoding='utf-8-sig')
    issues = pd.read_csv(config.TRANSFORMED_DIR / 'issues.csv', encoding='utf-8-sig')
    
    print(f"   ✅ {len(dim_elements)} elements")
    print(f"   ✅ {len(issues)} issues")
    
    # Create viewer control table
    print("\n2️⃣  Creating viewer control table...")
    
    # This table controls what the viewer shows
    viewer_control = dim_elements[['objectId', 'externalId', 'name', 'element_type']].copy()
    
    # Add issue information
    # Merge with issues to know which elements have problems
    element_issues = issues.groupby('objectId').agg({
        'issue_id': 'count',
        'severity': lambda x: x.mode()[0] if len(x) > 0 else 'None'
    }).reset_index()
    element_issues.columns = ['objectId', 'issue_count', 'max_severity']
    
    viewer_control = viewer_control.merge(
        element_issues,
        on='objectId',
        how='left'
    )
    
    # Fill missing values
    viewer_control['issue_count'] = viewer_control['issue_count'].fillna(0).astype(int)
    viewer_control['max_severity'] = viewer_control['max_severity'].fillna('None')
    
    # Add color codes based on issues
    viewer_control['highlight_color'] = viewer_control['max_severity'].map({
        'High': '#E74C3C',      # Red
        'Medium': '#F39C12',    # Orange
        'Low': '#F1C40F',       # Yellow
        'None': '#95A5A6'       # Gray
    })
    
    # Add visibility flag (Power BI can filter this)
    viewer_control['visible'] = True
    viewer_control['isolated'] = False
    
    # Save viewer control
    output_file = config.TRANSFORMED_DIR / 'viewer_control.csv'
    viewer_control.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"   ✅ Created viewer control: {output_file}")
    
    # Create issue-element mapping for highlighting
    print("\n3️⃣  Creating issue-element mapping...")
    
    issue_elements = issues[['issue_id', 'objectId', 'severity', 'status']].copy()
    issue_elements = issue_elements.merge(
        dim_elements[['objectId', 'externalId', 'name']],
        on='objectId',
        how='left'
    )
    
    output_file2 = config.TRANSFORMED_DIR / 'issue_elements.csv'
    issue_elements.to_csv(output_file2, index=False, encoding='utf-8-sig')
    
    print(f"   ✅ Created issue mapping: {output_file2}")
    
    # Create summary statistics
    print("\n4️⃣  Creating summary statistics...")
    
    summary = {
        'total_elements': len(viewer_control),
        'elements_with_issues': int((viewer_control['issue_count'] > 0).sum()),
        'high_severity': int((viewer_control['max_severity'] == 'High').sum()),
        'medium_severity': int((viewer_control['max_severity'] == 'Medium').sum()),
        'low_severity': int((viewer_control['max_severity'] == 'Low').sum()),
    }
    
    print(f"\n   📊 Summary:")
    for key, value in summary.items():
        print(f"      • {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ Integration files created!")
    print("=" * 60)
    print("\nFiles created:")
    print("  • viewer_control.csv - Controls 3D viewer")
    print("  • issue_elements.csv - Links issues to elements")
    print("\nNext: Set up Power BI dashboard")
    
    return True


if __name__ == "__main__":
    create_viewer_integration()