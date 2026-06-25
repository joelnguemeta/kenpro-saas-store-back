from django.contrib import admin

from .models import Device, RepairTicket, StatusHistory


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")

    # Append-only : pas d'ajout ni de suppression depuis l'inline admin
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "imei_serial", "customer", "type")
    list_filter = ("type",)
    search_fields = ("brand", "model", "imei_serial", "customer__name")


@admin.register(RepairTicket)
class RepairTicketAdmin(admin.ModelAdmin):
    list_display = ("pk", "device", "customer", "status", "technician", "intake_at")
    list_filter = ("status",)
    search_fields = ("device__imei_serial", "customer__name")
    readonly_fields = ("created_at", "updated_at")
    inlines = [StatusHistoryInline]


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("ticket", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
