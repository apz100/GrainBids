# GrainBids competitive market snapshot

Status: client-ready template; populate only with verified public or customer-authorized data.

## Cover

- Customer / prospect: `[name]`
- Region: `[controlled region]`
- Commodities: `[commodity list]`
- Data as of: `[timestamp and timezone]`
- Prepared by: GrainBids

## Executive findings

Use three to five short, factual findings. Each must identify its source timestamp and comparable delivery period. Describe a number as a posted bid, not an executable quote or delivered netback.

1. `[highest/lowest/range observation for one comparable delivery bucket]`
2. `[strict cash or basis change with the same delivery and futures contract]`
3. `[coverage, stale-source, or missing-market observation]`

## Comparable posted bids

| Commodity | Buyer / location | Delivery window | Futures contract | Cash price | Basis | Currency / unit | Captured at | Confidence |
|---|---|---|---|---:|---:|---|---|---|
| `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[CAD/bu or CAD/MT]` | `[timestamp]` | `[label]` |

Do not rank rows from different delivery periods, grades, currencies, or units as directly comparable.

## Material changes

| Buyer / location | Commodity | Delivery | Futures | Current | Prior comparable | Change | Evidence |
|---|---|---|---|---:|---:|---:|---|
| `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[value]` | `[row/source IDs]` |

If there are no exact comparable changes, state that. Do not substitute a contract roll or different delivery window.

## Source health and coverage

| Source | Status | Last success | Age | Rows used | Warning |
|---|---|---|---:|---:|---|
| `[value]` | `[healthy/stale/failed]` | `[timestamp]` | `[hours]` | `[count]` | `[value]` |

## What this may mean operationally

Limit this section to questions or verifications supported by the data:

- Which posted bid should be confirmed directly with the buyer?
- Does the customer have freight for the highlighted destination?
- Are grade, delivery capacity, payment terms, and contract terms compatible?
- Is the difference large enough to justify a delivered-netback comparison?

## Limitations

Posted-bid intelligence only. Freight is excluded unless explicitly shown. Verify current bid, grade, delivery window, futures contract, currency, units, payment terms, and freight before making a commercial decision. This is not a recommendation to buy, sell, store, hedge, or contract grain.
