from django.urls import path

from . import views

app_name = "ar_app"

urlpatterns = [
    path("", views.home, name="home"),
    path("upload/", views.upload_process, name="upload"),
    path("live/", views.live_page, name="live"),
    path("api/frame/", views.live_frame_api, name="api_frame"),
    path("api/snapshot/", views.live_snapshot, name="live_snapshot"),
    path("api/stats/", views.api_stats, name="api_stats"),
    path("gallery/", views.gallery, name="gallery"),
    path("gallery/<int:pk>/", views.gallery_detail, name="gallery_detail"),
    path("gallery/<int:pk>/delete/", views.gallery_delete, name="gallery_delete"),
    path("assets/", views.assets, name="assets"),
    path("assets/<str:kind>/<int:pk>/delete/", views.asset_delete, name="asset_delete"),
    path("marker/", views.marker_generator, name="download_marker"),
    path("marker/<int:marker_id>/", views.marker_generator, name="marker_by_id"),
]
