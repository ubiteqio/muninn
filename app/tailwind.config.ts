import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

/**
 * The design tokens come from the start screen handoff. Colours are declared as HSL channels in
 * src/index.css so that shadcn/ui components pick them up, and named after the Norse palette
 * ("Rabenschwarz", "Bernstein") wherever the design refers to them by name.
 */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        /** Hairlines and glass surfaces the design specifies as literal rgba values. */
        // Dividers: light lines on Rabenschwarz, dark ones on Pergament.
        hairline: 'rgb(var(--hairline) / <alpha-value>)',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
        chip: '6px',
        badge: '5px',
        thumb: '8px',
        mark: '11px',
        'mark-lg': '13px',
      },
      fontFamily: {
        /** One typeface for the whole app. */
        sans: ['"Inter Variable"', 'Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['10.5px', { lineHeight: '1.2' }],
        '3xs': ['9.5px', { lineHeight: '1.1' }],
        xs: ['11px', { lineHeight: '1.3' }],
        'xs-plus': ['11.5px', { lineHeight: '1.35' }],
        sm: ['12px', { lineHeight: '1.4' }],
        'sm-plus': ['12.5px', { lineHeight: '1.4' }],
        base: ['13px', { lineHeight: '1.45' }],
        'base-plus': ['13.5px', { lineHeight: '1.45' }],
        md: ['14px', { lineHeight: '1.45' }],
        /** Form and section headings. */
        lg: ['18px', { lineHeight: '1.3' }],
        title: ['22px', { lineHeight: '1.15' }],
        'title-lg': ['23px', { lineHeight: '1.15' }],
      },
      letterSpacing: {
        section: '0.16em',
        wordmark: '0.15em',
        'wordmark-rail': '0.18em',
      },
      spacing: {
        'safe-bottom': 'env(safe-area-inset-bottom, 0px)',
        'safe-top': 'env(safe-area-inset-top, 0px)',
        rail: '96px',
        aside: '352px',
      },
      boxShadow: {
        handle: '0 0 14px rgba(244,200,120,0.35)',
        artboard: '0 40px 90px rgba(0,0,0,0.6)',
      },
      backdropBlur: {
        bar: '14px',
        nav: '18px',
        chip: '8px',
      },
      keyframes: {
        /**
         * Overlays only fade. The keyframes must leave transform alone: a dialog is centred with
         * translate(-50%, -50%), and an animation that writes transform would drop that centring
         * for the length of the animation and let the box drift into place.
         */
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'fade-out': {
          from: { opacity: '1' },
          to: { opacity: '0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'fade-out': 'fade-out 120ms ease-in',
      },
    },
  },
  plugins: [animate],
} satisfies Config
