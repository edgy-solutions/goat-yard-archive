# ADR-0007: Availability and Outage Fallback

- **Status:** Proposed (revised 2026-05-25 — Tier 1 changed from separate-maintenance-page-via-Worker to in-app graceful degradation via Cloudflare Pages-hosted SPA)
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

### Tier 1 — In-app graceful degradation via Cloudflare-hosted SPA (launch-blocker)

The frontend SPA is hosted on Cloudflare Pages (free tier, CDN-distributed). The home cluster serves only `/api/*`. When the home backend is unreachable, the SPA still loads instantly from Cloudflare; it detects API failures in its existing error-handling path and renders a dignified inline "temporarily unavailable" UI rather than letting the page sit blank or showing a raw 502.

This is *graceful in-app degradation* — the user sees the real app with the real branding, with a clear inline status — rather than being redirected to a separate maintenance page.

Components:

1. **Frontend hosted on Cloudflare Pages.** The Vite/React build in `frontend/` deploys to Cloudflare Pages via GitHub integration (push-to-deploy). DNS for `goatyardarchive.org/*` (excluding `/api/*`) points at Pages. The build is fully static after Vite output; no server-side rendering, no runtime origin dependency for serving the SPA itself.

2. **Path-based routing in Cloudflare.** A Cloudflare Page Rule (or Worker if more control is needed) sends `/api/*` requests to the home origin and everything else to Cloudflare Pages. The SPA is *always* served regardless of home origin health.

3. **API client resilience in the SPA.** The frontend's fetch wrapper handles:
   - Network errors / `fetch` exceptions (origin unreachable).
   - HTTP 5xx (502 from Cloudflare, 500/503 from backend, gateway timeouts).
   - Configurable per-request timeout (e.g. 20s) with friendly cancellation.

   On any of these, the relevant UI surface renders a `<BackendUnavailable />` component instead of the failure-of-the-day default. Wording matches the project's restrained tone (one or two sentences, GitHub link, contact info).

4. **Cached non-volatile data.** The SPA fetches `/api/books` once and caches it in localStorage (with a TTL). This way the app's skeleton (book navigation, search shell) renders even on a cold visit during an API outage. Previous search results can optionally be cached the same way so a user who got an answer earlier can re-view it.

5. **Runtime config injection.** The current site does runtime injection of `__RUNTIME_CONFIG__` (Clerk publishable key, PostHog key, etc.) via server-side rendering of index.html. On Cloudflare Pages, runtime config is baked into the Vite build via Pages environment variables. Production has one config; rebuild on config change.

6. **Observability.** Cloudflare Analytics shows 5xx rate from origin; configure an alert for "5xx from origin > 20% over 5 min" posting to the existing Slack channel where Dagster diagnostics already land. SPA telemetry (PostHog) can also count `BackendUnavailable` renders per session.

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
2. **Cloudflare `Always Online` alone, no custom routing.** Cloudflare caches the homepage and serves it when origin is down. Doesn't help with API routes (`/api/search`), can serve stale content without warning the user, and doesn't visually signal that the site is in a degraded state. Not enough on its own.
3. **Separate static maintenance page via Cloudflare Worker (original Tier 1 design).** A Worker healthchecks origin and routes traffic to a *different* Cloudflare Pages deployment (`gya-fallback.pages.dev`) when origin is down. This was the original ADR-0007 design before the in-app degradation insight. Rejected on revision because:
   - It requires *two* deployment artifacts (live site + separate maintenance page) that must be kept visually in sync.
   - The Worker health-check round-trip adds latency on every request.
   - Users experience a "swap to a different site" rather than a clean inline error state — more jarring.
   - Doesn't preserve any client-side state (cached prior results, navigation context).

   The in-app degradation pattern achieves the same goal (don't show users a raw 5xx) with simpler architecture and better UX. The Worker approach remains a fallback if Cloudflare Pages free tier ever proves insufficient, but for the launch scope it's strictly inferior.
4. **Skip Tier 1, go straight to Tier 2 (hot backup).** Higher implementation cost, ongoing $3-5/month + sync complexity, and graceful in-app degradation is still useful even with a backup (covers the case where both home and backup are down, or the network path to backup is slow). Tier 1 → Tier 2 is the right ordering.
5. **Move primary hosting off home server entirely.** Defeats the project's small-footprint principle and changes the cost profile from "home electricity + ISP" to "cloud bill scales with usage". Not a fit for an indie-scale theological archive. Note that hosting the *frontend* on Cloudflare Pages is not this — it's a free CDN distribution of static build output, with zero ongoing cost.
6. **Pre-render the entire archive as static HTML and serve from GitHub Pages.** Tempting for cost reasons, but loses the interactive search-and-synthesis features that are the project's main value. The SPA's `BackendUnavailable` state can *link* to such a static export as a degraded-mode read-only option without the live site itself being static.

## Consequences

### Positive
- Brief outages become a minor UX bump rather than a credibility hit.
- Launch readiness no longer depends on home internet uptime during the launch window.
- Cloudflare Pages hosting costs ~$0/month.
- The frontend is now CDN-distributed globally, with faster initial loads everywhere (a free latency win even outside outage scenarios).
- Single deployment artifact (the SPA) — no separate maintenance page to keep visually in sync.
- The `<BackendUnavailable />` component lives in the React codebase alongside all other UI, so it gets the same review, theming, and i18n treatment as everything else.
- No health-check round-trip on every request; failure detection happens at the *individual API call* layer, which is more precise and lower-latency.

### Negative
- Frontend deploy pipeline changes: instead of building into the cluster container, build outputs go to Cloudflare Pages (via GitHub integration). One-time setup cost.
- Runtime config injection (currently server-side) must be replaced with build-time Vite env vars OR a small edge transform. Build-time is simpler; requires rebuild when keys rotate.
- Tier 1 still loses any in-flight `/api/search` requests during outage; users see the `<BackendUnavailable />` state on retry. (Same as the original design — unavoidable.)
- Splits hosting responsibility between Cloudflare (frontend) and home cluster (API). Slightly more conceptual overhead to debug "is it the frontend or the API?" but in practice the SPA's network panel makes this obvious.

### Risks
- **Cached SPA serves stale UI after a backend API contract change.** If the home backend deploys a breaking API change and the SPA is on an older Pages deploy, users see runtime errors. Mitigation: API versioning on the backend, and CI that builds + deploys SPA on every commit that touches `frontend/` or any shared types.
- **`<BackendUnavailable />` mis-triggers during transient errors.** A single failed request shouldn't permanently lock the user into the degraded state. Mitigation: per-request error state, retry button, exponential backoff. Component should re-attempt on user action, not stay sticky.
- **localStorage caching of search results raises privacy expectations.** If a user shares a device, cached prior searches may surprise them. Mitigation: scope cache to short TTL (e.g. 24h), expose a clear-cache control, document in the FAQ. The books-list cache is non-sensitive and can stay longer.
- **Tier 2 sync staleness:** if/when built, backup data could lag home data after ingestion runs. For a corpus that changes rarely, this is low-risk. Mitigation: surface "served from backup, data as of YYYY-MM-DD" banner on backup-served responses.
- **Cloudflare Pages free tier limits.** 500 builds/month and 100GB egress/month on the free tier. For a Puritan Board launch this is comfortable, but worth monitoring; an unusually-viral moment could brush the egress cap (mitigation: pay-as-you-go pricing kicks in cheaply if needed).

## Implementation Sketch (Tier 1)

```
1. Cloudflare Pages setup:
     - Connect this GitHub repo to a new Cloudflare Pages project.
     - Build command  : cd frontend && npm install && npm run build
     - Output dir     : frontend/dist
     - Env vars (build-time): VITE_CLERK_PUBLISHABLE_KEY, VITE_POSTHOG_KEY,
       VITE_POSTHOG_HOST, VITE_API_BASE (e.g. https://goatyardarchive.org/api)
     - Verify the deploy serves at gya.pages.dev (or whatever default).

2. DNS / routing in Cloudflare for goatyardarchive.org:
     - Default path (/*) -> Cloudflare Pages
     - /api/*           -> home origin (existing routing)
     - Confirm via curl that /api/health hits home and /index.html hits Pages.

3. Frontend resilience changes (in frontend/):
     - Create a fetch wrapper that catches network errors and 5xx, exposing
       them as a typed error to the React layer.
     - Create a <BackendUnavailable /> component matching the site's tone.
     - Wire the search page (and any other API-dependent surface) to render
       <BackendUnavailable /> on errors rather than empty / spinner-stuck states.
     - Cache /api/books in localStorage with a TTL on successful response so
       the app's chrome renders during a cold-start outage.
     - Optionally: cache the last N search responses similarly for re-view.

4. Runtime config migration:
     - Read VITE_* env vars in src/config.ts via import.meta.env.
     - Remove the server-side __RUNTIME_CONFIG__ injection from index.html
       (it stops being injected once SPA hosting moves to Pages).

5. Cloudflare alert: 5xx rate from origin > 20% over 5 min -> Slack channel.

6. Pre-launch smoke test:
     - Stop backend pod on home cluster.
     - Reload https://goatyardarchive.org -- SPA should load from Pages and
       immediately show <BackendUnavailable /> on the search page.
     - /api/search returns 502 (Cloudflare default for unreachable origin),
       which the SPA's fetch wrapper catches.
     - Restart backend pod; verify the SPA returns to normal on retry.
     - Verify no full page reload is needed for recovery.
```

## Open Questions

- **Exact copy for `<BackendUnavailable />`** — needs the project's tone, not LLM-generated placeholder text. One or two sentences. Probably worth drafting in the project owner's voice.
- **Should the degraded state link to a static read-only export of Gill?** Yes-or-no decision; if yes, what subset? A pre-rendered HTML of the corpus could live at a separate path on Cloudflare Pages. Adds work but increases value of the degraded mode.
- **Cached search history visibility.** Should the `<BackendUnavailable />` state surface the user's recent (locally-cached) search results, or just say "back shortly"? The former is more useful but exposes a new feature (search history) that the live site doesn't currently have. Defer until v2.
- **Tier 2 trigger:** what specifically would motivate moving from Tier 1 to Tier 2? Probably: 2+ outages > 12 hours each in a 90-day window, OR a Puritan Board thread reaches viral threshold and outage happens during peak. Document a written trigger so the decision isn't ad-hoc later.
- **API auth during outages.** Authenticated requests (Clerk) still need the home backend's auth middleware to validate tokens. If the SPA-cached state needs to remain useful when the backend is down, it should be tolerant of "user already authenticated locally but can't refresh server-side." For v1, just show the unavailable state for all API-dependent operations; defer cleverer caching.

## Dependencies

- Independent of all other ADRs. Can ship in parallel with [ADR-0004](0004-reference-eval-set-and-ci-gates.md), [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md) Phase 5, and [ADR-0006](0006-verbatim-quote-verification.md).
- The Tier 2 cold-backup option would interact with the data-snapshot work mentioned in [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md) (entity index snapshots to MinIO with versioning). If both ship, share the snapshot infrastructure.
