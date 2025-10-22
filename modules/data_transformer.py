"""
Data Transformer Module
Transforms cleaned data into Power BI ready star schema
"""
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)


class DataTransformer:
    """Transforms data into star schema for Power BI"""
    
    def __init__(self, config):
        self.config = config
    
    def transform_data(self, input_file, output_files):
        """Transform to star schema"""
        logger.info("=" * 80)
        logger.info("Starting Data Transformation")
        logger.info("=" * 80)
        
        # Load cleaned data
        logger.info(f"Loading cleaned data from {input_file}...")
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        logger.info(f"✅ Loaded {len(df)} rows")
        
        # Create dimension tables
        dim_elements = self._create_dim_elements(df)
        dim_levels = self._create_dim_levels(df)
        dim_types = self._create_dim_types(df)
        
        # Create fact tables
        fact_quantities = self._create_fact_quantities(df, dim_elements, dim_levels, dim_types)
        fact_properties = self._create_fact_properties(df)
        
        # Save all tables
        tables = {
            'dim_elements': dim_elements,
            'dim_levels': dim_levels,
            'dim_types': dim_types,
            'fact_quantities': fact_quantities,
            'fact_properties': fact_properties
        }
        
        for table_name, table_df in tables.items():
            output_file = output_files[table_name]
            table_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            logger.info(f"✅ Saved {table_name}: {len(table_df)} rows → {output_file.name}")
        
        logger.info("=" * 80)
        logger.info("Data Transformation Complete")
        logger.info("=" * 80)
        
        return tables
    
    def _create_dim_elements(self, df):
        """Create element dimension table"""
        logger.info("   Creating dim_elements...")
        
        dim_elements = df[['objectId', 'name', 'externalId', 'element_type', 'element_id']].copy()
        
        type_mapping = self._create_type_mapping(df)
        dim_elements['element_type_id'] = dim_elements['element_type'].map(type_mapping)
        
        level_col = self._find_level_column(df)
        if level_col:
            level_mapping = self._create_level_mapping(df, level_col)
            dim_elements['level_id'] = df[level_col].map(level_mapping)
            dim_elements['level_name'] = df[level_col]
        else:
            dim_elements['level_id'] = None
            dim_elements['level_name'] = None
        
        return dim_elements
    
    def _create_dim_levels(self, df):
        """Create level dimension table"""
        logger.info("   Creating dim_levels...")
        
        level_col = self._find_level_column(df)
        
        if level_col and level_col in df.columns:
            levels = df[level_col].dropna().unique()
            
            dim_levels = pd.DataFrame({
                'level_id': range(1, len(levels) + 1),
                'level_name': sorted(levels),
            })
            
            dim_levels['level_order'] = dim_levels['level_name'].apply(lambda x: self._extract_level_order(x))
        else:
            dim_levels = pd.DataFrame({
                'level_id': [1],
                'level_name': ['Unknown'],
                'level_order': [0]
            })
        
        return dim_levels
    
    def _create_dim_types(self, df):
        """Create element type dimension table"""
        logger.info("   Creating dim_types...")
        
        if 'element_type' in df.columns:
            types = df['element_type'].dropna().unique()
            
            dim_types = pd.DataFrame({
                'type_id': range(1, len(types) + 1),
                'type_name': sorted(types),
            })
            
            categories = self.config.get('element_categories', {})
            dim_types['category'] = dim_types['type_name'].apply(lambda x: self._categorize_element(x, categories))
        else:
            dim_types = pd.DataFrame({
                'type_id': [1],
                'type_name': ['Unknown'],
                'category': ['Other']
            })
        
        return dim_types
    
    def _create_fact_quantities(self, df, dim_elements, dim_levels, dim_types):
        """Create quantities fact table"""
        logger.info("   Creating fact_quantities...")
        
        quantity_cols = ['objectId']
        
        for col in df.columns:
            if col in ['length', 'width', 'height', 'volume', 'area', 'b', 'cost']:
                quantity_cols.append(col)
        
        fact_quantities = df[quantity_cols].copy() if all(c in df.columns for c in quantity_cols) else df[['objectId']].copy()
        
        fact_quantities['element_type_id'] = df['element_type'].map(dict(zip(dim_types['type_name'], dim_types['type_id'])))
        
        level_col = self._find_level_column(df)
        if level_col:
            fact_quantities['level_id'] = df[level_col].map(dict(zip(dim_levels['level_name'], dim_levels['level_id'])))
        else:
            fact_quantities['level_id'] = 1
        
        if 'phase' in df.columns:
            fact_quantities['phase'] = df['phase']
        
        return fact_quantities
    
    def _create_fact_properties(self, df):
        """Create properties fact table (all properties)"""
        logger.info("   Creating fact_properties...")
        return df.copy()
    
    def _find_level_column(self, df):
        """Find the level column"""
        level_patterns = ['Constraints_Base Level', 'Base Level', 'Level', 'level']
        
        for pattern in level_patterns:
            for col in df.columns:
                if pattern in col:
                    return col
        
        return None
    
    def _create_type_mapping(self, df):
        """Create mapping from type name to type ID"""
        if 'element_type' not in df.columns:
            return {}
        
        types = sorted(df['element_type'].dropna().unique())
        return {type_name: i + 1 for i, type_name in enumerate(types)}
    
    def _create_level_mapping(self, df, level_col):
        """Create mapping from level name to level ID"""
        levels = sorted(df[level_col].dropna().unique())
        return {level_name: i + 1 for i, level_name in enumerate(levels)}
    
    def _extract_level_order(self, level_name):
        """Extract numeric order from level name"""
        if pd.isna(level_name):
            return 0
        
        match = re.match(r'(\d+)', str(level_name))
        return int(match.group(1)) if match else 0
    
    def _categorize_element(self, element_type, categories):
        """Categorize element type"""
        if pd.isna(element_type):
            return 'Other'
        
        element_type_lower = str(element_type).lower()
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword.lower() in element_type_lower:
                    return category
        
        return 'Other'