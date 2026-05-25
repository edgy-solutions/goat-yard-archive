# ADR-0007: Availability and Outage Fallback

- **Status:** Proposed
- **Date:** 2026-05-24
- **Deciders:** Chris Nogradi

## Context

The system runs on a home server on a residential internet connection. Home internet outages of up to 24 hours have occurred and will recur — ISP maintenance, weather, hardware failures. When the home server is unreachable, the public site at goatyardarchive.org currently serves a generic Cloudflare 5xx error page.

A planned launch on Puritan Board changes the cost calculus around outages:

- A Puritan Board thread that lands on a 5xx page during a 24-hour ISP outage produces a credibility problem that lasts well beyond the outage itself. Visitors who hit an error the first time often don't return.
- The audience is theologically serious and patient with explanations — a maintenance page that's clearly explained and dignified is *not* a credibility hit. Silent failure is.
- Traffic from a Puritan Board thread can be modest-but-concentrated, not viral. A bad first impression matters more than a brief unavailability.

The other dimension: anything we build must be cheap and low-maintenance. The home server is the project's center of mass on purpose; we're not building toward a cloud-native deployment.

## Decision

A two-tier strategy. Tier 1 ships before launch; Tier 2 is a documented option for later, only if Tier 1 proves insufficient.

### Tier 1 — Static maintenance fallback via Cloudflare (launch-blocker)

When the home origin is unreachable, Cloudflare routes traffic to a static maintenance page hosted on Cloudflare Pages (free tier, same network as the proxy, low latency).

Components:

1. **Maintenance page** — a single static page at a separate Cloudflare Pages deployment (e.g. `gya-fallback.pages.dev`). Visual style matches the live site (same fonts, same color palette, same restrained 18th-century academic feel) so users understand they're looking at the same project, not a placeholder. Content:
   - Brief statement that the archive is temporarily unavailable.
   - One-sentence "voice" line in keeping with the project's tone (not impersonating Gill — that voice belongs to verbatim mode only — but referencing the historical character of the work).
   - Link to the GitHub repository for source-code curious visitors.
   - Optional: link to a static PDF or Markdown export of a subset of the commentary, so even during outages a serious reader can still consume Gill.
   - No login, no API calls, no JavaScript that depends on a backend — pure static HTML and CSS.

2. **Cloudflare routing rule** — a Cloudflare Worker or Page Rule that:
   - Checks origin health on each request (HEAD to `/health` with short timeout).
   - On unhealthy origin: rewrites the request to serve the maintenance page.
   - On healthy origin: passes through to the home server.
   - The check can be cached briefly (e.g. 30s) to avoid hammering origin during recovery.

3. **Origin healthcheck** — Cloudflare's existing `Always Online` feature provides a primitive baseline: it serves a cached version of the homepage when origin is down. This is *not enough* on its own (it doesn't handle API routes, it caches stale content), but combined with the Worker rewrite above it forms a robust fallback.

4. **Observability** — outages get logged. The simplest path: Cloudflare's analytics show 5xx rate from origin; we configure an alert for "5xx from origin > N%" that posts to the existing Slack channel where Dagster diagnostics already land.

### Tier 2 — Cold backup on cheap ARM cloud (deferred)

Only build if Tier 1 + observed outage patterns suggest the maintenance page alone isn't sufficient (e.g. an outage during a peak traffic moment when read access matters more than the dignified explanation).

Components:

1. **Backup compute** — Oracle Cloud Free Tier (4 ARM A1 cores + 24GB RAM, permanently free if not reaped) OR Hetzner CAX11 (~$3-5/month). The latter is more reliable; Oracle has been known to reclaim under-utilized free-tier instances.
2. **Data sync** — periodic snapshot of Weaviate index + MinIO bucket from home → backup node. Cadence: daily is probably fine for this content (Gill doesn't change). On the backup node, Weaviate + the backend container run in a low-resource configuration; some features (verbatim mode synthesis via OpenRouter LLM) still depend on external services and may degrade gracefully.
3. **DNS failover** — Cloudflare DNS health check, automatic failover to backup IP when home origin fails for > N minutes.
4. **Sync verification** — periodic check that backup-served queries return the same results as home-served queries, surfaced as Dagster asset metadata.

The maintenance page from Tier 1 is preserved as the *third* tier — if both home and backup are unreachable, the static page is the last line of defense.

## Alternatives Considered

1. **Do nothing — accept 5xx during outages.** Rejected for the launch reasons above. Acceptable in pre-launch where audience is small and forgiving.
2. **Cloudflare `Always Online` alone, no custom Worker.** Cloudflare caches the homepage and serves it when origin is down. Doesn't help with API routes (`/api/search`), can serve stale content without warning the user, and doesn't visually signal that the site is in a degraded state. Not enough on its own.
3. **Skip Tier 1, go straight to Tier 2 (hot backup).** Higher implementation cost, ongoing $3-5/month + sync complexity, and the maintenance page is still useful even with a backup (covers the case where both go down). Tier 1 → Tier 2 is the right ordering.
4. **Move primary hosting off home server entirely.** Defeats the project's small-footprint principle and changes the cost profile from "home electricity + ISP" to "cloud bill scales with usage". Not a fit for an indie-scale theological archive.
5. **Pre-render the entire archive as static HTML and serve from GitHub Pages.** Tempting for cost reasons, but loses the interactive search-and-synthesis features that are the project's main value. The maintenance page can *include* a link to such a static export as a degraded-mode read-only option, without the live site itself being static.

## Consequences

### Positive
- Brief outages become a minor UX bump rather than a credibility hit.
- Launch readiness no longer depends on home internet uptime during the launch window.
- Static page costs ~$0/month and ~1 hour to build.
- Visible degraded-state communication actually *helps* user trust — they understand the project's nature and constraints.

### Negative
- Adds a deployment surface (Cloudflare Pages) that needs to be kept in sync with the main site's visual style. Drift over time is a possibility.
- The Cloudflare Worker adds a small per-request latency overhead (microseconds for a healthcheck cache hit; ~50ms on cache miss). Acceptable.
- Tier 1 still loses any in-flight `/api/search` requests during outage; users get the maintenance page on retry rather than a successful response.

### Risks
- **Health check oscillation:** if origin is flapping (intermittent network), users see alternating maintenance/live pages within a session. Mitigation: cache the health state with a 30-second TTL and require N consecutive failures before flipping to maintenance mode.
- **Static fallback served when origin is healthy:** misconfigured rule could route traffic to maintenance page during normal operation. Mitigation: pre-launch smoke test (manually kill origin pod, verify failover; manually restore, verify return to live).
- **Tier 2 sync staleness:** if/when built, backup data could lag home data after ingestion runs. For a corpus that changes rarely, this is low-risk. Mitigation: surface "served from backup, data as of YYYY-MM-DD" banner on backup-served responses.

## Implementation Sketch (Tier 1)

```
1. Create gya-fallback.pages.dev on Cloudflare Pages with a single index.html
   that matches the live site's visual style. Commit the source under
   `frontend-fallback/` in this repo so it stays versioned alongside the project.

2. Create a Cloudflare Worker (or Page Rule) on the goatyardarchive.org zone:
     - Origin health check: HEAD https://origin/health, timeout 2s, cache 30s
     - On healthy: pass through
     - On unhealthy: fetch and return https://gya-fallback.pages.dev/index.html

3. Cloudflare alert: 5xx rate from origin > 20% over 5 min → Slack channel.

4. Pre-launch smoke test:
     - Stop backend pod on home cluster
     - Verify https://goatyardarchive.org serves maintenance page within 60s
     - Verify https://goatyardarchive.org/api/search returns maintenance page
       or graceful JSON error (not raw Cloudflare 502)
     - Restart backend pod
     - Verify return to normal within 60s
```

## Open Questions

- **Exact wording on the maintenance page** — needs to set the right tone. Probably worth a draft from the project owner, not a placeholder from an LLM.
- **Does the maintenance page link to a static read-only export of Gill?** Yes-or-no decision; if yes, what subset? A pre-rendered HTML of the corpus chapter-by-chapter is one option. Adds work but increases value of the degraded mode.
- **Should `/api/search` during maintenance return JSON (graceful API failure) or the HTML maintenance page (frontend handles it)?** API consumers would prefer JSON. Frontend users would prefer the page. Worth handling both based on `Accept` header.
- **Tier 2 trigger:** what specifically would motivate moving from Tier 1 to Tier 2? Probably: 2+ outages > 12 hours each in a 90-day window, OR a Puritan Board thread reaches viral threshold and outage happens during peak. Document a written trigger so the decision isn't ad-hoc later.

## Dependencies

- Independent of all other ADRs. Can ship in parallel with [ADR-0004](0004-reference-eval-set-and-ci-gates.md), [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md) Phase 5, and [ADR-0006](0006-verbatim-quote-verification.md).
- The Tier 2 cold-backup option would interact with the data-snapshot work mentioned in [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md) (entity index snapshots to MinIO with versioning). If both ship, share the snapshot infrastructure.
