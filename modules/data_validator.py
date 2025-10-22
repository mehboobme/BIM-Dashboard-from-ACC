"""
Data Validator Module
Validates data quality and generates reports
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates data quality and generates reports"""
    
    def __init__(self, config):
        self.config = config
        self.validation_results = []
    
    def validate_data(self, tables, report_files):
        """Validate all tables and generate reports"""
        logger.info("=" * 80)
        logger.info("Starting Data Validation")
        logger.info("=" * 80)
        
        for table_name, df in tables.items():
            logger.info(f"\n   Validating {table_name}...")
            self._validate_table(table_name, df)
        
        if self.config.get('generate_html_report'):
            self._generate_html_report(report_files['validation_report'])
        
        if self.config.get('generate_csv_summary'):
            self._generate_csv_summary(report_files['summary_report'])
        
        logger.info("\n" + "=" * 80)
        logger.info("Data Validation Complete")
        logger.info("=" * 80)
        
        return self.validation_results
    
    def _validate_table(self, table_name, df):
        """Run validation checks on a table"""
        checks = self.config.get('checks', {})
        
        # Null percentage check
        null_threshold = checks.get('null_percentage', 50)
        null_pct = (df.isnull().sum() / len(df)) * 100
        
        for col in df.columns:
            if null_pct[col] > null_threshold:
                self._add_warning(table_name, f"Column '{col}' has {null_pct[col]:.1f}% null values")
        
        # Duplicate IDs check
        if checks.get('duplicate_ids') and 'objectId' in df.columns:
            duplicates = df['objectId'].duplicated().sum()
            if duplicates > 0:
                self._add_error(table_name, f"Found {duplicates} duplicate objectId values")
            else:
                self._add_success(table_name, "No duplicate IDs found")
        
        # Value ranges check
        value_ranges = checks.get('value_ranges', {})
        for col, (min_val, max_val) in value_ranges.items():
            if col in df.columns:
                out_of_range = ((df[col] < min_val) | (df[col] > max_val)).sum()
                if out_of_range > 0:
                    self._add_warning(table_name, f"Column '{col}' has {out_of_range} values outside range [{min_val}, {max_val}]")
        
        # Record count
        self._add_info(table_name, f"Total records: {len(df)}")
        
        # Column count
        self._add_info(table_name, f"Total columns: {len(df.columns)}")
    
    def _add_success(self, table_name, message):
        """Add success validation result"""
        self.validation_results.append({
            'table': table_name,
            'level': 'SUCCESS',
            'message': message,
            'timestamp': datetime.now()
        })
        logger.info(f"      ✅ {message}")
    
    def _add_info(self, table_name, message):
        """Add info validation result"""
        self.validation_results.append({
            'table': table_name,
            'level': 'INFO',
            'message': message,
            'timestamp': datetime.now()
        })
        logger.info(f"      ℹ️  {message}")
    
    def _add_warning(self, table_name, message):
        """Add warning validation result"""
        self.validation_results.append({
            'table': table_name,
            'level': 'WARNING',
            'message': message,
            'timestamp': datetime.now()
        })
        logger.warning(f"      ⚠️  {message}")
    
    def _add_error(self, table_name, message):
        """Add error validation result"""
        self.validation_results.append({
            'table': table_name,
            'level': 'ERROR',
            'message': message,
            'timestamp': datetime.now()
        })
        logger.error(f"      ❌ {message}")
    
    def _generate_html_report(self, output_file):
        """Generate HTML validation report"""
        logger.info(f"\n   Generating HTML report...")
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Data Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .timestamp {{ color: #666; font-size: 14px; }}
        .success {{ color: #28a745; }}
        .info {{ color: #007bff; }}
        .warning {{ color: #ffc107; }}
        .error {{ color: #dc3545; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f8f9fa; }}
        .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>🔍 Data Validation Report</h1>
    <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Checks: {len(self.validation_results)}</p>
        <p class="success">✅ Success: {sum(1 for r in self.validation_results if r['level'] == 'SUCCESS')}</p>
        <p class="info">ℹ️  Info: {sum(1 for r in self.validation_results if r['level'] == 'INFO')}</p>
        <p class="warning">⚠️  Warnings: {sum(1 for r in self.validation_results if r['level'] == 'WARNING')}</p>
        <p class="error">❌ Errors: {sum(1 for r in self.validation_results if r['level'] == 'ERROR')}</p>
    </div>
    
    <h2>Validation Details</h2>
    <table>
        <thead>
            <tr>
                <th>Table</th>
                <th>Level</th>
                <th>Message</th>
                <th>Timestamp</th>
            </tr>
        </thead>
        <tbody>
"""
        
        for result in self.validation_results:
            level_class = result['level'].lower()
            html += f"""
            <tr>
                <td>{result['table']}</td>
                <td class="{level_class}">{result['level']}</td>
                <td>{result['message']}</td>
                <td>{result['timestamp'].strftime('%H:%M:%S')}</td>
            </tr>
"""
        
        html += """
        </tbody>
    </table>
</body>
</html>
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"   ✅ HTML report saved to {output_file.name}")
    
    def _generate_csv_summary(self, output_file):
        """Generate CSV summary report"""
        logger.info(f"   Generating CSV summary...")
        
        df = pd.DataFrame(self.validation_results)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        logger.info(f"   ✅ CSV summary saved to {output_file.name}")