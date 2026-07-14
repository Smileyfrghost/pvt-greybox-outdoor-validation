# Outdoor PV/T Grey-Box Modeling

[![Tests](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml/badge.svg)](https://github.com/Smileyfrghost/pvt-greybox-outdoor-validation/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-research%20prototype-orange)

Reproducible data-processing and baseline modeling code for a small water-cooled photovoltaic/thermal (PV/T) collector tested under transient outdoor conditions.

**Research areas:** photovoltaic-thermal systems, solar energy, transient thermal modeling, grey-box system identification, time-series validation, and reproducible research.

## Status

This is a scoped research companion repository, not a release of the earlier competition project. Version `0.1.0` contains the audited temperature/irradiance data pipeline, whole-day validation baselines, tests, and data-quality metadata. The original measurements are not redistributed yet because data ownership and licensing still need to be confirmed.

The current experiment inventory comprises nine test days, 41,599 logger records, and two day-level flow settings (300 and 500 mL/min). Twenty-one sensor-range failures occur on one day and are flagged rather than silently removed.

## What this repository supports

- Rebuilding the temperature/irradiance dataset from the original logger files.
- Reconstructing a monotonic elapsed-time axis when the logger counter resets.
- Preserving panel, tank, and inlet temperature channels without relabeling them.
- Comparing modest static and dynamic baselines using leave-one-day-out evaluation.
- Recording limitations and quality-control decisions in machine-readable form.

It does **not** support measured thermal power or thermal-efficiency claims because no outlet-water temperature was logged. Flow is a day-level setting, not a measured time series. Ambient temperature and wind are absent from the March logger. Electrical records require a separate, audited alignment step and are not yet part of this release.

## Repository layout

```text
analysis/                 Whole-day baseline model evaluation
scripts/                  Audited experiment-data builder
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

To evaluate whole-day baselines:

```bash
python analysis/fit_panel_temperature_models.py \
  --dataset data/processed/experimental_clean_v1.csv \
  --output-dir results/panel_temperature_baselines
```

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for the exact input filenames and [docs/CLAIM_BOUNDARIES.md](docs/CLAIM_BOUNDARIES.md) before interpreting results.

## Planned release path

1. Confirm permission and choose a licence for the experiment data.
2. Add the audited electrical-log parser and timestamp-alignment report.
3. Replace baseline regressions with a physically interpretable grey-box state model.
4. Freeze a tagged release and archive it with a DOI alongside the preprint.

## Citation

Citation metadata are provided in [CITATION.cff](CITATION.cff). A manuscript citation and archive DOI will be added when available.

## Licence

No reuse licence is granted yet. Code and data licensing will be separated before the first public research release.
