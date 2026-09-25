"""
Django views — the glue between the browser and the AR engine.
Pages: dashboard, upload-process, live webcam AR, gallery, assets (targets,
overlays, marker generator). APIs: JSON frame processing for the live page.
"""
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .ar_engine import (AREsult, ORBTracker, apply_filter, bgr_from_base64,
                        bgr_to_base64_jpeg, detect_aruco_markers,
                        generate_aruco_marker, get_aruco_dict, process_image)
from .forms import (ARUploadForm, OverlayUploadForm, TargetUploadForm)
from .models import ProcessedImage, TargetImage, VirtualObject

logger = logging.getLogger(__name__)

# Simple in-memory cache of ORB trackers keyed by target-image id.
_ORB_TRACKERS: dict = {}


def _get_tracker(target_pk: int) -> ORBTracker:
    tr = _ORB_TRACKERS.get(target_pk)
    if tr is None:
        img = _load_media_image(TargetImage.objects.get(pk=target_pk).image)
        tr = ORBTracker(img)
        _ORB_TRACKERS[target_pk] = tr
    return tr


def _load_media_image(field_file) -> np.ndarray:
    """Read a Django FieldFile into a BGR numpy array (works with storage)."""
    field_file.open("rb")
    data = field_file.read()
    field_file.close()
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Uploaded file is not a readable image")
    return img


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def home(request):
    """Landing / dashboard page with quick stats and feature cards."""
    context = {
        "n_processed": ProcessedImage.objects.count(),
        "n_targets": TargetImage.objects.count(),
        "n_overlays": VirtualObject.objects.count(),
        "recent": ProcessedImage.objects.all()[:4],
        "marker_url": reverse("ar_app:download_marker"),
    }
    return render(request, "home.html", context)


def upload_process(request):
    """
    Main workflow: upload a scene photo, pick a mode/overlay/filter and get
    the augmented result + stats back. Every run is stored in the gallery.
    """
    created = None
    result_json = None

    if request.method == "POST":
        form = ARUploadForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            scene = _load_media_image_like(cd["image"])
            overlay_img = (_load_media_image(cd["overlay"].image)
                           if cd["overlay"] else None)

            tracker = (_get_tracker(cd["target"].pk)
                       if (cd["mode"] == "orb" and cd["target"]) else None)
            res = process_image(
                scene,
                mode=cd["mode"],
                overlay_bgr=overlay_img,
                virtual_alpha=cd["alpha"],
                orb_tracker=tracker,
                image_filter=cd["image_filter"],
            )

            # Persist to gallery
            orig_file = ContentFile(_encode_jpeg_bytes(scene), name="scene.jpg")
            proc_file = ContentFile(_encode_jpeg_bytes(res.processed_bgr), name="out.jpg")
            created = ProcessedImage.objects.create(
                title=cd["image"].name[:120],
                mode=cd["mode"],
                original=orig_file,
                processed=proc_file,
                filter_name=cd["image_filter"],
                marker_ids=",".join(str(i) for i in res.marker_ids),
                aruco_count=res.aruco_count,
                good_matches=res.good_matches,
                inliers=res.inliers,
                processing_ms=res.processing_ms,
                stats_json=res.to_json(),
            )

            result_json = res.to_json()
            result_json["image"] = bgr_to_base64_jpeg(res.processed_bgr)
            if request.headers.get("HX-Request") == "true" or request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "result": result_json,
                                     "gallery_url": created.processed.url})
            # Non-AJAX fallback: re-render page with result
            form = ARUploadForm(initial={
                "mode": cd["mode"],
                "overlay": cd["overlay"],
                "target": cd["target"],
                "image_filter": cd["image_filter"],
                "alpha": int(cd["alpha"] * 100),
            })
    else:
        form = ARUploadForm()

    return render(request, "upload_process.html", {
        "form": form, "result": result_json, "last": created,
    })


def _load_media_image_like(django_file) -> np.ndarray:
    """Decode an UploadedFile / FieldFile into BGR."""
    django_file.seek(0)
    data = django_file.read()
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unsupported or corrupt image file")
    return img


def _encode_jpeg_bytes(img: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def gallery(request):
    items = ProcessedImage.objects.all()
    mode = request.GET.get("mode", "")
    if mode:
        items = items.filter(mode=mode)
    return render(request, "gallery.html", {"items": items, "active_mode": mode})


def gallery_detail(request, pk):
    item = get_object_or_404(ProcessedImage, pk=pk)
    return render(request, "gallery_detail.html", {"item": item})


def gallery_delete(request, pk):
    if request.method == "POST":
        item = get_object_or_404(ProcessedImage, pk=pk)
        item.original.delete(save=False)
        item.processed.delete(save=False)
        item.delete()
    return redirect("ar_app:gallery")


# ---------------------------------------------------------------------------
# Live webcam AR (browser sends JPEG frames via fetch; server returns JPEG)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def live_frame_api(request):
    """
    POST { image: data-url/jpeg, mode, target_id, overlay_id, alpha, filter }
    -> JSON { image: data-url, stats: {...} }
    Stateless by design: no session/cookie needed, perfect for a college demo.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        frame = bgr_from_base64(payload.get("image", ""))

        mode = payload.get("mode", "aruco")
        alpha = float(payload.get("alpha", 90)) / 100.0
        filt = payload.get("filter", "original")
        if filt != "original":
            frame = apply_filter(frame, filt)

        overlay_img = None
        overlay_id = payload.get("overlay_id")
        if overlay_id:
            try:
                overlay_img = _load_media_image(VirtualObject.objects.get(pk=overlay_id).image)
            except (VirtualObject.DoesNotExist, ValueError):
                pass

        tracker = None
        target_id = payload.get("target_id")
        if mode == "orb" and target_id:
            try:
                tracker = _get_tracker(int(target_id))
            except (TargetImage.DoesNotExist, ValueError):
                pass

        res = process_image(frame, mode=mode, overlay_bgr=overlay_img,
                            virtual_alpha=alpha, orb_tracker=tracker)
        stats = res.to_json()
        stats["image"] = bgr_to_base64_jpeg(res.processed_bgr, quality=80)
        return JsonResponse({"ok": True, "stats": stats})
    except Exception as exc:  # noqa: BLE001
        logger.exception("live_frame_api failed")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def live_page(request):
    targets = TargetImage.objects.all()
    overlays = VirtualObject.objects.all()
    return render(request, "live.html", {
        "targets": targets, "overlays": overlays,
    })


@csrf_exempt
@require_POST
def live_snapshot(request):
    """Save an augmented frame (from the Live page) into the gallery."""
    try:
        upload = request.FILES.get("image")
        if upload is None:
            return JsonResponse({"ok": False, "error": "no image"}, status=400)
        img = _load_media_image_like(upload)
        title = (request.POST.get("title") or "Live snapshot")[:120]
        item = ProcessedImage.objects.create(
            title=title,
            mode="filter",
            original=ContentFile(_encode_jpeg_bytes(img), name="snap_orig.jpg"),
            processed=ContentFile(_encode_jpeg_bytes(img), name="snap_proc.jpg"),
        )
        return JsonResponse({"ok": True, "id": item.pk,
                             "gallery_url": item.processed.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("live_snapshot failed")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


# ---------------------------------------------------------------------------
# Assets: targets & overlays management + marker generator
# ---------------------------------------------------------------------------
def assets(request):
    t_form, o_form = TargetUploadForm(), OverlayUploadForm()
    if request.method == "POST":
        which = request.POST.get("which")
        if which == "target":
            t_form = TargetUploadForm(request.POST, request.FILES)
            if t_form.is_valid():
                t_form.save()
                return redirect("ar_app:assets")
        elif which == "overlay":
            o_form = OverlayUploadForm(request.POST, request.FILES)
            if o_form.is_valid():
                o_form.save()
                return redirect("ar_app:assets")
    return render(request, "assets.html", {"t_form": t_form, "o_form": o_form,
                                           "targets": TargetImage.objects.all(),
                                           "overlays": VirtualObject.objects.all()})


def asset_delete(request, kind, pk):
    if request.method == "POST":
        if kind == "target":
            obj = get_object_or_404(TargetImage, pk=pk)
        else:
            obj = get_object_or_404(VirtualObject, pk=pk)
        obj.image.delete(save=False)
        obj.delete()
        _ORB_TRACKERS.pop(pk, None) if kind == "target" else None
    return redirect("ar_app:assets")


@require_GET
def marker_generator(request, marker_id: int = 23):
    """Serve a printable ArUco marker PNG (also used as the site's logo)."""
    marker_id = max(0, min(int(marker_id), 249))
    img = generate_aruco_marker(marker_id)
    ok, png = cv2.imencode(".png", img)
    resp = HttpResponse(png.tobytes(), content_type="image/png")
    resp["Content-Disposition"] = f'inline; filename="aruco_marker_{marker_id}.png"'
    return resp


def api_stats(request):
    """Small JSON endpoint the dashboard auto-refreshes with."""
    return JsonResponse({
        "processed": ProcessedImage.objects.count(),
        "targets": TargetImage.objects.count(),
        "overlays": VirtualObject.objects.count(),
        "uptime_note": "in-memory ORB tracker cache size: %d" % len(_ORB_TRACKERS),
    })
