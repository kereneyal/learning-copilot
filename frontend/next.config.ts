import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Required for the Docker multi-stage build: copies only the files needed
  // to run `node server.js` into the final slim image (no node_modules bloat).
  output: "standalone",
}

export default nextConfig
