from shapely.geometry import Point, Polygon

from pixel_bangkok.pois import anchor_point, build_pois, category
from pixel_bangkok.publish import merge_pois
from pixel_bangkok.schemas import PointOfInterest


def _way(bounds, way_id, coords, tags):
    return {
        "type": "way",
        "id": way_id,
        "tags": tags,
        "geometry": [
            {"lon": lon, "lat": lat}
            for lon, lat in (bounds.world_to_lonlat(x, y) for x, y in coords)
        ],
    }


def test_categories():
    assert category({"railway": "station"}) == "transit"
    assert category({"man_made": "pier"}) == "pier"
    assert category({"tourism": "museum", "historic": "yes"}) == "museum"
    assert category({"amenity": "place_of_worship"}) == "temple"
    assert category({"place": "neighbourhood"}) == "neighbourhood"
    assert category({"historic": "fort"}) == "historic"
    assert category({"tourism": "attraction"}) == "landmark"


def test_anchor_point_lies_inside_concave_footprints(bounds):
    l_shape = [(0, 0), (60, 0), (60, 10), (10, 10), (10, 60), (0, 60), (0, 0)]
    element = _way(bounds, 1, l_shape, {})
    lon, lat = anchor_point(element)
    x, y = bounds.lonlat_to_world(lon, lat)
    assert Polygon(l_shape).contains(Point(x, y))


def test_build_pois_ranks_filters_and_names(bounds):
    elements = [
        _way(
            bounds,
            1,
            [(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)],
            {"wikidata": "Q1", "name": "วัดหนึ่ง", "amenity": "place_of_worship"},
        ),
        _way(
            bounds,
            2,
            [(50, 10), (60, 10), (60, 20), (50, 20), (50, 10)],
            {"wikidata": "Q2", "name": "Museum", "name:en": "Old Museum", "tourism": "museum"},
        ),
        _way(
            bounds,
            3,
            [(900, 10), (910, 10), (910, 20), (900, 20), (900, 10)],
            {"wikidata": "Q3", "name": "Far away", "tourism": "attraction"},
        ),
        _way(
            bounds,
            4,
            [(70, 10), (80, 10), (80, 20), (70, 20), (70, 10)],
            {"wikidata": "not-a-qid", "name": "Broken", "tourism": "attraction"},
        ),
    ]
    wikidata = {
        "Q1": {
            "label_en": "Temple One",
            "label_th": "วัดหนึ่ง",
            "description_en": "temple",
            "enwiki": "Temple One",
            "sitelinks": 5,
        },
        "Q2": {"label_en": "Museum", "description_en": "museum", "enwiki": None, "sitelinks": 9},
        "Q3": {"label_en": "Far", "sitelinks": 50},
    }
    pois = build_pois(elements, wikidata, bounds)
    assert [poi["id"] for poi in pois] == ["old-museum", "temple-one"]
    temple = next(poi for poi in pois if poi["id"] == "temple-one")
    assert temple["name_th"] == "วัดหนึ่ง"
    assert temple["category"] == "temple"
    assert temple["description"] == "temple"
    assert temple["source_url"] == "https://en.wikipedia.org/wiki/Temple_One"
    assert "Wikidata Q1" in temple["source"]
    assert temple["rank"] == 5
    museum = next(poi for poi in pois if poi["id"] == "old-museum")
    assert museum["source_url"] == "https://www.wikidata.org/wiki/Q2"
    assert [poi["id"] for poi in build_pois(elements, wikidata, bounds, limit=1)] == ["old-museum"]


def _poi(bounds, poi_id, x, y, category="temple"):
    lon, lat = bounds.world_to_lonlat(x, y)
    return PointOfInterest.from_dict(
        {
            "id": poi_id,
            "name_en": poi_id,
            "category": category,
            "lon": lon,
            "lat": lat,
            "description": "",
        }
    )


def test_curated_pois_win_over_nearby_generated_ones(bounds):
    curated = [_poi(bounds, "wat-arun-central-prang", 50, 50)]
    generated = [
        _poi(bounds, "wat-arun", 60, 50),
        _poi(bounds, "wat-arun-pier", 60, 50, category="pier"),
        _poi(bounds, "elsewhere", 150, 80),
        _poi(bounds, "wat-arun-central-prang", 150, 20),
    ]
    merged = merge_pois(curated, generated, bounds)
    assert [poi.id for poi in merged] == ["wat-arun-central-prang", "wat-arun-pier", "elsewhere"]
