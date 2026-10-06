#!/usr/bin/env python3
"""
Turn-by-turn simulation engine for Fly-in.

Routes drones from start to end in the fewest possible turns while adhering
to zone and connection capacity constraints.
"""

# ── Standard library ─────────────────────────────────────────────────────────
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Project modules ──────────────────────────────────────────────────────────
from graph import Graph
from map_parser import FlyInParser, ZONE_RESTRICTED

STALL_THRESHOLD: int = 3


# ── Drone Data Model ─────────────────────────────────────────────────────────
@dataclass
class Drone:
    """
    State of an individual drone throughout simulation.

    Attributes:
        drone_id: Unique drone identifier (1, 2, ...).
        current_zone: Zone where the drone is currently located.
        path: List of zone names from start to goal.
        path_index: Current index within the assigned path.
        turns_remaining: Remaining turns in transit towards next_zone.
        next_zone: Target zone during multi-turn transit.
        delivered: True once the drone reaches the goal zone.
        stall_count: Consecutive turns without moving.
        route_index: Index of the current route in simulator._routes.
    """

    drone_id: int
    current_zone: str
    path: List[str] = field(default_factory=list)
    path_index: int = 0
    turns_remaining: int = 0
    next_zone: Optional[str] = None
    delivered: bool = False
    stall_count: int = 0
    route_index: int = 0

    @property
    def in_transit(self) -> bool:
        """
        Return True if the drone is mid-transit to a restricted zone.
        """
        return self.turns_remaining > 0

    @property
    def label(self) -> str:
        """
        Formatted drone label for simulation output (e.g. 'D1').
        """
        return f"D{self.drone_id}"

    def peek_next_zone(self) -> Optional[str]:
        """
        Return the next zone in the path without advancing.
        """
        siguiente_indice = self.path_index + 1
        if siguiente_indice >= len(self.path):
            return None
        return self.path[siguiente_indice]

    def __repr__(self) -> str:
        """
        Return a string representation of the drone for debugging.
        """
        if self.delivered:
            estado = "delivered"
        elif self.in_transit:
            estado = f"in transit to {self.next_zone}"
            f"({self.turns_remaining} turn(s) left)"
        else:
            estado = f"waiting at {self.current_zone} "
            f"(stall={self.stall_count})"
        return f"Drone(D{self.drone_id} | {estado} | path={self.path})"


# ── _TurnPlan — Turn Decisions Container ─────────────────────────────────────

@dataclass
class _TurnPlan:
    """Consolidated decisions and resource reservations for a single turn.

    Attributes:
        decisions: Mapping from drone_id to destination zone
        (or None if waiting).
        reserved_zones: Count of committed spots per zone for this turn.
        reserved_conns: Count of committed traversals per connection tuple.
        leaving_drones: Set of drone IDs vacating their current
        zones this turn.
    """

    decisions: Dict[int, Optional[str]] = field(default_factory=dict)
    reserved_zones: Dict[str, int] = field(default_factory=dict)
    reserved_conns: Dict[Tuple[str, str], int] = field(default_factory=dict)
    leaving_drones: "set[int]" = field(default_factory=set)


# ── Simulation Engine ────────────────────────────────────────────────────────
class Simulator:
    """
    Turn-by-turn simulation engine moving drones from start to goal.

    Attributes:
        graph: Validated Graph instance.
        show_capacity_info: flag that displays capacity information
        drones: List of active Drone instances.
        turn: Number of elapsed turns.
    """

    def __init__(
            self,
            graph: Graph,
            show_capacity_info: bool = False,
            ) -> None:
        """
        Initialize simulator, instantiate drones, and assign initial paths.

        Args:
            graph: Validated Graph instance.
            show_capacity_info: show_capacity_info: flag
            that displays capacity information

        Raises:
            ValueError: If no valid path exists between start and goal.
        """
        self.graph: Graph = graph
        self.show_capacity_info: bool = show_capacity_info

        self.turn: int = 0
        self._routes: List[List[str]] = []
        self.drones: List[Drone] = []

        for indice in range(graph.nb_drones):
            nuevo_dron = Drone(drone_id=indice + 1, current_zone=graph.start)
            self.drones.append(nuevo_dron)

        self._assign_paths()

    # ── Path Allocation ──────────────────────────────────────────────────────

    def _assign_paths(self) -> None:
        """
        Compute candidate paths and distribute them to drones in round-robin.

        Raises:
            ValueError: If find_all_paths() returns no paths
            between start and end.
        """
        rutas_encontradas: List[Tuple[float, List[str]]] = \
            self.graph.find_all_paths(
            self.graph.start,
            self.graph.end,
            max_paths=min(self.graph.nb_drones * 2, 50),
        )

        if not rutas_encontradas:
            raise ValueError(
                f"No valid route found between '{self.graph.start}' "
                f"and '{self.graph.end}'."
            )

        self._routes = []
        for _coste, ruta in rutas_encontradas:
            self._routes.append(ruta)

        for indice, dron in enumerate(self.drones):
            dron.route_index = indice % len(self._routes)
            dron.path = self._routes[dron.route_index]

    def _reassign_stalled(self, dron: Drone) -> None:
        """
        Reassign an alternative path to a drone blocked for too many turns.

        Args:
            dron: Drone instance experiencing stall.
        """
        if not self._routes:
            return

        dron.route_index = (dron.route_index + 1) % len(self._routes)
        nueva_ruta = self._routes[dron.route_index]
        dron.path = nueva_ruta
        dron.stall_count = 0

        if dron.current_zone in nueva_ruta:
            dron.path_index = nueva_ruta.index(dron.current_zone)
        else:
            dron.path_index = 0

    # ── Main Simulation Loop ─────────────────────────────────────────────────

    def run(self) -> List[str]:
        """
        Execute the full simulation turn by turn until all drones
        reach the goal.

        Returns:
            List of output lines formatted per subject specifications.

        Raises:
            ValueError: If simulation exceeds max turns (deadlock safeguard).
        """
        lineas_de_salida: List[str] = []
        max_turnos = max(1000, len(self.drones) * 20)

        while not self._todos_entregados():
            self.turn += 1
            linea_del_turno = self._run_turn()
            lineas_de_salida.append(linea_del_turno)

            if self.turn > max_turnos:
                raise ValueError(
                    f"Simulation terminated: exceeded {max_turnos} turns "
                    f"without delivering all drones. Potential deadlock."
                )

        return lineas_de_salida

    def _todos_entregados(self) -> bool:
        """
        Return True if all drones have reached the goal zone."""
        for dron in self.drones:
            if not dron.delivered:
                return False
        return True

    # ── Single Turn Execution ────────────────────────────────────────────────

    def _run_turn(self) -> str:
        """
        Execute a single simulation turn and return its formatted output line.
        """
        self._handle_stalled_drones()

        ocupacion_actual = self._compute_current_occupancy()
        plan = _TurnPlan()

        self._reserve_forced_arrivals(plan)
        self._decide_free_movements(plan, ocupacion_actual)
        decison_applicated = self._apply_decisions(plan)

        # ── Displays capacity information during simulation ──────────────────
        capacity_items: List[str] = []

        if self.show_capacity_info:
            max_zone_capacity: str | int

            for zone_name in plan.reserved_zones:
                if zone_name in (self.graph.start, self.graph.end):
                    max_zone_capacity = "inf"
                else:
                    max_zone_capacity = self.graph.zones[zone_name].max_drones
                zone_spot = sum(
                    1 for dron in self.drones
                    if dron.current_zone == zone_name and not dron.in_transit
                )
                capacity_items.append(
                    f"Zone {zone_name}: "
                    f"{zone_spot}/{max_zone_capacity} drones"
                    )

            max_conn_capacity: int
            for (src, dst), conn_spot in plan.reserved_conns.items():
                max_conn_capacity = self._max_link_capacity(src, dst)
                capacity_items.append(
                    f"Connection {src}-{dst}: "
                    f"{conn_spot}/{max_conn_capacity} capacity used"
                    )

        if capacity_items:
            line = decison_applicated + "\n" + ", ".join(capacity_items)
        else:
            line = decison_applicated

        return (line)

    def _handle_stalled_drones(self) -> None:
        """
        Reassign routes for drones stalled beyond the threshold.
        """
        for dron in self.drones:
            if dron.delivered:
                continue
            if dron.in_transit:
                continue
            if dron.stall_count >= STALL_THRESHOLD:
                self._reassign_stalled(dron)

    def _compute_current_occupancy(self) -> Dict[str, int]:
        """
        Count how many stationary drones are in each zone.
        """
        ocupacion: Dict[str, int] = {}
        for dron in self.drones:
            if dron.delivered or dron.in_transit:
                continue
            zona = dron.current_zone
            ocupacion[zona] = ocupacion.get(zona, 0) + 1
        return ocupacion

    # ── Pass 1A: Forced Arrivals ─────────────────────────────────────────────

    def _reserve_forced_arrivals(self, plan: _TurnPlan) -> None:
        """
        Reserve slots for drones already in transit completing their moves.
        """
        for dron in self.drones:
            if dron.delivered:
                plan.decisions[dron.drone_id] = None
                continue

            if not dron.in_transit:
                continue

            assert dron.next_zone is not None
            plan.leaving_drones.add(dron.drone_id)
            plan.decisions[dron.drone_id] = dron.next_zone
            plan.reserved_zones[dron.next_zone] = (
                plan.reserved_zones.get(dron.next_zone, 0) + 1
            )

    # ── Pass 1B: Free Movements ──────────────────────────────────────────────

    def _decide_free_movements(
            self,
            plan: _TurnPlan,
            ocupacion_actual: Dict[str, int]
            ) -> None:
        """
        Plan moves for stationary drones with available capacity.
        """
        for dron in self.drones:
            if dron.delivered or dron.in_transit:
                continue

            if not dron.path:
                plan.decisions[dron.drone_id] = None
                continue

            siguiente_zona = dron.peek_next_zone()

            if siguiente_zona is None:
                plan.decisions[dron.drone_id] = None
                continue

            if self.graph.zones.get(siguiente_zona) is None:
                plan.decisions[dron.drone_id] = None
                continue
            if not self._has_zone_capacity(
                siguiente_zona,
                ocupacion_actual,
                plan
            ):
                plan.decisions[dron.drone_id] = None
                continue

            if not self._has_connection_capacity(
                dron.current_zone,
                siguiente_zona,
                plan
            ):
                plan.decisions[dron.drone_id] = None
                continue

            plan.reserved_zones[siguiente_zona] = (
                plan.reserved_zones.get(siguiente_zona, 0) + 1
            )
            clave_conexion = self._canonical_connection_key(
                dron.current_zone,
                siguiente_zona
            )
            plan.reserved_conns[clave_conexion] = plan.reserved_conns.get(
                clave_conexion, 0) + 1
            plan.leaving_drones.add(dron.drone_id)
            plan.decisions[dron.drone_id] = siguiente_zona

    def _has_zone_capacity(
            self, nombre_zona: str,
            ocupacion_actual: Dict[str, int], plan: _TurnPlan
    ) -> bool:
        """
        Check if a zone has remaining capacity for this turn.
        """
        zona = self.graph.zones.get(nombre_zona)
        if zona is None:
            return False

        if nombre_zona in (self.graph.end, self.graph.start):
            return True

        capacidad_maxima = zona.max_drones

        drones_que_salen = self._count_drones_leaving_zone(nombre_zona, plan)

        ocupacion_efectiva = (
            ocupacion_actual.get(nombre_zona, 0)
            - drones_que_salen
            + plan.reserved_zones.get(nombre_zona, 0)
        )

        return ocupacion_efectiva < capacidad_maxima

    def _count_drones_leaving_zone(
            self,
            nombre_zona: str,
            plan: _TurnPlan
            ) -> int:
        """
        Count stationary drones leaving the specified zone this turn.
        """
        contador: int = 0
        for dron in self.drones:
            si_se_va: bool = dron.drone_id in plan.leaving_drones
            si_esta_aqui: bool = dron.current_zone == nombre_zona
            if si_se_va and not dron.in_transit and si_esta_aqui:
                contador += 1
        return contador

    def _has_connection_capacity(
            self, origen: str,
            destino: str,
            plan: _TurnPlan
            ) -> bool:
        """
        Check if a connection has available transit capacity for this turn.
        """
        capacidad_maxima = self._max_link_capacity(origen, destino)
        clave = self._canonical_connection_key(origen, destino)
        usado = plan.reserved_conns.get(clave, 0)
        return usado < capacidad_maxima

    def _max_link_capacity(self, origen: str, destino: str) -> int:
        """
        Return the maximum link capacity between two zones.
        """
        for conexion in self.graph.connections_from(origen):
            if conexion.target == destino:
                return conexion.max_link_capacity
        return 1

    @staticmethod
    def _canonical_connection_key(zona_a: str, zona_b: str) -> Tuple[str, str]:
        """
        Return a sorted tuple key for an undirected connection.
        """
        if zona_a <= zona_b:
            return (zona_a, zona_b)
        return (zona_b, zona_a)

    # ── Pass 2: Apply Decision ───────────────────────────────────────────────

    def _apply_decisions(self, plan: _TurnPlan) -> str:
        """
        Execute planned moves and return the formatted output turn line.
        """
        tokens_del_turno: List[str] = []

        for dron in self.drones:
            if dron.delivered:
                continue

            destino = plan.decisions.get(dron.drone_id)

            if destino is None:
                if not dron.in_transit:
                    dron.stall_count += 1
                continue

            token = self._move_drone_towards(dron, destino)
            tokens_del_turno.append(token)

            if dron.current_zone == self.graph.end and not dron.in_transit:
                dron.delivered = True

        return " ".join(tokens_del_turno)

    def _move_drone_towards(self, dron: Drone, destino: str) -> str:
        """
        Update drone position or transit state and return its output token.
        """
        if dron.in_transit:
            return self._continue_transit(dron)
        return self._start_new_move(dron, destino)

    def _continue_transit(self, dron: Drone) -> str:
        """
        Advance a drone that is currently in transit.
        """
        dron.turns_remaining -= 1

        if dron.turns_remaining == 0:
            assert dron.next_zone is not None
            dron.current_zone = dron.next_zone
            dron.path_index += 1
            dron.next_zone = None
            dron.stall_count = 0
            return f"{dron.label}-{dron.current_zone}"

        assert dron.next_zone is not None
        return f"{dron.label}-{dron.current_zone}-{dron.next_zone}"

    def _start_new_move(self, dron: Drone, destino: str) -> str:
        """
        Start a new move for a stationary drone towards a destination.
        """
        zona_destino = self.graph.zones[destino]

        if zona_destino.zone_type == ZONE_RESTRICTED:
            dron.next_zone = destino
            dron.turns_remaining = 1
            dron.stall_count = 0
            return f"{dron.label}-{dron.current_zone}-{destino}"

        dron.current_zone = destino
        dron.path_index += 1
        dron.stall_count = 0
        return f"{dron.label}-{dron.current_zone}"

    # ── Debug ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        """
        Return a debug string representation of the simulator.
        """
        entregados = 0
        for dron in self.drones:
            if dron.delivered:
                entregados += 1
        return (
            f"Simulator — turn={self.turn} | "
            f"drones={len(self.drones)} | "
            f"delivered={entregados}/{len(self.drones)}"
        )


# ── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "map_path.txt"

    if not os.path.exists(target):
        print(f"ERROR: '{target}' no encontrado.", file=sys.stderr)
        sys.exit(1)

    try:
        data = FlyInParser().parse_file(target)
        graph = Graph(data)
        sim = Simulator(graph)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"Map : {target}")
    print(f"Start: {graph.start}  ->  End: {graph.end}")
    print(f"Drones: {graph.nb_drones}\n")

    lines = sim.run()
    for i, line in enumerate(lines, 1):
        print(f"Turn {i:>3}: {line}")

    print(f"\nTotal: {sim.turn} turns")
