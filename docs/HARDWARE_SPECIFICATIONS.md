# Audited hardware specifications

## Current PV module specification

Evidence source: user direct correction dated 2026-09-14, supported by the confirmed same-rig manuscript.

| Field | Current value |
|---|---:|
| Cell/module type | Monocrystalline silicon module |
| Maximum power | 100 W |
| Effective illuminated area | 0.55 m2 |
| Model, dimensions, Voc/Isc/Vmp/Imp | Not yet confirmed for the current module |

Dividing 100 W by 1000 W/m2 times 0.55 m2 gives a reference conversion efficiency of approximately 18.18%. This is a rating-area calculation, not an outdoor measured efficiency.

The model should use `Ac=0.55 m2`, `Pmax_ref=100 W`, and no additional packing multiplier above one. Current-module Voc, Isc, Vmp and Imp remain unknown and do not get inherited from the obsolete record.

## Obsolete historical record

An author-provided photograph inspected on 2026-07-17 showed YTXN-6M-120W, 120 W, 21.4 V/6.80 A, 18 V/6.67 A and 1200 x 540 x 30 mm (0.648 m2 gross area). The user explicitly stated on 2026-09-14 that 120 W/0.648 m2 was not accurate for the current rig. These fields are retained only to explain prior code and reports; they must not be used as current inputs.
