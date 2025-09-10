from django.conf import settings

def global_dropdown_options(request):
    return {
        'csv_keys': settings.CSV_KEYS
    }
