"""
Data Extractor Module
Extracts properties from APS and saves to CSV with area calculations
"""
import csv
import logging
import math
import re
from collections import OrderedDict
from .aps_connector import APSConnector

logger = logging.getLogger(__name__)


class DataExtractor:
    """Extracts and exports APS data to CSV"""
    
    def __init__(self, aps_connector):
        self.connector = aps_connector
    
    def extract_to_csv(self, version_urn, output_file):
        """Complete extraction pipeline"""
        logger.info("=" * 80)
        logger.info("Starting Data Extraction")
        logger.info("=" * 80)
        
        # Translate
        if not self.connector.translate_model(version_urn):
            raise Exception("Translation failed")
        
        # Wait for translation
        if not self.connector.wait_for_translation(version_urn):
            raise Exception("Translation did not complete")
        
        # Get metadata
        metadata = self.connector.get_metadata(version_urn)
        if not metadata:
            raise Exception("Failed to get metadata")
        
        # Find 3D view
        view_3d = self._find_3d_view(metadata)
        if not view_3d:
            raise Exception("No 3D view found")
        
        guid = view_3d["guid"]
        logger.info(f"Processing 3D view: {view_3d.get('name', 'Unknown')}")
        
        # Get properties
        properties = self.connector.get_properties(version_urn, guid)
        if not properties:
            raise Exception("Failed to get properties")
        
        # Export to CSV with area calculation
        self._export_to_csv(properties, output_file)
        
        logger.info("=" * 80)
        logger.info("Data Extraction Complete")
        logger.info("=" * 80)
        
        return output_file
    
    def _find_3d_view(self, metadata):
        """Find the 3D viewable"""
        for view in metadata["data"]["metadata"]:
            if view.get("role") == "3d":
                return view
        return None
    
    def _calculate_area(self, properties_dict):
        """Calculate area if missing"""
        length = properties_dict.get("Dimensions_Length", "")
        width = properties_dict.get("Dimensions_Width", "")
        
        if length and width:
            try:
                length_val = self._parse_numeric(length)
                width_val = self._parse_numeric(width)
                if length_val and width_val:
                    if "mm" in str(length).lower():
                        length_val = length_val / 1000
                        width_val = width_val / 1000
                    area = length_val * width_val
                    return f"{area:.3f} m^2"
            except:
                pass
        
        diameter = properties_dict.get("Dimensions_b", "")
        if diameter:
            try:
                diameter_val = self._parse_numeric(diameter)
                if diameter_val:
                    if "mm" in str(diameter).lower():
                        diameter_val = diameter_val / 1000
                    radius = diameter_val / 2
                    area = math.pi * radius * radius
                    return f"{area:.3f} m^2"
            except:
                pass
        
        return None
    
    def _parse_numeric(self, value_str):
        """Extract numeric value from string"""
        if not value_str:
            return None
        
        try:
            numeric_part = ''.join(c for c in str(value_str).split()[0] if c.isdigit() or c in '.-')
            return float(numeric_part) if numeric_part else None
        except:
            return None
    
    def _export_to_csv(self, properties_data, output_file):
        """Export properties to CSV"""
        if not properties_data or "data" not in properties_data:
            raise Exception("No data to export")
        
        collection = properties_data.get("data", {}).get("collection", [])
        if not collection:
            raise Exception("No objects found in collection")
        
        logger.info(f"Processing {len(collection)} objects...")
        
        # Collect columns
        all_columns = OrderedDict()
        all_columns["objectId"] = None
        all_columns["name"] = None
        all_columns["externalId"] = None
        
        for obj in collection:
            properties = obj.get("properties", {})
            for category_name, category_props in properties.items():
                if isinstance(category_props, dict):
                    for prop_name in category_props.keys():
                        column_name = f"{category_name}_{prop_name}"
                        all_columns[column_name] = None
        
        if "Dimensions_Area" not in all_columns:
            all_columns["Dimensions_Area"] = None
        
        logger.info(f"Found {len(all_columns)} columns")
        
        # Prepare data
        csv_data = []
        area_calculated_count = 0
        
        for obj in collection:
            row = OrderedDict()
            row["objectId"] = obj.get("objectid", "")
            row["name"] = obj.get("name", "")
            row["externalId"] = obj.get("externalId", "")
            
            properties = obj.get("properties", {})
            props_flat = {}
            
            for category_name, category_props in properties.items():
                if isinstance(category_props, dict):
                    for prop_name, prop_value in category_props.items():
                        column_name = f"{category_name}_{prop_name}"
                        props_flat[column_name] = prop_value
                        row[column_name] = prop_value
            
            # Calculate area if missing
            if not props_flat.get("Dimensions_Area"):
                calculated_area = self._calculate_area(props_flat)
                if calculated_area:
                    row["Dimensions_Area"] = calculated_area
                    area_calculated_count += 1
            
            # Fill missing columns
            for col in all_columns.keys():
                if col not in row:
                    row[col] = ""
            
            csv_data.append(row)
        
        # Write CSV
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_columns.keys()))
            writer.writeheader()
            writer.writerows(csv_data)
        
        logger.info(f"✅ Exported {len(csv_data)} rows to {output_file}")
        logger.info(f"   • Total columns: {len(all_columns)}")
        logger.info(f"   • Areas calculated: {area_calculated_count}")
        
        return True