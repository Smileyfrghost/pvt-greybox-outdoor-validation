# Phase 1 data audit and operational alignment

> **2026-09-14 correction:** The user directly confirmed that the current rig is rated at **100 W** with **0.55 m2 effective area**. The earlier YTXN-6M-120W photograph, 120 W, 0.648 m2, dimensions and associated Voc/Isc/Vmp/Imp values below are retained only as historical audit evidence and are not current-rig specifications. The active configuration has been corrected; all dependent legacy LUTs, simulations, figures and reports are stale until regenerated. This correction does not release the channel, clock, operating-condition or physical-validation gates.

Audit date: 2026-07-17. Alignment revision: 2026-07-17 after author confirmation of the acquisition sequence.

## Outcome

The nine thermal/irradiance and electrical records can be reconstructed on a common operational clock. The earlier diagnostic that used the fifth thermal channel as elapsed wall time was rejected: on the timestamped reference day, that channel accumulates 1.6255 h while recorded wall time spans 4.4418 h.

The corrected clock uses the following evidence chain:

1. The complete 2026-03-17 timestamps establish a normal thermal sampling period of 5.834 s (5th--95th percentile: 5.823--5.846 s), with one 307.392 s acquisition gap.
2. The author confirmed that electrical logging was generally started first, thermal/irradiance logging later, and the two were stopped together or in close succession.
3. The non-timestamped thermal files are therefore reconstructed at 5.834 s per sample and anchored at the final electrical timestamp. Recorded timestamps are retained unchanged on 2026-03-17.
4. Where source file modification times are reliable, they independently lie within approximately six minutes of electrical stop and support the common-stop rule. Modification time is corroboration, not the primary clock.
5. Residual timing uncertainty is tested at +/-30, +/-60, and +/-120 s.

| Evidence block | Audited result | Manuscript status |
|---|---|---|
| Thermal/irradiance logger | 41,599 rows across nine days; 41,578 pass range checks; 21 failures on 2026-03-22 | usable with flags |
| Electrical instrument | 162,844 rows across nine days; 162,840 pass range and `P ~= V * I` checks; four failures on 2026-03-22 | usable with flags |
| Electrical originals | Four available XLSX files exactly match the corresponding Markdown exports | Markdown accepted as the nine-day parsing interface |
| Electrical sampling | Median interval is 1 s on 2026-03-16 through 2026-03-20 and 6 s on later days; 317 extra duplicate timestamps are preserved | usable after 30 s aggregation |
| Current unit | Eight headers say `mA`, but numerical consistency requires a scale of 1 A per recorded unit | inferred unit is defensible; conflict disclosed |
| Thermal clock | One timestamped reference day plus fixed-period/common-stop reconstruction on eight days | usable with shift sensitivity |
| PV module | YTXN-6M-120W, monocrystalline, 120 W, 18 V/6.67 A at maximum power, 21.4 V open circuit, 6.80 A short circuit, 0.648 m2 | nameplate supported |

The four electrically invalid rows are retained and excluded only by `valid_for_model`. No row is silently deleted. Original electrical record order is monotonic on all nine days.

## Alignment results

At the reconstructed operational clock, irradiance--power rank correlation is 0.89--0.98 on eight days and 0.61 on 2026-03-22. The reconstructed thermal duration differs from the complete electrical duration by only 2.1--3.3 min on 2026-03-18, 03-19, 03-20, 03-25, and 03-26. Larger differences on 03-16, 03-21, and 03-22 indicate that electrical logging began 21, 44, and 75 min earlier, respectively.

The 2026-03-22 electrical trace remains a special operating-state problem: power is zero for roughly the first 1.8 h despite substantial irradiance. This interval must be treated as load/logger-off behavior rather than a clock failure and excluded or modeled as a separate state.

The diagnostic now emits two local, Git-ignored tables:

- `thermal_clock_reconstruction_v1.csv`: every thermal record with its recorded or reconstructed timestamp and alignment basis.
- `electrothermal_aligned_30s_v1.csv`: valid thermal and electrical channels aggregated on common 30 s bins.

Correlation-ranked candidates remain diagnostic. Recorded timestamps or the author-confirmed common-stop rule define the operational clock; correlation is not allowed to overwrite those anchors merely to improve a score.

## Hardware evidence

The module nameplate photograph confirms model YTXN-6M-120W and dimensions 1200 x 540 x 30 mm. The resulting area is 0.648 m2 and the nameplate efficiency is approximately 18.5% at 1000 W/m2. The central model already used the correct area and 120 W rating. A legacy `packing_factor=1.10` was physically impossible and has been corrected to 1.00 because module area and nameplate efficiency are already represented explicitly.

B610 remains a system-description document rather than a raw acquisition log. Its outlet-temperature, thermal-efficiency, HIL, and controller-performance statements are not imported unless their underlying files are recovered and audited.

## Remaining evidence priorities

No new physical experiment is required for the base paper. The most valuable recoverable materials are now:

1. Temperature-sensor models, stated accuracy, and photographs or sketches of panel/tank/inlet probe placement.
2. Irradiance-meter model, accuracy, and evidence that its sensing plane was coplanar with the PV module.
3. Flowmeter or setting-device model and how 300 and 500 mL/min were established and checked.
4. Electrical load/charger/controller wiring and whether load or MPPT state changed during a day, especially on 2026-03-16 and 03-22.
5. Pump label/manual, rated voltage/current/power, maximum flow/head, and whether it ran continuously.
6. Tank volume, water charge, insulation/mixing arrangement, tube dimensions, and loop layout.
7. Experiment location, module tilt and azimuth, and confirmation of any setup change between dates.
8. The logger code defining the fifth thermal channel; useful for documentation, but no longer required to build the operational wall clock.

If an item cannot be recovered, record it as unavailable rather than infer a precise specification.

## Scope decision

The synchronization gate is passed for proceeding to whole-day electrothermal model development, subject to day-level and +/-30/60/120 s timing sensitivity. The next model stage must:

- retain complete-day holdouts;
- report 2026-03-22 both with and without the load-off interval;
- treat 300 and 500 mL/min as day-level settings rather than measured time series;
- avoid thermal-power or thermal-efficiency claims because outlet temperature is absent; and
- use the nameplate rating without an additional packing multiplier.
