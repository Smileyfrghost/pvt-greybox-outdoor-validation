"""Frozen one-state PV/T equation and exact-ZOH segment simulation; no fitting."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "data" / "metadata" / "frozen_greybox"
AREA_M2 = 0.55
FLOW_REF_ML_MIN = 500.0
SAMPLE_SECONDS = 60.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Boolean is not a numeric {name}")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"Invalid numeric {name}") from error
    if not math.isfinite(result):
        raise ValueError(f"Nonfinite {name}")
    return result


@dataclass(frozen=True)
class Parameters:
    C_eff: float
    alpha_eff: float
    UA_amb: float
    UA_water: float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, number(getattr(self, name), name))
        if self.C_eff <= 0 or min(self.alpha_eff, self.UA_amb, self.UA_water) < 0:
            raise ValueError("Invalid capacity or negative coupling/absorption")


def load_parameters() -> Parameters:
    manifest = json.loads((METADATA / "source_manifest.json").read_text(encoding="utf-8-sig"))
    files = manifest["public_files"]
    if {item["name"] for item in files} != {"model_contract.json", "shared_theta_frozen_v1.json"}:
        raise ValueError("Unexpected parameter/contract source map")
    for item in files:
        if digest(METADATA / item["name"]) != item["sha256"].lower():
            raise ValueError(f"Source hash changed: {item['name']}")
    contract = json.loads((METADATA / "model_contract.json").read_text(encoding="utf-8-sig"))
    expected = {"A_m2": AREA_M2, "flow_ref_mL_min": FLOW_REF_ML_MIN, "gamma_Pel": 1, "sampling_seconds": SAMPLE_SECONDS}
    if contract["constants"] != expected or contract["supported_flow_mL_min"] != [0, 500]:
        raise ValueError("Frozen constants/flow domain changed")
    saved = json.loads((METADATA / "shared_theta_frozen_v1.json").read_text(encoding="utf-8-sig"))
    return Parameters(**saved["theta"])


def heat_terms(temperature: float, inputs, parameters: Parameters) -> dict[str, float]:
    if len(inputs) != 5:
        raise ValueError("Inputs must be [G, Tamb, Ttank, Pel, flow_mL_min]")
    temperature = number(temperature, "temperature")
    G, ambient = number(inputs[0], "G"), number(inputs[1], "Tamb")
    power, flow = number(inputs[3], "Pel"), number(inputs[4], "flow")
    if flow not in (0, FLOW_REF_ML_MIN):
        raise ValueError("Frozen model supports prescribed flow 0 or 500 mL/min only")
    water = number(inputs[2], "Ttank") if flow else None
    solar = parameters.alpha_eff * AREA_M2 * G
    ambient_term = -parameters.UA_amb * (temperature - ambient)
    # OFF really removes the water term; avoid 0 * NaN for unavailable Ttank.
    water_term = -parameters.UA_water * (temperature - water) if flow else 0.0
    H = parameters.UA_amb + (parameters.UA_water if flow else 0.0)
    net = solar + ambient_term + water_term - power
    if not all(math.isfinite(value) for value in (solar, ambient_term, water_term, H, net)):
        raise FloatingPointError("Nonfinite heat balance; no clipping is applied")
    return {"solar_W": solar, "ambient_W": ambient_term, "water_W": water_term, "electrical_W": -power, "net_W": net, "H_W_K": H}


def step(temperature: float, inputs, parameters: Parameters, dt: float = SAMPLE_SECONDS) -> float:
    temperature = number(temperature, "temperature")
    dt = number(dt, "dt")
    if dt <= 0:
        raise ValueError("dt must be positive")
    terms = heat_terms(temperature, inputs, parameters)
    H = terms["H_W_K"]
    beta = -math.expm1(-H * dt / parameters.C_eff) / H if H else dt / parameters.C_eff
    result = temperature + beta * terms["net_W"]
    if not math.isfinite(result):
        raise FloatingPointError("Nonfinite state; no temperature clipping is applied")
    return result


def simulate(initial_temperature: float, inputs, parameters: Parameters) -> list[float]:
    """One input row per 60 s transition; each call is an independent segment."""
    rows = [list(row) for row in inputs]
    if any(len(row) != 5 for row in rows):
        raise ValueError("Every transition needs five inputs")
    flows = [number(row[4], "flow") for row in rows]
    if flows and any(flow != flows[0] for flow in flows):
        raise ValueError("Flow event inside segment: supply separate segments")
    states = [number(initial_temperature, "initial temperature")]
    for row in rows:
        states.append(step(states[-1], row, parameters))
    return states


def simulate_document(document: dict, parameters: Parameters) -> list[dict]:
    if document.get("schema") != "greybox-segments-v1" or document.get("sampling_seconds") != 60:
        raise ValueError("Expected greybox-segments-v1 at 60 s")
    if not isinstance(document.get("segments"), list) or not document["segments"]:
        raise ValueError("Explicit independent segments are required")
    records, seen = [], set()
    for segment in document["segments"]:
        identifier = segment["id"]
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ValueError("Segment identifiers must be nonempty and unique")
        seen.add(identifier)
        if not isinstance(segment["inputs"], list) or not segment["inputs"]:
            raise ValueError("Each segment requires at least one input transition")
        states = simulate(segment["initial_temperature_C"], segment["inputs"], parameters)
        records.extend({"segment": identifier, "state_index": index, "elapsed_s": index * 60, "temperature_C": value, "initialization": index == 0} for index, value in enumerate(states))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Use a new output directory; existing outputs are never overwritten")
    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
    records = simulate_document(document, load_parameters())
    manifest = {"input_sha256": digest(args.input), "parameters_sha256": digest(METADATA / "shared_theta_frozen_v1.json"), "contract_sha256": digest(METADATA / "model_contract.json"), "code_sha256": digest(Path(__file__)), "python": platform.python_version(), "numpy_required_by_this_kernel": False, "transitions": len(records) - len(document["segments"]), "initial_states": len(document["segments"]), "fit_calls": 0, "model_selection_calls": 0, "prediction_scoring_performed": False, "physical_validation": False, "claim_boundary": "Fixed one-state equation execution only; input provenance, observations and scoring support are external."}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "states.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"state_rows": len(records), **manifest}, indent=2))


if __name__ == "__main__":
    main()
