from django.contrib import admin

from .models import ProcessedImage, TargetImage, VirtualObject


@admin.register(TargetImage)
class TargetImageAdmin(admin.ModelAdmin):
    list_display = ("name", "uploaded_at")
    search_fields = ["name"]


@admin.register(VirtualObject)
class VirtualObjectAdmin(admin.ModelAdmin):
    list_display = ("name", "uploaded_at")
    search_fields = ["name"]


@admin.register(ProcessedImage)
class ProcessedImageAdmin(admin.ModelAdmin):
    list_display = ("__str__", "mode", "aruco_count", "good_matches",
                    "inliers", "processing_ms", "created_at")
    list_filter = ("mode", "filter_name", "created_at")
    readonly_fields = ("stats_json",)
