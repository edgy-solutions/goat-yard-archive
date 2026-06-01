// Single Worker that fronts goatyardarchive.org:
//   - /api/*   → forwarded to the home cluster via the cloudflared tunnel
//   - /scans/* → same (Gill scan PNGs come from MinIO behind the tunnel)
//   - anything else → served from the static SPA bundle in frontend/dist
//
// TUNNEL_HOST is set in wrangler.jsonc and points at the public hostname
// the cloudflared tunnel exposes for the home cluster's ingress.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/scans/")) {
      const tunnelUrl = new URL(request.url);
      tunnelUrl.hostname = env.TUNNEL_HOST;
      return fetch(new Request(tunnelUrl, request));
    }

    return env.ASSETS.fetch(request);
  },
};
