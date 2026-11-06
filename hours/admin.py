from django.contrib import admin

from .models import ApprovalRequest, AuditLog, Requirement, ServiceEntry


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ("grade_level", "hours_required")


class ApprovalRequestInline(admin.TabularInline):
    model = ApprovalRequest
    extra = 0
    can_delete = False
    exclude = ("token_hash",)
    readonly_fields = (
        "sent_to",
        "created_at",
        "expires_at",
        "opened_at",
        "responded_at",
        "revoked",
        "decision",
        "supervisor_typed_name",
        "supervisor_comment",
        "reminders_sent",
    )


class AuditInline(admin.TabularInline):
    model = AuditLog
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "actor", "actor_label", "action", "detail", "ip_address")


@admin.register(ServiceEntry)
class ServiceEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "service_date", "hours", "organization", "status", "school_year")
    list_filter = ("status", "school_year", "category")
    search_fields = (
        "student__email",
        "student__last_name",
        "organization",
        "supervisor_email",
    )
    date_hierarchy = "service_date"
    inlines = [ApprovalRequestInline, AuditInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "entry", "actor", "actor_label", "action")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
