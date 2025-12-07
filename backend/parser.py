import logging
import os
from datetime import datetime
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv
from models import ProductionDates, ProductionItem, ProductionItemInput
from openai import OpenAI
from pydantic import BaseModel
from utils import format_date_iso, parse_date

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def read_excel_flexible(file_path: str) -> pd.DataFrame:
    """
    Read Excel with pandas, handling various header row positions.
    
    Tries different header row positions (0, 1, 2) and returns the DataFrame
    with the most valid columns. Also handles merged cells by forward-filling.
    
    Args:
        file_path: Path to Excel file
        
    Returns:
        DataFrame with production data
        
    Raises:
        ValueError: If Excel file cannot be read
    """
    logger.info(f"Reading Excel file: {file_path}")
    
    # Try different header row positions (common patterns: 0, 1, 2)
    for header_row in [0, 1, 2]:
        try:
            df = pd.read_excel(file_path, sheet_name=0, header=header_row)
            
            # Check if we got valid column names (not all NaN/None)
            valid_columns = df.columns.notna().sum()
            if valid_columns > 5:  # At least 5 valid columns
                logger.info(f"Successfully read Excel with header at row {header_row}, {valid_columns} columns found")
                
                # Forward-fill NaN values from merged cells (common in color variants)
                df = df.ffill()
                
                # Remove completely empty rows
                df = df.dropna(how='all')
                
                logger.info(f"DataFrame shape after cleaning: {df.shape}")
                return df
                
        except Exception as e:
            logger.debug(f"Failed to read with header={header_row}: {e}")
            continue
    
    # Fallback: read with no header and let LLM figure it out
    logger.warning("Could not find valid header row, reading without header")
    try:
        df = pd.read_excel(file_path, sheet_name=0, header=None)
        df = df.ffill()
        df = df.dropna(how='all')
        return df
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")


def derive_status(dates: dict, shipping_date: Optional[str] = None) -> str:
    """
    Derive production status from completion dates.
    
    Logic:
    - "pending": No stages started
    - "in_production": Some stages completed, not delayed
    - "completed": All stages with dates are complete
    - "delayed": Past shipping date but not all stages complete
    
    Args:
        dates: Dictionary of stage dates (can include None values)
        shipping_date: Final shipping date (optional)
        
    Returns:
        Status string
    """
    today = datetime.now().date()
    
    # Get all non-null date values
    date_values = [d for d in dates.values() if d]
    
    if not date_values:
        return "pending"
    
    # Count completed stages (dates in the past)
    completed_stages = []
    future_stages = []
    
    for date_str in date_values:
        if date_str:
            parsed = parse_date(date_str)
            if parsed:
                if parsed.date() <= today:
                    completed_stages.append(parsed)
                else:
                    future_stages.append(parsed)
    
    total_stages = len(completed_stages) + len(future_stages)
    
    # Check if delayed (past shipping date but not all complete)
    if shipping_date:
        shipping_parsed = parse_date(shipping_date)
        if shipping_parsed and shipping_parsed.date() < today:
            if len(completed_stages) < total_stages:
                return "delayed"
    
    # All stages complete
    if total_stages > 0 and len(completed_stages) == total_stages:
        return "completed"
    
    # Some stages complete
    if len(completed_stages) > 0:
        return "in_production"
    
    return "pending"


async def extract_production_items(df: pd.DataFrame, filename: str) -> List[ProductionItem]:
    """
    Use OpenAI Structured Outputs to extract and normalize production data.
    
    Uses gpt-4o model with structured outputs (parse method) to ensure
    100% schema compliance. The LLM maps vendor-specific column names to
    our canonical schema and standardizes date formats.
    
    Args:
        df: DataFrame with production data
        filename: Source filename for traceability
        
    Returns:
        List of ProductionItem objects ready for MongoDB storage
        
    Raises:
        ValueError: If LLM extraction fails or API key missing
    """
    logger.info(f"Extracting production items from {filename}")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ValueError("OPENAI_API_KEY not set in environment variables")
    
    client = OpenAI(api_key=api_key)
    
    # Convert DataFrame to CSV string for LLM (more compact than markdown)
    table_data = df.to_csv(index=False)
    logger.debug(f"Table data size: {len(table_data)} characters")
    
    # Define response schema as nested Pydantic model
    class ProductionBatch(BaseModel):
        items: List[ProductionItemInput]
    
    try:
        # Use latest parse() method with Pydantic model directly
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",  # Latest model supporting structured outputs
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert at extracting production planning data from textile manufacturing sheets.

Your task:
1. Parse the production order data regardless of column name variations
2. Map vendor-specific headers to canonical fields:
   - Order ID: Look for "IO Number", "Job", "Order #", "Order", or similar
   - Style: Look for "Style", "Style Code"
   - Fabric: Look for "Fabric", "Fabric Spec", "Fabric Description" (may have leading/trailing spaces)
   - Color: Usually "Color", "Colour"
   - Quantity: Total order quantity (main quantity column, often just "Quantity" or "Qty")
3. Extract all date fields under production stages (Fabric, Cutting, Sewing, Embroidery, Size Set, VAP, Feeding, etc.)
   - Look for columns with "Date", "Plan", "Planned Date", "Plan Date"
   - Map to appropriate stage in the dates object
4. Handle merged cells - if style/fabric/color are empty or NaN, use value from previous row
5. Standardize ALL dates to YYYY-MM-DD format (handle DD-MM-YY, DD/MM/YYYY, DD.MM.YYYY, etc.)
6. Return ALL data rows as individual production items
7. Extract supplier name if available (often in Cutting or Fabric columns)
8. Extract required weight (look for "Reqd Wt", "Required Weight") if available
9. Skip any completely empty rows or header rows

IMPORTANT: 
- The shipping date should go in dates.shipping field
- Production stage dates should go in their respective fields (dates.fabric, dates.cutting, etc.)
- If you see multiple date columns per stage, prioritize the "Plan Date" or "Planned Date" columns
- Quantity should be an integer (parse from string if needed)"""
                },
                {
                    "role": "user",
                    "content": f"Extract all production items from this sheet:\n\n{table_data}"
                }
            ],
            response_format=ProductionBatch,  # Pass Pydantic model directly
        )
        
        message = completion.choices[0].message
        
        if message.parsed:
            logger.info(f"Successfully extracted {len(message.parsed.items)} items")
            
            # Add derived fields and convert to ProductionItem
            items = []
            for item_data in message.parsed.items:
                item_dict = item_data.model_dump()
                
                # Add metadata
                item_dict['source_file'] = filename
                
                # Derive status from dates
                dates_dict = item_dict['dates']
                item_dict['status'] = derive_status(dates_dict, dates_dict.get('shipping'))
                
                items.append(ProductionItem(**item_dict))
            
            logger.info(f"Created {len(items)} ProductionItem objects")
            return items
        else:
            # Handle refusal
            error_msg = f"LLM refused to parse: {message.refusal}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        raise


async def parse_production_sheet(file_path: str, filename: str) -> List[ProductionItem]:
    """
    Main entry point for parsing production planning Excel sheets.
    
    Orchestrates the full pipeline:
    1. Read Excel with flexible header detection
    2. Extract data using LLM with structured outputs
    3. Derive status and add metadata
    
    Args:
        file_path: Path to Excel file
        filename: Original filename for traceability
        
    Returns:
        List of ProductionItem objects ready for database storage
    """
    logger.info(f"Starting parse pipeline for {filename}")
    
    # Step 1: Read Excel
    df = read_excel_flexible(file_path)
    logger.info(f"Read {len(df)} rows from Excel")
    
    # Step 2: Extract with LLM
    items = await extract_production_items(df, filename)
    
    logger.info(f"Parse pipeline complete: {len(items)} items extracted")
    return items
