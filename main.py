"""
Main Orchestrator Script
Runs the complete APS to Power BI data pipeline
"""
import argparse
import logging
import sys
from pathlib import Path

import config
from modules.aps_connector import APSConnector
from modules.data_extractor import DataExtractor
from modules.data_cleaner import DataCleaner
from modules.data_transformer import DataTransformer
from modules.data_validator import DataValidator


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, config.LOGGING_CONFIG['level']),
        format=config.LOGGING_CONFIG['format'],
        datefmt=config.LOGGING_CONFIG['date_format'],
        handlers=[
            logging.FileHandler(config.FILES['log_file'], encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def run_extraction(logger):
    """Run data extraction stage"""
    logger.info("\n" + "🔹" * 40)
    logger.info("STAGE 1: DATA EXTRACTION")
    logger.info("🔹" * 40 + "\n")
    
    try:
        connector = APSConnector(
            client_id=config.APS_CONFIG['CLIENT_ID'],
            client_secret=config.APS_CONFIG['CLIENT_SECRET'],
            base_url=config.APS_CONFIG['BASE_URL']
        )
        
        extractor = DataExtractor(connector)
        
        output_file = extractor.extract_to_csv(
            version_urn=config.APS_CONFIG['VERSION_URN'],
            output_file=config.FILES['raw_properties']
        )
        
        logger.info(f"✅ Extraction complete: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}", exc_info=True)
        return False


def run_cleaning(logger):
    """Run data cleaning stage"""
    logger.info("\n" + "🔹" * 40)
    logger.info("STAGE 2: DATA CLEANING")
    logger.info("🔹" * 40 + "\n")
    
    try:
        cleaner = DataCleaner(config.CLEANING_CONFIG)
        
        output_file = cleaner.clean_data(
            input_file=config.FILES['raw_properties'],
            output_file=config.FILES['cleaned_properties']
        )
        
        logger.info(f"✅ Cleaning complete: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Cleaning failed: {e}", exc_info=True)
        return False


def run_transformation(logger):
    """Run data transformation stage"""
    logger.info("\n" + "🔹" * 40)
    logger.info("STAGE 3: DATA TRANSFORMATION")
    logger.info("🔹" * 40 + "\n")
    
    try:
        transformer = DataTransformer(config.TRANSFORM_CONFIG)
        
        tables = transformer.transform_data(
            input_file=config.FILES['cleaned_properties'],
            output_files=config.FILES
        )
        
        logger.info(f"✅ Transformation complete: {len(tables)} tables created")
        return tables
        
    except Exception as e:
        logger.error(f"❌ Transformation failed: {e}", exc_info=True)
        return None


def run_validation(logger, tables):
    """Run data validation stage"""
    logger.info("\n" + "🔹" * 40)
    logger.info("STAGE 4: DATA VALIDATION")
    logger.info("🔹" * 40 + "\n")
    
    try:
        validator = DataValidator(config.VALIDATION_CONFIG)
        
        results = validator.validate_data(
            tables=tables,
            report_files=config.FILES
        )
        
        logger.info(f"✅ Validation complete: {len(results)} checks performed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}", exc_info=True)
        return False


def run_full_pipeline(logger):
    """Run complete pipeline"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 STARTING FULL PIPELINE: APS TO POWER BI")
    logger.info("=" * 80 + "\n")
    
    # Stage 1: Extraction
    if not run_extraction(logger):
        logger.error("❌ Pipeline failed at extraction stage")
        return False
    
    # Stage 2: Cleaning
    if not run_cleaning(logger):
        logger.error("❌ Pipeline failed at cleaning stage")
        return False
    
    # Stage 3: Transformation
    tables = run_transformation(logger)
    if tables is None:
        logger.error("❌ Pipeline failed at transformation stage")
        return False
    
    # Stage 4: Validation
    if not run_validation(logger, tables):
        logger.error("❌ Pipeline failed at validation stage")
        return False
    
    # Success!
    logger.info("\n" + "=" * 80)
    logger.info("✅ PIPELINE COMPLETED SUCCESSFULLY!")
    logger.info("=" * 80)
    logger.info(f"\n📁 Output files:")
    logger.info(f"   Raw data: {config.FILES['raw_properties']}")
    logger.info(f"   Cleaned data: {config.FILES['cleaned_properties']}")
    logger.info(f"   Dimension tables:")
    logger.info(f"      • {config.FILES['dim_elements']}")
    logger.info(f"      • {config.FILES['dim_levels']}")
    logger.info(f"      • {config.FILES['dim_types']}")
    logger.info(f"   Fact tables:")
    logger.info(f"      • {config.FILES['fact_quantities']}")
    logger.info(f"      • {config.FILES['fact_properties']}")
    logger.info(f"   Reports:")
    logger.info(f"      • {config.FILES['validation_report']}")
    logger.info(f"      • {config.FILES['summary_report']}")
    logger.info(f"\n📊 Next Step: Refresh Power BI to see updated data")
    logger.info("=" * 80 + "\n")
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="APS to Power BI Data Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --full              Run complete pipeline
  python main.py --extract           Extract data only
  python main.py --clean             Clean data only
  python main.py --transform         Transform data only
  python main.py --validate          Validate data only
        """
    )
    
    parser.add_argument('--full', action='store_true', help='Run complete pipeline')
    parser.add_argument('--extract', action='store_true', help='Run extraction stage only')
    parser.add_argument('--clean', action='store_true', help='Run cleaning stage only')
    parser.add_argument('--transform', action='store_true', help='Run transformation stage only')
    parser.add_argument('--validate', action='store_true', help='Run validation stage only')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    try:
        # Validate configuration
        config.validate_config()
        
        # Run requested stages
        if args.full or not any([args.extract, args.clean, args.transform, args.validate]):
            success = run_full_pipeline(logger)
            sys.exit(0 if success else 1)
        
        else:
            if args.extract:
                if not run_extraction(logger):
                    sys.exit(1)
            
            if args.clean:
                if not run_cleaning(logger):
                    sys.exit(1)
            
            if args.transform:
                tables = run_transformation(logger)
                if tables is None:
                    sys.exit(1)
                
                if args.validate:
                    if not run_validation(logger, tables):
                        sys.exit(1)
            
            elif args.validate:
                import pandas as pd
                tables = {
                    'dim_elements': pd.read_csv(config.FILES['dim_elements']),
                    'dim_levels': pd.read_csv(config.FILES['dim_levels']),
                    'dim_types': pd.read_csv(config.FILES['dim_types']),
                    'fact_quantities': pd.read_csv(config.FILES['fact_quantities']),
                    'fact_properties': pd.read_csv(config.FILES['fact_properties'])
                }
                if not run_validation(logger, tables):
                    sys.exit(1)
            
            logger.info("\n✅ All requested stages completed successfully!")
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"\n❌ Pipeline failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()