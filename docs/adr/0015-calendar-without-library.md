# ADR-0015 Calendar built in-house, not with FullCalendar

Status: accepted (2026-11-13, Phase 7)

**Decision:** The calendar is built with the existing components: a month and week grid where each engagement is a bar spanning its days, a list view, and pointer-based drag and resize for Super Admin. FullCalendar was tried and removed.

**Why:** nginx serves `style-src 'self'`, and FullCalendar injects its stylesheet at runtime, so it would be blocked. Loosening the CSP (or adding nonces to a static host) weakens a control for a view that does not need a library: engagements are whole-day ranges, so the time-grid parts of the library add nothing.

**Consequences:** No new dependency. Drag works with mouse and pen only; touch and keyboard use the Change dates dialog, which is also the accessible route. Overlapping bars are packed into lanes per week and rows grow with them; a month with hundreds of overlapping engagements would need a "more" control.
