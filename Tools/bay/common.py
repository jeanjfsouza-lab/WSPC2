"""Shared constants and helpers for the Bay city pipeline (Tools/bay). Not run on its own.

The source is the user's drawn map, ASSETS TO USE/city_gps_relief_map_v2.png: a top view at 0.6 px per metre.
Its frame covers x = -2.90 .. +4.50 km (east) and y = -2.10 .. +2.65 km (north). The map is a brief, not a
blueprint: every stage may move things so the result reads as a real place.

World coordinates in every Tools/bay file are metres, x east and y north. Unreal gets x east, y south, in cm.
Intermediate data goes to Saved/Bay.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
SRC_MAP = os.path.join(PROJECT, "ASSETS TO USE", "city_gps_relief_map_v2.png")
DATA = os.path.join(PROJECT, "Saved", "Bay")

# frame of the map inside the picture (pixels) and its georeference
FX, FY, FW, FH = 180, 158, 4440, 2850
PX_PER_M = 0.6
M_PER_PX = 1.0 / PX_PER_M
X_LEFT = -2900.0
Y_TOP = 2500.0 + (250 - FY) / PX_PER_M      # the +2.5 km tick sits at picture row 250


# colours (R, G, B) used by every picture of the network, by traced kind and by designed class
ROAD_COLOURS = {"street": (20, 20, 20), "avenue": (170, 0, 200), "bridge": (235, 20, 20), "tunnel": (0, 70, 255),
                "freeway": (110, 0, 190), "arterial": (215, 0, 150), "alley": (120, 120, 120), "ramp": (0, 150, 215)}
ROAD_NAMES_PT = {"street": "rua", "avenue": "avenida / rodovia", "bridge": "ponte", "tunnel": "túnel",
                 "freeway": "rodovia", "arterial": "avenida", "alley": "rua estreita", "ramp": "alça"}


# Road classes: how wide each is built and how it may climb.
#   carriage  kerb to kerb, metres            sidewalk  each side, metres (0 = none)
#   grade     steepest allowed slope          hold      how closely it follows the ground (0 loose .. 1 exact)
#   lanes     travel lanes in all             median    width of a raised divider in the middle, metres
SECTIONS = {
    "freeway":  {"carriage": 30.0, "sidewalk": 0.0, "grade": 0.06, "hold": 0.03, "lanes": 6, "median": 2.4},
    "arterial": {"carriage": 17.0, "sidewalk": 3.6, "grade": 0.09, "hold": 0.07, "lanes": 4, "median": 0.0},
    "street":   {"carriage": 12.0, "sidewalk": 3.6, "grade": 0.17, "hold": 0.12, "lanes": 2, "median": 0.0},
    "alley":    {"carriage": 6.0,  "sidewalk": 0.0, "grade": 0.17, "hold": 0.15, "lanes": 1, "median": 0.0},
    "ramp":     {"carriage": 7.0,  "sidewalk": 0.0, "grade": 0.08, "hold": 0.02, "lanes": 1, "median": 0.0},
    "bridge":   {"carriage": 17.0, "sidewalk": 2.4, "grade": 0.06, "hold": 1.0,  "lanes": 4, "median": 0.0},
    "tunnel":   {"carriage": 17.0, "sidewalk": 0.0, "grade": 0.07, "hold": 1.0,  "lanes": 4, "median": 0.0},
}
CURB_M = 0.15              # sidewalk above the carriageway
ROAD_MIN_Z = 2.6           # no road surface lower than this above the sea (quay level)


def to_world(px, py):
    """Frame pixel (column, row) -> metres (east, north). Works on arrays."""
    return X_LEFT + np.asarray(px, dtype=np.float64) / PX_PER_M, Y_TOP - np.asarray(py, dtype=np.float64) / PX_PER_M


def to_pixel(x, y):
    """Metres (east, north) -> frame pixel (column, row), fractional. Works on arrays."""
    return (np.asarray(x, dtype=np.float64) - X_LEFT) * PX_PER_M, (Y_TOP - np.asarray(y, dtype=np.float64)) * PX_PER_M


def gauss(a, sigma_px):
    """Gaussian blur of a float image; large blurs run on a reduced copy."""
    import cv2
    a = np.asarray(a).astype(np.float32)
    if sigma_px <= 8:
        return cv2.GaussianBlur(a, (0, 0), sigma_px)
    f = int(sigma_px // 4)
    small = cv2.resize(a, (a.shape[1] // f + 1, a.shape[0] // f + 1), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma_px / f)
    return cv2.resize(small, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)


def fbm(shape, cell_px, seed, octaves=5):
    """Smooth fractal noise in about [-1, 1]: random grids from cell_px down, upsampled and summed."""
    import cv2
    rng = np.random.default_rng(seed)
    h, w = shape
    total = np.zeros(shape, np.float32)
    norm, amp, cell = 0.0, 1.0, float(cell_px)
    for _ in range(octaves):
        gh, gw = int(h / cell) + 3, int(w / cell) + 3
        grid = rng.uniform(-1, 1, (gh, gw)).astype(np.float32)
        up = cv2.resize(grid, (int(gw * cell), int(gh * cell)), interpolation=cv2.INTER_CUBIC)[:h, :w]
        total += amp * up
        norm += amp
        amp *= 0.55
        cell /= 2.0
        if cell < 2.0:
            break
    return np.clip(total / norm * 1.6, -1.0, 1.0)


def nconv(values, mask, sigma_px):
    """Normalised convolution: a smooth field from the values where mask is set. Returns (field, support)."""
    num = gauss(np.where(mask, values, 0.0), sigma_px)
    den = gauss(mask.astype(np.float32), sigma_px)
    return num / np.maximum(den, 1e-6), den


def fill_holes(values, mask):
    """Fills every pixel outside mask from the nearest known values, coarse to fine."""
    out = np.where(mask, values, 0.0).astype(np.float32)
    known = mask.copy()
    for sigma in (3, 8, 24, 72, 220):
        field, support = nconv(out, known, sigma)
        new = ~known & (support > 0.02)
        out[new] = field[new]
        known |= new
    out[~known] = float(np.nanmean(values[mask]))
    return out


def world_grid(h, w):
    """World coordinates (metres) of every pixel centre of an h x w map-grid image."""
    xs = X_LEFT + (np.arange(w, dtype=np.float32) + 0.5) * M_PER_PX
    ys = Y_TOP - (np.arange(h, dtype=np.float32) + 0.5) * M_PER_PX
    return np.meshgrid(xs, ys)


def bilinear(field, x, y):
    """Value of a map-grid raster at world positions (arrays), interpolated between pixel centres."""
    u, v = to_pixel(x, y)
    u = np.clip(u - 0.5, 0, field.shape[1] - 1.001)
    v = np.clip(v - 0.5, 0, field.shape[0] - 1.001)
    u0, v0 = u.astype(int), v.astype(int)
    fu, fv = u - u0, v - v0
    return (field[v0, u0] * (1 - fu) * (1 - fv) + field[v0, u0 + 1] * fu * (1 - fv)
            + field[v0 + 1, u0] * (1 - fu) * fv + field[v0 + 1, u0 + 1] * fu * fv)


def data_path(name):
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, name)


def load_json(name):
    with open(data_path(name)) as f:
        return json.load(f)


def save_json(name, obj, indent=None):
    with open(data_path(name), "w") as f:
        json.dump(obj, f, indent=indent)
