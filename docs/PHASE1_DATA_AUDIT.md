# Phase 1 data audit and paper decision gate

Audit date: 2026-07-17.

## Outcome

The electrical and thermal records can each be reconstructed reproducibly, but a nine-day pointwise electro-thermal dataset cannot yet be claimed. The limiting evidence is the thermal clock, not the electrical parser.

| Evidence block | Audited result | Manuscript status |
|---|---|---|
| Thermal/irradiance logger | 41,599 rows across nine days; 41,578 pass range checks; 21 failures on 2026-03-22 | usable with flags |
| Electrical instrument | 162,844 rows across nine days; 162,840 pass range and `P ~= V * I` checks; four failures on 2026-03-22 | usable with flags |
| Electrical originals | Four available XLSX files exactly match the corresponding Markdown exports | Markdown accepted as the nine-day parsing interface |
| Electrical sampling | Median interval is 1 s on 2026-03-16 through 2026-03-20 and 6 s on later days; 317 extra duplicate-timestamp rows are preserved | usable after aggregation policy is stated |
| Current unit | Eight headers say `mA`, but numerical consistency requires a scale of 1 A per recorded unit | inferred unit is defensible; conflict must be disclosed |
| Thermal wall clock | Only 2026-03-17 has complete recorded timestamps | insufficient for nine-day synchronization |
| Fifth thermal channel | On 2026-03-17, wall-clock duration is 4.4418 h and reconstructed fifth-channel duration is 1.6255 h (ratio 2.7326) | cannot be treated as wall-clock time without further evidence |

The four electrically invalid rows are retained in the processed file and excluded only by `valid_for_model`. No row is silently deleted. Original electrical record order is monotonic on all nine days; duplicate timestamps originate in the source files rather than a sorting artifact.

## Alignment diagnostic

For non-timestamped days, the diagnostic scans 30 s candidate starts that place the complete relative thermal record inside the electrical window. It scores each candidate using 75% irradiance-power rank correlation and 25% smoothed first-difference agreement. This is a candidate-ranking device, not clock measurement.

The current result is one day with recorded wall-clock timestamps, three moderate but unconfirmed candidates (2026-03-16, 2026-03-21, and 2026-03-25), and five ambiguous days. The 2026-03-17 direct timestamp alignment has a diagnostic score of 0.687, but its relative logger counter follows a materially different timebase. File modification times are close to electrical stop times on several later days, yet their implied starts differ from correlation-ranked starts by roughly 68--241 min. Modification time is therefore retained only as secondary forensic evidence.

No aligned training table is emitted by the diagnostic. This is deliberate: generating one would turn an unverified correlation peak into false measurement precision.

## What B610 contributes

The B610 document is a system description and claimed-results document, not a raw acquisition log or an instrument timing manual. Its platform diagram shows an intended irradiance meter, flowmeter, electrical parameter tester, inlet/outlet temperature sensing, pump, and load. The files currently in hand contain panel, tank, inlet and irradiance channels; day-level flow labels; and separate electrical measurements. They do not contain measured outlet temperature, time-resolved flow, ambient temperature, wind, or control commands.

Accordingly, B610 is usable for apparatus context and for locating missing records. Its stated outlet-temperature, thermal-efficiency, HIL, and control-performance results are not imported into the paper evidence chain unless their underlying files are found and audited.

## Evidence needed from the experiment record

The highest-value recovery items are:

1. Original timestamped serial-monitor exports for the eight non-timestamped thermal days.
2. Written start and stop times for both thermal and electrical logging, preferably with minute-level or better precision.
3. The code or instrument setting defining the fifth thermal channel and its reset behavior.
4. Photographs, notebook pages, messages, or screen captures that independently anchor logger start/stop events.
5. Any original outlet-temperature, flowmeter, pump-command, ambient-temperature, or wind files referenced by B610.

## Scope decision gate

Freeze the primary manuscript scope no later than 2026-08-03.

- Continue with the nine-day electro-thermal grey-box paper only if both 500 mL/min days and at least five 300 mL/min days obtain auditable wall-clock mappings, the fifth-channel timebase is explained or replaced, and alignment sensitivity at +/-30, +/-60, and +/-120 s does not overturn the main validation result.
- If that gate is not met, freeze a thermal-response paper based on the nine audited temperature/irradiance days. Electrical data may appear as a separately described measurement stream or a timestamped single-day case, but not as falsely synchronized pointwise targets.
- Do not spend August tuning a dynamic model on the current `elapsed_s` field until the timebase decision is resolved. Static day-level exploration is acceptable; confirmatory dynamic metrics are not.

This gate favors a smaller defensible preprint over a broader paper whose central electro-thermal dataset cannot be reproduced.
