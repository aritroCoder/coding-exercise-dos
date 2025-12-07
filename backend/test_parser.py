"""
Test script for parser.py - verify Excel parsing and LLM extraction
"""
import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

import logging
from parser import parse_production_sheet, read_excel_flexible

from utils import format_date_iso

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_parser():
    """Test parser with a sample file"""
    
    # Test file
    test_file = "/home/fishnak/coding/startup/coding-exercise-dos/data/tna-uno.xlsx"
    
    logger.info("="*60)
    logger.info("Testing Excel Parser with tna-uno.xlsx")
    logger.info("="*60)
    
    try:
        logger.info("\n[1/2] Testing Excel reading...")
        df = read_excel_flexible(test_file)
        logger.info(f"✓ Successfully read Excel: {df.shape[0]} rows, {df.shape[1]} columns")
        logger.info(f"Columns: {list(df.columns)[:10]}")  # Show first 10 columns
        
        logger.info("\n[2/2] Testing LLM extraction...")
        items = await parse_production_sheet(test_file, "tna-uno.xlsx")
        logger.info(f"✓ Successfully extracted {len(items)} production items")
        
        logger.info("\n" + "="*60)
        logger.info("Sample Results (first 3 items):")
        logger.info("="*60)
        
        for i, item in enumerate(items[:3], 1):
            logger.info(f"\nItem {i}:")
            logger.info(f"  Order: {item.order_number}")
            logger.info(f"  Style: {item.style}")
            logger.info(f"  Fabric: {item.fabric}")
            logger.info(f"  Color: {item.color}")
            logger.info(f"  Quantity: {item.quantity}")
            logger.info(f"  Status: {item.status}")
            logger.info(f"  Shipping Date: {item.dates.shipping}")
            logger.info(f"  Fabric Date: {item.dates.fabric}")
            logger.info(f"  Cutting Date: {item.dates.cutting}")
            logger.info(f"  Sewing Date: {item.dates.sewing}")
            if item.supplier:
                logger.info(f"  Supplier: {item.supplier}")
        
        logger.info("\n" + "="*60)
        logger.info(f"✓ All tests passed! Parser ready for integration.")
        logger.info("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_parser())
    sys.exit(0 if success else 1)
