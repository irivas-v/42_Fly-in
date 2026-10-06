#!/usr/bin/env python3
"""
Map file parser for the Fly-in simulation.

Parses input .txt files and extracts zones,
connections,
and metadata into MapData.
"""

# ── Standard library ────────────────────────────────────────────────────────
import re
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, NoReturn, Optional, Set


# ── Zone type constants──────────────────────────────────────────────
ZONE_NORMAL: str = "normal"
ZONE_BLOCKED: str = "blocked"
ZONE_RESTRICTED: str = "restricted"
ZONE_PRIORITY: str = "priority"


# Set: unique elements without duplicates
VALID_ZONE_TYPES: Set[str] = {
    ZONE_NORMAL,
    ZONE_BLOCKED,
    ZONE_RESTRICTED,
    ZONE_PRIORITY
    }

# Metadata keys recognized inside [...] blocks
VALID_META_KEYS: Set[str] = {
    "zone",
    "color",
    "max_drones",
    "max_link_capacity"
    }


# ── Data models ─────────────────────────────────────────────────────────
@dataclass
class Zone:
    """
    Represents a map zone (hub, start_hub, or end_hub).

    Attributes:
        name: Unique zone identifier without dashes or spaces.
        x: Integer X coordinate.
        y: Integer Y coordinate.
        zone_type: Zone classification (normal, restricted, priority, blocked).
        max_drones: Maximum concurrent drones allowed (default 1).
        color: Optional color name for visual display (default 'none').
    """
    name: str
    x: int
    y: int
    zone_type: str = ZONE_NORMAL
    max_drones: int = 1
    color: str = "none"


@dataclass
class Connection:
    """
    Bidirectional connection between two zones.

    Attributes:
        source: Origin zone name.
        target: Destination zone name.
        max_link_capacity: Maximum simultaneous drones allowed in transit.
    """
    source: str
    target: str
    max_link_capacity: int = 1


@dataclass
class MapData:
    """
    Container holding validated map components after parsing.

    Attributes:
        nb_drones: Total number of drones to route.
        start_hub: Name of the starting zone.
        end_hub: Name of the destination zone.
        zones: Mapping of zone names to Zone instances.
        connections: List of bidirectional Connection instances.
    """
    nb_drones: int = 0
    start_hub: Optional[str] = None
    end_hub: Optional[str] = None
    zones: Dict[str, Zone] = field(default_factory=dict)
    # field(default_factory=dict): creates a NEW dictionary for each MapData
    connections: List[Connection] = field(default_factory=list)


# ── Parser ───────────────────────────────────────────────────────────────────

class FlyInParser:
    """
    Parses and validates Fly-in map files into MapData instances.
    """

    def __init__(self) -> None:
        # re.compile() turns the pattern into an optimized regex object.
        # r"\[(.*?)\]" -> searches for [anything] on the line.
        # .*? -> non-greedy: matches as few characters as possible.
        self._meta_re: re.Pattern[str] = re.compile(r"\[(.*?)\]")

    # ── Public method ───────────────────────────────────────────────────────

    def parse_file(self, file_path: str) -> MapData:
        """
        Parse a map file and return a validated MapData instance.

        Args:
            file_path: Path to the map text file.

        Returns:
            Fully validated MapData object.

        Raises:
            SystemExit: If the file is missing or contains format errors.
        """
        map_data = MapData()
        first_data_seen = False

        try:
            with open(file_path, "r") as f:
                for line_num, raw in enumerate(f, 1):
                    line = raw.split("#", 1)[0].strip()

                    if not line:
                        continue

                    meta_str, line = self._split_meta(line)
                    meta = self._parse_meta(meta_str, line_num)

                    # ── Dispatch according to line prefix ──────────────
                    if line.startswith("nb_drones:"):
                        self._read_nb_drones(line, line_num, map_data)
                        first_data_seen = True

                    elif line.startswith(("start_hub:", "end_hub:", "hub:")):
                        if not first_data_seen:
                            self._error(
                                line_num,
                                "nb_drones must appear before the zones"
                            )
                        self._read_zone(line, line_num, meta, map_data)

                    elif line.startswith("connection:"):
                        if not first_data_seen:
                            self._error(
                                line_num,
                                "'nb_drones' must appear before connections"
                                )
                        self._read_connection(line, line_num, meta, map_data)
                        for conn in map_data.connections:
                            for zone_name in (conn.source, conn.target):
                                if zone_name not in map_data.zones:
                                    raise ValueError(
                                        f"Connection '{conn.source}-"
                                        f"{conn.target}': "
                                        f"zone '{zone_name}' not defined."
                                        )

                    else:
                        self._error(line_num, f"Unrecognized line:'{line}'")

            self._validate(map_data)

        except FileNotFoundError:
            print(f"ERROR: '{file_path}' not found.", file=sys.stderr)
            sys.exit(1)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        return map_data

    # ── Private parsing methods──────────────────────────────────────────

    def _split_meta(self, line: str) -> tuple[str, str]:
        """
        Extract metadata inside brackets from a line.

        Args:
            line: Cleaned line text.

        Returns:
            Tuple of (raw metadata string without brackets, stripped line).
        """
        match = self._meta_re.search(line)
        if match:
            meta_str = match.group(1)
            clean_line = self._meta_re.sub("", line).strip()
            return meta_str, clean_line
        return "", line

    def _parse_meta(self, meta_str: str, line_num: int) -> Dict[str, str]:
        """
        Parse key-value metadata tokens inside brackets into a dictionary.

        Args:
            meta_str: Content enclosed within brackets.
            line_num: Line number for error reporting.

        Returns:
            Dictionary of metadata key-value pairs.
        """
        meta: Dict[str, str] = {}
        if not meta_str:
            return meta

        for token in meta_str.split():
            if "=" not in token:
                self._error(line_num, f"metadata without '=': '{token}'")

            # split("=", 1): splits only on the FIRST '='
            # "max_drones=2" → ["max_drones", "2"]
            key, value = token.split("=", 1)
            key, value = key.strip(), value.strip()

            # Si  '=', error user:
            # [color=blue=max_drones=2]  [color=blue max_drones=2]
            if "=" in value:
                self._error(
                    line_num,
                    f"malformed value '{token}': '{value}' contains '='. "
                    "Did you forget a space between metadata entries?"
                )

            if key not in VALID_META_KEYS:
                self._error(
                    line_num,
                    f"unknown metadata key '{key}'. "
                    f"Valid keys: {sorted(VALID_META_KEYS)}"
                )

            meta[key] = value
        return meta

    def _read_nb_drones(
        self, line: str, line_num: int, map_data: MapData
    ) -> None:
        """
        Parse drone count line and assign it to map_data.

        Args:
            line: Cleaned input line.
            line_num: Current line number.
            map_data: MapData instance to update.
        """
        raw = line.split(":", 1)[1].strip()

        if not raw.isdigit() or int(raw) <= 0:
            self._error(
                line_num,
                f"'nb_drones' must be a positive integer, received: '{raw}'"
                )

        map_data.nb_drones = int(raw)

    def _read_zone(
        self,
        line: str,
        line_num: int,
        meta: Dict[str, str],
        map_data: MapData,
    ) -> None:
        """
        Parse a zone definition line (hub, start_hub, or end_hub).

        Args:
            line: Cleaned input line without metadata brackets.
            line_num: Current line number.
            meta: Parsed metadata dictionary.
            map_data: MapData instance to update.
        """
        # split(":", 1): separa keyword del resto en el primer ':'
        keyword, rest = line.split(":", 1)
        keyword = keyword.strip()
        parts: List[str] = rest.strip().split()

        if len(parts) < 3:
            self._error(
                line_num,
                f"incomplete zone definition, "
                f"expected <nombre> <x> <y>: '{line}'"
                )

        name = parts[0]

        if "-" in name:
            self._error(
                line_num,
                f"zone name cannot contain '-': '{name}'"
                )

        if (not (parts[1].lstrip("-").isdigit())
                or not (parts[2].lstrip("-").isdigit())):
            self._error(
                line_num,
                f"coordinates must be integers: '{parts[1]}' '{parts[2]}'"
                )

        x, y = int(parts[1]), int(parts[2])

        if name in map_data.zones:
            self._error(
                line_num,
                f"duplicate zone name: '{name}'"
                )

        zone_type = meta.get("zone", ZONE_NORMAL)
        if zone_type not in VALID_ZONE_TYPES:
            self._error(
                line_num,
                f"invalid zone type '{zone_type}'. "
                f"Valid types: {sorted(VALID_ZONE_TYPES)}"
                )

        if keyword in ("start_hub", "end_hub") and zone_type == ZONE_BLOCKED:
            self._error(
                line_num,
                f"{keyword} cannot be of type '{ZONE_BLOCKED}'")

        if keyword in ("start_hub", "end_hub"):
            raw_max: int = sys.maxsize
        else:
            raw_max_text: str = meta.get("max_drones", "1")
            if not raw_max_text.isdigit() or int(raw_max_text) <= 0:
                self._error(
                    line_num,
                    "max_drones must be a positive integer, "
                    f"received: '{raw_max_text}'"
                    )
            raw_max = int(raw_max_text)

        zone = Zone(
            name=name,
            x=x,
            y=y,
            zone_type=zone_type,
            max_drones=raw_max,
            color=meta.get("color", "none"),
        )
        map_data.zones[name] = zone

        if keyword == "start_hub":
            if map_data.start_hub is not None:
                self._error(
                    line_num,
                    "only one start_hub can be defined"
                    )
            map_data.start_hub = name
        elif keyword == "end_hub":
            if map_data.end_hub is not None:
                self._error(
                    line_num,
                    "sonly one end_hub can be defined"
                    )
            map_data.end_hub = name

    def _read_connection(
        self,
        line: str,
        line_num: int,
        meta: Dict[str, str],
        map_data: MapData,
    ) -> None:
        """Parse a connection definition line.

        Args:
            line: Cleaned input line without metadata brackets.
            line_num: Current line number.
            meta: Parsed metadata dictionary.
            map_data: MapData instance to update.
        """
        conn_str = line.split(":", 1)[1].strip()

        parts = conn_str.split("-", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            self._error(
                line_num,
                "malformed connection, expected zone1-zone2: "
                f"'{conn_str}'",
                )

        src, dst = parts[0].strip(), parts[1].strip()

        if src == dst:
            self._error(
                line_num,
                f"invalid connection {src}-{dst} cannot connect to itself"
            )

        raw_cap = meta.get("max_link_capacity", "1")
        if not raw_cap.isdigit() or int(raw_cap) <= 0:
            self._error(
                line_num,
                "max_link_capacity must be a positive integer, "
                f"received: '{raw_cap}'",
                )

        # Subject §VII.4: a-b and b-a are the same connection -> duplicate
        for existing in map_data.connections:
            if {existing.source, existing.target} == {src, dst}:
                self._error(
                    line_num,
                    f"duplicate connection: '{src}-{dst}'"
                    )

        map_data.connections.append(Connection(src, dst, int(raw_cap)))

    # ── Final validation ─────────────────────────────────────────────────────

    def _validate(self, map_data: MapData) -> None:
        """
        Perform global map validation once all lines are parsed.

        Args:
            map_data: MapData instance to validate.

        Raises:
            ValueError: If map constraints or required hubs are not satisfied.
        """
        if map_data.nb_drones <= 0:
            raise ValueError("“nb_drones” must be greater than 0.")
        if map_data.start_hub is None:
            raise ValueError("Missing 'start_hub' definition.")
        if map_data.end_hub is None:
            raise ValueError("Missing 'end_hub' definition.")
        if map_data.start_hub == map_data.end_hub:
            raise ValueError(
                "'start_hub' and 'end_hub' cannot be the same zone."
            )

        for conn in map_data.connections:
            for zone_name in (conn.source, conn.target):
                if zone_name not in map_data.zones:
                    raise ValueError(
                        f"Connection '{conn.source}-{conn.target}': "
                        f"zone '{zone_name}' is not defined."
                    )
    # ── Error reporting utility ──────────────────────────────────────────────

    @staticmethod
    def _error(line_num: int, msg: str) -> NoReturn:
        """Raise a formatted ValueError with line number context.

        Args:
            line_num: Line number where error occurred.
            msg: Description of the parsing error.

        Raises:
            ValueError: Always raised.
        """
        raise ValueError(f"[Line {line_num}] Error: {msg}")


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "map_path.txt"
    if not os.path.exists(target):
        print(f"ERROR: '{target}' not found.", file=sys.stderr)
        sys.exit(1)

    parser = FlyInParser()
    data = parser.parse_file(target)

    print(f"Mapa '{target}' — {data.nb_drones} drones")
    print(f"  Inicio : {data.start_hub}")
    print(f"  Fin    : {data.end_hub}")
    print(f"\nZonas ({len(data.zones)}):")
    for z in data.zones.values():
        print(f"  {z.name:20} type={z.zone_type:10} max={z.max_drones}  "
              f"color={z.color}  ({z.x},{z.y})")
    print(f"\nConnections ({len(data.connections)}):")
    for c in data.connections:
        print(f"  {c.source} <--> {c.target}  (cap={c.max_link_capacity})")
