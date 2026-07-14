# Public release checklist

## Repository presentation

- Repository name: `pvt-greybox-outdoor-validation`
- Description: `Audited data pipeline and whole-day grey-box modeling for transient outdoor PV/T experiments.`
- Topics: `pvt`, `solar-energy`, `grey-box-model`, `system-identification`, `time-series`, `reproducible-research`
- Default branch: `main`
- Development branch prefix: `agent/`

## Include in the first public release

- English and Chinese READMEs.
- `CITATION.cff` and a version tag.
- Audited Python scripts in `scripts/` and `analysis/`.
- Synthetic unit tests and GitHub Actions workflow.
- Data schema, QC metadata, reproducibility guide, and claim boundaries.

## Do not upload in the first public release

- The B610 competition manual or any CV/PS/application file.
- Historical HIL, optimizer, PINN, firmware, and competition result figures.
- Model weights, Origin projects, Simulink files, DLLs, object files, or packaged archives.
- Raw or processed experiment measurements until ownership and a data licence are confirmed.
- Results produced by unaudited legacy scripts.

## Before changing the repository to public

1. Confirm every collaborator agrees to public release of the experiment data.
2. Choose separate licences for code and data; do not assume the same licence covers both.
3. Run the unit tests and regenerate QC totals from the exact data snapshot.
4. Add the electrical parser only after checking units, timestamp behavior, and alignment tolerance.
5. Tag a release such as `v0.1.0`; archive a paper-ready version with Zenodo or another DOI repository.
6. Replace development language in the README with the final manuscript/preprint citation.
