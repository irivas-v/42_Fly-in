#!/usr/bin/env python3
"""
Graph representation and pathfinding algorithms for the Fly-in simulation.

Builds an adjacency list from MapData and provides BFS,
Dijkstra, and DFS multi-path routing.
"""

# ── Librería estándar ────────────────────────────────────────────────────────
import heapq
import math
from collections import deque
from typing import Dict, List, Optional, Tuple
import sys
import os
from map_parser import FlyInParser
# ── Importamos desde map_parser ──────────────────────────────────────────────
from map_parser import (
    ZONE_BLOCKED,
    ZONE_PRIORITY,
    ZONE_RESTRICTED,
    Connection,
    MapData,
    Zone,
)


# ── Clase Graph ──────────────────────────────────────────────────────────────

class Graph:
    """
    Adjacency graph representing zones and bidirectional connections.

    Attributes:
        zones: Dictionary of zones indexed by name.
        start: Starting zone name.
        end: Destination zone name.
        nb_drones: Total number of drones to route.
    """

    def __init__(self, map_data: MapData) -> None:
        """
        Initialize graph from validated MapData.

        Args:
            map_data: Validated MapData instance from the parser.
        """
        self.zones: Dict[str, Zone] = map_data.zones
        self.nb_drones: int = map_data.nb_drones

        if map_data.start_hub is None:
            raise ValueError("Missing 'start_hub' definition.")
        if map_data.end_hub is None:
            raise ValueError("Missing 'end_hub' definition.")
        self.start: str = map_data.start_hub
        self.end: str = map_data.end_hub

        self._adj: Dict[str, List[Connection]] = {
            name: [] for name in self.zones
            }

        self._build_adj(map_data.connections)

    def _build_adj(self, connections: List[Connection]) -> None:
        """
        Populate the adjacency list with bidirectional connections.

        Args:
            connections: List of Connection instances from MapData.
        """
        for conn in connections:
            self._adj[conn.source].append(conn)

            reverse = Connection(
                source=conn.target,
                target=conn.source,
                max_link_capacity=conn.max_link_capacity,
            )
            self._adj[conn.target].append(reverse)

    # ── Basic Queries ────────────────────────────────────────────────────────
    def neighbors(self, zone_name: str) -> List[Zone]:
        """
        Return accessible neighbor zones, excluding blocked zones.

        Args:
            zone_name: Name of the origin zone.

        Returns:
            List of accessible neighboring Zone instances.
        """
        result: List[Zone] = []
        for conn in self._adj.get(zone_name, []):
            neighbor = self.zones.get(conn.target)

            if neighbor and neighbor.zone_type != ZONE_BLOCKED:
                result.append(neighbor)
        return result

    def connections_from(self, zone_name: str) -> List[Connection]:
        """
        Return all outgoing Connection objects for a zone.

        Args:
            zone_name: Name of the origin zone.

        Returns:
            List of Connection instances departing from the zone.
        """
        return self._adj.get(zone_name, [])

    def entry_cost(self, zone_name: str) -> float:
        """
        Return movement cost in turns to enter a destination zone.

        Args:
            zone_name: Destination zone name.

        Returns:
            Cost as float (normal: 1.0, priority: 0.9, restricted: 2.0).

        Raises:
            ValueError: If zone_name is not in the graph.
        """
        zone = self.zones.get(zone_name)
        if zone is None:
            raise ValueError(f"Unknown zone: {zone_name}")
        elif zone.zone_type == ZONE_RESTRICTED:
            return 2.0
        elif zone.zone_type == ZONE_PRIORITY:
            return 0.9
        else:
            return 1.0

    def turns_to_enter(self, zone_name: str) -> int:
        """
        Return discrete turns required to enter a destination zone.

        Args:
            zone_name: Destination zone name.

        Returns:
            Integer turns (1 for normal/priority, 2 for restricted).
        """
        return math.ceil(self.entry_cost(zone_name))

    # ── BFS (Breadth-First Search) ───────────────────────────────────────────

    def bfs(
            self,
            start: str,
            end: str
            ) -> Optional[List[str]]:
        """
        Find path with the minimum number of hops using BFS.

        Args:
            start: Starting zone name.
            end: Destination zone name.

        Returns:
            List of zone names representing the path, or None if unreachable.
        """
        if start not in self.zones or end not in self.zones:
            return None

        queue: deque[List[str]] = deque([[start]])
        visited: set[str] = {start}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == end:
                return path

            for neighbor in self.neighbors(current):
                if neighbor.name not in visited:
                    visited.add(neighbor.name)

                    queue.append(path + [neighbor.name])

        return None

    # ── Dijkstra — Lowest Cost Path ──────────────────────────────────────────

    def dijkstra(
            self,
            start: str,
            end: str
            ) -> Optional[Tuple[float, List[str]]]:
        """
        Find the lowest-cost path between start and end using
        Dijkstra's algorithm.

        Args:
            start: Starting zone name.
            end: Destination zone name.

        Returns:
            Tuple of (total_cost, path) or None if unreachable.
        """
        if start not in self.zones or end not in self.zones:
            return None

        heap: List[Tuple[float, str, List[str]]] = [(0.0, start, [start])]

        best: Dict[str, float] = {start: 0.0}

        while heap:
            cost, current, path = heapq.heappop(heap)
            if cost > best.get(current, float("inf")):
                continue

            if current == end:
                # Lowest-cost path found
                return (cost, path)

            for neighbor in self.neighbors(current):
                step = self.entry_cost(neighbor.name)
                new_cost = cost + step

                if new_cost < best.get(neighbor.name, float("inf")):
                    best[neighbor.name] = new_cost
                    # Push item maintaining the heap invariant
                    heapq.heappush(heap, (new_cost, neighbor.name,
                                          path + [neighbor.name]))

        return None

    # ── Multi-Path Search (DFS) ──────────────────────────────────────────────

    def find_all_paths(
        self,
        start: str,
        end: str,
        max_paths: int,
    ) -> List[Tuple[float, List[str]]]:
        """
        Find up to max_paths simple paths sorted by ascending cost.

        Args:
            start: Starting zone name.
            end: Destination zone name.
            max_paths: Maximum number of distinct paths to retrieve.

        Returns:
            List of (cost, path) tuples sorted in ascending order of cost.
        """
        results: List[Tuple[float, List[str]]] = []

        # DFS Stack: (current_zone, path_so_far, accumulated_cost)
        stack: List[Tuple[str, List[str], float]] = [(start, [start], 0.0)]

        while stack and len(results) < max_paths:
            current, path, cost = stack.pop()

            if current == end:
                results.append((cost, path))
                continue

            for neighbor in self.neighbors(current):
                if neighbor.name not in path:
                    step = self.entry_cost(neighbor.name)
                    stack.append((
                        neighbor.name,
                        path + [neighbor.name],
                        cost + step
                        ))

        results.sort(key=lambda t: t[0])
        return results

    # ── Debug ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        """Return a string representation of the graph for debugging."""
        lines = [
            f"Graph — {len(self.zones)} zonas | "
            f"start={self.start} | end={self.end} | drones={self.nb_drones}"
        ]
        for name, conns in self._adj.items():
            targets = [c.target for c in conns]
            lines.append(f"  {name:20} → {targets}")
        return "\n".join(lines)


# ── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":

    target = sys.argv[1] if len(sys.argv) > 1 else "map_path.txt"

    if not os.path.exists(target):
        print(f"ERROR: '{target}' no encontrado.", file=sys.stderr)
        sys.exit(1)

    data = FlyInParser().parse_file(target)
    g = Graph(data)

    print(g)

    print("\n── BFS ──")
    bfs_path = g.bfs(g.start, g.end)
    if bfs_path:
        print(f"  Ruta ({len(bfs_path)-1} saltos): {' → '.join(bfs_path)}")
    else:
        print("  Sin camino.")

    print("\n── Dijkstra ──")
    dijk = g.dijkstra(g.start, g.end)
    if dijk:
        cost, path = dijk
        print(
            f"  Path (coste={cost:.1f}, "
            f"~{math.ceil(cost)} turns): {' → '.join(path)}")
        for zone_name in path:
            z = g.zones[zone_name]
            print(f"    {zone_name:20} type={z.zone_type:10} "
                  f"entry_cost={g.entry_cost(zone_name)}")
    else:
        print("  No path found.")

    print("\n── All Paths (up to 5) ──")
    for c, p in g.find_all_paths(g.start, g.end, max_paths=5):
        print(f"  cost={c:.1f}  {' → '.join(p)}")
