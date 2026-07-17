# Outdoor PVT experiment data quality report

Total rows: 41599; valid sensor-range rows: 41578.

| Date | Flow (mL/min) | Rows | Invalid | Active G>=100 | Duration (h) | Median dt (s) |
|---|---:|---:|---:|---:|---:|---:|
| 2026-03-16 | 300 | 2483 | 0 | 2483 | 1.740 | 2.500 |
| 2026-03-17 | 300 | 2690 | 0 | 2682 | 1.625 | 2.100 |
| 2026-03-18 | 300 | 6267 | 0 | 5945 | 6.905 | 4.400 |
| 2026-03-19 | 300 | 5472 | 0 | 5470 | 6.218 | 4.300 |
| 2026-03-20 | 300 | 5460 | 0 | 5460 | 6.792 | 4.800 |
| 2026-03-21 | 300 | 4227 | 0 | 4227 | 5.056 | 4.400 |
| 2026-03-22 | 300 | 4431 | 21 | 4312 | 5.885 | 5.400 |
| 2026-03-25 | 500 | 5243 | 0 | 5243 | 5.502 | 4.000 |
| 2026-03-26 | 500 | 5326 | 0 | 5323 | 5.914 | 4.100 |

## Known limitations

- Flow is a day-level set point (300 or 500 mL/min), not a measured time series.
- No outlet-water temperature channel is present; thermal power and thermal efficiency cannot be measured directly.
- No ambient-air temperature channel is present in these logger files.
- Electrical measurements are stored separately and require timestamp-based alignment before use.
- The fifth logger channel is retained as logger_time_s, but its wall-clock meaning is not established. On the timestamped 2026-03-17 record, wall-clock and reconstructed logger-counter durations differ materially.
