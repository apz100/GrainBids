# GrainBids freight and netback comparison

Status: client-ready template; every assumption must be supplied or confirmed by the customer.

## Scenario definition

- Origin: `[location]`
- Commodity / grade: `[value]`
- Quantity: `[MT]`
- Delivery period: `[value]`
- Currency: `[CAD or USD]`
- FX rate and timestamp, if required: `[value]`
- Freight convention: `[customer pickup / delivered / third-party truck]`

## Freight assumptions

| Lane | Distance | Rate basis | Fixed charges | Total freight $/MT | Source / owner | Confirmed at |
|---|---:|---|---:|---:|---|---|
| `[origin -> destination]` | `[km]` | `[$/MT/km or quoted $/MT]` | `[value]` | `[value]` | `[customer/carrier]` | `[timestamp]` |

Never infer unknown freight as zero.

## Comparable destinations

| Destination | Bid interpretation | Delivery | Futures | Posted cash $/MT | Freight $/MT | Other declared cost $/MT | Estimated origin netback $/MT | Difference vs reference |
|---|---|---|---|---:|---:|---:|---:|---:|
| `[value]` | `[FOB/delivered]` | `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[cash - freight - costs]` | `[value]` |

## Calculation audit

For every row show:

```text
estimated origin netback = compatible cash bid - freight - declared additional costs
```

Keep basis, futures, cash, freight, and gross spread separate. Do not label gross spread as profit.

## Verification checklist

- [ ] Bid is current and executable for the stated quantity and grade.
- [ ] Delivery window and futures contract are shown.
- [ ] Currency and units match or a timestamped FX conversion is shown.
- [ ] Freight direction, rate, fuel surcharge, waiting time, and minimum charge are confirmed.
- [ ] Receiving hours, unload constraints, shrink/discounts, and payment terms are reviewed.
- [ ] Customer understands this is a scenario comparison, not a trade instruction.
