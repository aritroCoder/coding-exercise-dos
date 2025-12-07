import logging
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


def parse_date(date_input: any) -> Optional[datetime]:
    """
    Parse date from various formats to datetime object.
    Handles DD-MM-YY, DD/MM/YYYY, DD.MM.YYYY, ISO formats, and pandas Timestamp.
    
    Args:
        date_input: Date string, datetime object, or pandas Timestamp
        
    Returns:
        datetime object or None if parsing fails
    """
    if date_input is None or (isinstance(date_input, str) and date_input.strip() == ""):
        return None
    
    if isinstance(date_input, datetime):
        return date_input
    
    try:
        if hasattr(date_input, 'to_pydatetime'):
            return date_input.to_pydatetime()
    except Exception:
        pass
    
    if isinstance(date_input, str):
        try:
            parsed = date_parser.parse(date_input, dayfirst=True)
            return parsed
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_input}': {e}")
            return None
    
    return None


def format_date_iso(date_input: any) -> Optional[str]:
    """
    Format date to ISO format (YYYY-MM-DD).
    
    Args:
        date_input: Date string, datetime object, or pandas Timestamp
        
    Returns:
        ISO formatted date string (YYYY-MM-DD) or None
    """
    parsed = parse_date(date_input)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return None
