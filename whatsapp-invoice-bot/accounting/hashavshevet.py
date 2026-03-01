"""
HashavShevet Integration
========================
Uploads invoice data to the HashavShevet accounting system via their API.
Credentials are read from environment variables.
"""

import os
import httpx
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


async def upload_to_hashavshevet(invoice_data: Dict) -> Tuple[bool, str]:
    """
    Upload invoice to HashavShevet.
    Returns (success: bool, message: str).
    """

    api_token = os.getenv("HASHAVSHEVET_API_TOKEN")
    company_id = os.getenv("HASHAVSHEVET_COMPANY_ID")

    # If credentials are not set yet, run in demo mode
    if not api_token or not company_id:
        logger.warning("HashavShevet credentials not configured — running in DEMO mode")
        logger.info(f"Would upload: {invoice_data}")
        return True, "מצב הדגמה — החשבונית לא הועלתה בפועל (ממתין לפרטי גישה לחשבשבת)"

    try:
        url = f"https://priority.hashavshevet.co.il/api/companies/{company_id}/invoices"

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Map our fields to HashavShevet's API format
        payload = {
            "supplierName": invoice_data.get("supplier_name"),
            "supplierTaxId": invoice_data.get("supplier_id"),
            "invoiceNumber": invoice_data.get("invoice_number"),
            "invoiceDate": invoice_data.get("invoice_date"),
            "dueDate": invoice_data.get("due_date"),
            "netAmount": _to_float(invoice_data.get("net_amount")),
            "vatAmount": _to_float(invoice_data.get("vat_amount")),
            "totalAmount": _to_float(invoice_data.get("total_amount")),
            "currency": invoice_data.get("currency", "ILS"),
            "notes": invoice_data.get("notes"),
            "lines": [
                {
                    "description": item.get("description"),
                    "quantity": item.get("quantity"),
                    "unitPrice": item.get("unit_price"),
                    "lineTotal": item.get("line_total"),
                }
                for item in (invoice_data.get("items") or [])
            ]
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code in (200, 201):
            logger.info(f"HashavShevet upload successful: {response.json()}")
            return True, "הועלה בהצלחה לחשבשבת"
        else:
            logger.error(f"HashavShevet error {response.status_code}: {response.text}")
            return False, f"שגיאה מחשבשבת: {response.status_code} — {response.text[:200]}"

    except httpx.TimeoutException:
        logger.error("HashavShevet request timed out")
        return False, "תם הזמן בתקשורת עם חשבשבת — נסה שוב"

    except Exception as e:
        logger.error(f"HashavShevet upload error: {e}", exc_info=True)
        return False, f"שגיאה בהעלאה לחשבשבת: {str(e)}"


def _to_float(value) -> float | None:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("₪", "").strip())
    except (ValueError, TypeError):
        return None
