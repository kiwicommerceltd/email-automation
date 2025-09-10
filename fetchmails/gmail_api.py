import os
import json
import base64
import pdfkit
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email.utils
import sys
import django
from shutil import copy2
from django.conf import settings


# for databse save orm 
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)   

sys.path.append(os.path.dirname(APP_DIR)) 
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailorders.settings")
django.setup()

# 📍 Step 3: Import Django models after setup
from fetchmails.models import EmailOrder, Customer, Notification, CustomerAddress
from fetchmails.generate_csv import run_document_ai_pipeline 

import logging

# Create logs directory if it doesn't exist
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Log file path
LOG_FILE = os.path.join(LOG_DIR, "gmail_fetcher.log")

# Configure logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,  # Change to DEBUG for more details
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(console_handler)



CREDENTIALS_FILE = os.path.join(APP_DIR, "credentials.json")
TOKEN_FILE = os.path.join(APP_DIR, "token.json")
LAST_FETCH_FILE = os.path.join(APP_DIR, "last_fetch.json")
ATTACHMENTS_DIR = os.path.join(PROJECT_ROOT, "media", "fetchmails", "email_pdfs")



ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.png', '.jpg', '.jpeg', '.xlsx']
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)


def authenticate_gmail():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=3000)
            # creds = flow.run_console()
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds


def get_last_fetch_time():
    if os.path.exists(LAST_FETCH_FILE):
        with open(LAST_FETCH_FILE, "r") as f:
            return json.load(f).get("lastFetch")
    return None


def save_last_fetch_time(timestamp):
    with open(LAST_FETCH_FILE, "w") as f:
        json.dump({"lastFetch": timestamp}, f)


def fetch_new_emails():
    creds = authenticate_gmail()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    last_fetch_time = get_last_fetch_time()
    query = f"after:{last_fetch_time}" if last_fetch_time else ""

    results = service.users().messages().list(userId="me", maxResults=1, q=query).execute()
    messages = results.get("messages", [])

    if not messages:
        print("No new emails.")
        logging.info("No new emails!!")
        return

    latest_timestamp = last_fetch_time

    for message in messages:
        msg = service.users().messages().get(userId="me", id=message["id"]).execute()
        email_timestamp = int(msg["internalDate"]) // 1000

        if email_timestamp == last_fetch_time:
            continue

        subject = next((h["value"] for h in msg["payload"]["headers"] if h["name"] == "Subject"), "Unknown")
        sender = next((h["value"] for h in msg["payload"]["headers"] if h["name"] == "From"), "Unknown")
        snippet = msg.get("snippet", "No content available")

        from_raw = extract_header_value(msg["payload"]["headers"], "From")
        sender_name, sender_email = email.utils.parseaddr(from_raw or "")
        if not Customer.objects.filter(email=sender_email).exists():
            logging.info(f"This customer does not exist... {sender_email}")
            Notification.objects.create(
                title="New customer detected",
                message=f"No customer found for email: {sender_email}",
                type="customer",
                level="warning"
            )
            continue

        print(f"Checking: {subject} from {sender}")
        process_attachments( service, message["id"], msg["payload"], snippet, msg["payload"]["headers"], msg["internalDate"])

        if not latest_timestamp or email_timestamp > latest_timestamp:
            latest_timestamp = email_timestamp

    if latest_timestamp:
        save_last_fetch_time(latest_timestamp)


def extract_header_value(headers, name):
    return next((h["value"] for h in headers if h["name"] == name), None)

def convert_xlsx_to_pdf(xlsx_path, pdf_output_path):
    import pandas as pd
    import pdfkit

    try:
        df = pd.read_excel(xlsx_path)
        # Replace NaN with empty strings
        df.fillna('', inplace=True)
        html_table = df.to_html(index=False)

        html_template = f"""
        <html>
        <head>
            <style>
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid black; padding: 5px; text-align: left; }}
            </style>
        </head>
        <body>
        <h2>{os.path.basename(xlsx_path)}</h2>
        {html_table}
        </body>
        </html>
        """

        pdfkit.from_string(html_template, pdf_output_path)
        print(f"✅ Converted Excel to PDF: {pdf_output_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to convert Excel to PDF: {e}")
        return False

def process_attachments(service, email_id, payload, snippet, headers, internal_timestamp):
    found_attachment = False
    file_path = None  # Absolute path

    # Extract basic details
    from_raw = extract_header_value(headers, "From")
    sender_name, sender_email = email.utils.parseaddr(from_raw or "")
    
    date_header = extract_header_value(headers, "Date")
    if date_header:
        from email.utils import parsedate_to_datetime
        parsed_dt = parsedate_to_datetime(date_header)
        email_date = parsed_dt.strftime("%Y-%m-%d")
        email_time = parsed_dt.strftime("%H:%M:%S")
    else:
        dt = datetime.fromtimestamp(int(internal_timestamp) / 1000)
        email_date = dt.strftime("%Y-%m-%d")
        email_time = dt.strftime("%H:%M:%S")

    def process_parts(parts):
        nonlocal found_attachment, file_path
        for part in parts:
            filename = part.get("filename")
            body = part.get("body", {})
            if filename:
                ext = os.path.splitext(filename)[1].lower()
                if ext in ALLOWED_EXTENSIONS:
                    att_id = body.get("attachmentId")
                    if att_id:
                        try:
                            attachment = service.users().messages().attachments().get(
                                userId="me", messageId=email_id, id=att_id
                            ).execute()
                            data = attachment.get("data")
                            file_data = base64.urlsafe_b64decode(data.encode("UTF-8"))
                            safe_filename = f"{email_id}_{filename}"
                            original_path = os.path.join(ATTACHMENTS_DIR, safe_filename)
                            with open(original_path, "wb") as f:
                                f.write(file_data)
                            print(f"✅ Saved attachment: {original_path}")

                            # Convert to PDF if it's an .xlsx file
                            if ext == ".xlsx":
                                pdf_output_path = os.path.splitext(original_path)[0] + ".pdf"
                                success = convert_xlsx_to_pdf(original_path, pdf_output_path)
                                if success:
                                    os.remove(original_path)  # Delete original .xlsx
                                    file_path = pdf_output_path
                                    print(f"📄 Only PDF retained: {file_path}")
                                else:
                                    file_path = original_path  # fallback to original if PDF fails
                                    print(f"⚠️ Using original .xlsx due to PDF failure")
                            else:
                                file_path = original_path

                            found_attachment = True

                        except Exception as e:
                            logging.error(f"Failed to save attachment for {email_id}: {e}")
                            print(f"❌ Failed to save attachment for {email_id}: {e}")
                            
            if "parts" in part:
                process_parts(part["parts"])


    process_parts(payload.get("parts", []))

    if not found_attachment:
        try:
            safe_filename = f"{email_id}.pdf"
            pdf_path = os.path.join(ATTACHMENTS_DIR, safe_filename)
            html_content = f"""
            <html>
            <body>
            <h2>Email Content</h2>
            <p>{snippet}</p>
            </body>
            </html>
            """
            pdfkit.from_string(html_content, pdf_path)
            print(f"📄 Saved email content as PDF: {pdf_path}")
            file_path = pdf_path
        except Exception as e:
            print(f"❌ Failed to generate content PDF for {email_id}: {e}")

    # ✅ Save to database regardless
    print(f"📬 From: {sender_name}")
    print(f"📬 ID: {sender_email}")
    print(f"📅 Date: {email_date}")
    print(f"⏰ Time: {email_time}")

    # Path relative to media/
    saved_pdf_path = os.path.relpath(file_path, os.path.join(PROJECT_ROOT, "media")) if file_path else None

    email_order, created = EmailOrder.objects.get_or_create(
        email_id=email_id,
        defaults={
            'sender_name': sender_name,
            'sender_email': sender_email,
            'email_date': email_date,
            'email_time': email_time,
            'saved_pdf_path': saved_pdf_path,
            'status': 'Ready'
        }
    )

    if created:
        logging.info(f"New email order created: emailId={email_id}, sender={sender_email}")


    # Auto-create customer if not found (Onboarding new customer)
    # if not Customer.objects.filter(email=sender_email).exists():
    #     new_customer = Customer.objects.create(
    #         name=sender_name,
    #         email=sender_email
    #     )
    #     logging.info(f"This user is onboarded - {sender_email}")
    #     try:
    #         if file_path and os.path.exists(file_path):
    #             # Create directory for storing customer PDFs
    #             customer_pdf_dir = os.path.join(settings.MEDIA_ROOT, "uploads", "customers_pdf")
    #             os.makedirs(customer_pdf_dir, exist_ok=True)

    #             original_filename = os.path.basename(file_path)
    #             extension = os.path.splitext(original_filename)[1]  # Includes the dot, e.g., ".jpg"
    #             base_filename = f"customer_{new_customer.id}_document"
    #             new_filename = f"{base_filename}{extension}"
    #             dest_path = os.path.join(customer_pdf_dir, new_filename)
                
    #             copy2(file_path, dest_path)

    #             # Save relative path to database (relative to MEDIA_ROOT)
    #             relative_path = os.path.relpath(dest_path, settings.MEDIA_ROOT)
    #             new_customer.document = relative_path 
    #             new_customer.save()

    #             logging.info(f"Attachment saved for customer {new_customer.id}: {relative_path}")
    #         else:
    #             logging.info(f"No file to save for new customer {new_customer.id}")
    #     except Exception as e:
    #         logging.info(f"Failed to save customer attachment: {e}")


    # Run document AI and save CSV in output folder
    if file_path:
        try:

            # ✅ Build output_csv directory inside media/fetchmails/output_csv
            csv_output_dir = os.path.join(settings.MEDIA_ROOT, "fetchmails", "output_csv")
            os.makedirs(csv_output_dir, exist_ok=True)

            pdf_filename = os.path.basename(file_path)  # e.g., abcd1234_invoice.pdf
            csv_filename = os.path.splitext(pdf_filename)[0] + ".csv"
            csv_path = os.path.join(csv_output_dir, csv_filename)

            # Run your AI/processing function here

            # Get the customer data with address 
            customer = Customer.objects.get(email=sender_email)

            customer_data = {
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "customer_code": customer.customer_code,
                "document": customer.document,
                "extra_data": customer.extra_data,
                "default_address_id": customer.default_address_id,
                "addresses": list(
                    CustomerAddress.objects.filter(customer=customer).values(
                        "entity_id", "address_code", "street", "city", "country", "postcode"
                    )
                )
            }

            # END the customer data with address 
            # print(customer_data)
            # exit()

            result = run_document_ai_pipeline(file_path, csv_path, customer_data=customer_data)

            try:
                email_order = EmailOrder.objects.get(email_id=email_id)

                if result["status"] == "success":
                    email_order.status = "Generated"
                elif result["status"] == "no_data":
                    email_order.status = "Failed"
                elif result["status"] == "error":
                    email_order.status = "Failed"
                else:
                    email_order.status = "Unknown"

                email_order.save()
                logging.info(f"Status updated to '{email_order.status}' for email ID: {email_id}")

            except EmailOrder.DoesNotExist:
                logging.info(f"EmailOrder not found for ID {email_id}, unable to update status.")

        except Exception as e:
            logging.info(f"Failed to run Document AI pipeline for {file_path}: {e}")



if __name__ == "__main__":
    logging.info("Start Cron Job To Fetch New Emails...")
    fetch_new_emails()
