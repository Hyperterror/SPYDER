/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow images from external domains (logo placeholders)
  images: {
    domains: ['lh3.googleusercontent.com'],
  },
}

module.exports = nextConfig
