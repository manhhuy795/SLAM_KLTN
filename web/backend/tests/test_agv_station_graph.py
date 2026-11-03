import unittest

from app.services.agv_station_graph import (
    StationGraphError,
    plan_station_route,
)


def graph():
    return {
        "map_id": "test-map", "robot_id": 7,
        "nodes": [
            *({"id": name, "kind": "STATION"} for name in
              ("HOME", "PICKUP", "RACK_A", "RACK_B", "RACK_C", "RACK_D")),
            {"id": "J1", "kind": "JUNCTION"},
        ],
        "edges": [
            {"source": "HOME", "destination": "J1", "direction": "FORWARD",
             "cost": 1, "action": "STRAIGHT"},
            {"source": "J1", "destination": "PICKUP", "direction": "FORWARD",
             "cost": 1, "action": "LEFT", "verification_marker": "test-only"},
            {"source": "HOME", "destination": "PICKUP", "direction": "FORWARD",
             "cost": 5, "action": "STRAIGHT"},
        ],
        "junction_transitions": [
            {"incoming": "HOME", "junction": "J1", "outgoing": "PICKUP", "action": "LEFT"},
        ],
    }


def route(data=None, **overrides):
    return plan_station_route(data or graph(), map_id=overrides.get("map_id", "test-map"),
                              robot_id=overrides.get("robot_id", 7),
                              source=overrides.get("source", "HOME"),
                              destination=overrides.get("destination", "PICKUP"))


class StationGraphTests(unittest.TestCase):
    def test_shortest_route_uses_directed_junction_steps(self):
        self.assertEqual([(edge["source"], edge["destination"]) for edge in route()],
                         [("HOME", "J1"), ("J1", "PICKUP")])

    def test_unreachable_rack_and_unknown_station(self):
        with self.assertRaisesRegex(StationGraphError, "unreachable"):
            route(destination="RACK_D")
        with self.assertRaisesRegex(StationGraphError, "Unknown source"):
            route(destination="RACK_E")
        data = graph()
        data["nodes"].append({"id": "RACK_E", "kind": "STATION"})
        with self.assertRaisesRegex(StationGraphError, "Unknown station"):
            route(data)

    def test_missing_edges_and_required_station(self):
        data = graph()
        data["edges"] = []
        with self.assertRaisesRegex(StationGraphError, "edges"):
            route(data)
        data = graph()
        data["nodes"] = [n for n in data["nodes"] if n["id"] != "RACK_D"]
        with self.assertRaisesRegex(StationGraphError, "Required stations"):
            route(data)

    def test_invalid_junction_and_turn_sequence(self):
        data = graph()
        data["nodes"] = [n for n in data["nodes"] if n["id"] != "J1"]
        with self.assertRaisesRegex(StationGraphError, "endpoints"):
            route(data)
        data = graph()
        data["edges"][0]["action"] = "LEFT"
        with self.assertRaisesRegex(StationGraphError, "turn outside"):
            route(data)
        data = graph()
        data["edges"][1]["action"] = "U_TURN"
        with self.assertRaisesRegex(StationGraphError, "Invalid turn"):
            route(data)
        data = graph()
        data["junction_transitions"][0]["action"] = "RIGHT"
        with self.assertRaisesRegex(StationGraphError, "does not match"):
            route(data)

    def test_undeclared_transition_cannot_be_planned(self):
        data = graph()
        data["junction_transitions"] = []
        data["edges"] = data["edges"][:2]
        with self.assertRaisesRegex(StationGraphError, "unreachable"):
            route(data)

    def test_dijkstra_tracks_incoming_junction_edge(self):
        data = graph()
        data["edges"].extend([
            {"source": "HOME", "destination": "RACK_A", "direction": "FORWARD",
             "cost": 2, "action": "STRAIGHT"},
            {"source": "RACK_A", "destination": "J1", "direction": "FORWARD",
             "cost": 1, "action": "STRAIGHT"},
        ])
        data["junction_transitions"] = [
            {"incoming": "RACK_A", "junction": "J1", "outgoing": "PICKUP", "action": "LEFT"},
        ]
        self.assertEqual([(step["source"], step["destination"]) for step in route(data)],
                         [("HOME", "RACK_A"), ("RACK_A", "J1"), ("J1", "PICKUP")])

    def test_malformed_transition_is_rejected(self):
        data = graph()
        data["junction_transitions"][0]["incoming"] = "RACK_B"
        with self.assertRaisesRegex(StationGraphError, "transition endpoints"):
            route(data)
        data = graph()
        data.pop("junction_transitions")
        with self.assertRaisesRegex(StationGraphError, "transitions are required"):
            route(data)

    def test_invalid_direction_cost_and_marker(self):
        for key, value, message in (
            ("direction", "REVERSE", "forward"),
            ("cost", float("nan"), "cost"),
            ("verification_marker", "", "marker"),
        ):
            data = graph()
            data["edges"][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(StationGraphError, message):
                route(data)

    def test_wrong_map_or_robot_association(self):
        with self.assertRaisesRegex(StationGraphError, "does not match"):
            route(map_id="other-map")
        with self.assertRaisesRegex(StationGraphError, "does not match"):
            route(robot_id=8)

    def test_duplicate_edge_and_junction_endpoint(self):
        data = graph()
        data["edges"].append(dict(data["edges"][0]))
        with self.assertRaisesRegex(StationGraphError, "Duplicate directed"):
            route(data)
        with self.assertRaisesRegex(StationGraphError, "endpoints must be stations"):
            route(source="J1")

    def test_malformed_graph_inputs_fail_as_validation_errors(self):
        data = graph()
        data["edges"][0]["source"] = []
        with self.assertRaises(StationGraphError):
            route(data)
        data = graph()
        data["edges"][0]["action"] = []
        with self.assertRaises(StationGraphError):
            route(data)
        with self.assertRaises(StationGraphError):
            route(source=[])


if __name__ == "__main__":
    unittest.main()
