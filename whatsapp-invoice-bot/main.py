"""
WhatsApp Invoice Bot - Main Application
=======================================
Receives invoices via WhatsApp, reads them with AI, and uploads to accounting systems.
"""

import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import anthropic
from dotenv import load_dotenv
from invoice_processor import extract_invoice_data, validate_invoice
from accounting.hashavshevet import upload_to_hashavshevet
from accounting.priority import upload_to_priority

load_dotenv()

app = FastAPI(title="WhatsApp Invoice Bot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize API clients
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Which accounting system to use: "hashavshevet" or "priority"
ACCOUNTING_SYSTEM = os.getenv("ACCOUNTING_SYSTEM", "hashavshevet")


def send_whatsapp_message(to: str, message: str):
    """Send a WhatsApp message back to the user via Twilio."""
    try:
        twilio_client.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
            to=to,
            body=message
        )
        logger.info(f"Message sent to {to}")
    except Exception as e:
        logger.error(f"Failed to send message to {to}: {e}")


async def process_invoice(from_number: str, media_url: str, media_type: str):
    """
    Main invoice processing pipeline:
    1. Download the image from Twilio
    2. Extract invoice data using Claude AI
    3. Validate the extracted data
    4. Upload to the accounting system
    5. Notify the user of the result
    """
    try:
        logger.info(f"Processing invoice from {from_number}")

        # Step 1: Download the invoice image from Twilio
        twilio_auth = (
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        )
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(media_url, auth=twilio_auth)
            img_response.raise_for_status()
            image_data = base64.standard_b64encode(img_response.content).decode("utf-8")

        # Step 2: Extract data using Claude AI
        logger.info("Sending image to Claude for extraction...")
        invoice_data = await extract_invoice_data(anthropic_client, image_data, media_type)
        logger.info(f"Extracted data: {invoice_data}")

        # Step 3: Validate the extracted data
        is_valid, missing_fields = validate_invoice(invoice_data)

        if not is_valid:
            missing_str = "\n".join(f"• {f}" for f in missing_fields)
            send_whatsapp_message(
                from_number,
                f"❌ לא הצלחנו לקרוא את כל פרטי החשבונית.\n\n"
                f"השדות הבאים חסרים או לא ברורים:\n{missing_str}\n\n"
                f"📸 אנא שלח/י שוב תמונה ברורה וישרה של החשבונית."
            )
            return

        # Step 4: Upload to accounting system
        logger.info(f"Uploading to {ACCOUNTING_SYSTEM}...")
        if ACCOUNTING_SYSTEM == "priority":
            success, message = await upload_to_priority(invoice_data)
        else:
            success, message = await upload_to_hashavshevet(invoice_data)

        # Step 5: Notify the user
        if success:
            send_whatsapp_message(
                from_number,
                f"✅ החשבונית נקלטה בהצלחה במערכת!\n\n"
                f"📋 *פרטי החשבונית שנרשמה:*\n"
                f"• ספק: {invoice_data.get('supplier_name', '-')}\n"
                f"• מספר חשבונית: {invoice_data.get('invoice_number', '-')}\n"
                f"• תאריך: {invoice_data.get('invoice_date', '-')}\n"
                f"• סכום לפני מע\"מ: ₪{invoice_data.get('net_amount', '-')}\n"
                f"• מע\"מ: ₪{invoice_data.get('vat_amount', '-')}\n"
                f"• סה\"כ לתשלום: ₪{invoice_data.get('total_amount', '-')}\n\n"
                f"תודה! 🙏"
            )
        else:
            send_whatsapp_message(
                from_number,
                f"⚠️ קראנו את החשבונית אך הייתה בעיה בהעלאה למערכת.\n"
                f"אנא פנה/י לצוות התמיכה.\n"
                f"פרטים טכניים: {message}"
            )

    except Exception as e:
        logger.error(f"Unexpected error processing invoice from {from_number}: {e}", exc_info=True)
        send_whatsapp_message(
            from_number,
            "❌ אירעה שגיאה בעיבוד החשבונית.\n"
            "אנא נסה/י שוב מאוחר יותר או פנה/י לתמיכה."
        )


@app.get("/")
async def root():
    return {"status": "running", "service": "WhatsApp Invoice Bot"}


@app.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    MediaUrl0: str = Form(default=None),
    MediaContentType0: str = Form(default=None),
):
    """
    Twilio sends all incoming WhatsApp messages here.
    We respond immediately with an acknowledgment and process in the background.
    """
    response = MessagingResponse()

    if NumMedia and NumMedia > 0 and MediaUrl0:
        # User sent an image — assume it's an invoice
        background_tasks.add_task(
            process_invoice,
            from_number=From,
            media_url=MediaUrl0,
            media_type=MediaContentType0 or "image/jpeg"
        )
        response.message(
            "✅ קיבלנו את החשבונית!\n"
            "אנחנו מעבדים אותה כעת... נחזור אליך תוך מספר שניות 🔄"
        )
    else:
        # User sent text — guide them
        response.message(
            "שלום! 👋 אני הבוט לניהול חשבוניות.\n\n"
            "📄 *איך משתמשים?*\n"
            "פשוט שלח/י תמונה ברורה של החשבונית ואטפל בשאר!\n\n"
            "✔️ ודא/י שהתמונה ברורה וכל הטקסט קריא."
        )

    return Response(content=str(response), media_type="application/xml")
