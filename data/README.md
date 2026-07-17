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
| `experiment_date` | ISO date | Stable date identifier that cannot be read as a decimal |
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
| `timestamp` | datetime | Recorded wall-clock time when present (2026-03-17 only) |
| `wall_elapsed_s` | s | Elapsed wall-clock time when timestamp coverage is complete |
| `valid_sensor_range` | bool | Temperature and irradiance plausibility flag |
| `active_irradiance` | bool | `G_W_m2 >= 100` flag |

The fifth-channel timebase is not assumed to be wall-clock time. On 2026-03-17, the wall-clock duration is 2.7326 times the reconstructed fifth-channel duration.

The alignment diagnostic instead calibrates a 5.834 s normal sample period from the recorded 2026-03-17 timestamps. It preserves that day's timestamps and reconstructs the other days by sample order plus an author-confirmed common-stop anchor. Generated tables retain `alignment_basis` and `reference_sample_period_s`; residual shifts of +/-30, +/-60, and +/-120 s are evaluated explicitly.

## Electrical input and schema

The electrical builder accepts one instrument Markdown export per day and optional XLSX originals for cross-checking. Its core output fields are ISO experiment date, source-row order, sequence, wall-clock timestamp, voltage, raw and scaled current, active power, calculated `V * I` power, consistency flags, duplicate-timestamp flags, and source SHA-256.

The current header says `mA` on eight days although the numerical values satisfy `P ~= V * I` only when interpreted as amperes. The chosen scale and the header conflict are both retained; the header is never silently rewritten.

`experimental_clean_v1_qc.*` and `electrical_clean_v1_qc.*` are committed as provenance metadata. The real raw and processed measurements remain excluded until release permission and a data licence are confirmed.
