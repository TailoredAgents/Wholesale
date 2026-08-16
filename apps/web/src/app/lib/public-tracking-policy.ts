export const nonPublicTrackingRoutePrefixes = [
  "/os",
  "/leads",
  "/sign-in",
  "/sign-up",
  "/__clerk",
  "/auth",
  "/sso-callback",
] as const;

function matchesRoutePrefix(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/**
 * One policy controls every public-site browser measurement surface. Protected
 * workspaces and authentication screens must not initialize marketing scripts
 * or be counted as public traffic.
 */
export function isPublicTrackingPath(pathname: string) {
  if (!pathname.startsWith("/")) return false;
  return !nonPublicTrackingRoutePrefixes.some((prefix) => matchesRoutePrefix(pathname, prefix));
}
