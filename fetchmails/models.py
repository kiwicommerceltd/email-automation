from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import JSONField
import os

class EmailOrder(models.Model):
    STATUS_CHOICES = [
        ('Ready', 'Ready'),
        ('Generated', 'Generated'),
        ('Failed', 'Failed'),
    ]

    email_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    sender_name = models.CharField(max_length=255, null=True, blank=True)
    sender_email = models.EmailField(null=True, blank=True)
    email_date = models.DateField(null=True, blank=True)
    email_time = models.TimeField(null=True, blank=True)
    saved_pdf_path = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Ready')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f"EmailOrder #{self.id} - {self.sender_name or 'Unknown'}"



def customer_document_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    # Prepare the filename using customer ID (if saved)
    if instance.pk:
        filename = f"customer_{instance.pk}_document.{ext}"
    else:
        # fallback for unsaved instances
        filename = f"temp_customer_document.{ext}"
    return os.path.join("uploads", "customers_pdf", filename)

class Customer(models.Model):
    name = models.CharField(max_length=255)
    customer_code = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(blank=True, null=True, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    extra_data = models.JSONField(default=dict, blank=True)

    # New file upload field
    document = models.FileField(upload_to=customer_document_upload_path, blank=True, null=True)

    # ForeignKey to CustomerAddress (default address)
    default_address = models.ForeignKey(
        "CustomerAddress", 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_customers"
    )

    def __str__(self):
        return self.name

class CustomerAddress(models.Model):
    entity_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    address_code = models.CharField(max_length=100, null=True, blank=True)  # e.g., "Home", "Work"
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postcode = models.CharField(max_length=20)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.address_code or 'Address'} - {self.customer.name}"
    

# notification code 
class Notification(models.Model):
    LEVEL_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    title = models.CharField(max_length=255, blank=True, null=True)  # optional
    message = models.TextField()
    type = models.CharField(max_length=50, blank=True, null=True)    # optional
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default="info")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title or ''} [{self.level.upper()}] {self.message[:50]}"

