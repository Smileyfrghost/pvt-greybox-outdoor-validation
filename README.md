# Outdoor PV/T Grey-Box Modeling

[![Tests](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml/badge.svg)](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-research%20prototype-orange)

Reproducible data-processing and baseline modeling code for a small water-cooled photovoltaic/thermal (PV/T) collector tested under transient outdoor conditions.

**Research areas:** photovoltaic-thermal systems, solar energy, transient thermal modeling, grey-box system identification, time-series validation, and reproducible research.

## Method scope

This code companion contains temperature/irradiance and electrical-power parsers, exploratory whole-day baselines, an early electro-thermal clock diagnostic, a minute-resolution irradiance-workbook audit, tests, and data-quality metadata. The exploratory baseline and early clock commands use historical protocols, which differ from the later frozen manuscript study. See [methods and evidence](docs/METHODS_AND_EVIDENCE.md) before interpreting outputs. Original measurements are supplied separately.

The current experiment inventory comprises nine test days, 41,599 thermal/irradiance logger records, 162,844 electrical records, and two day-level flow settings (300 and 500 mL/min). Twenty-one thermal sensor-range failures and four voltage-current-power consistency failures are flagged rather than silently removed.

## What this repository supports

- Rebuilding the temperature/irradiance dataset from the original logger files.
- Reconstructing a monotonic elapsed-time axis when the logger counter resets.
- Preserving legacy temperature-channel fields without treating their names as independently confirmed sensor locations.
- Parsing active power, voltage, and current from all nine original instrument exports.
- Inferring the current scale from the physical relation `P ~= V * I` while retaining header-unit conflicts in QC.
- Reconstructing non-timestamped thermal clocks from the 5.834 s timestamped reference period and the author-confirmed common-stop acquisition sequence.
- Reporting correlation-ranked alternatives and +/-30/60/120 s timing sensitivity without allowing correlation to overwrite physical clock anchors.
- Comparing modest static and dynamic baselines using leave-one-day-out evaluation.
- Recording limitations and quality-control decisions in machine-readable form.

It does **not** support measured thermal power or thermal-efficiency claims because no outlet-water temperature was logged. Flow is a day-level setting, not a measured time series. Ambient temperature and wind are absent from the March logger. One thermal day contains wall-clock timestamps; the remaining clocks are operational reconstructions based on its stable sampling period and the confirmed acquisition sequence, and must retain timing-sensitivity analysis.

## Repository layout

```text
analysis/                 Whole-day baselines and clock-alignment diagnostics
scripts/                  Audited thermal and electrical data builders
tests/                    Synthetic parser and model tests
data/                     Schema and data-quality metadata
docs/                     Reproduction guide and claim boundaries
results/                  Locally generated outputs (ignored by Git)
.github/workflows/        Automated tests
```

## Quick start

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

To rebuild the dataset after obtaining the original logger files:

```bash
python scripts/build_experimental_dataset.py \
  --raw-dir data/raw/temperature \
  --output-dir data/processed
```

To parse the electrical exports and diagnose clock alignment:

```bash
python scripts/build_electrical_dataset.py \
  --power-dir data/raw/electrical \
  --xlsx-dir data/raw/electrical_xlsx \
  --output-dir data/processed

python analysis/diagnose_electrothermal_alignment.py \
  --thermal-csv data/processed/experimental_clean_v1.csv \
  --electrical-csv data/processed/electrical_clean_v1.csv \
  --output-dir results/alignment
```

To evaluate whole-day baselines:

```bash
python analysis/fit_panel_temperature_models.py \
  --dataset data/processed/experimental_clean_v1.csv \
  --output-dir results/panel_temperature_baselines
```

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for the exact input filenames and [docs/CLAIM_BOUNDARIES.md](docs/CLAIM_BOUNDARIES.md) before interpreting results.

## Irradiance workbook audit

```bash
python analysis/audit_irradiance_campaign.py data/raw/irradiance results/irradiance_audit
```

Input workbooks must use minute observations and the documented W/m2, MJ/m2 and h units. `.xlsx` support uses `openpyxl`; legacy `.xls` support additionally requires `xlrd`. The script flags coverage and channel issues without modifying source files. It does not establish sensor geometry or turn station readings into panel-plane irradiance.

See the [repository map](docs/REPOSITORY_MAP.md) and [Chinese entry point](README_zh.md) for file locations. Project progress and upload batches are maintained in local project-management records, not this usage README.

## Citation

Citation metadata are provided in [CITATION.cff](CITATION.cff). A manuscript citation and archive DOI will be added when available.

## Licence

No reuse licence is granted yet. Code and data licensing will be separated before the first public research release.
