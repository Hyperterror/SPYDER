import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          bg:          '#070D14',
          surface:     '#0C141F',
          panel:       '#0E1724',
          panelHover:  '#131F30',
          border:      '#162338',
          borderLight: '#21334E',
          cyan:        '#00E5FF',
          cyanDim:     '#00A8BD',
          red:         '#FF4D4D',
          amber:       '#F59E0B',
          purple:      '#A855F7',
          green:       '#10B981',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'spin-slow':  'spin 1.5s linear infinite',
        'spider':     'spiderFloat 8s ease-in-out infinite',
      },
      keyframes: {
        spiderFloat: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-8px)' },
        },
      },
    },
  },
  plugins: [],
}

export default config
