import logging
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from database import (
    create_indexes,
    delete_item,
    get_item_by_id,
    get_items,
    get_status_counts,
    get_total_count,
    insert_items,
)
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from parser import parse_production_sheet

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:pass1234@localhost:27017/production?authSource=admin")
client: Optional[AsyncIOMotorClient] = None
db = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global client, db
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client.production
        await client.server_info()  # Test connection
        logger.info("Connected to MongoDB successfully")
        
        await create_indexes(db)
        logger.info("Database indexes created/verified")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")

    yield

    # Shutdown
    if client:
        client.close()
        logger.info("Disconnected from MongoDB")

# Create FastAPI app
app = FastAPI(
    title="Production Planning Parser API",
    description="API for parsing and managing production planning data",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Production Planning Parser API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check MongoDB connection
        if client:
            await client.server_info()
            mongo_status = "connected"
        else:
            mongo_status = "disconnected"
    except Exception as e:
        mongo_status = "error"
        logger.debug(f"MongoDB health check error: {e}")

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mongodb": mongo_status
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and parse production planning sheet.
    Accepts Excel files (.xlsx, .xls) and extracts production items using AI.
    """
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename provided"
        )
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    if not db:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available"
        )
    
    temp_file_path = None
    
    try:
        logger.info(f"Processing upload: {file.filename}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            contents = await file.read()
            temp_file.write(contents)
            temp_file_path = temp_file.name
        
        logger.info(f"Saved temporary file: {temp_file_path}")
        
        items = await parse_production_sheet(temp_file_path, file.filename)
        
        if not items:
            logger.warning(f"No items extracted from {file.filename}")
            return JSONResponse(
                status_code=200,
                content={
                    "message": "File processed but no items found",
                    "filename": file.filename,
                    "items_extracted": 0,
                    "items_stored": 0
                }
            )
        
        logger.info(f"Extracted {len(items)} items from {file.filename}")
        
        inserted_count = await insert_items(db, items)
        
        logger.info(f"Stored {inserted_count} items from {file.filename}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "File processed successfully",
                "filename": file.filename,
                "items_extracted": len(items),
                "items_stored": inserted_count
            }
        )
        
    except ValueError as e:
        logger.error(f"Validation error processing {file.filename}: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse file: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error processing {file.filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing file: {str(e)}"
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Cleaned up temporary file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")

@app.get("/api/production-items")
async def get_production_items(
    skip: int = 0,
    limit: int = 100,
    style: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Get production line items with optional filtering and pagination.
    
    Query Parameters:
    - skip: Number of items to skip (default: 0)
    - limit: Maximum items to return (default: 100, max: 1000)
    - style: Filter by style (case-insensitive partial match)
    - status: Filter by status (exact match)
    """
    if not db:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available"
        )
    
    if limit > 1000:
        limit = 1000
    
    if skip < 0:
        skip = 0
    
    try:
        items = await get_items(
            db,
            skip=skip,
            limit=limit,
            style=style,
            status=status
        )
        
        total_count = await get_total_count(
            db,
            style=style,
            status=status
        )
        
        status_counts = await get_status_counts(db)
        
        logger.debug(f"Retrieved {len(items)} items (total: {total_count})")
        
        return {
            "items": items,
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "status_counts": status_counts
        }
        
    except Exception as e:
        logger.error(f"Error retrieving production items: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve items: {str(e)}"
        )

@app.get("/api/production-items/{item_id}")
async def get_production_item(item_id: str):
    """
    Get a specific production item by its MongoDB ObjectId.
    
    Path Parameters:
    - item_id: MongoDB ObjectId as string
    """
    if not db:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available"
        )
    
    try:
        item = await get_item_by_id(db, item_id)
        
        if not item:
            logger.info(f"Item not found: {item_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Production item with id '{item_id}' not found"
            )
        
        logger.debug(f"Retrieved item: {item_id}")
        return item
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving item {item_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve item: {str(e)}"
        )

@app.delete("/api/production-items/{item_id}")
async def delete_production_item(item_id: str):
    """
    Delete a production item by its MongoDB ObjectId.
    
    Path Parameters:
    - item_id: MongoDB ObjectId as string
    """
    if not db:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available"
        )
    
    try:
        deleted = await delete_item(db, item_id)
        
        if not deleted:
            logger.info(f"Item not found for deletion: {item_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Production item with id '{item_id}' not found"
            )
        
        logger.info(f"Deleted item: {item_id}")
        return {
            "message": "Item deleted successfully",
            "id": item_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting item {item_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete item: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)