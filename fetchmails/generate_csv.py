from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions
from datetime import datetime
import csv
import re
import requests
import json
import mimetypes
import os
from django.conf import settings


# Set these variables
project_id = "order-processing-gen-ai"
location = "us"
processor_id = "952176022bd2d10"
file_path = "email_pdfs/test.pdf"
output_csv = "output_csv/output.csv"

# Create Document AI client
client_options = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
client = documentai.DocumentProcessorServiceClient(client_options=client_options)

name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

import logging

# Create logs directory if it doesn't exist
# for databse save orm 
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)   
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


def process_document(file_path):
    # Detect MIME type from file extension
    mime_type, _ = mimetypes.guess_type(file_path)
    
    if mime_type not in ["application/pdf", "image/png", "image/jpeg"]:
        raise ValueError(f"Unsupported file type: {mime_type}")

    with open(file_path, "rb") as file:
        file_content = file.read()

    document = {
        "content": file_content,
        "mime_type": mime_type
    }

    request = {"name": name, "raw_document": document}
    result = client.process_document(request=request)
    return result.document

# function to get the email id 
def extract_email_from_text(text):
    """Extract email address from document text using regex"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    matches = re.findall(email_pattern, text)
    return matches[0] if matches else ""  # default fallback


# function to get the order date and delivery data 
def extract_dates_from_text(text):
    """Extract PO date and delivery date from document text with flexible matching"""
    date_info = {
        "po_number": "",
        "po_date": "",
        "delivery_date": ""
    }
    
    # PO Number patterns
    po_number_patterns = [
        r'(?:PO|Purchase Order|Order)\s*(?:No|Number|#)?\s*[:]?\s*(\d+)',
        r'\bPO\b\s*(\d+)',
        r'\b(?:PO|Order)\s*(\d+)'
    ]
    
    # Improved date patterns with better context awareness
    date_patterns = [
        # Order Date patterns (more specific to avoid confusion)
         (r'PO\s*Date\s*[:]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', "po_date"),

        (r'Order\s*Date\s*[:]?\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})', "po_date"),
        (r'Date\s*[:]?\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})(?=\s*Order)', "po_date"),

        (r'Delivery\s*Date\s*[:]?\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})', "delivery_date"),
        (r'Delivery\s*on\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})', "delivery_date"),
        (r'Deliver\s*by\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})', "delivery_date"),
    ]
    
    # Extract PO Number
    for pattern in po_number_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_info["po_number"] = match.group(1).strip()
            break
    
    # Extract all dates with context
    found_dates = []
    for pattern, date_type in date_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            found_dates.append({
                "date": match.group(1).replace(".", "/"), 
                "type": date_type,
                "position": match.start()
            })
    

    po_dates = [d for d in found_dates if d["type"] == "po_date"]
    delivery_dates = [d for d in found_dates if d["type"] == "delivery_date"]
    
    if po_dates:
        date_info["po_date"] = normalize_date(po_dates[0]["date"])
    if delivery_dates:
        date_info["delivery_date"] = normalize_date(delivery_dates[0]["date"])
    
    print(f"📅 Extracted Dates: {date_info}")
    return date_info

def normalize_date(raw_date):
    """Normalize date format to DD/MM/YYYY"""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            date_obj = datetime.strptime(raw_date, fmt)
            return date_obj.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw_date  # Return original if all parsing fails



import csv  # Make sure this is imported at the top of your file

def extract_data_to_csv(document, grouped_data, validated_address, output_csv, mapped_result=None):
    lines = []
    document_text = document.text

    if mapped_result is None:
        mapped_result = {}

    print(mapped_result)
    # exit()
        
    custom_data = mapped_result.get('extracted_data') if isinstance(mapped_result, dict) else {}
    print(custom_data)
    extracted_email = custom_data.get("Email") or extract_email_from_text(document_text)
    date_info = extract_dates_from_text(document_text)
    # print(extracted_email)
    # print(date_info)
    # print(grouped_data.get("order_date"))

    # Fallback values from mapped_result or grouped_data

    inner_result = mapped_result.get('mapped_result', {})
    required_keys = ['Product Code', 'Quantity', 'Supplier Code', 'Description', 'Price']

    if all(k in inner_result and inner_result[k] for k in required_keys):
        product_codes = [re.sub(r'\W+', '', p) for p in inner_result['Product Code']]
        raw_quantities = inner_result['Quantity']
        quantities = [int(''.join(filter(str.isdigit, str(q)))) for q in raw_quantities]
        descriptions = inner_result['Description']
        prices = inner_result['Price']
        supplier_codes = inner_result['Supplier Code']
    else:
        product_codes = grouped_data.get("product_code", [])
        quantities = grouped_data.get("quantity", grouped_data.get("order_quantity", []))
        descriptions = grouped_data.get("description", [])
        prices = grouped_data.get("price", [])
        supplier_codes = grouped_data.get("supplier_code", [])

    # ✅ For Debugging
    # print("Product Codes:", product_codes)
    # print("Quantities:", quantities)
    # print("Descriptions:", descriptions)
    # print("Prices:", prices)
    # print("Supplier Codes:", supplier_codes)

    # exit()
    # Get grouped data
    # descriptions = grouped_data.get("description", [])
    # quantities = grouped_data.get("quantity", grouped_data.get("order_quantity", []))
    # prices = grouped_data.get("price", [])
    # product_codes = grouped_data.get("product_code", [])
    # supplier_codes = grouped_data.get("supplier_code", [])

    # Order Number
    po_no = grouped_data.get("po_no", [])
    po_number_value = (custom_data.get("Order Number")) or (po_no[0] if isinstance(po_no, list) and po_no else date_info.get("po_number", ""))

    # Order Date 
    po_date = (
        custom_data.get("Order Date")
        or (grouped_data.get("order_date")[0] if isinstance(grouped_data.get("order_date"), list) and grouped_data.get("order_date") else None)
        or date_info.get("po_date", "")
    )

    # Delivery Date
    delivery_dates = date_info.get("delivery_date", [])
    delivery_date = custom_data.get("Delivery Date") or (
        delivery_dates[0] if isinstance(delivery_dates, list) and delivery_dates else ""
    )
    # print(po_number_value)
    # print(po_date)
    # print(delivery_date)
    # exit()

    # 🚫 Abort if no data found
    if not descriptions and not quantities and not prices:
        logging.error("No data available to extract. Skipping CSV generation.")
        return "Failed"
    
    if not (len(descriptions) == len(quantities) == len(product_codes)):
        logging.error("PDF format is incorrect: Mismatched lengths in extracted data.")
        return "Failed" 

    # Create CSV lines
    for i in range(max(len(descriptions), len(quantities), len(product_codes))):
        description = descriptions[i] if i < len(descriptions) else ""
        quantity = quantities[i] if i < len(quantities) else ""
        unit_price = prices[i] if i < len(prices) else ""
        product_code_full = product_codes[i] if i < len(product_codes) else ""
        supplier_code = supplier_codes[i] if i < len(supplier_codes) else ""

        product_code_short = ""
        if not supplier_codes:
            if product_code_full:
                if '-' in product_code_full:
                    product_code_short = product_code_full.split('-')[0]
                elif supplier_code and product_code_full.isdigit():
                    product_code_short = supplier_code
                else:
                    product_code_short = product_code_full

        line = [
            "LINE", str(i+1), product_code_short, "", quantity, "", product_code_full,
            "", "", unit_price, description
        ] + [""]*13 + [
            po_date, quantity, "EA"
        ] + [""]*68

        lines.append(line)

    # HEAD section
    head = [
        "HEAD", "76001", "",
        validated_address.get("v", ""),
        po_number_value,
        po_date,
        delivery_date,
        "", "", "", "", "",
        extracted_email, "", "", "",
        validated_address.get("q", ""),
        validated_address.get("r", ""),
        "", validated_address.get("t", ""),
        validated_address.get("u", ""),
        validated_address.get("v", ""),
        "76001",
        validated_address.get("v", ""),
        "", "", "", "", "FINAL",
        po_date,
        "", "", "", "", "", "", "", "", "", "",
        extracted_email
    ] + [""] * 70

    recon = ["RECON", "HPC", "76001", po_number_value, str(len(lines))] + [""] * 95

    # Write CSV
    try:
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(head)
            writer.writerows(lines)
            writer.writerow(recon)
        # logging.info(f"CSV file generated successfully: {output_csv}")
        return "Generated"
    except Exception as e:
        logging.error(f"❌ Error writing CSV: {str(e)}")
        return "Failed"



def get_text(layout, document):
    """Concatenate text segments from layout."""
    response = ""
    for segment in layout.text_anchor.text_segments:
        start_index = int(segment.start_index) if segment.start_index else 0
        end_index = int(segment.end_index)
        response += document.text[start_index:end_index]
    return response.strip()


# to process to address
def validate_address(address_lines, region_code="GB", api_key="YOUR_API_KEY"):
    if not address_lines or not isinstance(address_lines, list) or not any(address_lines):
        print("Skipping validation: address_lines missing or invalid.")
        return {} 

    url = f"https://addressvalidation.googleapis.com/v1:validateAddress?key={api_key}"
    
    payload = {
        "address": {
            "regionCode": region_code,
            "addressLines": address_lines
        }
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    data = response.json()

    if "error" in data:
        print("❌ API Error:", data["error"])
        return None

    components = {}
    try:
        for comp in data["result"]["address"]["addressComponents"]:
            components[comp["componentType"]] = comp["componentName"]["text"]
    except Exception as e:
        print("⚠️ Parsing error:", e)

    # --- CSV field mapping logic ---
    raw_first_line = address_lines[0] if address_lines else ""

    # Fallback if point_of_interest is missing or partial
    poi = components.get("point_of_interest", "")
    if poi and len(poi.split()) >= 2:
        q = poi
    else:
        q = raw_first_line

    # r field: Combine subpremise + premise + locality + route
    r_parts = []
    for key in ["subpremise", "premise", "locality", "route"]:
        val = components.get(key)
        if val and val not in q:
            r_parts.append(val)
    r = " ".join(r_parts).strip()

    # Other fields
    s = ""  # Not needed for now, reserved
    t = components.get("postal_town", "")
    u = components.get("administrative_area_level_2", "")
    v = components.get("postal_code", "")

    return {
        "formattedAddress": data["result"]["address"].get("formattedAddress", ""),
        "components": components,
        "verdict": data["result"]["verdict"],
        "q": q,
        "r": r,
        "s": s,
        "t": t,
        "u": u,
        "v": v
    }


# to extract table data using custom processor 
def run_custom_processor_and_print_output(file_path, customer_data=None):
    # if customer_addresses is None or not isinstance(customer_addresses, list):
    #     customer_addresses = []
    project_id = "order-processing-gen-ai"
    location = "us"
    custom_processor_id = "eaa9b1b010772675"
    version_id = "pretrained-foundation-model-v1.3-2024-08-31"
    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    )

    # ✅ Use the versioned processor path here
    processor_name = client.processor_version_path(
        project=project_id,
        location=location,
        processor=custom_processor_id,
        processor_version=version_id,
    )

    # ✅ Detect MIME type from file extension
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type not in ["application/pdf", "image/png", "image/jpeg", "image/jpg"]:
        raise ValueError(f"Unsupported file type: {mime_type}")
    
    with open(file_path, "rb") as file:
        file_content = file.read()

    document = {
        "content": file_content,
        "mime_type": mime_type
    }

    request = {"name": processor_name, "raw_document": document}
    result = client.process_document(request=request)
    doc = result.document


    print("\n==============================")
    print("📄 Output from Custom Processor")
    print("==============================")
    # Initialize dictionaries to store grouped data
    grouped_data = {}
    confidence_data = {}

    # Process entities and group by type
    for entity in doc.entities:
        entity_type = entity.type_.lower()
        value = entity.mention_text.strip()
        confidence = round(entity.confidence * 100, 2)
        
        # Initialize lists for new entity types
        if entity_type not in grouped_data:
            grouped_data[entity_type] = []
            confidence_data[f"{entity_type}_confidence"] = []
        
        # Add values to appropriate lists
        grouped_data[entity_type].append(value)
        confidence_data[f"{entity_type}_confidence"].append(confidence)

    # Print grouped data in requested format
    # print("\n📊 Grouped Data:")
    # for entity_type, values in grouped_data.items():
    #     print(f"{entity_type}{values}")

    # ========== OPTIONAL: VALIDATE ADDRESS ==========
    # ✅ Format customer addresses

    # code to match address with the saved address in the database
    # formatted_addresses = []
    # for addr in customer_addresses:
    #     full_addr = " ".join([
    #         addr.get("street", ""),
    #         addr.get("city", ""),
    #         addr.get("country", ""),
    #         addr.get("postcode", "")
    #     ]).strip()
    #     formatted_addresses.append(full_addr)

    # print("Formatted Customer Addresses")
    # print(formatted_addresses)
    # # ✅ Clean order addresses (replace \n with spaces)
    # order_address = list(set(grouped_data.get("deliver_address", [])))
    # order_addresses = [addr.replace("\n", " ").strip() for addr in order_address]
    # print("Cleaned Order Addresses")
    # print(order_addresses)

    # # ✅ Try to match order address in customer addresses
    # matches = None
    # for o_addr in order_addresses:
    #     for c_addr in formatted_addresses:
    #         if o_addr.lower() in c_addr.lower() or c_addr.lower() in o_addr.lower():
    #             matches = {
    #                 "order_address": o_addr,
    #                 "customer_address": c_addr
    #             }
    #             break
    #     if matches:
    #         break
    # END code to match address with the saved address in the database
    if not list(set(grouped_data.get("deliver_address", []))):
        default_id = customer_data.get("default_address_id")
        addresses = customer_data.get("addresses", [])

        # find matching address
        default_address = next(
            (addr for addr in addresses if addr.get("entity_id") == default_id),
            None
        )

        address_data = {}
        if default_address:
            address_data = {
                "q": default_address.get("address_code", ""), 
                "r": default_address.get("street", ""),
                "s": "",  
                "t": default_address.get("city", ""),
                "u": default_address.get("country", ""),
                "v": default_address.get("postcode", ""),
            }
        else:
            print("⚠️ No default address found for this customer")
            address_data = {}
    else:
        # when deliver_address is provided in grouped_data
        address_data = validate_address(
            list(set(grouped_data.get("deliver_address", []))),
            region_code="GB",
            api_key="AIzaSyA3rGJbR6g9T9IuebyKgU9rwYdRyIYKgDI"
        )

    # print(address_data)
    # exit()
    return {
        "grouped_data": grouped_data,
        "raw_document": doc,
        "validated_address": address_data
    }



from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions
import mimetypes, os

def extract_table_columns_from_documentai(file_path, customer_data=None):
    if customer_data is None or not isinstance(customer_data, dict):
        customer_data = {}

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type not in ("application/pdf", "image/png", "image/jpeg"):
        raise ValueError(f"Unsupported file type: {mime_type}")

    # Initialize Document AI client
    project_id = "order-processing-gen-ai"
    location = "us"
    processor_id = "952176022bd2d10"
    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    )
    name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    with open(file_path, "rb") as f:
        content = f.read()
    document = {"content": content, "mime_type": mime_type}
    request = {"name": name, "raw_document": document}
    result = client.process_document(request=request)
    doc = result.document
    # print(doc)
    # Get the all keys and values of the pdf file
    exclude_values = {"Description", "Quantity", "Price", "Product Code", "Supplier Code"}
    # customer_keys = [key for key, value in customer_data.items() if value not in exclude_values]
    customer_keys = {key: value for key, value in customer_data.items() if value not in exclude_values}
    print(customer_keys)
    normalized_customer_keys = {key.rstrip(":").strip(): key for key in customer_keys}
    # exit()
    extracted_data = {}
    for page in doc.pages:
        for field in page.form_fields:
            key_start = field.field_name.text_anchor.text_segments[0].start_index
            key_end = field.field_name.text_anchor.text_segments[0].end_index
            value_start = field.field_value.text_anchor.text_segments[0].start_index
            value_end = field.field_value.text_anchor.text_segments[0].end_index

            key = doc.text[key_start:key_end].strip()
            value = doc.text[value_start:value_end].strip()

            normalized_key = key.rstrip(":").strip()

            # Check if normalized_key exists in the normalized_customer_keys
            if normalized_key in normalized_customer_keys:
                raw_key = normalized_customer_keys[normalized_key]
                friendly_key = customer_keys[raw_key]
                extracted_data[friendly_key] = value
    # print(extracted_data)
    # exit()
    

    def extract_text(layout):
        text = ""
        for segment in layout.text_anchor.text_segments:
            start = int(segment.start_index) if segment.start_index else 0
            end = int(segment.end_index)
            text += doc.text[start:end]
        return text.strip()

    for page in doc.pages:
        for table in page.tables:
            if not table.header_rows:
                continue
            
            num_cols = len(table.header_rows[0].cells)
            headers = []
            for col_idx in range(num_cols):
                parts = []
                for header_row in table.header_rows:
                    cell_text = extract_text(header_row.cells[col_idx].layout)
                    if cell_text:
                        parts.append(cell_text)
                header_text = " ".join(parts).strip()
                headers.append(header_text)

            print("🧾 Extracted Headers:", headers)
            print("🎯 Customer Column Mapping:", customer_data)

            rows = []
            for body_row in table.body_rows:
                row_texts = [extract_text(cell.layout) for cell in body_row.cells]
                row_texts += [''] * (len(headers) - len(row_texts))
                rows.append(dict(zip(headers, row_texts)))

            # 🧾 Raw Table Log - Full
            print("🧾 Raw Extracted Table:")
            print("Headers:", headers)
            for i, row in enumerate(rows, start=1):
                print(f"Row {i}:", [row.get(h, "") for h in headers])
            
            # ✅ Extract rows that have a non-empty 'Order Qty'
            # extract key and value only for table header keys 
            filtered_mapped_result = {}
            for key, value in customer_data.items():
                if value in exclude_values:
                    normalized_key = key.split('_')[0] if '_' in key and key.split('_')[-1].isdigit() else key
                    filtered_mapped_result[normalized_key] = value

            print(filtered_mapped_result)
            # exit()
            label_to_column = {v: k for k, v in filtered_mapped_result.items()}
            qty_column = label_to_column.get("Quantity", "").strip()
            rows_with_quantity = [row for row in rows if row.get(qty_column, "").strip()]
            
            print("\n📦 Rows with Quantity Values:")
            for i, row in enumerate(rows_with_quantity, start=1):
                print(f"Row {i}:", [row.get(h, "") for h in headers])

            lower_column_mapping = {k.strip().lower(): v for k, v in filtered_mapped_result.items()}

            matched_header_map = {}
            for header in headers:
                normalized_header = header.lower().strip()
                for key_lower, custom_name in lower_column_mapping.items():
                    if key_lower and key_lower in normalized_header:
                        matched_header_map[header] = custom_name
                        break

            print("✅ Matched Header Keys:", list(matched_header_map.keys()))
            if matched_header_map:
                mapped_result = {custom: [] for custom in matched_header_map.values()}
                for row in rows_with_quantity:
                    for orig_header, custom_name in matched_header_map.items():
                        mapped_result[custom_name].append(row.get(orig_header, "").strip())

                if any(mapped_result.values()):
                    print("🔍 Final Mapped Result:")
                    for key, values in mapped_result.items():
                        print(f"{key}: {values}")
                    # return mapped_result
                    return {
                            "extracted_data": extracted_data,
                            "mapped_result": mapped_result
                        }

    print("No matched headers found.")
    return {
        "extracted_data": extracted_data,
        "mapped_result": {}
    }



   
if __name__ == "__main__":
    # First process with the standard processor
    print("hiiii")
    # logging.info("starting to run the standard processor")
    # exit()
    doc = process_document(file_path)
    
    customer_data = {"PO Date": "Order Date", "DATE REQ": "Delivery Date", "PO Number": "Order Number", "Supplier Pack size": "Price", "Order Qty": "Quantity", "Supplier Code": "Supplier Code", "Hygenol Product Code": "Product Code", "Description": "Description"}
    mapped_result = extract_table_columns_from_documentai(file_path, customer_data)
    # print(mapped_result)
    # exit()
    # Then run the custom processor and get grouped data

    custom_result = run_custom_processor_and_print_output(file_path)
    
    # # Extract CSV using BOTH the original document and grouped data
    extract_data_to_csv(doc, custom_result["grouped_data"], custom_result["validated_address"], output_csv, mapped_result)
    # extract_data_to_csv(doc, custom_result["grouped_data"], custom_result["validated_address"], output_csv)

def run_document_ai_pipeline(file_path, output_csv, customer_data=None):
    if customer_data is None:
        customer_data = {}

    # print("customer data first")
    # print(customer_data)
    # exit()

    try:
        doc = process_document(file_path)
        mapped_result = extract_table_columns_from_documentai(file_path, customer_data['extra_data']) #optional
        custom_result = run_custom_processor_and_print_output(file_path, customer_data)

        # Run CSV extraction and get status
        csv_status = extract_data_to_csv(doc, custom_result["grouped_data"], custom_result["validated_address"], output_csv, mapped_result)

        if csv_status == "Generated":
            print(f"\n✅ Pipeline complete for {file_path} → CSV saved to {output_csv}")
            logging.info(f"Successfully generated CSV file for: {file_path}")
            return {"status": "success", "csv_path": output_csv}
        else:
            # print("⚠️ No valid data found for CSV generation.")
            logging.error("No valid data found for CSV generation.")
            return {"status": "no_data", "message": "PDF file is not valid for CSV generation."}

    except Exception as e:
        # print(f"Error in pipeline for {file_path}: {str(e)}")
        logging.error(f"Error in pipeline for {file_path}: {str(e)}")
        return {"status": "error", "message": str(e)}
