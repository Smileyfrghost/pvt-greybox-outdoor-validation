# Repository map

| Directory | Contents | Interface |
|---|---|---|
| `scripts/` | Temperature and electrical parsers | Read source exports; write processed tables and QC metadata |
| `analysis/` | Exploratory baselines, early clock diagnostics, irradiance workbook audit | Explicit input/output paths; generated files go under `results/` |
| `tests/` | Synthetic software checks | `python -m unittest discover -s tests -v` |
| `data/` | Input schema and historical QC summaries | Measurements are supplied separately |
| `docs/` | Hardware evidence, method boundaries and reproduction instructions | Start with `METHODS_AND_EVIDENCE.md` |
| `results/` | Local generated outputs | Excluded from Git except the usage README |
| `.github/workflows/` | Python test workflow | Synthetic checks on pushes and pull requests |

This code companion is not an archive of all local paper drafts, simulations, firmware experiments or application documents. The local workspace maintains project status, task batches and run/research logs separately from these usage documents.

Keep raw experiments, personal correspondence, institutional-access PDFs, virtual environments and generated outputs out of code commits. Save new computations in separate output directories with input and code provenance.
