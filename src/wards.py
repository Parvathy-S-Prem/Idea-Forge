"""Point-in-polygon lookup against official GCC ward + zone boundaries."""
import json
import re
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

DATA = Path(__file__).resolve().parent.parent / "data"
CHENNAI_BBOX = (80.05, 12.80, 80.36, 13.30)  # lon_min, lat_min, lon_max, lat_max (coarse pre-check)


def _load(filename):
    p = DATA / filename
    if not p.exists():
        return None
    feats = json.loads(p.read_text(encoding="utf-8"))["features"]
    geoms = [shape(f["geometry"]) for f in feats]
    return feats, geoms, STRtree(geoms)


def _label(props, pattern, prefix):
    """Pick the property whose key matches `pattern` (e.g. ward number), else first string value."""
    for k, v in props.items():
        if re.search(pattern, k, re.I) and str(v).strip():
            return f"{prefix} {str(v).strip()}" if str(v).strip().isdigit() else str(v).strip()
    for v in props.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


_wards = _zones = None
_loaded = False


def _ensure():
    global _wards, _zones, _loaded
    if not _loaded:
        _wards, _zones, _loaded = _load("wards.geojson"), _load("zones.geojson"), True


def in_bbox(lat, lon):
    return CHENNAI_BBOX[0] <= lon <= CHENNAI_BBOX[2] and CHENNAI_BBOX[1] <= lat <= CHENNAI_BBOX[3]


def _hit(layer, pt):
    feats, geoms, tree = layer
    for i in tree.query(pt, predicate="intersects"):
        return feats[int(i)]["properties"]
    return None


def lookup(lat, lon):
    """Return {'ward','zone'} or None if outside GCC. Raises if boundary files are missing."""
    _ensure()
    if _wards is None:
        raise RuntimeError("data/wards.geojson missing - run scripts/convert_kml.py")
    pt = Point(lon, lat)
    wp = _hit(_wards, pt)
    if wp is None:
        return None
    ward = _label(wp, r"ward.*(no|num|name)|^ward$", "Ward")
    zone = _label(wp, r"zone", "Zone")
    if (zone is None or zone == ward) and _zones is not None:
        zp = _hit(_zones, pt)
        zone = _label(zp, r"zone.*(no|num|name)|^zone$", "Zone") if zp else None
    return {"ward": ward, "zone": zone}
