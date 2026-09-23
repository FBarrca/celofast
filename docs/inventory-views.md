# Inventory policy draft views

These Celonis views hold draft parameters. They do not start Python, change its
configuration, or display simulated results.

## Choose material

[Open the selection view](https://ai-apps.eu-1.celonis.cloud/package-manager/ui/studio/ui/spaces/9f7cc225-132d-49e7-8b0d-b626b1000b41/packages/d58d5d35-55a3-45c1-be45-942a37e0e97c/nodes/073510cf-12f4-4164-8f6d-30fbe1eea355).

The map selects plant countries; the model does not provide plant coordinates.
Plant and material filters narrow the table. Clicking a material opens Details
and passes that row's exact MaterialMasterPlant ID as `sim_material_plant_id`.

## Details

View key: `inventory-policy-details`, node
`863eb91b-11b0-4697-84c9-27781088c6db`.

The top section shows the selected material, location, current stock, safety
stock and stock-keeping unit. A native range calendar binds `sim_start_date`
and `sim_end_date`. Both boundary days are included and these dates drive the
chart's daily axis:

```sql
TIMELINE_COLUMN(
  DAYS,
  FROM(ROUND_DAY({t ${sim_start_date}})),
  TO(ROUND_DAY({t ${sim_end_date}}))
)

-- Component filter.
FILTER "o_celonis_MaterialMasterPlant"."ID" = '${sim_material_plant_id}';
```

The stock series uses `INTERPOLATE(..., LINEAR)` over daily snapshot quantities
to connect recorded snapshots continuously. It remains null before the first
and after the last recorded snapshot for the selected material-plant. This is
visual interpolation, not a reconstruction of daily inventory from movements.
Current stock may differ from the last historical snapshot and remains the
Python simulation's starting inventory.

Replenishment and consumption bars use actual `MaterialMovement.CreationTime`
dates, `MovementQuantityConverted`, and the KM's `IsReplenishmentRelevant` /
`IsConsumptionRelevant` flags. Quantities are summed by event day; consumption
is displayed below zero. No periodic monthly or simulated events are generated.
Days without relevant movements have no event bars. The native chart limit is
5,000 daily rows; longer ranges can truncate.

The calendar replaces the past/future month-count controls. Supplier history
remains a separate number of days. This draft still does not execute Python;
the calendar defines view parameters and the displayed time window only.

### DH220R / plant 1000 reconciliation

A browser PQL audit found one history row and one unique history ID for each
populated month, October 2024 through July 2026. October records 653; every
month from November onward records 3,110. SUM, MIN and MAX agree within each
month. The current-stock field records 2,959, a difference of 151 pieces.
This is a difference in the source snapshots, not duplicate summation in the
chart. Current-source freshness and the movement explanation for that difference
were not established. Use 2,959 for starting inventory. The view explicitly
labels history as month-end inventory and distinguishes it from current stock.

## View variables

Variables are defined in Celonis separately from the view YAML. All numeric
defaults are editable assumptions, not calibrated supplier estimates.

| Variable | Type | Default / purpose |
| --- | --- | --- |
| `sim_material_plant_id` | String | Passed from selection table |
| `sim_supplier_history_days` | Number | 180 |
| `sim_start_date` | Date | 2025-09-17; first included calendar day |
| `sim_end_date` | Date | 2026-12-17; last included calendar day |
| `sim_inventory_policy` | String | `sS`; alternatives `sQ`, `RS` |
| `sim_show_ss` | Boolean | true; internal visibility flag for `(s,S)` |
| `sim_show_sq` | Boolean | false; internal visibility flag for `(s,Q)` |
| `sim_show_rs` | Boolean | false; internal visibility flag for `(R,S)` |
| `sim_ss_reorder_point` | Number | 80 |
| `sim_ss_target_stock` | Number | 180 |
| `sim_sq_reorder_point` | Number | 80 |
| `sim_sq_quantity` | Number | 100 |
| `sim_rs_review_days` | Number | 7 |
| `sim_rs_target_stock` | Number | 260 |
| `sim_sourcing_policy` | String | `historical`; alternatives `manual`, `single` |
| `sim_supplier_id` | String | Selected Celonis supplier |
| `sim_supplier_lead_days` | Number | 1; manual calendar-day assumption |
| `sim_supplier_share` | Number | 100; manual percentage |
| `sim_supplier_overrides` | String | Human-readable settings accumulated in this session |
| `sim_arrival_overrides` | String | `[]`; revised dates for existing overdue receipts |

### Selected-policy parameters

Only the selected inventory policy's description, labels and two inputs are
visible. All three groups occupy the same two-column layout. Their values remain
in separate variables, so switching policies does not discard previous inputs.

The selector binds `sim_inventory_policy` and all three `sim_show_*` Boolean
variables. Each item updates the policy code and visibility flags together.
Grid elements use `${sim_show_ss}`, `${sim_show_sq}` or `${sim_show_rs}` as their
visibility value. Reset returns the selection and visibility flags to `(s,S)`.
The flags are UI state, not simulation parameters. A future integration should
read only the parameter pair belonging to `sim_inventory_policy`.

Browser checks confirmed all three field combinations and retained an edited
`(s,S)` target after switching through the other policies. The test edit was
restored to its original value afterward.

The Details layout uses compact section captions, five-row input controls and
short descriptions. The chart is 36 grid rows high. Browser screenshots checked the top, selected
policy, suppliers and revised-arrival sections for readable labels and clipping.

The page starts with material and inventory context, without an additional lab
title. Three numbered section headings separate **Inventory policy**, **Supplier
policy**, and **Supplier parameters**. The supplier table and lead-time/share
controls sit together under Supplier parameters. The date-range control sits
above the timeline, beside supplier history; its bindings are
`sim_start_date` and `sim_end_date`. It does not connect the draft to Python.

## Suppliers and sourcing

The supplier table shows supplier ID, name and distinct purchase-line count
for the selected pair. It follows purchase schedules through purchase lines
and headers to the vendor master. Counts are reference information across
available purchasing records; they are not historical allocation shares.

The supplier dropdown binds vendor IDs to purchase-schedule grain. Its CASE
expression includes only schedules for `sim_material_plant_id`, because the
dropdown does not consistently apply component filters to its option query.

Select a supplier, enter lead time and percentage share, then choose **Add
supplier setting**. The visible session list includes material-plant and
supplier IDs. **Clear supplier settings** clears that list. Clear and rebuild
the list when revising an existing entry; this draft is not a keyed editable
supplier database. Allow each input change to finish before adding its setting.

Historical sourcing selects the intended method; this draft does not calculate
completed-receipt medians or historical volume shares. Those remain in Python.
Manual shares must total 100%; single-supplier sourcing uses 100%. Supplier
eligibility, duplicate entries, numerical bounds and totals require validation
before any future simulation integration.

## Actions and integration boundary

- **Reset parameters** restores policy/time-window defaults and clears supplier
  settings and revised arrivals, retaining the selected material-plant.
- **Change material / location** opens the selection view.
- **Run simulation - not connected** has no action.

No views were deployed. The draft uses KM `km-to-be-copied` in package
`d58d5d35-55a3-45c1-be45-942a37e0e97c`. This is a different package from the
earlier Python example. No code reads view variables yet.

## Browser verification

- Calendar Apply narrowed the chart to January 1–31, 2025, including both days.
- Live queries reconciled consumption of 861 units on four event dates for
  HLM05N/6300, and replenishment of 469 units on January 12, 2023 for SBLT01W/8000.
  Single-day boundaries and windows without movements also passed.
- Continuous stock for SBLT01W/8000 covered all 731 days between its first and
  last snapshots (July 31, 2024 through July 31, 2026), without extrapolation.

- The material link passed the exact selected pair to the context table.
- DH220R at plant 1000 displayed monthly history with readable date labels.
- BF004Y at plant 6200 showed current stock and an empty history chart.
- DH220R at plant 1000 resolved a purchasing supplier in the supplier table.
- Its supplier dropdown offered that supplier; other supplier IDs were excluded.
- Adding a supplier setting retained the chosen ID, 12-day lead time and 100%
  share; clearing removed the test entry.
- Celonis YAML validation reported zero issues and draft saves succeeded.
- Reset restored the default sourcing mode, policy, numeric values and empty
  overrides while retaining the selected material and stock context.
