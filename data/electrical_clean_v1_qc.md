# Electrical experiment data quality report

Parsed 162,844 rows across 9 experiment days; 162,840 rows pass the current range and V-I-P consistency flags.

| Date | Rows | Start | End | Median dt (s) | P range (W) | Duplicate timestamps | V-I-P inconsistent | Header conflict |
|---|---:|---|---|---:|---:|---:|---:|:---:|
| 2026-03-16 | 15697 | 12:46:51 | 17:08:51 | 1.0 | 0.00 to 95.20 | 18 | 0 | no |
| 2026-03-17 | 26561 | 09:39:24 | 17:02:01 | 1.0 | 0.00 to 32.78 | 8 | 0 | yes |
| 2026-03-18 | 36710 | 07:43:45 | 17:56:18 | 1.0 | 0.00 to 96.56 | 90 | 0 | yes |
| 2026-03-19 | 32017 | 08:03:55 | 16:58:13 | 1.0 | 0.00 to 101.30 | 78 | 0 | yes |
| 2026-03-20 | 31993 | 08:14:31 | 17:08:24 | 1.0 | 4.34 to 98.22 | 90 | 0 | yes |
| 2026-03-21 | 4544 | 08:36:09 | 16:10:33 | 6.0 | 8.25 to 92.01 | 0 | 0 | yes |
| 2026-03-22 | 5001 | 09:04:34 | 17:29:53 | 6.0 | 0.00 to 93.05 | 33 | 4 | yes |
| 2026-03-25 | 5122 | 08:08:49 | 16:40:59 | 6.0 | 0.00 to 85.63 | 0 | 0 | yes |
| 2026-03-26 | 5199 | 08:41:02 | 17:20:55 | 6.0 | 7.04 to 79.05 | 0 | 0 | yes |

## XLSX cross-check

- 2026-03-21: row count equal=True; timestamps equal=True; max numeric differences={'voltage_V': 0.0, 'current_raw': 0.0, 'active_power_W': 0.0}.
- 2026-03-22: row count equal=True; timestamps equal=True; max numeric differences={'voltage_V': 0.0, 'current_raw': 0.0, 'active_power_W': 0.0}.
- 2026-03-25: row count equal=True; timestamps equal=True; max numeric differences={'voltage_V': 0.0, 'current_raw': 0.0, 'active_power_W': 0.0}.
- 2026-03-26: row count equal=True; timestamps equal=True; max numeric differences={'voltage_V': 0.0, 'current_raw': 0.0, 'active_power_W': 0.0}.

## Known limitations

- The current header is inconsistent with the numeric scale on some days; scale is inferred from P ~= V*I and the conflict is retained in QC.
- Duplicate wall-clock timestamps are preserved and flagged rather than silently removed.
- The instrument's constant environment-temperature field is metadata, not a measured outdoor ambient-temperature series.
- Electrical timestamps cannot be aligned to relative-time thermal logs without an explicit or auditable offset procedure.
