import osmium

from pixel_bangkok.osm_pbf import matches_map, matches_poi, select_elements

BBOX = (100.0, 13.0, 100.01, 13.01)


def _write(path):
    writer = osmium.SimpleWriter(str(path))
    inside = [
        (1, 100.002, 13.002),
        (2, 100.004, 13.002),
        (3, 100.004, 13.004),
        (4, 100.002, 13.004),
    ]
    outside = [(5, 100.5, 13.5), (6, 100.6, 13.5), (7, 100.6, 13.6)]
    for node_id, lon, lat in inside + outside:
        writer.add_node(osmium.osm.mutable.Node(id=node_id, location=(lon, lat), tags={}))
    writer.add_node(
        osmium.osm.mutable.Node(id=8, location=(100.003, 13.003), tags={"natural": "tree"})
    )
    writer.add_node(
        osmium.osm.mutable.Node(
            id=9,
            location=(100.003, 13.0035),
            tags={"name": "Pier", "wikidata": "Q1", "man_made": "pier"},
        )
    )
    writer.add_node(
        osmium.osm.mutable.Node(id=10, location=(100.003, 13.0035), tags={"shop": "bakery"})
    )
    writer.add_way(osmium.osm.mutable.Way(id=20, nodes=[1, 2, 3, 4, 1], tags={"building": "yes"}))
    writer.add_way(osmium.osm.mutable.Way(id=21, nodes=[5, 6, 7, 5], tags={"building": "yes"}))
    writer.add_way(osmium.osm.mutable.Way(id=22, nodes=[1, 2, 3, 4, 1], tags={}))
    writer.add_way(osmium.osm.mutable.Way(id=23, nodes=[1, 3], tags={"highway": "residential"}))
    writer.add_relation(
        osmium.osm.mutable.Relation(
            id=30,
            members=[("w", 22, "outer")],
            tags={"type": "multipolygon", "natural": "water"},
        )
    )
    writer.close()


def test_selects_area_features_with_geometry(tmp_path):
    pbf = tmp_path / "test.osm.pbf"
    _write(pbf)
    elements, pois = select_elements(pbf, BBOX)
    keys = {(e["type"], e["id"]) for e in elements}
    assert keys == {("node", 8), ("node", 9), ("way", 20), ("way", 23), ("relation", 30)}
    building = next(e for e in elements if e["id"] == 20)
    assert len(building["geometry"]) == 5
    assert building["geometry"][0] == {"lat": 13.002, "lon": 100.002}
    water = next(e for e in elements if e["id"] == 30)
    assert water["members"][0]["role"] == "outer"
    assert len(water["members"][0]["geometry"]) == 5
    assert [(e["type"], e["id"]) for e in pois] == [("node", 9)]


def test_rules_mirror_the_overpass_query():
    assert matches_map({"building": "yes"}, "node")
    assert matches_map({"highway": "footway"}, "way")
    assert not matches_map({"highway": "bus_stop"}, "node")
    assert matches_map({"landuse": "religious"}, "way")
    assert not matches_map({"landuse": "farmland"}, "way")
    assert matches_map({"amenity": "parking"}, "way")
    assert not matches_map({"shop": "bakery"}, "node")
    assert matches_poi({"name": "x", "wikidata": "Q1", "historic": "fort"})
    assert not matches_poi({"name": "x", "historic": "fort"})
    assert not matches_poi({"name": "x", "wikidata": "Q1", "shop": "mall"})
