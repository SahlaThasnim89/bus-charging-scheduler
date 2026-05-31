from dataclasses import dataclass, field
from typing import List, Optional

# INPUT MODELS

@dataclass
class Segment:
    from_stop: str
    to_stop: str
    distance_km: float


@dataclass
class Route:
    stops: List[str]
    segments: List[Segment]
    speed_kmh: float

    def distance_between(self, from_stop: str, to_stop: str) -> float:
        stops = self.stops
        i = stops.index(from_stop)
        j = stops.index(to_stop)
        if i > j:
            i, j = j, i
        total = 0.0
        for seg in self.segments:
            if stops.index(seg.from_stop) >= i and stops.index(seg.to_stop) <= j:
                total += seg.distance_km
        return total
 
    def travel_time_min(self, from_stop: str, to_stop: str) -> float:
        dist = self.distance_between(from_stop, to_stop)
        return (dist / self.speed_kmh) * 60


@dataclass
class Station:
    id: str
    chargers: int = 1


@dataclass
class Physics:
    battery_range_km: float     # max km on a full charge (240)
    charge_time_min: float      # how long a charge takes (25 min)
    charge_to_km: float         # what "full" means in km (240)
                                # could be partial charge in the future


@dataclass
class Weights:
    individual: float = 1.0
    operator: float = 1.0
    overall: float = 1.0


@dataclass
class Bus:
    id: str
    operator: str
    direction: str          # "BK" or "KB"
    departure_min: float    # minutes from midnight
    origin: str        # e.g. "Bengaluru" or "Kochi" — loaded from YAML
    destination: str   # e.g. "Kochi" or "Bengaluru" — loaded from YAML


@dataclass
class Scenario:
    id: int
    name: str
    description: str
    route: Route
    stations: List[Station]
    physics: Physics
    weights: Weights
    buses: List[Bus]


# OUTPUT MODELS 

@dataclass
class ChargeEvent:
    station_id: str
    arrive_min: float
    wait_min: float
    charge_start_min: float
    depart_min: float


@dataclass
class StationEvent:
    bus_id: str
    operator: str
    charge_event: ChargeEvent


@dataclass
class BusTimeline:
    bus_id: str
    operator: str
    direction: str
    departure_min: float
    charge_events: List[ChargeEvent] = field(default_factory=list)
    arrival_min: float = 0.0        # when it reached its destination
    
    @property
    def total_wait_min(self) -> float:
        return sum(e.wait_min for e in self.charge_events)
 
    @property
    def total_trip_min(self) -> float:
        return self.arrival_min - self.departure_min


@dataclass
class StationLog:
    station_id: str
    events: List[StationEvent] = field(default_factory=list)


@dataclass
class ScheduleResult:    
    scenario_id: int
    bus_timelines: List[BusTimeline] = field(default_factory=list)
    station_logs: List[StationLog] = field(default_factory=list)