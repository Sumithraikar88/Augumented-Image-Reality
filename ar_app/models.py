from django.db import models


class TargetImage(models.Model):
    """Reference image used for ORB feature-based AR ('the thing to find')."""

    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="targets/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.name


class VirtualObject(models.Model):
    """Overlay image (logo, 3-D style sprite, texture) pasted onto AR targets."""

    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="overlays/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.name


class ProcessedImage(models.Model):
    """Record of every AR/image-processing run performed via uploads."""

    MODES = [
        ("aruco", "Marker-based AR (ArUco)"),
        ("orb", "Feature-based AR (ORB matching)"),
        ("filter", "Image-processing filter only"),
    ]

    title = models.CharField(max_length=120, blank=True)
    mode = models.CharField(max_length=10, choices=MODES, default="aruco")
    original = models.ImageField(upload_to="originals/")
    processed = models.ImageField(upload_to="processed/")
    filter_name = models.CharField(max_length=20, default="original")
    marker_ids = models.CharField(max_length=200, blank=True)
    aruco_count = models.PositiveIntegerField(default=0)
    good_matches = models.PositiveIntegerField(default=0)
    inliers = models.PositiveIntegerField(default=0)
    processing_ms = models.FloatField(default=0.0)
    stats_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Processed image"
        verbose_name_plural = "Processed images"

    def __str__(self):
        return self.title or f"{self.get_mode_display()} #{self.pk}"
