# from google.cloud import documentai_v1 as documentai
# from google.api_core.client_options import ClientOptions

# def extract_pdf_keys(file_path):
#     """Use Document AI Form Parser to extract table header keys from PDF"""
#     # Setup
#     project_id = "order-processing-gen-ai"
#     location = "us"
#     processor_id = "952176022bd2d10"  # ✅ Use Form Parser or General processor ID here
#     client = documentai.DocumentProcessorServiceClient(
#         client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
#     )

#     name = client.processor_path(project=project_id, location=location, processor=processor_id)

#     # Read file content
#     with open(file_path, "rb") as f:
#         file_content = f.read()

#     raw_document = {
#         "content": file_content,
#         "mime_type": "application/pdf"
#     }

#     request = {
#         "name": name,
#         "raw_document": raw_document
#     }

#     result = client.process_document(request=request)
#     document = result.document

#     extracted_keys = []

#     # Loop through tables and extract the first row (assumed headers)
#     for page in document.pages:
#         for table in page.tables:
#             if table.header_rows:
#                 header_row = table.header_rows[0]
#                 for cell in header_row.cells:
#                     cell_text = get_text(cell.layout, document)
#                     extracted_keys.append(cell_text.strip())

#     # Remove duplicates and return
#     unique_keys = list(dict.fromkeys(extracted_keys))
#     print("📊 Extracted Table Headings:", unique_keys)
#     return unique_keys


# def get_text(layout, document):
#     """Extracts text from layout based on text anchor."""
#     response = ""
#     for segment in layout.text_anchor.text_segments:
#         start_index = int(segment.start_index) if segment.start_index else 0
#         end_index = int(segment.end_index)
#         response += document.text[start_index:end_index]
#     return response.strip()
