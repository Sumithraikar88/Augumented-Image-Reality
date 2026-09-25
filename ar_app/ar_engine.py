"""
Augmented Reality Engine for Image Processing
=============================================
Core computer-vision pipeline built on OpenCV:

1. Marker-based AR : ArUco fiducial marker detection -> pose estimation ->
                     perspective warp of a virtual object onto the marker.
2. Feature-based AR: ORB keypoint detection + Hamming-distance matching
                     between a reference "target" image and a scene image,
                     followed by RANSAC homography and overlay warping.
3. Live AR streaming: per-frame processing of webcam frames sent from the
                     browser (JPEG in / JPEG out over HTTP).

All functions accept/return BGR numpy arrays (OpenCV convention) unless a
JPEG/PNG byte string is produced for transport over HTTP.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Global tunables
# ---------------------------------------------------------------------------
ARUCO_DICT_NAME = "DICT_6X6_250"
MARKER_SIZE_METERS = 0.06          # printed marker side length, used for pose
MIN_MATCH_COUNT = 10               # minimum good ORB matches for homography
FLANN_INDEX_PARAMS = dict(algorithm=6, table_number=6, key_size=12,
                          multi_probe_level=1)  # LSH for binary descriptors
FLANN_SEARCH_PARAMS = dict(checks=32)


# ---------------------------------------------------------------------------
# Data classes describing AR results
# ---------------------------------------------------------------------------
@dataclass
class MarkerPose:
    """6-DoF pose of one detected marker (rotation + translation vectors)."""
    marker_id: int
    corners: np.ndarray            # 4x2 image coordinates
    rvec: Optional[np.ndarray] = None
    tvec: Optional[np.ndarray] = None

    @property
    def distance_meters(self) -> Optional[float]:
        if self.tvec is None:
            return None
        return float(np.linalg.norm(self.tvec))

    @property
    def yaw_pitch_roll_deg(self) -> Optional[Tuple[float, float, float]]:
        if self.rvec is None:
            return None
        rot_mat, _ = cv2.Rodrigues(self.rvec)
        sy = math.sqrt(rot_mat[0, 0] ** 2 + rot_mat[1, 0] ** 2)
        if sy > 1e-6:
            pitch = math.degrees(math.atan2(rot_mat[2, 1], rot_mat[2, 2]))
            yaw = math.degrees(math.atan2(-rot_mat[2, 0], sy))
            roll = math.degrees(math.atan2(rot_mat[1, 0], rot_mat[0, 0]))
        else:  # gimbal lock
            pitch = math.degrees(math.atan2(-rot_mat[1, 2], rot_mat[1, 1]))
            yaw = math.degrees(math.atan2(-rot_mat[2, 0], sy))
            roll = 0.0
        return pitch, yaw, roll


@dataclass
class AREsult:
    """Everything produced by one processing run, for templates + JSON."""
    processed_bgr: Optional[np.ndarray] = None
    mode: str = "none"
    aruco_count: int = 0
    marker_ids: list = field(default_factory=list)
    orb_keypoints_scene: int = 0
    orb_keypoints_target: int = 0
    good_matches: int = 0
    inliers: int = 0
    homography: Optional[np.ndarray] = None
    overlay_alpha: float = 0.85
    processing_ms: float = 0.0
    poses: list = field(default_factory=list)   # list[MarkerPose]
    tracking_confidence: int = 0
    image_metrics: dict = field(default_factory=dict)

    # -- JSON view for the frontend -----------------------------------------
    def to_json(self) -> dict:
        pose_dicts = []
        for p in self.poses:
            yaw_pitch_roll = p.yaw_pitch_roll_deg
            pose_dicts.append({
                "id": int(p.marker_id),
                "corners": np.asarray(p.corners, dtype=float).tolist(),
                "distance_m": p.distance_meters,
                "rpy_deg": list(yaw_pitch_roll) if yaw_pitch_roll else None,
            })
        return {
            "mode": self.mode,
            "aruco_count": self.aruco_count,
            "marker_ids": self.marker_ids,
            "orb_keypoints_scene": self.orb_keypoints_scene,
            "orb_keypoints_target": self.orb_keypoints_target,
            "good_matches": self.good_matches,
            "inliers": self.inliers,
            "homography": self.homography.tolist() if self.homography is not None else None,
            "overlay_alpha": self.overlay_alpha,
            "processing_ms": round(self.processing_ms, 2),
            "tracking_confidence": self.tracking_confidence,
            "image_metrics": self.image_metrics,
            "poses": pose_dicts,
        }


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def get_aruco_dict(name: str = ARUCO_DICT_NAME):
    """Return the requested predefined ArUco dictionary (OpenCV 3/4/5 safe)."""
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def bgr_from_base64(data_b64: str) -> np.ndarray:
    """Decode a base64 JPEG (from the browser webcam) into a BGR image."""
    if "," in data_b64:                       # strip data-url prefix
        data_b64 = data_b64.split(",", 1)[1]
    buf = np.frombuffer(base64.b64decode(data_b64), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image data")
    return img


def bgr_to_base64_jpeg(img: np.ndarray, quality: int = 85) -> str:
    """Encode a BGR image to a base64 JPEG data-url for <img> tags."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _load_image(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def _resize_to_width(img: np.ndarray, width: int = 960) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img
    scale = width / w
    return cv2.resize(img, (width, int(h * scale)), interpolation=cv2.INTER_AREA)


def analyse_image(img_bgr: np.ndarray) -> dict:
    """Return small, useful image-quality readings for the UI and API."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if brightness < 65:
        exposure = "low light"
    elif brightness > 205:
        exposure = "high light"
    else:
        exposure = "balanced"
    return {
        "width": int(img_bgr.shape[1]),
        "height": int(img_bgr.shape[0]),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
        "sharpness": round(sharpness, 1),
        "exposure": exposure,
    }


# ---------------------------------------------------------------------------
# 1) ArUco marker-based AR
# ---------------------------------------------------------------------------
def detect_aruco_markers(img_bgr: np.ndarray, annotate: bool = True):
    """
    Detect ArUco markers in the image.

    Returns (corners, ids, rejected) exactly like cv2.aruco.detectMarkers.
    """
    aruco_dict = get_aruco_dict()
    params = cv2.aruco.DetectorParameters_create() if hasattr(
        cv2.aruco, "DetectorParameters_create") else cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners, ids, rejected = detector.detectMarkers(img_bgr)
    return corners, ids, rejected


def aruco_overlay(img_bgr: np.ndarray, overlay_bgr: Optional[np.ndarray] = None,
                  virtual_alpha: float = 0.9, draw_axes: bool = True) -> AREsult:
    """
    Classic marker-based AR:
      * find every ArUco marker,
      * estimate its 3-D pose from a calibrated-ish default camera matrix,
      * warp the overlay image onto each marker via perspective transform,
      * optionally draw the 3-D coordinate axes (pose visualisation).
    """
    result = AREsult(mode="aruco", overlay_alpha=virtual_alpha)
    out = img_bgr.copy()
    corners, ids, _ = detect_aruco_markers(img_bgr)

    if ids is None or len(ids) == 0:
        result.processed_bgr = out
        return result

    h, w = img_bgr.shape[:2]
    # Reasonable default intrinsics; a real calibration would refine these.
    camera_matrix = np.array([[w, 0, w / 2],
                              [0, w, h / 2],
                              [0, 0, 1]], dtype=np.float64)
    dist_coeffs = np.zeros((5, 1), dtype=np.float64)

    if ids is not None:
        result.aruco_count = int(len(ids))
        result.marker_ids = [int(i) for i in ids.flatten()]
        marker_areas = []

        for i, corner in enumerate(corners):
            pts = corner.reshape(4, 2)
            mid = int(ids[i].flatten()[0])
            marker_areas.append(abs(cv2.contourArea(pts.astype(np.float32))))

            # --- pose estimation (solvePnP on the 4 known corners) -------
            obj_pts = np.array([[-MARKER_SIZE_METERS / 2,  MARKER_SIZE_METERS / 2, 0],
                                [ MARKER_SIZE_METERS / 2,  MARKER_SIZE_METERS / 2, 0],
                                [ MARKER_SIZE_METERS / 2, -MARKER_SIZE_METERS / 2, 0],
                                [-MARKER_SIZE_METERS / 2, -MARKER_SIZE_METERS / 2, 0]],
                               dtype=np.float32)
            ok, rvec, tvec = cv2.solvePnP(obj_pts, pts.astype(np.float32),
                                          camera_matrix, dist_coeffs)
            pose = MarkerPose(marker_id=mid, corners=pts,
                              rvec=rvec if ok else None,
                              tvec=tvec if ok else None)
            result.poses.append(pose)

            # --- overlay warp (virtual object pinned to the marker) ------
            if overlay_bgr is not None:
                oh, ow = overlay_bgr.shape[:2]
                src = np.float32([[0, 0], [ow, 0], [ow, oh], [0, oh]])
                dst = pts.astype(np.float32)
                M = cv2.getPerspectiveTransform(src, dst)
                warped = cv2.warpPerspective(overlay_bgr, M, (w, h))
                mask = np.zeros((h, w), dtype=np.float32)
                cv2.fillConvexPoly(mask, dst.astype(np.int32), 1.0)
                mask = cv2.GaussianBlur(mask, (5, 5), 0)[..., None]  # soft edge
                a = float(np.clip(virtual_alpha, 0.0, 1.0))
                out[:] = (warped.astype(np.float32) * a * mask +
                          out.astype(np.float32) * (1 - a * mask)).astype(np.uint8)

            # --- annotations ----------------------------------------------
            if draw_axes and ok:
                cv2.drawFrameAxes(out, camera_matrix, dist_coeffs,
                                  rvec, tvec, MARKER_SIZE_METERS * 0.75, 2)
            cv2.polylines(out, [pts.astype(np.int32)], True, (0, 255, 0), 2)
            cx, cy = pts.mean(axis=0).astype(int)
            label = f"ID {mid}"
            if pose.distance_meters is not None:
                label += f"  {pose.distance_meters * 100:.0f} cm"
            cv2.putText(out, label, (cx - 30, cy - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(out, label, (cx - 30, cy - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

        # Larger, clearly resolved marker regions give a more reliable pose.
        frame_area = max(1, h * w)
        coverage = min(1.0, sum(marker_areas) / frame_area * 8)
        result.tracking_confidence = int(min(99, 55 + coverage * 44))

    result.processed_bgr = out
    return result


# ---------------------------------------------------------------------------
# 2) ORB feature-based AR
# ---------------------------------------------------------------------------
class ORBTracker:
    """
    Keeps a reference target image and matches it against scenes with ORB.

    Usage:
        tracker = ORBTracker(target_bgr)
        result  = tracker.process(scene_bgr, overlay_bgr=logo)
    """

    def __init__(self, target_bgr: np.ndarray, n_features: int = 3000):
        self.orb = cv2.ORB_create(nfeatures=n_features, scaleFactor=1.2, nlevels=8)
        self.target_bgr = _resize_to_width(target_bgr, 720)
        self.kp_t, self.des_t = self.orb.detectAndCompute(
            cv2.cvtColor(self.target_bgr, cv2.COLOR_BGR2GRAY), None)
        self.matcher = cv2.FlannBasedMatcher(FLANN_INDEX_PARAMS, FLANN_SEARCH_PARAMS)

    @property
    def target_ready(self) -> bool:
        return self.des_t is not None and len(self.kp_t) >= MIN_MATCH_COUNT

    def match(self, scene_gray: np.ndarray):
        """Match target descriptors against a grayscale scene. Returns good matches."""
        kp_s, des_s = self.orb.detectAndCompute(scene_gray, None)
        if des_s is None or self.des_t is None:
            return kp_s, []
        knn = self.matcher.knnMatch(self.des_t, des_s, k=2)
        good = []
        for pair in knn:
            if len(pair) == 2:
                m, n = pair
                if m.distance < 0.75 * n.distance:      # Lowe's ratio test
                    good.append(m)
        return kp_s, good

    def process(self, scene_bgr: np.ndarray,
                overlay_bgr: Optional[np.ndarray] = None,
                virtual_alpha: float = 0.85) -> AREsult:
        """
        Feature-based AR on one scene frame:
        find the target, compute homography, warp the overlay onto it and
        draw the matched keypoint bounding region.
        """
        result = AREsult(mode="orb", overlay_alpha=virtual_alpha)
        result.orb_keypoints_target = len(self.kp_t) if self.kp_t else 0
        out = scene_bgr.copy()
        scene_gray = cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2GRAY)
        kp_s, good = self.match(scene_gray)
        result.orb_keypoints_scene = len(kp_s) if kp_s else 0
        result.good_matches = len(good)

        if not self.target_ready or len(good) < MIN_MATCH_COUNT:
            cv2.putText(out, "Target not found", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3, cv2.LINE_AA)
            result.processed_bgr = out
            return result

        src_pts = np.float32([self.kp_t[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_s[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, inlier_mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        result.homography = H
        result.inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0

        if H is None:
            result.processed_bgr = out
            return result

        result.tracking_confidence = int(np.clip(
            (result.inliers / max(MIN_MATCH_COUNT, result.good_matches)) * 100, 0, 99))

        h_t, w_t = self.target_bgr.shape[:2]
        box = np.float32([[0, 0], [w_t, 0], [w_t, h_t], [0, h_t]]).reshape(-1, 1, 2)
        projected = cv2.perspectiveTransform(box, H)

        # --- overlay warp ---------------------------------------------------
        if overlay_bgr is not None:
            h_s, w_s = scene_bgr.shape[:2]
            oh, ow = overlay_bgr.shape[:2]
            src = np.float32([[0, 0], [ow, 0], [ow, oh], [0, oh]]).reshape(-1, 1, 2)
            warped = cv2.warpPerspective(
                overlay_bgr, H @ cv2.getPerspectiveTransform(src, box), (w_s, h_s))
            mask = np.zeros((h_s, w_s), dtype=np.float32)
            cv2.fillConvexPoly(mask, np.int32(projected.reshape(4, 2)), 1.0)
            mask = cv2.GaussianBlur(mask, (7, 7), 0)[..., None]
            a = float(np.clip(virtual_alpha, 0.0, 1.0))
            out[:] = (warped.astype(np.float32) * a * mask +
                      out.astype(np.float32) * (1 - a * mask)).astype(np.uint8)

        # --- annotations: target border + matches ---------------------------
        cv2.polylines(out, [np.int32(projected)], True, (0, 255, 255), 3, cv2.LINE_AA)
        for m, ok_in in zip(good[:120], inlier_mask.reshape(-1)[:120]):
            if ok_in:
                p1 = tuple(np.int32(self.kp_t[m.queryIdx].pt))
                p2 = tuple(np.int32(kp_s[m.trainIdx].pt))
                cv2.circle(out, p2, 2, (0, 255, 0), -1)

        cv2.putText(out, f"Inliers: {result.inliers}/{result.good_matches}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
        result.processed_bgr = out
        return result


# ---------------------------------------------------------------------------
# 3) Image-enhancement filters
# ---------------------------------------------------------------------------
def _cartoonify(im: np.ndarray) -> np.ndarray:
    gray = cv2.medianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, 9, 9)
    color = cv2.bilateralFilter(im, 9, 250, 250)
    return cv2.bitwise_and(color, color, mask=edges)


def _pencil_sketch(im: np.ndarray) -> np.ndarray:
    gray, _ = cv2.pencilSketch(im, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
    return gray


def _clarity(im: np.ndarray) -> np.ndarray:
    """Local contrast plus a gentle unsharp mask for low-contrast photos."""
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(l)
    enhanced = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    soft = cv2.GaussianBlur(enhanced, (0, 0), 2.2)
    return cv2.addWeighted(enhanced, 1.35, soft, -0.35, 0)


def _denoise(im: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(im, None, 7, 7, 7, 21)


def _neon_edges(im: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 160)
    glow = cv2.GaussianBlur(edges, (0, 0), 6)
    out = np.zeros_like(im)
    out[..., 0] = glow
    out[..., 1] = edges
    out[..., 2] = np.maximum(edges, glow // 2)
    return cv2.addWeighted(im, 0.28, out, 1.15, 0)


def _night_vision(im: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    boosted = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    out = np.zeros_like(im)
    out[..., 1] = boosted
    out[..., 0] = (boosted * 0.22).astype(np.uint8)
    return out


def _document_scan(im: np.ndarray) -> np.ndarray:
    """High-contrast document style scan useful for notes and printed pages."""
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 55, 55)
    scanned = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 10)
    return cv2.cvtColor(scanned, cv2.COLOR_GRAY2BGR)


FILTERS = {
    "original": lambda im: im,
    "clarity": _clarity,
    "denoise": _denoise,
    "grayscale": lambda im: cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR),
    "edges": lambda im: cv2.cvtColor(cv2.Canny(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 90, 180), cv2.COLOR_GRAY2BGR),
    "neon": _neon_edges,
    "nightvision": _night_vision,
    "scan": _document_scan,
    "cartoon": _cartoonify,
    "sketch": lambda im: cv2.cvtColor(_pencil_sketch(im), cv2.COLOR_GRAY2BGR),
    "thermal": lambda im: cv2.applyColorMap(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLORMAP_JET),
    "negative": lambda im: 255 - im,
    "blur": lambda im: cv2.GaussianBlur(im, (21, 21), 0),
}


def apply_filter(img_bgr: np.ndarray, name: str) -> np.ndarray:
    return FILTERS.get(name, FILTERS["original"])(img_bgr)


# ---------------------------------------------------------------------------
# 4) Marker generation (print it, point the webcam at it!)
# ---------------------------------------------------------------------------
def generate_aruco_marker(marker_id: int = 23, side_px: int = 400) -> np.ndarray:
    """Render a printable ArUco marker with a white quiet zone around it."""
    marker = cv2.aruco.generateImageMarker(get_aruco_dict(), int(marker_id),
                                          side_px) if hasattr(
        cv2.aruco, "generateImageMarker") else cv2.aruco.drawMarker(
        get_aruco_dict(), int(marker_id), side_px)
    quiet = int(side_px * 0.25)
    canvas = np.full((side_px + 2 * quiet, side_px + 2 * quiet), 255, dtype=np.uint8)
    canvas[quiet:quiet + side_px, quiet:quiet + side_px] = marker
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# 5) Dispatcher used by Django views
# ---------------------------------------------------------------------------
def process_image(img_bgr: np.ndarray,
                  mode: str = "aruco",
                  overlay_bgr: Optional[np.ndarray] = None,
                  virtual_alpha: float = 0.85,
                  orb_tracker: Optional[ORBTracker] = None,
                  image_filter: str = "original") -> AREsult:
    """
    Single entry point for the Django layer.

    mode:
      "aruco"  -> marker-based AR
      "orb"    -> feature-based AR (needs orb_tracker with a target image)
      "filter" -> plain image-processing filter, no AR
    """
    import time
    t0 = time.perf_counter()

    img_bgr = _resize_to_width(img_bgr, 1280)
    if image_filter != "original":
        img_bgr = apply_filter(img_bgr, image_filter)

    if mode == "aruco":
        res = aruco_overlay(img_bgr, overlay_bgr=overlay_bgr, virtual_alpha=virtual_alpha)
    elif mode == "orb" and orb_tracker is not None:
        res = orb_tracker.process(img_bgr, overlay_bgr=overlay_bgr,
                                  virtual_alpha=virtual_alpha)
    else:
        res = AREsult(mode="filter", processed_bgr=img_bgr.copy())

    res.processing_ms = (time.perf_counter() - t0) * 1000.0
    res.image_metrics = analyse_image(res.processed_bgr)
    return res
