import yaml
from scheduler.models import (
    Segment, Route, Station, Physics, Weights, Bus, Scenario
)


def parse_time(time_str: str) -> float:
    hours, minutes = time_str.strip().split(":")
    return float(hours) * 60 + float(minutes)


def minutes_to_hhmm(minutes: float) -> str:
    total_minutes = int(minutes) % (24 * 60)   # wrap around midnight
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h:02d}:{m:02d}"


def load_scenario(filepath: str) -> Scenario:
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    # --- Route ---
    # Build Segment objects from the segments list in YAML
    segments = [
        Segment(
            from_stop=seg["from"],
            to_stop=seg["to"],
            distance_km=float(seg["distance_km"])
        )
        for seg in data["route"]["segments"]
    ]
 
    route = Route(
        stops=data["route"]["stops"],
        segments=segments,
        speed_kmh=float(data["route"]["speed_kmh"])
    )

    # --- Stations ---
    # chargers defaults to 1 if not specified in YAML
    stations = [
        Station(
            id=s["id"],
            chargers=int(s.get("chargers", 1))
        )
        for s in data["stations"]
    ]
 
    # --- Physics ---
    physics = Physics(
        battery_range_km=float(data["physics"]["battery_range_km"]),
        charge_time_min=float(data["physics"]["charge_time_min"]),
        charge_to_km=float(data["physics"]["charge_to_km"])
    )
 
    # --- Weights ---
    # All weights default to 1.0 if not specified in YAML
    w = data.get("weights", {})
    weights = Weights(
        individual=float(w.get("individual", 1.0)),
        operator=float(w.get("operator", 1.0)),
        overall=float(w.get("overall", 1.0))
    )

    # --- Buses ---
    buses = []
    for b in data["buses"]:
        buses.append(Bus(
            id=b["id"],
            operator=b["operator"],
            direction = b["direction"],
            departure_min=parse_time(b["departure"]),
            origin=b["origin"],             # e.g. "Bengaluru"
            destination=b["destination"]    # e.g. "Kochi"
        ))
 
    return Scenario(
        id=data["meta"]["id"],
        name=data["meta"]["name"],
        description=data["meta"]["description"],
        route=route,
        stations=stations,
        physics=physics,
        weights=weights,
        buses=buses
    )