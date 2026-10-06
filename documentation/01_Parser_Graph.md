# Parser y Graph — Explicación detallada

> Este documento explica **línea a línea** cómo funcionan `map_parser.py` y `graph.py`
> del proyecto Fly-in. Cada sección incluye un ejemplo concreto para que puedas
> verificar mentalmente lo que ocurre al ejecutar el código.

---

## Índice

1. [[#1. El flujo general|1. El flujo general]]
2. [[#2. map_parser.py|2. map_parser.py]]
   - [[#2.1 Por qué se llama map_parser y no parser|2.1 Por qué se llama map_parser y no parser]]
   - [[#2.2 Las constantes de zona|2.2 Las constantes de zona]]
   - [[#2.3 Los dataclasses: Zone, Connection, MapData|2.3 Los dataclasses: Zone, Connection, MapData]]
   - [[#2.4 FlyInParser — la clase|2.4 FlyInParser — la clase]]
   - [[#2.5 _split_meta — separar los corchetes|2.5 _split_meta — separar los corchetes]]
   - [[#2.6 _parse_meta — convertir texto en dict|2.6 _parse_meta — convertir texto en dict]]
   - [[#2.7 _read_nb_drones y el orden inicial|2.7 _read_nb_drones y el orden inicial]]
   - [[#2.8 _read_zone — validaciones y capacidad especial|2.8 _read_zone — validaciones y capacidad especial]]
   - [[#2.9 _read_connection y max_link_capacity|2.9 _read_connection y max_link_capacity]]
   - [[#2.10 _validate — comprobaciones finales|2.10 _validate — comprobaciones finales]]
   - [[#2.11 _error y NoReturn|2.11 _error y NoReturn]]
3. [[#3. graph.py|3. graph.py]]
   - [[#3.1 Lista de adyacencia vs matriz|3.1 Lista de adyacencia vs matriz]]
   - [[#3.2 _build_adj — construir el grafo|3.2 _build_adj — construir el grafo]]
   - [[#3.3 neighbors, connections_from, entry_cost y turns_to_enter|3.3 neighbors, connections_from, entry_cost y turns_to_enter]]
   - [[#3.4 BFS — búsqueda en anchura|3.4 BFS — búsqueda en anchura]]
   - [[#3.5 Dijkstra — camino de menor coste|3.5 Dijkstra — camino de menor coste]]
   - [[#3.6 find_all_paths — múltiples rutas|3.6 find_all_paths — múltiples rutas]]
4. [[#4. Errores comunes y por qué los detectamos|4. Errores comunes y por qué los detectamos]]

---

## 1. El flujo general

```
archivo.txt
    │
    ▼
FlyInParser.parse_file()
    │  lee línea a línea
    │  extrae metadatos [...]
    │  construye objetos Zone y Connection
    │  valida el mapa completo
    │
    ▼
MapData
    ├── nb_drones: int
    ├── start_hub: str
    ├── end_hub:   str
    ├── zones:       Dict[str, Zone]
    └── connections: List[Connection]
    │
    ▼
Graph.__init__(map_data)
    │  construye lista de adyacencia
    │  (para cada zona → lista de sus conexiones directas)
    │
    ▼
Graph
    ├── neighbors()        → zonas accesibles vecinas (excluye blocked)
    ├── connections_from() → conexiones salientes completas (con max_link_capacity)
    ├── entry_cost()       → coste float de entrar a una zona (normal=1.0, priority=0.9, restricted=2.0)
    ├── turns_to_enter()   → turnos enteros calculados con math.ceil()
    ├── bfs()              → camino con menos saltos (sin ponderar coste)
    ├── dijkstra()         → camino de menor coste en turnos
    └── find_all_paths()   → hasta max_paths rutas ordenadas por coste
```

**Ejemplo de mapa mínimo** (usaremos este a lo largo del documento):

```
nb_drones: 2

start_hub: start 0 0 [color=green]
hub: waypoint1 1 0 [color=blue]
hub: waypoint2 2 0 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-waypoint1
connection: waypoint1-waypoint2
connection: waypoint2-goal
```

---

## 2. map_parser.py

### 2.1 Por qué se llama map_parser y no parser

Python tiene un módulo interno llamado `parser` (deprecado en 3.9, eliminado en 3.12).
Si llamamos a nuestro archivo `parser.py` y luego hacemos `from parser import ...`,
Python puede importar el módulo incorrecto dependiendo de la versión y la carpeta.
Llamándolo `map_parser.py` evitamos la ambigüedad.

### 2.2 Las constantes de zona

```python
ZONE_NORMAL:     str = "normal"
ZONE_BLOCKED:    str = "blocked"
ZONE_RESTRICTED: str = "restricted"
ZONE_PRIORITY:   str = "priority"

VALID_ZONE_TYPES: Set[str] = {ZONE_NORMAL, ZONE_BLOCKED, ZONE_RESTRICTED, ZONE_PRIORITY}
VALID_META_KEYS:  Set[str] = {"zone", "color", "max_drones", "max_link_capacity"}
```

**Por qué constantes en vez de strings directos:**

Sin constantes, `graph.py` tendría que escribir `"blocked"` como string literal.
Si en el futuro alguien cambia el nombre (improbable, pero posible), lo tendría que
cambiar en dos archivos. Con constantes, importas `ZONE_BLOCKED` y lo cambias en
un solo sitio. Además, mypy puede detectar typos en el nombre de la constante
(`ZONE_BLOKED` da error), pero no en un string literal (`"bloked"` no da error).

**Por qué `Set` y no `List`:**

`if zone_type in VALID_ZONE_TYPES` → con `Set` es O(1) (tiempo constante), con `List` es O(n)
(tendría que recorrer la lista uno a uno).
Para cuatro elementos la diferencia es insignificante, pero es el hábito correcto.

### 2.3 Los dataclasses: Zone, Connection, MapData

```python
@dataclass
class Zone:
    name: str
    x: int
    y: int
    zone_type: str = ZONE_NORMAL
    max_drones: int = 1
    color: str = "none"
```

`@dataclass` genera automáticamente el método `__init__` equivalente a:

```python
def __init__(self, name, x, y, zone_type="normal", max_drones=1, color="none"):
    self.name = name
    self.x = x
    ...
```

**Por qué `zone_type` y no `type`:**

`type` es un builtin de Python (`type(42)` devuelve `<class 'int'>`).
Usarlo como atributo no da error, pero sombrea el builtin dentro de la clase
y confunde a mypy con --strict. `zone_type` es más explícito.

**Por qué `x` e `y` son `int` y no `float`:**

El subject dice: *"The zones coordinates will always be integers"*.
Usar `int` lo documenta en el código y mypy lo verifica.

**`field(default_factory=dict)` en MapData:**

```python
zones: Dict[str, Zone] = field(default_factory=dict)
```

Sin `field(default_factory=...)`, todos los objetos `MapData` compartirían
el **mismo** diccionario. Es un bug clásico de Python:

```python
# ❌ MAL — todas las instancias comparten el mismo dict
@dataclass
class MapData:
    zones: Dict = {}  # este dict se crea UNA vez cuando se define la clase

a = MapData()
b = MapData()
a.zones["x"] = 1
print(b.zones)  # {"x": 1}  ← bug! b también lo tiene

# ✅ BIEN — cada instancia crea su propio dict
@dataclass
class MapData:
    zones: Dict = field(default_factory=dict)  # dict() se llama CADA vez que se crea un MapData
```

### 2.4 FlyInParser — la clase

```python
class FlyInParser:
    def __init__(self) -> None:
        self._meta_re: re.Pattern[str] = re.compile(r"\[(.*?)\]")
```

`re.compile()` convierte el patrón en un objeto optimizado que Python puede reutilizar
sin recompilar. Si el parse procesase 10.000 líneas, recompilar la regex en cada línea
sería un coste innecesario.

**La regex `r"\[(.*?)\]"`:**

| Parte | Significado |
|-------|-------------|
| `\[` | corchete literal `[` (escapado porque `[` tiene significado especial en regex) |
| `(.*?)` | captura cualquier cosa (`.`) cero o más veces (`*`), non-greedy (`?`) |
| `\]` | corchete literal `]` |

Non-greedy (`?`) significa que captura lo **mínimo** posible:
- Con `[color=red][max=2]`: greedy capturaría `color=red][max=2`, non-greedy capturaría solo `color=red`.

### 2.5 _split_meta — separar los corchetes

```python
def _split_meta(self, line: str) -> tuple[str, str]:
    match = self._meta_re.search(line)
    if match:
        meta_str  = match.group(1)                       # contenido sin corchetes
        clean_line = self._meta_re.sub("", line).strip() # línea sin el bloque [...]
        return meta_str, clean_line
    return "", line
```

**Ejemplo paso a paso:**

```
Entrada:  "hub: gate1 1 0 [color=red max_drones=2]"

search()  → encuentra "[color=red max_drones=2]" en la línea
group(1)  → "color=red max_drones=2"   (el contenido dentro)
sub()     → "hub: gate1 1 0 "          (elimina "[color=red max_drones=2]")
strip()   → "hub: gate1 1 0"           (quita el espacio final)

Salida: ("color=red max_drones=2", "hub: gate1 1 0")
```

### 2.6 _parse_meta — convertir texto en dict

```python
def _parse_meta(self, meta_str: str, line_num: int) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if not meta_str:
        return meta
    for token in meta_str.split():
        key, value = token.split("=", 1)
        ...
        meta[key] = value
    return meta
```

**Ejemplo paso a paso:**

```
meta_str = "color=red max_drones=2"

split()   → ["color=red", "max_drones=2"]

Token 1: "color=red"
    split("=", 1)  → ["color", "red"]
    "=" not in "red"  → OK
    "color" in VALID_META_KEYS  → OK
    meta["color"] = "red"

Token 2: "max_drones=2"
    split("=", 1)  → ["max_drones", "2"]
    meta["max_drones"] = "2"

Resultado: {"color": "red", "max_drones": "2"}
```

**Por qué `split("=", 1)` y no `split("=")`:**

`split("=")` sin límite: `"a=b=c"` → `["a", "b", "c"]` → desempaquetado `key, value` da error.
`split("=", 1)` con límite 1: `"a=b=c"` → `["a", "b=c"]` → `key="a"`, `value="b=c"`.
Luego chequeamos que `value` no contenga `=` para detectar el error del usuario.

**Por qué comprobamos `"=" in value`:**

Si el usuario escribe `[color=blue=max_drones=2]` (olvidó el espacio), obtenemos:
- token = `"color=blue=max_drones=2"`
- key = `"color"`, value = `"blue=max_drones=2"` (contiene `=`)

Sin la comprobación, guardamos `color="blue=max_drones=2"` y perdemos `max_drones` silenciosamente.
Con la comprobación, paramos y avisamos al usuario.

### 2.7 _read_nb_drones y el orden inicial

```python
raw = line.split(":", 1)[1].strip()
if not raw.isdigit() or int(raw) <= 0:
    self._error(line_num, f"nb_drones debe ser entero positivo, recibido: '{raw}'")
map_data.nb_drones = int(raw)
```

**Por qué `isdigit()` y `int(raw) <= 0`:**
- `"5".isdigit()` → `True`
- `"-5".isdigit()` → `False` (rechaza negativos)
- `"5.0".isdigit()` → `False` (rechaza floats)
- `"".isdigit()` → `False` (rechaza vacío)

**Garantía de orden del subject (§VII.4):**
El subject exige que `nb_drones` sea la primera línea de datos del archivo. En `parse_file()`,
se usa la variable `first_data_seen = False`. Si aparece cualquier zona o conexión antes de haber
procesado `nb_drones:`, el parser se detiene inmediatamente con error descriptivo:
`"nb_drones debe aparecer antes de las zonas"` o `"nb_drones debe aparecer antes de las conexiones"`.

### 2.8 _read_zone — validaciones y capacidad especial

```python
keyword, rest = line.split(":", 1)   # "hub: gate1 1 0" → keyword="hub", rest=" gate1 1 0"
parts = rest.strip().split()         # ["gate1", "1", "0"]
name = parts[0]                      # "gate1"
x, y = int(parts[1]), int(parts[2]) # 1, 0
```

`_read_zone` aplica una batería rigurosa de validaciones antes de instanciar `Zone`:

1. **Estructura mínima:** Comprueba `len(parts) >= 3` para asegurar `<nombre> <x> <y>`.
2. **Sin guiones en el nombre:** `if "-" in name: self._error(...)`.
   El subject prohíbe guiones en nombres de zona porque `-` es el separador de conexiones (`connection: A-B`).
3. **Coordenadas enteras:** `parts[1].lstrip("-").isdigit()` permite enteros negativos y positivos pero rechaza decimales y caracteres inválidos.
4. **Nombres únicos:** `if name in map_data.zones` evita zonas duplicadas.
5. **Tipo de zona válido:** Comprueba `zone_type in VALID_ZONE_TYPES` (`normal`, `blocked`, `restricted`, `priority`).
6. **Hubs no bloqueados:** `start_hub` y `end_hub` no pueden ser de tipo `blocked`.
7. **Único start y end:** Solo puede definirse exactamente un `start_hub` y un `end_hub`.
8. **Regla de capacidad especial del subject v1.6 (§VII.4):**
   > *"The max_drones capacity is ignored on the start_hub and end_hub zones: these have no capacity limit... If such metadata is present on those two zones, it is ignored and is not a validation error."*

   Por ello, en `start_hub` y `end_hub` se asigna directamente `raw_max: int = 9999` (sin límite práctico),
   mientras que en zonas regulares (`hub:`) se exige que `max_drones` sea un entero estrictamente positivo (`> 0`).

```python
zone = Zone(
    name=name,
    x=x,
    y=y,
    zone_type=zone_type,
    max_drones=raw_max,
    color=meta.get("color", "none"),
)
map_data.zones[name] = zone
```

### 2.9 _read_connection y max_link_capacity

```python
conn_str = line.split(":", 1)[1].strip()  # "gate1-gate2"
parts = conn_str.split("-", 1)            # ["gate1", "gate2"]
src, dst = parts[0].strip(), parts[1].strip()
```

1. **Separación con `split("-", 1)`:** Divide exactamente en dos extremos `src` y `dst`.
2. **Capacidad de conexión (`max_link_capacity`):**
   Se extrae de los metadatos `meta.get("max_link_capacity", "1")` y se valida que sea un entero positivo (`int(raw_cap) > 0`).
3. **Detección de enlaces duplicados y bidireccionales:**
   El subject establece que `A-B` y `B-A` representan el mismo enlace bidireccional:

```python
for existing in map_data.connections:
    if {existing.source, existing.target} == {src, dst}:
        self._error(line_num, f"conexión duplicada: '{src}-{dst}'")

map_data.connections.append(Connection(src, dst, int(raw_cap)))
```

`{A, B} == {B, A}` evalúa a `True` independientemente del orden, evitando enlaces redundantes.

### 2.10 _validate — comprobaciones finales

Estas validaciones no se pueden hacer durante el parsing línea a línea porque
requieren tener el mapa **completo**:

- `nb_drones > 0` — podría haberse puesto `nb_drones: 0`
- `start_hub != None` — podría faltar la línea `start_hub:`
- `end_hub != None` — ídem
- `start_hub != end_hub` — un mapa donde start y end son la misma zona no tiene sentido
- Conexiones referencian zonas existentes — una conexión puede aparecer antes de que la zona esté definida en el archivo, así que lo verificamos al final

### 2.11 _error y NoReturn

```python
@staticmethod
def _error(line_num: int, msg: str) -> NoReturn:
    raise ValueError(f"[Línea {line_num}] Error: {msg}")
```

`NoReturn` es un tipo especial de mypy que significa *"esta función nunca devuelve"*.
Sin él, mypy podría avisar de variables "posiblemente no asignadas":

```python
# Sin NoReturn, mypy no sabe que _error() lanza excepción
if not raw.isdigit():
    self._error(...)
value = int(raw)   # mypy avisa: 'raw' podría no ser un número válido aquí
                   # (aunque sabemos que _error() habría parado el programa)

# Con NoReturn, mypy sabe que si _error() se llamó, la línea siguiente nunca se ejecuta
# → no genera warnings falsos
```

---

## 3. graph.py

### 3.1 Lista de adyacencia vs matriz

Hay dos formas de representar un grafo:

**Matriz de adyacencia** — una tabla N×N donde `tabla[A][B] = 1` si hay conexión:

```
         start  wp1  wp2  goal
start  [   0     1    0    0  ]
wp1    [   1     0    1    0  ]
wp2    [   0     1    0    1  ]
goal   [   0     0    1    0  ]
```

Problema: con 100 zonas → tabla de 10.000 celdas, la mayoría a 0 (grafos escasos).

**Lista de adyacencia** — para cada zona, solo guardamos sus vecinas reales:

```python
_adj = {
    "start":     [Connection("start", "wp1")],
    "wp1":       [Connection("wp1", "start"), Connection("wp1", "wp2")],
    "wp2":       [Connection("wp2", "wp1"), Connection("wp2", "goal")],
    "goal":      [Connection("goal", "wp2")],
}
```

Solo ocupamos espacio para conexiones que existen. Para el mapa lineal del subject
con 4 zonas y 3 conexiones: 6 entradas en la lista vs 16 celdas en la matriz.

### 3.2 _build_adj — construir el grafo

En `Graph.__init__`, la lista de adyacencia se inicializa primero para **todas** las zonas con listas vacías:

```python
self._adj: Dict[str, List[Connection]] = {
    name: [] for name in self.zones
}
```

Esto garantiza que cualquier consulta a `_adj[zone_name]` sea segura y nunca lance `KeyError`,
incluso para zonas aisladas o sin conexiones.

A continuación, `_build_adj` rellena las conexiones en ambos sentidos:

```python
def _build_adj(self, connections: List[Connection]) -> None:
    for conn in connections:
        self._adj[conn.source].append(conn)         # A → B
        reverse = Connection(
            source=conn.target,
            target=conn.source,
            max_link_capacity=conn.max_link_capacity,
        )
        self._adj[conn.target].append(reverse)      # B → A
```

**Ejemplo con el mapa lineal:**

```
El parser devuelve:
    connections = [
        Connection("start", "waypoint1", 1),
        Connection("waypoint1", "waypoint2", 1),
        Connection("waypoint2", "goal", 1),
    ]

Después de _build_adj:
    _adj = {
        "start":     [Connection("start", "waypoint1", 1)],
        "waypoint1": [Connection("waypoint1", "start", 1),     # reverse
                      Connection("waypoint1", "waypoint2", 1)],
        "waypoint2": [Connection("waypoint2", "waypoint1", 1), # reverse
                      Connection("waypoint2", "goal", 1)],
        "goal":      [Connection("goal", "waypoint2", 1)],     # reverse
    }
```

Guardamos objetos `Connection` completos (no solo el nombre del vecino) porque
el simulador necesita `max_link_capacity` para saber cuántos drones pueden cruzar
el enlace simultáneamente.

### 3.3 neighbors, connections_from, entry_cost y turns_to_enter

#### `neighbors` — Zonas accesibles
Recorre las conexiones salientes de una zona, busca los objetos `Zone` destino y
devuelve solo aquellos que no son de tipo `blocked`:

```python
def neighbors(self, zone_name: str) -> List[Zone]:
    result: List[Zone] = []
    for conn in self._adj.get(zone_name, []):
        neighbor = self.zones.get(conn.target)
        if neighbor and neighbor.zone_type != ZONE_BLOCKED:
            result.append(neighbor)
    return result
```

Filtramos `blocked` aquí, en el nivel más bajo posible. Así BFS, Dijkstra y DFS
nunca exploran zonas bloqueadas — no necesitan comprobarlo manualmente.

#### `connections_from` — Conexiones completas
A diferencia de `neighbors()`, devuelve los objetos `Connection` con su capacidad:

```python
def connections_from(self, zone_name: str) -> List[Connection]:
    return self._adj.get(zone_name, [])
```

Es el método que consulta el simulador para saber si hay capacidad disponible en el enlace (`max_link_capacity`).

#### `entry_cost` — Coste ponderado para pathfinding
El coste en turnos de entrar a una zona depende exclusivamente del `zone_type` del **destino**:

```python
def entry_cost(self, zone_name: str) -> float:
    zone = self.zones.get(zone_name)
    if zone is None:
        raise ValueError(f"Zona desconocida: {zone_name}")
    elif zone.zone_type == ZONE_RESTRICTED:
        return 2.0
    elif zone.zone_type == ZONE_PRIORITY:
        return 0.9   # Menor que 1.0 → Dijkstra la prefiere en empates
    else:
        return 1.0
```

**Por qué `priority = 0.9` y no `1.0`:**
El subject §VII.1 indica que las zonas prioritarias deben tener preferencia en el pathfinding.
Si tuvieran coste 1.0, Dijkstra las trataría exactamente igual que a las normales. Con 0.9, ante dos rutas
de igual longitud, la que atraviesa zonas `priority` acumula menor coste y Dijkstra la selecciona en primer lugar.

#### `turns_to_enter` — Turnos enteros para el simulador
Convierte el coste flotante en turnos discretos con `math.ceil`:

```python
def turns_to_enter(self, zone_name: str) -> int:
    return math.ceil(self.entry_cost(zone_name))
```

Devuelve `1` para zonas `normal` o `priority`, y `2` para zonas `restricted`.

### 3.4 BFS — búsqueda en anchura

**Idea:** explorar el grafo en "capas". Primero todos los vecinos directos,
luego los vecinos de los vecinos, etc. El primero que llega al destino
es el camino con menos saltos.

El método devuelve `Optional[List[str]]`: devuelve la lista de nombres de zonas si existe camino,
o `None` si `start` y `end` no están conectados.

```
Estado inicial:  cola = [ [start] ],  visitados = {start}

Turno 1: saco [start]
  vecinos de start: waypoint1
  cola = [ [start, wp1] ],  visitados = {start, wp1}

Turno 2: saco [start, wp1]
  vecinos de wp1: start (visitado, skip), wp2
  cola = [ [start, wp1, wp2] ],  visitados = {start, wp1, wp2}

Turno 3: saco [start, wp1, wp2]
  vecinos de wp2: wp1 (visitado, skip), goal
  cola = [ [start, wp1, wp2, goal] ]

Turno 4: saco [start, wp1, wp2, goal]
  current == end → devolvemos [start, wp1, wp2, goal]
```

**Por qué `deque` y no `list`:**

`deque.popleft()` es O(1). `list.pop(0)` es O(n) porque Python desplaza todos
los elementos una posición a la izquierda. Para un mapa grande con cientos de
nodos en cola, la diferencia es significativa.

**Por qué guardamos el camino completo en la cola:**

```python
queue: deque[List[str]] = deque([[start]])
```

Alternativa más eficiente en memoria: guardar solo `(zona_actual, zona_padre)`
y reconstruir el camino al final. Pero para este proyecto, el número de zonas
es pequeño y guardar el camino completo hace el código más legible.

### 3.5 Dijkstra — camino de menor coste

**Diferencia clave con BFS:**
BFS trata todos los pasos igual (coste 1). Dijkstra usa un coste variable por paso
(ponderando `priority` a 0.9 y `restricted` a 2.0) y siempre procesa el nodo de menor coste acumulado.

Devuelve `Optional[Tuple[float, List[str]]]`: una tupla `(coste_total, [ruta])` o `None` si no hay camino.

```
Estado inicial: heap = [(0.0, "start", ["start"])]
                best  = {"start": 0.0}

Paso 1: saco (0.0, "start")
  vecinos: waypoint1 (normal, coste=1.0)
  nuevo coste = 0.0 + 1.0 = 1.0
  best["waypoint1"] = 1.0
  heap = [(1.0, "waypoint1", ["start", "wp1"])]

Paso 2: saco (1.0, "waypoint1")
  vecinos: start (coste 1.0 + 1.0 = 2.0, peor que best[start]=0.0, skip)
           waypoint2 (coste 1.0 + 1.0 = 2.0)
  best["waypoint2"] = 2.0
  heap = [(2.0, "waypoint2", ["start", "wp1", "wp2"])]

Paso 3: saco (2.0, "waypoint2")
  vecinos: wp1 (skip), goal (coste 2.0 + 1.0 = 3.0)
  best["goal"] = 3.0
  heap = [(3.0, "goal", ["start", "wp1", "wp2", "goal"])]

Paso 4: saco (3.0, "goal")
  current == end → devolvemos (3.0, ["start", "wp1", "wp2", "goal"])
```

**¿Por qué hay duplicados en el heap y cómo los eliminamos?**

```python
if cost > best.get(current, float("inf")):
    continue
```

Cuando encontramos una ruta más barata a una zona, añadimos la nueva tupla al heap
pero NO eliminamos la antigua (heapq no tiene operación de actualización eficiente).
Cuando sacamos la tupla antigua, `cost > best[current]` será True y la saltamos.

### 3.6 find_all_paths — múltiples rutas

**Por qué necesitamos varias rutas:**
Con `max_drones=1` (por defecto), dos drones no pueden estar en la misma zona
al mismo tiempo. Si mandamos 8 drones por la misma ruta, se bloquean en cadena.
El simulador necesita rutas alternativas para distribuirlos en round-robin y evitar deadlocks.

**DFS iterativo con pila y límite `max_paths`:**

```python
results: List[Tuple[float, List[str]]] = []
stack: List[Tuple[str, List[str], float]] = [(start, [start], 0.0)]

while stack and len(results) < max_paths:
    current, path, cost = stack.pop()    # Sacamos el último (DFS)

    if current == end:
        results.append((cost, path))     # Guardamos la ruta encontrada
        continue                         # No exploramos más allá del destino

    for neighbor in self.neighbors(current):
        if neighbor.name not in path:    # Evitar ciclos
            step = self.entry_cost(neighbor.name)
            stack.append((neighbor.name, path + [neighbor.name], cost + step))

results.sort(key=lambda t: t[0])         # Ordenar por coste ascendente
return results
```

**BFS vs DFS para encontrar rutas:**

| | BFS | DFS |
|---|---|---|
| Estructura | Cola (deque) | Pila (list) |
| Primera ruta encontrada | La más corta | Cualquiera |
| Para múltiples rutas | Menos natural | Más natural |
| Uso en este proyecto | `bfs()` | `find_all_paths()` |

En `find_all_paths`, se ordenan al final por coste flotante (`results.sort(key=lambda t: t[0])`),
garantizando que la primera ruta sea siempre la más óptima y las siguientes alternativas viables.

---

## 4. Errores comunes y por qué los detectamos

| Error en el archivo | Qué hace el parser | Por qué |
|---|---|---|
| `[color=red=blue]` | Error: valor `red=blue` contiene `=` | `"=" in value` tras `split("=", 1)` |
| `[color=blue=max_drones=2]` | Error: valor contiene `=` | Falta un espacio entre metadatos |
| `[foo=bar]` | Error: clave desconocida `foo` | `key not in VALID_META_KEYS` |
| Hub antes de `nb_drones:` | Error: `nb_drones` debe aparecer antes de las zonas | `first_data_seen == False` |
| `nb_drones: -5` o `0` | Error: `nb_drones` debe ser entero positivo | `not raw.isdigit() or int(raw) <= 0` |
| `hub: gate-1 0 0` | Error: nombre no puede contener `-` | `"-" in name` (reservado como separador) |
| `hub: gate1 1.5 0` | Error: coordenadas deben ser enteros | `not parts[1].lstrip("-").isdigit()` |
| `hub: gate1 0 0` repetido | Error: zona duplicada | `name in map_data.zones` |
| `[zone=invalid]` | Error: tipo inválido `invalid` | `zone_type not in VALID_ZONE_TYPES` |
| `start_hub: hub 0 0 [zone=blocked]` | Error: `start_hub` no puede ser de tipo `blocked` | Start y end deben ser accesibles |
| Segundo `start_hub:` o `end_hub:` | Error: solo puede haber un start_hub / end_hub | `map_data.start_hub is not None` |
| `hub: ... [max_drones=0]` | Error: `max_drones` debe ser entero positivo | En hubs regulares `int(raw_max) <= 0` |
| `connection: a-b [max_link_capacity=0]` | Error: `max_link_capacity` debe ser entero positivo | `int(raw_cap) <= 0` |
| `connection: a-b` y `b-a` repetidos | Error: conexión duplicada | `{src, dst} == {existing.src, existing.dst}` |
| Falta `start_hub:` o `end_hub:` | Error en `_validate`: Falta start_hub / end_hub | El grafo no tendría origen o destino |
| `start_hub == end_hub` | Error en `_validate`: no pueden ser la misma zona | Recorrido trivial o sin sentido |
| Conexión con zona no definida | Error en `_validate`: zona no definida | La arista apunta a un vértice inexistente |
