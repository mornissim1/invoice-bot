"""
Priority Integration
====================
Uploads invoice data to the Priority ERP system via their REST API.
Credentials are read from environment variables.
"""

import os
import httpx
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


async def upload_to_priority(invoice_data: Dict) -> Tuple[bool, str]:
    """
    Upload invoice to Priority ERP.
    Returns (success: bool, message: str).
    """

    priority_url = os.getenv("PRIORITY_API_URL")       # e.g. https://yourcompany.priority-software.com
    priority_user = os.getenv("PRIORITY_API_USER")
    priority_password = os.getenv("PRIORITY_API_PASSWORD")
    priority_tabula = os.getenv("PRIORITY_TABULA")      # Company name/code in Priority

    # If credentials not set, run in demo mode
    if not all([priority_url, priority_user, priority_password, priority_tabula]):
        logger.warning("Priority credentials not configured — running in DEMO mode")
        logger.info(f"Would upload: {invoice_data}")
        return True, "מצב הדגמה — החשבונית לא הועלתה בפועל (ממתין לפרטי גישה לפריוריטי)"

    try:
        # Priority REST API endpoint for vendor invoices
        url = f"{priority_url.rstrip('/')}/odata/Priority/{priority_tabula}/AINVOICES"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Map our fields to Priority's OData format
        payload = {
            "DEBITNUM": invoice_data.get("supplier_id", ""),       # Supplier tax ID
            "IVNUM": str(invoice_data.get("invoice_number", "")),  # Invoice number
            "IVDATE": _format_date_for_priority(invoice_data.get("invoice_date")),
            "DUEDATE": _format_date_for_priority(invoice_data.get("due_date")),
            "TOTPRICE": _to_float(invoice_data.get("total_amount")) or 0,
            "VATPRICE": _to_float(invoice_data.get("vat_amount")) or 0,
            "QPRICE": _to_float(invoice_data.get("net_amount")) or 0,
            "CURRENCY": invoice_data.get("currency", "ILS"),
            "DETAILS": invoice_data.get("notes") or "",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                auth=(priority_user, priority_password)
            )

        if response.status_code in (200, 201):
            logger.info(f"Priority upload successful")
            return True, "הועלה בהצלחה לפריוריטי"
        else:
            logger.error(f"Priority error {response.status_code}: {response.text}")
            return False, f"שגיאה מפריוריטי: {response.status_code} — {response.text[:200]}"

    except httpx.TimeoutException:
        logger.error("Priority request timed out")
        return False, "תם הזמן בתקשורת עם פריוריטי — נסה שוב"

    except Exception as e:
        logger.error(f"Priority upload error: {e}", exc_info=True)
        return False, f"שגיאה בהעלאה לפריוריטי: {str(e)}"


def _to_float(value) -> float | None:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("₪", "").strip())
    except (ValueError, TypeError):
        return None


def _format_date_for_priority(date_str: str | None) -> str | None:
    """
    Convert DD/MM/YYYY to Priority's expected format YYYY-MM-DDT00:00:00Z.
    """
    if not date_str:
        return None
    try:
        parts = date_str.split("/")
        if len(parts) == 3:
            dd, mm, yyyy = parts
            return f"{yyyy}-{mm}-{dd}T00:00:00Z"
    except Exception:
        pass
    return None
