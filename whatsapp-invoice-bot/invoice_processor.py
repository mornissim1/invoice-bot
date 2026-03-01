"""
Invoice Processor
=================
Uses Claude AI (vision) to extract structured data from invoice images,
then validates that all required fields are present and correct.
"""

import json
import logging
import anthropic
from typing import Dict, Tuple, List

logger = logging.getLogger(__name__)


async def extract_invoice_data(
    client: anthropic.Anthropic,
    image_data: str,
    media_type: str
) -> Dict:
    """
    Send the invoice image to Claude and extract structured data.
    Returns a dictionary with all invoice fields.
    """

    prompt = """אתה מומחה לקריאת חשבוניות ישראליות.

נתח את החשבונית בתמונה והחזר JSON בלבד (ללא הסברים, ללא markdown) עם השדות הבאים:

{
  "supplier_name": "שם הספק המלא",
  "supplier_id": "ח.פ. או ע.מ. של הספק",
  "invoice_number": "מספר החשבונית",
  "invoice_date": "תאריך החשבונית בפורמט DD/MM/YYYY",
  "due_date": "תאריך פירעון בפורמט DD/MM/YYYY אם קיים, אחרת null",
  "net_amount": "סכום לפני מע\"מ כמספר עשרוני, לדוגמה 1000.00",
  "vat_amount": "סכום המע\"מ כמספר עשרוני",
  "total_amount": "הסכום הכולל כמספר עשרוני",
  "vat_rate": "אחוז המע\"מ כמספר, לרוב 17 או 18",
  "currency": "סוג מטבע, ברירת מחדל ILS",
  "items": [
    {
      "description": "תיאור הפריט",
      "quantity": "כמות",
      "unit_price": "מחיר ליחידה",
      "line_total": "סה\"כ שורה"
    }
  ],
  "notes": "הערות אם קיימות, אחרת null"
}

חוקים:
- החזר JSON תקני בלבד — אסור להוסיף טקסט לפני או אחרי.
- אם שדה לא מופיע בחשבונית, הכנס null.
- סכומים יהיו מספרים עשרוניים בלבד (ללא פסיקים ותמות).
- תאריכים יהיו בפורמט DD/MM/YYYY בלבד."""

    # Normalize media type for Claude
    if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        media_type = "image/jpeg"

    message = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Clean up markdown code blocks if Claude added them
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    invoice_data = json.loads(response_text)
    return invoice_data


def validate_invoice(invoice_data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate that all required fields are present and have valid values.
    Returns (is_valid, list_of_missing_fields).
    """

    required_fields = {
        "supplier_name": "שם ספק",
        "invoice_number": "מספר חשבונית",
        "invoice_date": "תאריך חשבונית",
        "total_amount": "סכום כולל",
    }

    missing = []

    for field, label in required_fields.items():
        value = invoice_data.get(field)
        if value is None or str(value).strip() == "" or str(value).lower() == "null":
            missing.append(label)

    # Validate numeric amounts
    for amount_field, label in [
        ("total_amount", "סכום כולל"),
        ("net_amount", "סכום לפני מע\"מ"),
    ]:
        value = invoice_data.get(amount_field)
        if value is not None and str(value).lower() != "null":
            try:
                float(str(value).replace(",", "").replace("₪", "").strip())
            except (ValueError, TypeError):
                missing.append(f"סכום לא תקין: {label}")

    is_valid = len(missing) == 0
    return is_valid, missing
