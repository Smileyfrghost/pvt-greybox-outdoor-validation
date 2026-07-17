# Outdoor PV/T Grey-Box Modeling

[![Tests](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml/badge.svg)](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-research%20prototype-orange)

Reproducible data-processing and baseline modeling code for a small water-cooled photovoltaic/thermal (PV/T) collector tested under transient outdoor conditions.

**Research areas:** photovoltaic-thermal systems, solar energy, transient thermal modeling, grey-box system identification, time-series validation, and reproducible research.

## Status

This is a scoped research companion repository, not a release of the earlier competition project. It contains audited temperature/irradiance and electrical-power pipelines, whole-day validation baselines, an electro-thermal clock-alignment diagnostic, tests, and data-quality metadata. The original measurements are not redistributed yet because data ownership and licensing still need to be confirmed.

The current experiment inventory comprises nine test days, 41,599 thermal/irradiance logger records, 162,844 electrical records, and two day-level flow settings (300 and 500 mL/min). Twenty-one thermal sensor-range failures and four voltage-current-power consistency failures are flagged rather than silently removed.

## What this repository supports

- Rebuilding the temperature/irradiance dataset from the original logger files.
- Reconstructing a monotonic elapsed-time axis when the logger counter resets.
- Preserving panel, tank, and inlet temperature channels without relabeling them.
- Parsing active power, voltage, and current from all nine original instrument exports.
- Inferring the current scale from the physical relation `P ~= V * I` while retaining header-unit conflicts in QC.
- Ranking candidate electro-thermal offsets without presenting correlation-based alignment as a measured clock offset.
- Comparing modest static and dynamic baselines using leave-one-day-out evaluation.
- Recording limitations and quality-control decisions in machine-readable form.

It does **not** support measured thermal power or thermal-efficiency claims because no outlet-water temperature was logged. Flow is a day-level setting, not a measured time series. Ambient temperature and wind are absent from the March logger. Only one thermal day contains wall-clock timestamps; the remaining electro-thermal offsets are diagnostic candidates, not confirmed synchronization.

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

## Planned release path

1. Confirm permission and choose a licence for the experiment data.
2. Recover external clock anchors for the non-timestamped thermal days or freeze a thermal-only paper scope.
3. Replace baseline regressions with a physically interpretable grey-box state model.
4. Freeze a tagged release and archive it with a DOI alongside the preprint.

## Citation

Citation metadata are provided in [CITATION.cff](CITATION.cff). A manuscript citation and archive DOI will be added when available.

## Licence

No reuse licence is granted yet. Code and data licensing will be separated before the first public research release.
