# Task: Integrate Signals into dashboard

## Objective
Surface signal forecast data directly on the dashboard so users can see predictions without navigating to the separate Signals page.

## Background
Signals currently lives on its own isolated page at `/signals`. The dashboard is the primary market discovery surface and should surface forecast data contextually.

## Scope
- Fetch signal health and recent forecasts on dashboard load
- Add a compact signals summary card to the dashboard
- Link to full signals page for details

## Files likely to change
- `apps/web/app/dashboard/page.tsx`

## Constraints
- Must not change the API or data model
- Must not break any existing dashboard functionality
- Keep the signals card compact and below the main sections
