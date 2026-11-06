from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import GradeAssignment, User


class GradeAssignmentInline(admin.TabularInline):
    model = GradeAssignment
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "role", "graduation_year", "is_active")
    list_filter = ("role", "graduation_year", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("last_name", "first_name")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("School", {"fields": ("role", "graduation_year", "ms_oid")}),
    )
    inlines = [GradeAssignmentInline]


@admin.register(GradeAssignment)
class GradeAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "grade_level")
    list_filter = ("grade_level",)
