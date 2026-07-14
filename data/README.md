# Data contract

## Original input files

The dataset builder expects the following files in one directory:

| Experiment day | Filename | Flow setting (mL/min) |
|---|---|---:|
| 3.16 | `3.16.txt` | 300 |
| 3.17 | `3.17.docx` | 300 |
| 3.18 | `3.18.txt` | 300 |
| 3.19 | `3.19.txt` | 300 |
| 3.20 | `3.20.txt` | 300 |
| 3.21 | `3.21.txt` | 300 |
| 3.22 | `3.22.txt` | 300 |
| 3.25 | `3.25.txt` | 500 |
| 3.26 | `3.26.txt` | 500 |

The five logger values are interpreted as panel temperature, tank temperature, inlet temperature, irradiance, and logger time. This mapping follows the original 3.16 header and is not inferred from the old processed CSV files.

## Processed schema

| Column | Unit | Meaning |
|---|---|---|
| `date` | - | Experiment-day label |
| `flow_ml_min` | mL/min | Day-level flow setting |
| `flow_kg_s` | kg/s | Converted setting assuming water density of 1 kg/L |
| `sample_order` | - | Row order within a day |
| `T_panel_C` | degC | Panel temperature channel |
| `T_tank_C` | degC | Tank temperature channel |
| `T_inlet_C` | degC | Collector-inlet temperature channel |
| `G_W_m2` | W/m2 | Plane-of-array irradiance channel |
| `logger_time_s` | s | Original resetting logger counter |
| `elapsed_s` | s | Reconstructed monotonic elapsed time |
| `valid_sensor_range` | bool | Temperature and irradiance plausibility flag |
| `active_irradiance` | bool | `G_W_m2 >= 100` flag |

`experimental_clean_v1_qc.json` and `experimental_clean_v1_qc.md` are committed as provenance metadata. The real raw and processed measurements remain excluded until release permission and a data licence are confirmed.
