"""
Data Cleaner Module
Cleans and standardizes extracted data
"""
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)


class DataCleaner:
    """Cleans and standardizes raw data"""
    
    def __init__(self, config):
        self.config = config
    
    def clean_data(self, input_file, output_file):
        """
        Main cleaning pipeline:
        1. Load data
        2. Remove empty columns
        3. Standardize units
        4. Parse numeric values
        5. Clean text fields
        6. Validate data
        """
        logger.info("=" * 80)
        logger.info("Starting Data Cleaning")
        logger.info("=" * 80)
        
        # Step 1: Load data
        logger.info(f"Loading data from {input_file}...")
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        logger.info(f"✅ Loaded {len(df)} rows, {len(df.columns)} columns")
        
        initial_rows = len(df)
        initial_cols = len(df.columns)
        
        # Step 2: Remove columns with high null percentage
        df = self._remove_empty_columns(df)
        
        # Step 3: Standardize units and parse numeric values
        df = self._standardize_units(df)
        
        # Step 4: Clean text fields
        df = self._clean_text_fields(df)
        
        # Step 5: Add calculated fields
        df = self._add_calculated_fields(df)
        
        # Step 6: Remove duplicate rows
        df = df.drop_duplicates(subset=['objectId'], keep='first')
        
        # Step 7: Save cleaned data
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        logger.info(f"✅ Cleaned data saved to {output_file}")
        logger.info(f"   • Initial: {initial_rows} rows, {initial_cols} columns")
        logger.info(f"   • Final: {len(df)} rows, {len(df.columns)} columns")
        logger.info(f"   • Removed: {initial_cols - len(df.columns)} columns")
        logger.info("=" * 80)
        
        return output_file
    
    def _remove_empty_columns(self, df):
        """Remove columns with high percentage of null values"""
        threshold = self.config.get('null_threshold', 0.95)
        
        initial_cols = len(df.columns)
        required = self.config.get('required_columns', [])
        
        # Calculate null percentage for each column
        null_pct = df.isnull().sum() / len(df)
        
        # Keep columns below threshold or required columns
        cols_to_keep = []
        for col in df.columns:
            if col in required or null_pct[col] < threshold:
                cols_to_keep.append(col)
        
        df = df[cols_to_keep]
        
        removed = initial_cols - len(df.columns)
        if removed > 0:
            logger.info(f"   Removed {removed} columns with >{threshold*100}% nulls")
        
        return df
    
    def _standardize_units(self, df):
        """Parse and standardize units (mm to m, etc.)"""
        numeric_cols = self.config.get('numeric_columns', [])
        conversions = self.config.get('unit_conversions', {})
        
        logger.info("   Standardizing units...")
        converted_count = 0
        
        for col in df.columns:
            # Check if column should be processed
            if any(pattern in col for pattern in ['Dimensions_', 'Length', 'Width', 'Height', 'Volume', 'Area', 'Cost']):
                try:
                    # Create new column for numeric value
                    numeric_col_name = col.replace('Dimensions_', '').replace(' ', '_').lower()
                    
                    # Parse values
                    df[numeric_col_name] = df[col].apply(lambda x: self._parse_value_with_unit(x, conversions))
                    
                    if df[numeric_col_name].notna().sum() > 0:
                        converted_count += 1
                        
                except Exception as e:
                    logger.warning(f"   Could not parse column {col}: {e}")
        
        logger.info(f"   ✅ Standardized {converted_count} numeric columns")
        return df
    
    def _parse_value_with_unit(self, value_str, conversions):
        """Extract numeric value and convert units"""
        if pd.isna(value_str) or value_str == "":
            return None
        
        try:
            value_str = str(value_str).strip()
            
            # Extract number and unit
            match = re.match(r'([-+]?\d*\.?\d+)\s*([a-zA-Z^_฿]*)', value_str)
            
            if match:
                number = float(match.group(1))
                unit = match.group(2).strip()
                
                # Convert based on unit
                if unit in conversions:
                    return number * conversions[unit]
                elif unit:
                    # Unknown unit, try to infer
                    if 'mm' in unit.lower():
                        return number * 0.001  # mm to m
                    elif 'cm' in unit.lower():
                        return number * 0.01   # cm to m
                    elif 'm' in unit.lower() and '^3' not in unit:
                        return number * 1.0    # already in meters
                
                return number
            
            # If no match, try to parse as float
            return float(value_str.split()[0])
            
        except:
            return None
    
    def _clean_text_fields(self, df):
        """Clean and standardize text fields"""
        logger.info("   Cleaning text fields...")
        
        for col in df.columns:
            if df[col].dtype == 'object':
                # Strip whitespace
                df[col] = df[col].astype(str).str.strip()
                
                # Replace empty strings with None
                df[col] = df[col].replace(['', 'nan', 'None'], None)
        
        logger.info("   ✅ Text fields cleaned")
        return df
    
    def _add_calculated_fields(self, df):
        """Add useful calculated fields"""
        logger.info("   Adding calculated fields...")
        
        # Extract element type from name (before bracket)
        if 'name' in df.columns:
            df['element_type'] = df['name'].apply(
                lambda x: str(x).split('[')[0].strip() if pd.notna(x) else None
            )
        
        # Extract element ID from name (inside bracket)
        if 'name' in df.columns:
            df['element_id'] = df['name'].apply(
                lambda x: self._extract_element_id(x)
            )
        
        # Parse level information
        for col in df.columns:
            if 'Level' in col and 'level' not in df.columns:
                df['level'] = df[col]
                break
        
        # Parse phase
        for col in df.columns:
            if 'Phase' in col and 'phase' not in df.columns:
                df['phase'] = df[col]
                break
        
        logger.info("   ✅ Calculated fields added")
        return df
    
    def _extract_element_id(self, name):
        """Extract element ID from name like 'Element [123456]'"""
        if pd.isna(name):
            return None
        
        match = re.search(r'\[(\d+)\]', str(name))
        return match.group(1) if match else None