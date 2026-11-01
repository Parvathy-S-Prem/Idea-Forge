"""Convert a KML (GCC Ward Map / Zones Map 2022 from data.opencity.in) to GeoJSON.

Usage:  python scripts/convert_kml.py data/raw/wards.kml data/wards.geojson
Prints the property keys found so you can check which one holds the ward/zone id.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET


def _strip(tag):
    return tag.split("}")[-1]


def _coords(text):
    pts = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append([float(parts[0]), float(parts[1])])
    return pts


def _polygons(pm):
    polys = []
    for poly in pm.iter():
        if _strip(poly.tag) != "Polygon":
            continue
        rings = []
        for ring in poly.iter():
            if _strip(ring.tag) == "coordinates":
                rings.append(_coords(ring.text or ""))
        if rings:
            polys.append(rings)  # first = outer, rest = holes (order in KML)
    return polys


def convert(src, dst):
    root = ET.parse(src).getroot()
    feats = []
    for pm in root.iter():
        if _strip(pm.tag) != "Placemark":
            continue
        props = {}
        for el in pm.iter():
            t = _strip(el.tag)
            if t == "name" and el.text:
                props["name"] = el.text.strip()
            elif t == "SimpleData":
                props[el.attrib.get("name", "")] = (el.text or "").strip()
            elif t == "Data":
                v = next((c.text for c in el if _strip(c.tag) == "value"), "")
                props[el.attrib.get("name", "")] = (v or "").strip()
            elif t == "description" and el.text and "<td>" in el.text:
                for k, v in re.findall(r"<td>([^<]+)</td>\s*<td>([^<]*)</td>", el.text):
                    props[k.strip()] = v.strip()
        polys = _polygons(pm)
        if not polys:
            continue
        geom = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    json.dump({"type": "FeatureCollection", "features": feats}, open(dst, "w", encoding="utf-8"))
    print(f"{len(feats)} features -> {dst}")
    if feats:
        print("property keys:", list(feats[0]["properties"].keys()))
        print("sample:", feats[0]["properties"])


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
