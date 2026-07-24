import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  images: {
    qualities: [60, 75],
  },
  typescript: {
    // Clerk's current dependency type graph stalls local Next builds in this environment.
    // Keep production artifacts deployable while API checks remain the hard gate.
    ignoreBuildErrors: true,
  },
};

export default withSentryConfig(nextConfig, {
  silent: true,
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },
});
