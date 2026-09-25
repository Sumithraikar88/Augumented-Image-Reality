"""
Self-test + demo seeder for the AR project.

Run:  venv/Scripts/python seed_demo.py

What it does:
 1. Unit-test the AR engine (ArUco detect, pose, ORB match, homography).
 2. Generate a printable ArUco marker -> media/markers/.
 3. Create demo DB rows: a virtual overlay object and a demo scene processed
    with marker-based AR (so the gallery is not empty on first run).
 4. Smoke-test every Django page + JSON API via the Django test client.
"""
import io
import sys
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os_environ_was = None
import os  # noqa: E402  (kept after sys.path for clarity)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ar_project.settings")

import django  # noqa: E402

django.setup()

from ar_app.ar_engine import (  # noqa: E402
    ORBTracker, aruco_overlay, detect_aruco_markers, generate_aruco_marker,
    process_image,
)
from ar_app.models import ProcessedImage, TargetImage, VirtualObject  # noqa: E402


def make_scene_with_marker(marker_img: np.ndarray) -> np.ndarray:
    """Paste the ArUco marker onto a textured 'desk' background, slightly rotated."""
    scene = np.full((720, 960, 3), 60, dtype=np.uint8)
    # Add some texture so ORB has features to grab too.
    noise = np.random.default_rng(42).integers(0, 40, (720, 960), dtype=np.uint8)
    scene[..., 0] = np.clip(scene[..., 0].astype(int) + noise, 0, 255).astype(np.uint8)

    marker = cv2.resize(marker_img, (200, 200), interpolation=cv2.INTER_NEAREST)
    M = cv2.getRotationMatrix2D((100, 100), 12, 1.0)
    marker_rot = cv2.warpAffine(marker, M, (200, 200), borderValue=(255, 255, 255))
    scene[240:440, 380:580] = marker_rot
    return scene


def make_logo_overlay() -> np.ndarray:
    """Simple branded logo used as the virtual object."""
    logo = np.full((160, 160, 3), (24, 28, 36), dtype=np.uint8)
    cv2.rectangle(logo, (0, 0), (159, 159), (238, 211, 34), 4)
    cv2.circle(logo, (80, 70), 38, (238, 211, 34), -1)
    cv2.putText(logo, "AR", (52, 135), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (255, 255, 255), 3, cv2.LINE_AA)
    return logo


def make_target_image() -> np.ndarray:
    """A distinctive reference image for ORB mode (checker + shapes)."""
    t = np.full((300, 300, 3), 235, dtype=np.uint8)
    for i in range(0, 300, 30):
        for j in range(0, 300, 30):
            if (i // 30 + j // 30) % 2 == 0:
                t[i:i + 30, j:j + 30] = (40, 40, 40)
    cv2.circle(t, (150, 150), 55, (0, 140, 255), -1)
    cv2.putText(t, "TARGET", (60, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (200, 30, 30), 2, cv2.LINE_AA)
    return t


def engine_tests() -> bool:
    print("=" * 62)
    print("1) AR engine self-tests")
    print("=" * 62)
    ok = True

    marker = generate_aruco_marker(marker_id=23)
    assert marker.shape[0] == 600, "marker should include quiet zone (400+2*100)"

    scene = make_scene_with_marker(marker)

    # --- ArUco detection --------------------------------------------------
    corners, ids, _ = detect_aruco_markers(scene)
    found = 0 if ids is None else len(ids)
    print(f"   ArUco markers detected: {found} (expected >=1)")
    ok &= found >= 1

    # --- Overlay + pose ---------------------------------------------------
    res = aruco_overlay(scene, overlay_bgr=make_logo_overlay())
    print(f"   aruco_overlay: mode={res.mode}, count={res.aruco_count}, "
          f"poses={len(res.poses)}, ms={res.processing_ms:.1f}")
    ok &= res.aruco_count >= 1 and len(res.poses) >= 1
    if res.poses:
        p = res.poses[0]
        print(f"   pose ID {p.marker_id}: distance={p.distance_meters:.3f} m, "
              f"rpy={[round(x, 1) for x in p.yaw_pitch_roll_deg]}")
        ok &= p.distance_meters is not None

    # --- ORB feature-based AR ----------------------------------------------
    target = make_target_image()
    tracker = ORBTracker(target)
    scene2 = target.copy()
    M = cv2.getRotationMatrix2D((150, 150), 18, 0.85)
    scene2 = cv2.warpAffine(scene2, M, (960, 720), borderValue=(90, 90, 90))
    res2 = tracker.process(scene2, overlay_bgr=make_logo_overlay())
    print(f"   ORB: kp_target={res2.orb_keypoints_target}, "
          f"kp_scene={res2.orb_keypoints_scene}, good={res2.good_matches}, "
          f"inliers={res2.inliers}")
    ok &= res2.good_matches >= 10 and res2.inliers >= 8 and res2.homography is not None

    # --- Dispatcher --------------------------------------------------------
    res3 = process_image(scene, mode="aruco", overlay_bgr=make_logo_overlay(),
                         image_filter="cartoon")
    print(f"   process_image dispatcher: mode={res3.mode}, ms={res3.processing_ms:.1f}")
    ok &= res3.processed_bgr is not None
    return ok


def seed_database() -> None:
    print("=" * 62)
    print("2) Seeding demo data")
    print("=" * 62)
    marker = generate_aruco_marker(marker_id=23)

    # Printable marker file
    markers_dir = BASE_DIR / "media" / "markers"
    markers_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(markers_dir / "aruco_marker_23.png"), marker)
    print(f"   wrote media/markers/aruco_marker_23.png")

    if VirtualObject.objects.count() == 0:
        buf = cv2.imencode(".png", make_logo_overlay())[1].tobytes()
        VirtualObject.objects.create(
            name="Demo logo",
            image=django.core.files.base.ContentFile(buf, "demo_logo.png"))
        print("   created VirtualObject 'Demo logo'")

    if TargetImage.objects.count() == 0:
        buf = cv2.imencode(".png", make_target_image())[1].tobytes()
        TargetImage.objects.create(
            name="Demo target",
            image=django.core.files.base.ContentFile(buf, "demo_target.png"))
        print("   created TargetImage 'Demo target'")

    if ProcessedImage.objects.count() == 0:
        scene = make_scene_with_marker(marker)
        res = aruco_overlay(scene, overlay_bgr=make_logo_overlay())
        ok, jpg1 = cv2.imencode(".jpg", scene)
        ok2, jpg2 = cv2.imencode(".jpg", res.processed_bgr)
        ProcessedImage.objects.create(
            title="Demo — marker AR with logo overlay",
            mode="aruco",
            original=django.core.files.base.ContentFile(jpg1.tobytes(), "demo_orig.jpg"),
            processed=django.core.files.base.ContentFile(jpg2.tobytes(), "demo_proc.jpg"),
            marker_ids=",".join(map(str, res.marker_ids)),
            aruco_count=res.aruco_count,
            processing_ms=res.processing_ms,
            stats_json=res.to_json(),
        )
        print("   created demo ProcessedImage in gallery")


def page_smoke_tests() -> bool:
    print("=" * 62)
    print("3) Django page & API smoke tests")
    print("=" * 62)
    from django.test import Client

    client = Client()
    ok = True
    for url in ["/", "/upload/", "/live/", "/gallery/", "/assets/",
                "/marker/23/", "/api/stats/"]:
        r = client.get(url)
        status = "OK " if r.status_code == 200 else "FAIL"
        if r.status_code != 200:
            ok = False
        print(f"   [{status}] GET {url} -> {r.status_code}")

    # Full upload+process round trip through the actual view (AJAX path).
    from ar_app.models import VirtualObject
    vo = VirtualObject.objects.first()
    marker = generate_aruco_marker(marker_id=23)
    scene = make_scene_with_marker(marker)
    jpg = cv2.imencode(".jpg", scene)[1].tobytes()
    upload = io.BytesIO(jpg)
    upload.name = "scene.jpg"

    r = client.post("/upload/", {
        "image": upload,
        "mode": "aruco",
        "overlay": str(vo.pk) if vo else "",
        "image_filter": "original",
        "alpha": "90",
    }, headers={"x-requested-with": "XMLHttpRequest"})
    data = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
    print(f"   [{'OK ' if data.get('ok') else 'FAIL'}] POST /upload/ (AJAX) -> "
          f"{r.status_code}, aruco_count={data.get('result', {}).get('aruco_count')}")
    ok &= bool(data.get("ok")) and data.get("result", {}).get("aruco_count", 0) >= 1

    # Live frame API round trip.
    import base64
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
    r = client.post("/api/frame/", data=bytes(np.array([0]).tobytes()), content_type="application/octet-stream") \
        if False else client.post("/api/frame/", data=json_dumps({"image": data_url, "mode": "aruco", "alpha": 90}),
                                  content_type="application/json")
    d = r.json()
    print(f"   [{'OK ' if d.get('ok') else 'FAIL'}] POST /api/frame/ -> {r.status_code}, "
          f"markers={d.get('stats', {}).get('aruco_count')}")
    ok &= bool(d.get("ok")) and d.get("stats", {}).get("aruco_count", 0) >= 1

    # Snapshot endpoint.
    snap_upload = io.BytesIO(jpg)
    snap_upload.name = "snapshot.jpg"
    r = client.post("/api/snapshot/", {"title": "smoke", "image": snap_upload},
                    headers={"x-requested-with": "XMLHttpRequest"})
    d2 = r.json()
    print(f"   [{'OK ' if d2.get('ok') else 'FAIL'}] POST /api/snapshot/ -> {r.status_code}")
    ok &= bool(d2.get("ok"))

    # Admin loads (login page).
    r = client.get("/admin/login/")
    print(f"   [{'OK ' if r.status_code == 200 else 'FAIL'}] GET /admin/login/ -> {r.status_code}")
    ok &= r.status_code == 200
    return ok


def json_dumps(obj) -> bytes:
    import json
    return json.dumps(obj).encode("utf-8")


if __name__ == "__main__":
    print("\nAR Image Processing — self-test & seeder\n")
    t1 = engine_tests()
    seed_database()
    t2 = page_smoke_tests()
    print("=" * 62)
    print("ALL TESTS PASSED" if (t1 and t2) else "SOME TESTS FAILED")
    sys.exit(0 if (t1 and t2) else 1)
