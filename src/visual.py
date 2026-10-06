#!/usr/bin/env python3
"""Turn-by-turn ANSI visualizer for Fly-in simulations.

Reconstructs and displays map states, occupied zones, and link utilization
by replaying movement lines produced by the simulator.
"""

# ── Standard library ─────────────────────────────────────────────────────────
import os
import sys
from typing import Dict, List, Tuple

# ── Project modules ──────────────────────────────────────────────────────────
from graph import Graph
from map_parser import FlyInParser
from simulator import Simulator

# ── ANSI Escape Codes ────────────────────────────────────────────────────────
# \033[
# <n>m
# \033[0m

RESET: str = "\033[0m"
BOLD: str = "\033[1m"

_COLOR_CODES: Dict[str, str] = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "grey": "\033[90m",
    "orange": "\033[38;5;208m",
    "purple": "\033[38;5;93m",
    "brown": "\033[38;5;94m",
    "gold": "\033[38;5;220m",
    "lime": "\033[38;5;154m",
}
_DEFAULT_COLOR: str = "\033[37m"


class Visualizer:
    """Reconstruct and render turn-by-turn simulation states with ANSI colors.

    Attributes:
        graph: Validated Graph instance.
        positions: Mapping from drone label (e.g. 'D1') to stationary zone name
        transit: Mapping from drone label to (source, destination) while
        in transit.
    """

    def __init__(self, graph: Graph, nb_drones: int):
        """
        Initialize visualizer placing all drones at the start hub.

        Args:
            graph: Validated Graph instance.
            nb_drones: Total number of active drones.
        """
        self.graph: Graph = graph
        self.positions: Dict[str, str] = {
            f"D{i}": graph.start
            for i in range(1, nb_drones + 1)
        }
        self.transit: Dict[str, Tuple[str, str]] = {}

# ── Módulo A: ANSI Color Helpers ─────────────────────────────────────────────

    def _get_zone_color(self, zone_name: str) -> str:
        """
        Return the ANSI escape code for the specified zone color.
        """

        zone = self.graph.zones.get(zone_name)
        color_zone = zone.color if zone else "none"
        color_ansi = _COLOR_CODES.get(color_zone.lower(), _DEFAULT_COLOR)
        return (color_ansi)

    def _format_token(self, token: str) -> str:
        """
        Colorize and format a single movement token with ANSI styles
        """

        parts = token.split("-")
        drone_id = parts[0]
        rest_token = token[len(drone_id):]
        zone_name = parts[-1]
        color_ansi = self._get_zone_color(zone_name)

        return (
            f"{color_ansi}{BOLD}{drone_id}{RESET}"
            f"{color_ansi}{rest_token}{RESET}"
            )

# ── Módulo B: Positioning Logic ──────────────────────────────────────────────

    def _update_drone_position(self, token: str) -> None:
        """
        Update drone positions or transit status based on a movement token
        """

        parts = token.split("-")
        drone_id = parts[0]

        if len(parts) == 2:
            self.transit.pop(drone_id, None)
            self.positions[drone_id] = parts[1]
        elif len(parts) == 3:
            self.positions.pop(drone_id, None)
            self.transit[drone_id] = (parts[1], parts[2])
        # Other unexpected formats: ignored to preserve replay stability.

# ── Módulo C: Text Block Generation ──────────────────────────────────────────

    def _format_movements_line(self, line: str) -> str:
        """
        Update state and return a colorized string of all movements in the turn
        """

        colored_tokens: List[str] = []
        tokens: List[str] = line.split()
        for token in tokens:
            self._update_drone_position(token)
            colored_tokens.append(self._format_token(token))

        return (" ".join(colored_tokens))

    def _format_occupied_zones(self) -> List[str]:
        """
        Generate formatted lines reporting occupied zones and transit status.
        """

        zone_drones: Dict[str, List[str]] = {}
        for drone, zone in self.positions.items():
            zone_drones.setdefault(zone, []).append(drone)
        lines: List[str] = []
        for zone_name, drones_in_zone in sorted(zone_drones.items()):
            color = self._get_zone_color(zone_name)
            ordenados = sorted(drones_in_zone)
            drones_bold = [f"{BOLD}{d}{RESET}" for d in ordenados]
            label: str = " ".join(drones_bold)

            lines.append(f"{color}{zone_name}{RESET}: {label}")

        if self.transit:
            for drone_id in sorted(self.transit):
                src, dst = self.transit[drone_id]
                lines.append(f"in transit: {drone_id}: {src} -> {dst}")

        return lines

# ── Módulo D: Orchestration ──────────────────────────────────────────────────

    def replay(self, lines: List[str]) -> None:
        """
        Replay full simulation turn by turn with formatted ANSI output.

        Args:
            lines: List of turn strings produced by Simulator.run().
        """
        print(f"\nStart: {self.graph.start}  ->  End: {self.graph.end}")
        print(f"Drones: {self.graph.nb_drones}\n")

        for i, line in enumerate(lines, 1):
            print(f"\n{BOLD}-- Turno {i} --{RESET}")

            if "\n" in line:
                movements_part, cap_parts = line.split("\n", 1)
            else:
                movements_part, cap_parts = line, ""

            print(self._format_movements_line(movements_part))

            if cap_parts:
                print(f"Capacities: {cap_parts}")

            print("\nOccupied zones:")
            for d in (self._format_occupied_zones()):
                print(f" - {d}")

        print(f"\n{BOLD}Total: {len(lines)} turnos{RESET}")


# ── Punto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "map_path.txt"

    if not os.path.exists(target):
        print(f"ERROR: '{target}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        data = FlyInParser().parse_file(target)
        graph = Graph(data)
        sim = Simulator(graph)
        lines = sim.run()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"Map : {target}")
    print(f"Start: {graph.start}  ->  End: {graph.end}")
    print(f"Drones: {graph.nb_drones}\n")

    viz = Visualizer(graph, graph.nb_drones)
    viz.replay(lines)
