from shapely.geometry import Polygon, box

from pixel_bangkok.depthsort import back_to_front


def _order(shapes: dict[str, Polygon]) -> list[str]:
    names = list(shapes)
    return [names[index] for index in back_to_front(list(shapes.values()), names)]


def test_far_building_is_drawn_first():
    assert _order({"near": box(0, 0, 10, 10), "far": box(0, 20, 10, 30)}) == ["far", "near"]


def test_l_shaped_building_in_front_despite_deeper_centroid():
    l_shape = Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 100), (0, 100)])
    small = box(15, 20, 25, 30)
    assert l_shape.centroid.y > small.centroid.y
    assert _order({"l_shape": l_shape, "small": small}) == ["small", "l_shape"]


def test_long_building_between_two_others():
    shapes = {
        "front": box(0, 0, 10, 10),
        "long": box(5, 20, 100, 30),
        "back": box(80, 40, 90, 200),
        "aside": box(200, 0, 210, 10),
    }
    order = _order(shapes)
    assert order.index("back") < order.index("long") < order.index("front")


def test_unrelated_buildings_fall_back_to_centroid_then_name():
    shapes = {"b": box(0, 0, 10, 10), "a": box(20, 0, 30, 10), "c": box(40, 5, 50, 15)}
    assert _order(shapes) == ["c", "a", "b"]


def test_cycles_are_broken_deterministically():
    shapes = {
        "a": Polygon([(0, 0), (20, 0), (20, 5), (5, 5), (5, 30), (0, 30)]),
        "b": Polygon([(10, 10), (30, 10), (30, 40), (25, 40), (25, 15), (10, 15)]),
        "c": Polygon([(-5, 35), (22, 35), (22, 20), (17, 20), (17, 32), (-5, 32)]),
    }
    first = _order(shapes)
    assert sorted(first) == ["a", "b", "c"]
    assert _order(shapes) == first


def test_empty_input():
    assert back_to_front([], []) == []


def test_screen_overlap_filter_keeps_real_occlusion():
    l_shape = Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 100), (0, 100)])
    small = box(15, 20, 25, 30)
    assert back_to_front([l_shape, small], ["l_shape", "small"], raised=[50.0, 50.0]) == [1, 0]


def test_separated_items_fall_back_to_centroid_order():
    near = box(0, 0, 10, 10)
    far = box(0, 40, 10, 50)
    assert back_to_front([near, far], ["near", "far"], raised=[1.0, 1.0]) == [1, 0]
