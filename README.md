# Bus Charging Scheduler

A scheduling system for electric buses charging along the Bengaluru → Kochi route.
Built with Python and Streamlit.

## What it does

- Reads a scenario (buses, route, stations, weights) from a YAML file
- Decides which charging stations each bus uses
- Decides the order buses charge at each station using a weighted priority score
- Shows a per-bus timetable and per-station charging order

---

## Running Locally

### Prerequisites
- Python 3.8 or higher
- pip

### Steps

**1. Clone the repo**
```bash
git clone https://github.com/SahlaThasnim89/bus-charging-scheduler.git
cd bus-charging-scheduler
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Run the app**
```bash
streamlit run app.py
```

The app opens automatically at `http://localhost:8501`

---

## Project Structure

```
bus-charging-scheduler/
├── app.py                    # Streamlit UI
├── requirements.txt          # Python dependencies
├── README.md
├── ARCHITECTURE.md           # Design decisions and future changes
├── scheduler/
│   ├── __init__.py
│   ├── models.py             # Data structures (Bus, Route, Station, etc.)
│   ├── loader.py             # Reads YAML files into typed objects
│   ├── rules.py              # Scoring functions for scheduling priority
│   └── engine.py            # Core event-driven simulation
└── scenarios/
    ├── scenario_01.yaml      # Even spacing — baseline
    ├── scenario_02.yaml      # Bunched start — heavy early contention
    ├── scenario_03.yaml      # Asymmetric load — uneven traffic
    ├── scenario_04.yaml      # Operator heavy — KPN dominates, operator weight 2.0
    └── scenario_05.yaml      # Worst case — maximum contention
```

---

## How to Change a Weight

Weights are in the scenario YAML file. Open the relevant scenario and edit
the `weights` section:

```yaml
# scenarios/scenario_04.yaml
weights:
  individual: 1.0   # how much to prioritize buses that have waited longest
  operator: 2.0     # how much to prioritize operators whose fleet is behind
  overall: 1.0      # how much to prioritize buses closest to empty battery
```

Change any number and re-run the app. No code changes needed anywhere.

**What each weight does:**
- `individual` — higher value = scheduler strongly avoids letting any single bus wait too long
- `operator` — higher value = scheduler strongly avoids letting any one operator's fleet fall behind
- `overall` — higher value = scheduler strongly prioritizes buses closest to running out of battery

---

## How to Add a New Rule

Example: **priority buses always jump the queue**

### Step 1 — Add scoring function to `scheduler/rules.py`

```python
def priority_bus_score(bus: Bus) -> float:
    """Priority buses get a very high score — always jump the queue."""
    return 1000.0 if bus.is_priority else 0.0
```

### Step 2 — Add one line to `priority_score()` in `scheduler/rules.py`

```python
score = (
    weights.individual * individual_score(...) +
    weights.operator   * operator_score(...)   +
    weights.overall    * overall_score(...)    +
    weights.priority   * priority_bus_score(bus)  # ← new line
)
```

### Step 3 — Add field to `Weights` in `scheduler/models.py`

```python
@dataclass
class Weights:
    individual: float = 1.0
    operator:   float = 1.0
    overall:    float = 1.0
    priority:   float = 1.0   # ← new line
```

### Step 4 — Add field to `Bus` in `scheduler/models.py`

```python
@dataclass
class Bus:
    ...
    is_priority: bool = False   # ← new line
```

### Step 5 — Update `scheduler/loader.py`

```python
buses.append(Bus(
    ...
    is_priority=b.get("is_priority", False)  # ← new line
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
    is_priority: true   # ← new line
```

`engine.py` is never touched. Existing scenarios are unaffected.

---

## How to Add a New Scenario

1. Create a new YAML file in `scenarios/` following the same structure
2. Add it to `SCENARIO_FILES` in `app.py`:

```python
SCENARIO_FILES = {
    ...
    "Scenario 6 — Your New Scenario": "scenarios/scenario_06.yaml",
}
```

That's it.

---

## How to Add a New Station

Open the relevant scenario YAML and add the station in two places:

```yaml
route:
  stops: ["Bengaluru", "A", "B", "E", "C", "D", "Kochi"]  # add "E"
  segments:
    - from: B
      to: E
      distance_km: 60    # new segment
    - from: E
      to: C
      distance_km: 40    # updated segment

stations:
  - id: E
    chargers: 1          # new station
```

No code changes needed.

---

## The 5 Scenarios

| Scenario | Description | Key feature |
|----------|-------------|-------------|
| 1 | Even Spacing | Buses every 15 min — baseline |
| 2 | Bunched Start | Tight cluster early — heavy contention |
| 3 | Asymmetric Load | 10 BK buses, only 4 KB buses |
| 4 | Operator Heavy | KPN has 8/10 BK buses, operator weight = 2.0 |
| 5 | Worst Case | All 20 buses in 72 min window — max contention |

---

## Tech Stack

- **Python 3.8+**
- **Streamlit** — UI
- **PyYAML** — scenario file parsing
- **Pandas** — table display
- **heapq** — priority queue for event processing (built-in)
- **dataclasses** — typed data models (built-in)
