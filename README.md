# The Ultimate Image Processing — Augmented Reality Web App

A Django + OpenCV web application that implements **Augmented Reality** with
classic **image processing** techniques — entirely server-side in Python.

## Features

| Feature | Technique |
|---|---|
| **Marker-based AR** | ArUco (DICT_6X6_250) fiducial detection, `solvePnP` 6-DoF pose estimation, perspective warp of a virtual object onto each marker, 3-D axis drawing, distance readout |
| **Feature-based AR** | ORB keypoints + FLANN (LSH) matching, Lowe's ratio test, RANSAC homography, projected target border, inlier visualisation |
| **Live webcam AR** | Browser `getUserMedia` frames are JPEG-encoded and POSTed to a Django JSON API; the server augments each frame and returns JPEG. Self-clocking request loop. |
| **Vision enhancement suite** | Clarity boost (CLAHE + sharpening), denoise, document scan, night vision, neon edge glow, thermal, sketch, cartoon, Canny edges and more — stackable with any AR mode |
| **Vision telemetry** | Live tracking-confidence, response latency, resolution, exposure, contrast and sharpness readings for every processed frame |
| **Futuristic interface** | Animated scanner HUD, ambient motion, live status signals, responsive command panels and reduced-motion support |
| **Gallery** | Every upload is stored with full pipeline stats (markers, matches, inliers, ms) and browsable/filterable/deletable |
| **Assets manager** | ORB target images, virtual overlay objects, printable ArUco markers (IDs 0–9 + any ID via URL) |
| **Admin panel** | `/admin/` CRUD over all models |

## Quick start

```bash
# 1. Create virtualenv + install deps
python -m venv venv
venv/Scripts/pip install -r requirements.txt      # Windows
# venv/bin/pip install -r requirements.txt        # macOS/Linux

# 2. Migrate + seed demo data (also runs the full self-test suite)
venv/Scripts/python manage.py migrate
venv/Scripts/python seed_demo.py

# 3. Run
venv/Scripts/python manage.py runserver
```

Open http://127.0.0.1:8000 — the gallery is pre-seeded with a demo result.

**Admin login:** `admin` / `admin1234` (change it!)

## How to use the AR modes

1. **Marker AR**: print `/marker/23/`, place it in view of your webcam (or upload
   a photo of it), choose *Marker-based AR*, pick a virtual object overlay → the
   logo gets pinned to the marker with pose axes drawn.
2. **ORB AR**: upload a distinctive reference image under *Assets → targets*
   (a demo one is seeded), choose *Feature-based AR*, then point the camera so
   the target appears → homography-warped overlay + match visualisation.
3. **Live camera**: go to *Live AR Camera*, press **Start**, hold up the printed
   marker, switch modes/filters/overlays in real time, and hit **Save snapshot**
   to push the current augmented frame into the gallery.

## Architecture

```
Browser (HTML/JS, getUserMedia, canvas JPEG)
   │  POST /api/frame/ (JSON: base64 JPEG + params)
   ▼
Django view (ar_app/views.py)
   │
   ▼
AR engine (ar_app/ar_engine.py)  — pure OpenCV/NumPy
   ├─ detect_aruco_markers()   → ArUco corners + IDs
   ├─ aruco_overlay()          → solvePnP pose + perspective warp + axes
   ├─ ORBTracker.process()     → ORB/FLANN match → RANSAC homography → warp
   └─ apply_filter()           → Canny / cartoon / sketch / thermal / ...
   ▼
JPEG back to browser (base64 data-url)  +  JSON stats
```

### Project layout

```
ar_app/
  ar_engine.py    # all computer vision (framework-independent)
  models.py       # TargetImage, VirtualObject, ProcessedImage
  views.py        # pages + JSON APIs
  forms.py        # upload forms
  admin.py, urls.py, migrations/
templates/        # base, home, upload_process, live, gallery, gallery_detail, assets
static/css/style.css, static/js/live.js
media/            # uploads, processed outputs, printable markers
seed_demo.py      # self-test + demo seeder
```

## Configuration notes

- `MARKER_SIZE_METERS` in `ar_engine.py` — physical printed marker side length;
  change it to your print size so distances are accurate.
- The camera matrix is a sensible default (`fx=fy=image width`); feed real
  calibration values via `cv2.calibrateCamera` for production pose accuracy.
- ORB trackers are cached per target in memory (`_ORB_TRACKERS`); restart clears.
- `DEBUG = True` / `ALLOWED_HOSTS = ["*"]` — demo settings; tighten before deploying.
- Webcam requires **HTTPS or localhost** (browser policy).

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/frame/` | POST JSON `{image, mode, overlay_id, target_id, filter, alpha}` | Augment one live frame → `{ok, stats:{image, aruco_count, marker_ids, good_matches, inliers, processing_ms, ...}}` |
| `/api/snapshot/` | POST multipart `{title, image}` | Save an augmented frame into the gallery |
| `/api/stats/` | GET | Dashboard counters |
| `/marker/<id>/` | GET | Printable ArUco marker PNG (0–249) |
| `/upload/` | POST multipart | Process an uploaded scene (AJAX returns JSON) |
