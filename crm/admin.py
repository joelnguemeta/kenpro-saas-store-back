from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "type", "trust_level", "is_express", "tenant")
    list_filter = ("type", "trust_level", "is_express")
    search_fields = ("name", "phone", "email", "niu")
