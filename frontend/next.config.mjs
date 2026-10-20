import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @param {string} phase @returns {import('next').NextConfig} */
const nextConfig = (phase) => ({
  reactStrictMode: true,
  // A production build must not overwrite the running dev server's artifacts.
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
});

export default nextConfig;
