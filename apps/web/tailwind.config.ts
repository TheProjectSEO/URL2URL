import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Custom fonts matching globals.css design system
      fontFamily: {
        display: ['var(--font-display)', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
        sans: ['var(--font-display)', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
      },

      // Custom animations matching globals.css
      animation: {
        'fade-in': 'fade-in 0.5s ease-out both',
        'slide-in-right': 'slide-in-right 0.4s ease-out both',
        'scale-in': 'scale-in 0.3s ease-out both',
        'shimmer': 'shimmer 2s linear infinite',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },

      // Custom spacing for larger layouts
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '112': '28rem',
        '128': '32rem',
      },

      // Backdrop blur values
      backdropBlur: {
        xs: '2px',
      },

      // Box shadow with accent glow
      boxShadow: {
        'glow': '0 0 20px -5px rgba(139, 92, 246, 0.3)',
        'glow-lg': '0 0 40px -10px rgba(139, 92, 246, 0.4)',
        'inner-glow': 'inset 0 0 20px rgba(139, 92, 246, 0.1)',
        'card': '0 4px 30px rgba(0, 0, 0, 0.15)',
        'elevated': '0 8px 40px rgba(0, 0, 0, 0.25)',
      },

      // Border radius values
      borderRadius: {
        '4xl': '2rem',
        '5xl': '2.5rem',
      },

      // Custom transition duration
      transitionDuration: {
        '250': '250ms',
        '350': '350ms',
        '400': '400ms',
      },

      // Custom screen breakpoints
      screens: {
        'xs': '475px',
        '3xl': '1800px',
      },

      // Typography scale
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.02em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem', letterSpacing: '-0.02em' }],
        '5xl': ['3rem', { lineHeight: '3.25rem', letterSpacing: '-0.02em' }],
      },

      // Line clamp utilities
      lineClamp: {
        7: '7',
        8: '8',
        9: '9',
        10: '10',
      },

      // Z-index scale
      zIndex: {
        '60': '60',
        '70': '70',
        '80': '80',
        '90': '90',
        '100': '100',
      },
    },
  },
  plugins: [],
} satisfies Config;
