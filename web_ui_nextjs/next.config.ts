import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Prevent CSS from being split into separate chunks — keeps all
  // styles in a single file so they can't partially fail to load.
  experimental: {
    cssChunking: false,
  },
};

export default nextConfig;
