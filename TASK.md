# Task: Dashboard responsive/mobile improvements

## Objective
Make the dense dashboard table UI more usable on smaller screens through CSS responsive improvements.

## Background
The dashboard is described as "dense desktop-first table UI." It has 13-column tables, complex filter grids, and sections that don't adapt well to mobile.

## Scope
- Improve filter bar stacking on small screens
- Hide less important columns on mobile in preview table
- Reduce header/meta padding on mobile
- Compact the sections for smaller viewports
- No logic changes, only CSS/layout

## Files likely to change
- `apps/web/app/dashboard/page.tsx`

## Constraints
- Must not change functionality
- Must not break existing desktop layout
- Must not touch API or data logic
