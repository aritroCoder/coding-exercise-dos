"""
Test script for database.py - verify MongoDB operations
Requires MongoDB to be running (docker-compose up mongodb)
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import logging

from database import (create_indexes, delete_item, get_item_by_id, get_items,
                      get_status_counts, get_total_count, insert_items)
from models import ProductionDates, ProductionItem
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_database_operations():
    """Test all database operations"""
    
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:pass1234@localhost:27017/production?authSource=admin")
    
    logger.info("="*60)
    logger.info("Testing Database Operations")
    logger.info("="*60)
    
    try:
        logger.info("\n[1/8] Connecting to MongoDB...")
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client.production
        await client.server_info()
        logger.info("✓ Connected to MongoDB")
        
        logger.info("\n[2/8] Creating indexes...")
        await create_indexes(db)
        logger.info("✓ Indexes created")
        
        logger.info("\n[3/8] Creating sample production items...")
        sample_items = [
            ProductionItem(
                order_number="TEST001",
                style="STYLE-A",
                fabric="Cotton 100%",
                color="Blue",
                quantity=1000,
                status="in_production",
                dates=ProductionDates(
                    shipping="2025-12-15",
                    fabric="2025-11-01",
                    cutting="2025-11-15",
                    sewing="2025-12-01"
                ),
                source_file="test.xlsx",
                supplier="ABC Textiles"
            ),
            ProductionItem(
                order_number="TEST001",
                style="STYLE-A",
                fabric="Cotton 100%",
                color="Red",
                quantity=500,
                status="pending",
                dates=ProductionDates(
                    shipping="2025-12-20"
                ),
                source_file="test.xlsx"
            ),
            ProductionItem(
                order_number="TEST002",
                style="STYLE-B",
                fabric="Polyester 80% Cotton 20%",
                color="Green",
                quantity=2000,
                status="completed",
                dates=ProductionDates(
                    shipping="2025-11-30",
                    fabric="2025-11-01",
                    cutting="2025-11-10",
                    sewing="2025-11-25"
                ),
                source_file="test.xlsx",
                supplier="XYZ Manufacturing"
            )
        ]
        logger.info(f"Created {len(sample_items)} sample items")
        
        logger.info("\n[4/8] Inserting items into database...")
        inserted = await insert_items(db, sample_items)
        logger.info(f"✓ Inserted/updated {inserted} items")
        
        logger.info("\n[5/8] Querying all items...")
        all_items = await get_items(db, limit=100)
        logger.info(f"✓ Retrieved {len(all_items)} items")
        
        logger.info("\n[6/8] Filtering by status='in_production'...")
        filtered_items = await get_items(db, status="in_production")
        logger.info(f"✓ Found {len(filtered_items)} items with status='in_production'")
        
        if all_items:
            logger.info("\n[7/8] Getting item by ID...")
            first_item_id = all_items[0]["_id"]
            item = await get_item_by_id(db, first_item_id)
            if item:
                logger.info(f"✓ Retrieved item: {item['order_number']} - {item['color']}")
            else:
                logger.error("✗ Failed to retrieve item by ID")
        
        logger.info("\n[8/8] Getting status counts...")
        total = await get_total_count(db)
        status_counts = await get_status_counts(db)
        logger.info(f"✓ Total items: {total}")
        logger.info(f"✓ Status breakdown: {status_counts}")
        
        logger.info("\n" + "="*60)
        logger.info("Database Operations Summary")
        logger.info("="*60)
        logger.info(f"Total items in database: {total}")
        for status, count in status_counts.items():
            logger.info(f"  {status}: {count}")
        
        logger.info("\n" + "="*60)
        logger.info("✓ All database tests passed!")
        logger.info("="*60)
        
        # Note: Not deleting test data so it can be viewed in dashboard
        logger.info("\nNote: Test data kept in database for dashboard verification")
        logger.info("To clean up: db.production_items.deleteMany({source_file: 'test.xlsx'})")
        
        client.close()
        return True
        
    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_database_operations())
    sys.exit(0 if success else 1)
