# ARCHITECTURE.md — Bus Charging Scheduler

## Table of Contents
1. [Scheduling Approach](#scheduling-approach)
2. [Data Structure Design](#data-structure-design)
3. [Anticipated Future Changes](#anticipated-future-changes)
4. [How to Change a Weight](#how-to-change-a-weight)
5. [How to Add a New Rule](#how-to-add-a-new-rule)
6. [Assumptions Made](#assumptions-made)

---

## Scheduling Approach

### What I chose: Event-Driven Simulation with Weighted Priority Scoring

The scheduler runs a discrete-event simulation using a priority queue
(`heapq`). Time moves forward by processing events in chronological order.
When multiple buses compete for the same charger, a weighted scoring
function decides who goes first.

### How it works

Every bus generates a sequence of events:

```
depart → arrive_station → charging_done → arrive_station → charging_done → arrive_dest
```

These events are pushed into a min-heap ordered by time. The engine always
processes the earliest event next. When a bus arrives at a busy station, it
joins a per-station queue ranked by priority score. When a charger frees up,
the highest-scoring bus in the queue gets it.

### Why not other approaches?

**Pure FCFS (First Come First Served)**
- Ignores weights entirely
- Cannot implement operator fairness or range urgency
- Not tunable — operations team has no control

**ILP / OR-Tools (Integer Linear Programming)**
- Overkill for this problem size
- Adding a new rule requires reformulating the entire mathematical model
- Results are non-transparent — hard to explain why a specific bus got priority
- Weights are embedded in the objective function, not in one obvious place

**Genetic / Simulated Annealing**
- Non-deterministic — same input can produce different outputs
- Hard to defend specific decisions in an operational context
- Slow to converge for small problems

**Event-driven simulation wins because:**
- Every scheduling decision is traceable and explainable
- New rules slot in as isolated scoring functions — engine untouched
- Weights live in one obvious place (YAML) — trivial to tune
- Scales naturally: more buses, stations, routes = same engine, more events
- Maps directly to how the real world works

---

## Data Structure Design

### One YAML file = one complete world

Each scenario is a fully self-contained YAML file. It carries everything
the scheduler needs: route, stations, physics, weights, and buses.

```
scenarios/
├── scenario_01.yaml   ← complete world
├── scenario_02.yaml   ← complete world
├── scenario_03.yaml   ← complete world
├── scenario_04.yaml   ← complete world
└── scenario_05.yaml   ← complete world
```

### Why self-contained and not a shared base file?

A shared base file creates hidden dependencies between scenarios.
If the interview says "double chargers at B for scenario 4", you edit
scenario_04.yaml only — no risk of affecting other scenarios.

With a shared base, that same change would ripple through all scenarios
or require complex override logic.

### YAML structure

```yaml
meta:
  id: 1
  name: "Scenario 1 — Even Spacing"
  description: "Baseline case"

route:
  stops: ["Bengaluru", "A", "B", "C", "D", "Kochi"]
  speed_kmh: 60
  segments:
    - from: Bengaluru
      to: A
      distance_km: 100

stations:
  - id: A
    chargers: 1        # supports multiple chargers per station

physics:
  battery_range_km: 240
  charge_time_min: 25
  charge_to_km: 240    # supports partial charging in future

weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0

buses:
  - id: bus-BK-01
    operator: kpn
    direction: BK
    origin: Bengaluru
    destination: Kochi
    departure: "19:00"
```

### Key design decisions

**`chargers: int` on Station**
Supports multiple chargers per station without any code change.
Change YAML only.

**`speed_kmh` on Route**
Different scenarios can run at different speeds.
Change YAML only.

**`charge_to_km` on Physics**
Supports partial charging in future (e.g. charge to 80% only).
Field already exists — just needs a rule to use it.

**`origin` and `destination` on Bus (not derived from direction)**
Direction (`BK`/`KB`) is just a display label.
Origin and destination are explicit city names from YAML.
Adding Mumbai→Goa route needs zero code changes.

**Times stored as float minutes from midnight**
`"19:00"` → `1140.0`. Arithmetic is simple addition.
No datetime objects, no timezone complexity anywhere.

**Soft rules as isolated functions in rules.py**
Each rule knows nothing about the others.
Adding a rule = one new function + one line in priority_score().
Engine never changes.

---

## Anticipated Future Changes

This table lists every change I anticipated when designing the data
structure, and how the design handles it without code changes.

| Change | How the design handles it |
|--------|--------------------------|
| Add a new charging station | Add segment + station entry to YAML. Route.distance_between() works for any stops. Zero code changes. |
| Remove a charging station | Remove from YAML. Zero code changes. |
| Double chargers at a station | Change `chargers: 1` to `chargers: 2` in YAML. Engine reads `station.chargers` dynamically. Zero code changes. |
| Change segment distance | Edit `distance_km` in YAML. Zero code changes. |
| Change bus speed | Edit `speed_kmh` in YAML. Zero code changes. |
| Add a new operator | Add buses with new operator name in YAML. Operator score computes dynamically for any operator name. Zero code changes. |
| Add a new route (Mumbai→Goa) | New scenario YAML with different stops and segments. Origin/destination are explicit strings not hardcoded. Zero code changes. |
| Change battery range | Edit `battery_range_km` in YAML. Zero code changes. |
| Change charging time | Edit `charge_time_min` in YAML. Zero code changes. |
| Partial charging (charge to 80%) | `charge_to_km` field already exists in Physics. Add one rule to use it. |
| Priority buses jump the queue | Add `is_priority` field to Bus in YAML + one scoring function in rules.py. Engine untouched. |
| Time-of-day electricity costs | Add `cost_schedule` to Station in YAML. Add one scoring function. |
| Driver shift limits | Add `shift_end_min` to Bus in YAML. Add one hard constraint. |
| Multiple routes sharing stations | Stations are identified by id only — independent of route. A station can appear in multiple route YAMLs. |
| More buses per scenario | Add more entries to `buses` list in YAML. Engine scales linearly. |
| New soft rule (any) | One function in rules.py + one line in priority_score(). Engine untouched. |
| New hard rule (any) | One validation function called before/after simulation. Engine untouched. |
| Tune weights per scenario | Edit weight values in that scenario's YAML only. |
| Add a new weight dimension | Add field to Weights dataclass + one line in priority_score(). |

---

## How to Change a Weight

All weights live in the scenario YAML file under the `weights` key.

**Example: double the operator weight for scenario 4**

```yaml
# scenarios/scenario_04.yaml
weights:
  individual: 1.0
  operator: 2.0    # changed from 1.0 to 2.0
  overall: 1.0
```

That is the only change needed. No code changes anywhere.

The engine reads weights from the Scenario object which is loaded
from the YAML. The priority_score() function in rules.py uses
`weights.operator` directly — so changing the YAML value changes
the scheduler's behavior automatically.

---

## How to Add a New Rule

**Example: priority buses always jump the queue**

### Step 1 — Add scoring function to `rules.py`

```python
def priority_bus_score(bus: Bus) -> float:
    """Priority buses get a very high score — always jump the queue."""
    return 1000.0 if bus.is_priority else 0.0
```

### Step 2 — Add one line to `priority_score()` in `rules.py`

```python
score = (
    weights.individual * individual_score(...) +
    weights.operator   * operator_score(...)   +
    weights.overall    * overall_score(...)    +
    weights.priority   * priority_bus_score(bus)  # ← add this line
)
```

### Step 3 — Add field to `Weights` in `models.py`

```python
@dataclass
class Weights:
    individual: float = 1.0
    operator:   float = 1.0
    overall:    float = 1.0
    priority:   float = 1.0   # ← add this line
```

### Step 4 — Add field to `Bus` in `models.py`

```python
@dataclass
class Bus:
    id: str
    operator: str
    direction: str
    departure_min: float
    origin: str
    destination: str
    is_priority: bool = False   # ← add this line
```

### Step 5 — Update `loader.py` to read the new field

```python
buses.append(Bus(
    ...
    is_priority=b.get("is_priority", False)  # ← add this line
))
```

### Step 6 — Mark priority buses in YAML

```yaml
buses:
  - id: bus-BK-01
    operator: kpn
    origin: Bengaluru
    destination: Kochi
    departure: "19:00"
    is_priority: true    # ← add this line
```

**engine.py is never touched.**
Existing scenarios are unaffected (is_priority defaults to False).

---

## Assumptions Made

These are decisions I made where the spec was ambiguous. Each is
defensible and documented so they can be revisited.

**1. Charging plan selected at departure time**
Each bus picks its charging stations when it departs, based on
estimated wait times at each station at that moment. This is a
greedy estimate — actual waits may differ. Alternative: replan
at each station. Chose departure-time planning for simplicity
and predictability.

**2. Minimum charging stops**
A bus takes the minimum valid plan with lowest estimated wait.
It does not charge at extra stations unnecessarily. A bus going
Bengaluru→Kochi will use exactly 2 stops unless all 2-stop plans
are invalid.

**3. Overall score = km since last charge**
I interpreted "overall network efficiency" as prioritizing buses
closest to running out of battery. A stranded bus disrupts every
bus behind it — preventing that is a network-wide concern.

**4. Tiebreaking by arrival order**
When two buses have identical priority scores, the one that
arrived at the station first gets the charger. This is fair,
transparent, and matches real-world queue behavior.

**5. Speed is constant**
All buses travel at the same speed with no traffic variation,
exactly as specified. Speed is in the YAML so it can be changed
per scenario.

**6. Endpoints are not scheduling stations**
Bengaluru and Kochi have slow chargers that fully charge buses
before departure. They are not part of the scheduling problem
as specified.

**7. Times wrap around midnight**
Some buses arrive after midnight. Times are stored as float
minutes from midnight and wrap correctly for display
(e.g. 1450 min → 00:10).
```