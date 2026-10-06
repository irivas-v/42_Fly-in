#!/usr/bin/env python3
# ── Standard library ─────────────────────────────────────────────────────────

import os
import sys
import argparse

# ── Project modules ──────────────────────────────────────────────────────────
from map_parser import FlyInParser
from graph import Graph
from simulator import Simulator
from visual import Visualizer


# ── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    """
    Parse CLI arguments, run the simulation, and display the output.

    Returns:
    None. If file does not exist, exits with sys.exit(1).
    If the map is invalid, exits with sys.exit(2).
    """

    parser = argparse.ArgumentParser(
        prog="fly-in",
        description="Drone routing simulation (Fly-in project, 42 Madrid).",
        epilog="Example: python3 main.py maps/01_linear_path.txt --visual"
        )
    parser.add_argument(
        "map_file",
        nargs="?",
        default=None,
        help="Path to the map .txt file"
    )
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Enable ANSI rendering with numbered turns, "
        "zone colors, and occupancy states"
    )
    parser.add_argument(
        "--capacity-info",
        action="store_true",
        help=" displays capacity information during simulation, "
        "both zone and connection states"
    )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # ── Map loading  ─────────────────────────────────────────────────────────
    if not os.path.exists(args.map_file):
        print(f"ERROR: '{args.map_file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        data = FlyInParser().parse_file(args.map_file)
        graph = Graph(data)
        sim = Simulator(graph, show_capacity_info=args.capacity_info)
        lines = sim.run()

    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)

    # ── Render opcional ──────────────────────────────────────────────────────
    if args.visual:
        visualizer = Visualizer(graph, graph.nb_drones)
        visualizer.replay(lines)
    else:
        # ── Mandatory output specification (subject §VII.5) ──────────────────
        print("\n".join(lines))


if __name__ == "__main__":
    main()
