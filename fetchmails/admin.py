from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.http import HttpResponseRedirect
from django.contrib import messages
import os
from django.http import FileResponse
from django.conf import settings 

from .models import EmailOrder, Customer, CustomerAddress, Notification
from fetchmails.generate_csv import run_document_ai_pipeline  # Your pipeline function
# for the customer things 
from django import forms
from django.utils.safestring import mark_safe
import requests, json
from urllib.parse import urlencode

admin.site.site_header = "Email Order Admin"
admin.site.site_title = "Email Orders Admin Portal"
admin.site.index_title = "Welcome to the Email Orders Dashboard"

@admin.register(EmailOrder)
class EmailOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'email_id',
        'sender_name',
        'sender_email',
        'map_key_button',
        'email_date',
        'email_time',
        'saved_pdf_path',
        'created_at',
        'status',
        'generate_csv_button',
    )
    list_filter = ('email_date', 'status')
    search_fields = ('sender_name', 'sender_email', 'email_id')
    ordering = ('-email_date',)
    ordering = ('-created_at',)
    list_editable = ('status',)
    list_per_page = 20

    def map_key_button(self, obj):
        try:
            customer = Customer.objects.get(email=obj.sender_email)
            base_url = reverse('admin:fetchmails_customer_change', args=[customer.id])
            query_string = urlencode({'saved_pdf_path': obj.saved_pdf_path})
            full_url = f"{base_url}?{query_string}"
            return format_html(
                '<a style="display: flex;width: max-content;" class="button" href="{}">Map Key</a>', full_url
            )
        except Customer.DoesNotExist:
            return "No Match"
    
    map_key_button.short_description = "Map Key"
    map_key_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('generate-csv/<int:pk>/', self.admin_site.admin_view(self.trigger_csv_generation), name='generate_csv'),
            path('download-csv/<int:pk>/', self.admin_site.admin_view(self.download_csv_file), name='download_csv'),
        ]
        return custom_urls + urls

    def generate_csv_button(self, obj):
        if obj.status == "Generated":
            download_url = reverse('admin:download_csv', args=[obj.pk])
            return format_html(
                '''
                <a class="button" style="padding:3px 6px;background-color:#007bff;color:white;border-radius:4px;text-align:center;display:block;" 
                   href="{0}">Download CSV</a>
                ''',
                download_url
            )
        else:
            btn_text = "Generate Again" if obj.status == "Failed" else "Generate CSV"
            btn_color = "#dc3545" if obj.status == "Failed" else "#28a745"
            return format_html(
                '''
                <a id="gen-btn-{0}" class="button" style="padding:3px 6px;background-color:{2};color:white;border-radius:4px;text-align:center;display:block;" 
                   href="{1}" onclick="return confirm('Are you sure you want to generate the CSV?') && showLoader('gen-btn-{0}')">{3}</a>
                ''',
                obj.pk,
                reverse('admin:generate_csv', args=[obj.pk]),
                btn_color,
                btn_text
            )

    
    generate_csv_button.short_description = 'Generate CSV'
    generate_csv_button.allow_tags = True

    def trigger_csv_generation(self, request, pk):
        try:
            obj = EmailOrder.objects.get(pk=pk)

            if obj.status == "Generated":
                self.message_user(request, "CSV already generated.", level=messages.WARNING)
                return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:index')))

            try:
                customer = Customer.objects.get(email=obj.sender_email)
            
                # Build full customer_data dict
                customer_data = {
                    "id": customer.id,
                    "name": customer.name,
                    "email": customer.email,
                    "customer_code": customer.customer_code,
                    "document": customer.document,
                    "extra_data": customer.extra_data,   # keep your existing extra_data
                    "default_address_id": customer.default_address_id,  # assuming this field exists
                    "addresses": list(
                        CustomerAddress.objects.filter(customer=customer).values(
                            "entity_id", "address_code", "street", "city", "country", "postcode"
                        )
                    )
                }
            except Customer.DoesNotExist:
                self.message_user(
                    request,
                    f"No customer found with email: {obj.sender_email}",
                    level=messages.ERROR
                )
                return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:index')))

            # Build absolute path from media root
            pdf_path = os.path.join(settings.MEDIA_ROOT, obj.saved_pdf_path)
            csv_output_dir = os.path.join(settings.MEDIA_ROOT, "fetchmails", "output_csv")
            os.makedirs(csv_output_dir, exist_ok=True)

            # Generate CSV filename
            pdf_filename = os.path.basename(obj.saved_pdf_path)
            csv_filename = os.path.splitext(pdf_filename)[0] + ".csv"
            csv_path = os.path.join(csv_output_dir, csv_filename)

            result = run_document_ai_pipeline(pdf_path, csv_path, customer_data)
            if not isinstance(result, dict):
                result = {"status": "error", "message": "Pipeline did not return a valid result dictionary."}

            status = result.get("status")
            message = result.get("message", "")

            if status == "success":
                obj.status = "Generated"
                obj.save()
                request.session["csv_download_filename"] = csv_filename
                self.message_user(request, f"CSV generated for order ID {pk}.", level=messages.SUCCESS)

            elif status == "no_data":
                obj.status = "Failed"
                obj.save()
                self.message_user(request, "PDF file is not valid for CSV generation.", level=messages.ERROR)

            else:
                obj.status = "Failed"
                obj.save()
                self.message_user(request, f"Pipeline failed: {message}", level=messages.ERROR)

        except EmailOrder.DoesNotExist:
            self.message_user(request, "Order not found.", level=messages.ERROR)

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:index')))

    def download_csv_file(self, request, pk):
        try:
            obj = EmailOrder.objects.get(pk=pk)
            pdf_filename = os.path.basename(obj.saved_pdf_path)
            csv_filename = os.path.splitext(pdf_filename)[0] + ".csv"
            csv_path = os.path.join(settings.MEDIA_ROOT, "fetchmails", "output_csv", csv_filename)

            if not os.path.exists(csv_path):
                self.message_user(request, "CSV file does not exist.", level=messages.ERROR)
                return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:index')))

            return FileResponse(open(csv_path, 'rb'), as_attachment=True, filename=csv_filename)

        except Exception as e:
            self.message_user(request, f"❌ Error downloading CSV: {str(e)}", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:index')))


# for customer address in customer form 
class CustomerAddressInline(admin.StackedInline):
    model = CustomerAddress
    extra = 0  # how many empty rows to show
    fields = ("entity_id", "address_code", "street", "city", "country", "postcode")
    readonly_fields = ("entity_id", "created_at")
    show_change_link = True
    # can_delete = False

class CustomerForm(forms.ModelForm):
    extra_data_field = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Customer
        exclude = ('created_at',)

    class Media:
        js = ('fetchmails/js/pdf_live_preview.js',)
        css = {
            'all': ('fetchmails/css/pdf_preview.css',)
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)  # Inject request manually in admin
        super().__init__(*args, **kwargs)

        # Set the existing extra_data as initial JSON
        self.fields['extra_data_field'].initial = json.dumps(self.instance.extra_data or {})

        # Hidden customer_id field for JS
        if self.instance and self.instance.pk:
            preview_html = f'''
                <input type="hidden" id="id_customer_id" value="{self.instance.pk}" />
            '''
            if self.instance.document:
                file_url = self.instance.document.url
                preview_html += f'''
                    <div id="existingPdfPreview" data-pdf-url="{file_url}">
                        <p>Loading PDF preview...</p>
                    </div>
                '''
            self.fields['document'].help_text = mark_safe(preview_html)

    def clean(self):
        cleaned_data = super().clean()
        raw = self.data.get("extra_data", "{}")
    
        try:
            parsed = json.loads(raw or "{}")
            if isinstance(parsed, dict):
                cleaned_data["extra_data"] = parsed
            else:
                raise ValueError("Parsed extra_data is not a dict")
        except Exception as e:
            self.add_error("extra_data", "Invalid JSON format")
            print("Invalid extra_data JSON:", e, raw)
    
        return cleaned_data


    def save(self, commit=True):
        instance = super().save(commit=False)

         # ✅ Overwrite the uploaded PDF with saved one if exists
        saved_pdf_path = self.request.GET.get("saved_pdf_path") if self.request else None
        if saved_pdf_path and instance.document:
            existing_pdf_path = instance.document.path
            saved_pdf_abs_path = os.path.join(settings.MEDIA_ROOT, saved_pdf_path)

            if os.path.exists(saved_pdf_abs_path):
                try:
                    with open(saved_pdf_abs_path, "rb") as src, open(existing_pdf_path, "wb") as dst:
                        dst.write(src.read())
                    print(f"✔️ Replaced PDF at {existing_pdf_path} with {saved_pdf_abs_path}")
                except Exception as e:
                    print(f"❌ Failed to replace PDF: {e}")


        if hasattr(self, '_parsed_extra_data'):
            instance.extra_data = self._parsed_extra_data
        if commit:
            instance.save()
        return instance



# Admin

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerForm
    list_display = ("id", "name", "email", "created_at","document", "customer_code", "display_extra_fields")
    list_display_links = ("name", "email")
    search_fields = ("name", "email", "customer_code")
    inlines = [CustomerAddressInline]

    def display_extra_fields(self, obj):
        return ", ".join([f"{k}: {v}" for k, v in obj.extra_data.items()]) if obj.extra_data else "—"

    display_extra_fields.short_description = "Extra Fields"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        class FormWithRequest(form):
            def __new__(cls, *args, **kw):
                kw['request'] = request
                return form(*args, **kw)
        return FormWithRequest

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['customer_id'] = object_id
        # Add saved_pdf_path from query string (if present)
        saved_pdf_path = request.GET.get('saved_pdf_path')
        if saved_pdf_path:
            extra_context['saved_pdf_path'] = saved_pdf_path

        return super().change_view(request, object_id, form_url, extra_context=extra_context)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "default_address":
            # when editing existing customer
            customer_id = request.resolver_match.kwargs.get("object_id")
            if customer_id:
                kwargs["queryset"] = CustomerAddress.objects.filter(customer_id=customer_id)
            else:
                # when adding a new customer -> no addresses yet
                kwargs["queryset"] = CustomerAddress.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# code to display address data in  admin grid 
@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ("entity_id", "customer", "address_code", "street", "city", "country", "postcode", "created_at")
    list_display_links = ("entity_id", "customer")
    search_fields = ("customer__name", "street", "city", "country", "postcode")
    list_filter = ("country", "city")
    ordering = ("-created_at",)
    list_per_page = 20


# for notification  
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "colored_message", "level", "created_at", "is_read")
    list_filter = ("level", "is_read")
    search_fields = ("message",)
    ordering = ("-created_at",)
    list_per_page = 20
    actions = ["mark_as_read", "mark_as_unread"]

    # Bulk actions
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notifications marked as read.")
    mark_as_read.short_description = "Mark selected notifications as read"

    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"{updated} notifications marked as unread.")
    mark_as_unread.short_description = "Mark selected notifications as unread"

    # Custom column with colored row text / background
    def colored_message(self, obj):
        if not obj.is_read:
            # Highlight unread (yellow bg)
            return format_html(
                '<span style="background-color:#fff3cd; padding:3px; border-radius:3px;">{}</span>',
                obj.message[:50]
            )
        else:
            # Subtle green bg for read
            return format_html(
                '<span style="background-color:#d4edda; padding:3px; border-radius:3px;">{}</span>',
                obj.message[:50]
            )
    colored_message.short_description = "Message"