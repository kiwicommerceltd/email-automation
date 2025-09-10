from django.shortcuts import render
from django.http import FileResponse, Http404
import os
from django.conf import settings
# for the customer 

def download_generated_csv(request):
    filename = request.session.pop("csv_download_filename", None)
    if not filename:
        raise Http404("No file to download.")

    file_path = os.path.join(settings.MEDIA_ROOT, "fetchmails/output_csv", filename)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    raise Http404("File not found.")

def home(request):
    return render(request, 'home.html')


