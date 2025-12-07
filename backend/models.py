from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProductionDates(BaseModel):
    """Timeline dates for production stages (ISO format: YYYY-MM-DD)"""
    shipping: Optional[str] = None
    fabric: Optional[str] = None
    cutting: Optional[str] = None
    sewing: Optional[str] = None
    embroidery: Optional[str] = None
    size_set: Optional[str] = None
    vap: Optional[str] = None  # Value Added Process
    feeding: Optional[str] = None


class ProductionItemInput(BaseModel):
    """Input model for LLM extraction (before status derivation)"""
    order_number: str
    style: str
    fabric: str
    color: str
    quantity: int
    dates: ProductionDates
    supplier: Optional[str] = None
    required_weight: Optional[float] = None


class ProductionItem(BaseModel):
    """Complete model for MongoDB storage (with derived fields)"""
    order_number: str
    style: str
    fabric: str
    color: str
    quantity: int
    status: str = "pending"
    dates: ProductionDates
    supplier: Optional[str] = None
    required_weight: Optional[float] = None
    source_file: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        # Allow field aliases for MongoDB _id
        populate_by_name = True
