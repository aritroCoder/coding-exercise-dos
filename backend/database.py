import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from models import ProductionItem
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create MongoDB indexes for the production_items collection.
    
    Indexes:
    - order_number: Single field index for lookups
    - status: Single field index for filtering
    - (order_number, color): Unique compound index for deduplication
    - created_at: Descending index for sorting by recency
    
    Args:
        db: AsyncIOMotorDatabase instance
    """
    collection = db.production_items
    
    logger.info("Creating MongoDB indexes for production_items collection...")
    
    try:
        await collection.create_index("order_number")
        logger.info("✓ Created index on 'order_number'")
        
        await collection.create_index("status")
        logger.info("✓ Created index on 'status'")
        
        await collection.create_index(
            [("order_number", 1), ("color", 1)],
            unique=True,
            name="order_color_unique"
        )
        logger.info("✓ Created unique compound index on (order_number, color)")
        
        await collection.create_index([("created_at", -1)])
        logger.info("✓ Created descending index on 'created_at'")
        
        logger.info("All indexes created successfully")
        
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")


async def insert_items(db: AsyncIOMotorDatabase, items: List[ProductionItem]) -> int:
    """
    Insert production items with upsert logic to prevent duplicates.
    
    Uses (order_number, color) as the unique key for upserting.
    Updates the updated_at timestamp on every upsert.
    
    Args:
        db: AsyncIOMotorDatabase instance
        items: List of ProductionItem objects to insert
        
    Returns:
        Number of items inserted or updated
    """
    collection = db.production_items
    inserted_count = 0
    
    logger.info(f"Inserting {len(items)} production items...")
    
    for item in items:
        try:
            item_dict = item.model_dump()
            
            item_dict['updated_at'] = datetime.utcnow()
            
            result = await collection.update_one(
                {
                    "order_number": item.order_number,
                    "color": item.color
                },
                {"$set": item_dict},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count:
                inserted_count += 1
                action = "inserted" if result.upserted_id else "updated"
                logger.debug(f"✓ {action.capitalize()} item: {item.order_number} - {item.color}")
                
        except DuplicateKeyError as e:
            logger.warning(f"Duplicate key for {item.order_number} - {item.color}: {e}")
            continue
        except Exception as e:
            logger.error(f"Failed to insert item {item.order_number}: {e}")
            continue
    
    logger.info(f"✓ Inserted/updated {inserted_count} items out of {len(items)}")
    return inserted_count


async def get_items(
    db: AsyncIOMotorDatabase,
    skip: int = 0,
    limit: int = 100,
    style: Optional[str] = None,
    status: Optional[str] = None,
    order_number: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query production items with optional filters and pagination.
    
    Args:
        db: AsyncIOMotorDatabase instance
        skip: Number of items to skip (for pagination)
        limit: Maximum number of items to return
        style: Filter by style (case-insensitive partial match)
        status: Filter by exact status
        order_number: Filter by order number (case-insensitive partial match)
        
    Returns:
        List of production item dictionaries
    """
    collection = db.production_items
    query = {}
    
    if style:
        query["style"] = {"$regex": style, "$options": "i"}
    
    if status:
        query["status"] = status
    
    if order_number:
        query["order_number"] = {"$regex": order_number, "$options": "i"}
    
    logger.debug(f"Querying items with filters: {query}, skip={skip}, limit={limit}")
    
    cursor = collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
    items = await cursor.to_list(length=limit)
    
    for item in items:
        if "_id" in item:
            item["_id"] = str(item["_id"])
    
    logger.debug(f"Found {len(items)} items")
    return items


async def get_item_by_id(db: AsyncIOMotorDatabase, item_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single production item by its MongoDB ObjectId.
    
    Args:
        db: AsyncIOMotorDatabase instance
        item_id: String representation of MongoDB ObjectId
        
    Returns:
        Production item dictionary or None if not found
    """
    collection = db.production_items
    
    try:
        obj_id = ObjectId(item_id)
        item = await collection.find_one({"_id": obj_id})
        
        if item:
            item["_id"] = str(item["_id"])
            logger.debug(f"Found item with id {item_id}")
            return item
        else:
            logger.debug(f"No item found with id {item_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error retrieving item {item_id}: {e}")
        return None


async def delete_item(db: AsyncIOMotorDatabase, item_id: str) -> bool:
    """
    Delete a production item by its MongoDB ObjectId.
    
    Args:
        db: AsyncIOMotorDatabase instance
        item_id: String representation of MongoDB ObjectId
        
    Returns:
        True if item was deleted, False otherwise
    """
    collection = db.production_items
    
    try:
        obj_id = ObjectId(item_id)
        result = await collection.delete_one({"_id": obj_id})
        
        if result.deleted_count > 0:
            logger.info(f"✓ Deleted item with id {item_id}")
            return True
        else:
            logger.warning(f"No item found with id {item_id} to delete")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting item {item_id}: {e}")
        return False


async def get_total_count(
    db: AsyncIOMotorDatabase,
    style: Optional[str] = None,
    status: Optional[str] = None,
    order_number: Optional[str] = None
) -> int:
    """
    Get total count of production items matching the filters.
    Useful for pagination calculations.
    
    Args:
        db: AsyncIOMotorDatabase instance
        style: Filter by style (case-insensitive partial match)
        status: Filter by exact status
        order_number: Filter by order number (case-insensitive partial match)
        
    Returns:
        Total count of matching items
    """
    collection = db.production_items
    query = {}
    
    if style:
        query["style"] = {"$regex": style, "$options": "i"}
    
    if status:
        query["status"] = status
    
    if order_number:
        query["order_number"] = {"$regex": order_number, "$options": "i"}
    
    count = await collection.count_documents(query)
    logger.debug(f"Total count with filters {query}: {count}")
    
    return count


async def get_status_counts(db: AsyncIOMotorDatabase) -> Dict[str, int]:
    """
    Get count of items grouped by status.
    Useful for dashboard statistics.
    
    Args:
        db: AsyncIOMotorDatabase instance
        
    Returns:
        Dictionary mapping status to count
    """
    collection = db.production_items
    
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    
    status_counts = {item["_id"]: item["count"] for item in results}
    
    logger.debug(f"Status counts: {status_counts}")
    return status_counts
