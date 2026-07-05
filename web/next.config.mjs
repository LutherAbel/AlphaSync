/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep local dev and production build output isolated.
  // This prevents `next build` from invalidating the CSS/JS chunks served by `next dev`.
  distDir: process.env.NEXT_DIST_DIR || '.next',
};

export default nextConfig;
