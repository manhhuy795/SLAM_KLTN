"""Data-only AGV station graph. No topology or firmware commands are assumed."""

from heapq import heappop, heappush
from math import isfinite


REQUIRED_STATIONS = frozenset({"HOME", "PICKUP", *(f"RACK_{name}" for name in "ABCD")})
ACTIONS = frozenset({"STRAIGHT", "LEFT", "RIGHT"})


class StationGraphError(ValueError):
    pass


def validate_station_graph(graph, *, map_id, robot_id):
    """Validate supplied topology and return its node kinds and directed edges.

    Direction FORWARD means movement along the declared source-to-destination edge;
    it is a planning label, not an ESP32 command.
    """
    if not isinstance(graph, dict) or not isinstance(map_id, str) or not map_id:
        raise StationGraphError("A graph and map_id are required")
    if type(robot_id) is not int or robot_id <= 0:
        raise StationGraphError("A positive robot_id is required")
    if graph.get("map_id") != map_id or graph.get("robot_id") != robot_id:
        raise StationGraphError("Graph map or robot does not match the request")

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    transitions = graph.get("junction_transitions")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not edges:
        raise StationGraphError("Graph nodes and physical edges are required")
    if not isinstance(transitions, list):
        raise StationGraphError("Explicit junction transitions are required")

    kinds = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise StationGraphError("Invalid node")
        name, kind = node.get("id"), node.get("kind")
        if not isinstance(name, str) or not name or not isinstance(kind, str) or kind not in {"STATION", "JUNCTION"}:
            raise StationGraphError("Invalid node id or kind")
        if name in kinds:
            raise StationGraphError("Duplicate node")
        if name in REQUIRED_STATIONS and kind != "STATION":
            raise StationGraphError("Required destination must be a station")
        if kind == "STATION" and name not in REQUIRED_STATIONS:
            raise StationGraphError("Unknown station")
        kinds[name] = kind
    if not REQUIRED_STATIONS.issubset(kinds):
        raise StationGraphError("Required stations are missing")

    adjacency = {name: [] for name in kinds}
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise StationGraphError("Invalid edge")
        source, target = edge.get("source"), edge.get("destination")
        if not isinstance(source, str) or not isinstance(target, str):
            raise StationGraphError("Invalid edge endpoints")
        if source not in kinds or target not in kinds or source == target:
            raise StationGraphError("Unknown or identical edge endpoints")
        if (source, target) in seen:
            raise StationGraphError("Duplicate directed edge")
        seen.add((source, target))
        cost = edge.get("cost")
        if type(cost) not in {int, float} or not isfinite(cost) or cost <= 0:
            raise StationGraphError("Edge cost must be finite and positive")
        if edge.get("direction") != "FORWARD":
            raise StationGraphError("Only explicit forward directed edges are supported")
        action = edge.get("action")
        if not isinstance(action, str) or action not in ACTIONS or (action != "STRAIGHT" and kinds[source] != "JUNCTION"):
            raise StationGraphError("Invalid turn action or turn outside a junction")
        marker = edge.get("verification_marker")
        if marker is not None and (not isinstance(marker, str) or not marker):
            raise StationGraphError("Invalid verification marker")
        adjacency[source].append(edge)
    allowed = set()
    for transition in transitions:
        if not isinstance(transition, dict):
            raise StationGraphError("Invalid junction transition")
        incoming = transition.get("incoming")
        junction = transition.get("junction")
        outgoing = transition.get("outgoing")
        action = transition.get("action")
        if (not all(isinstance(name, str) for name in (incoming, junction, outgoing))
                or junction not in kinds or kinds[junction] != "JUNCTION"
                or incoming == outgoing or (incoming, junction) not in seen
                or (junction, outgoing) not in seen):
            raise StationGraphError("Invalid junction transition endpoints")
        outgoing_edge = next(edge for edge in adjacency[junction] if edge["destination"] == outgoing)
        if action != outgoing_edge["action"]:
            raise StationGraphError("Junction transition action does not match outgoing edge")
        key = (incoming, junction, outgoing)
        if key in allowed:
            raise StationGraphError("Duplicate junction transition")
        allowed.add(key)
    return kinds, adjacency, allowed


def plan_station_route(graph, *, map_id, robot_id, source, destination):
    """Return directed edge steps for the cheapest supplied path; never dispatch."""
    kinds, adjacency, transitions = validate_station_graph(graph, map_id=map_id, robot_id=robot_id)
    if not isinstance(source, str) or not isinstance(destination, str) or source not in kinds or destination not in kinds:
        raise StationGraphError("Unknown source or destination station")
    if kinds[source] != "STATION" or kinds[destination] != "STATION":
        raise StationGraphError("Route endpoints must be stations")
    if source == destination:
        return []

    start = (None, source)
    queue = [(0, start)]
    costs = {start: 0}
    previous = {}
    arrived = None
    while queue:
        cost, state = heappop(queue)
        if cost != costs[state]:
            continue
        incoming, node = state
        if node == destination:
            arrived = state
            break
        for edge in adjacency[node]:
            target = edge["destination"]
            if kinds[node] == "JUNCTION" and (incoming, node, target) not in transitions:
                continue
            next_state = (node, target)
            new_cost = cost + edge["cost"]
            if new_cost < costs.get(next_state, float("inf")):
                costs[next_state] = new_cost
                previous[next_state] = (state, edge)
                heappush(queue, (new_cost, next_state))
    if arrived is None:
        raise StationGraphError("Destination is unreachable")

    steps = []
    state = arrived
    while state != start:
        state, edge = previous[state]
        steps.append(edge)
    steps.reverse()
    return steps
