/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Windows 11 color scheme
        win11: {
          primary: '#0067C0',
          primaryHover: '#004F92',
          secondary: '#605E5C',
          accent: '#0078D4',
          surface: '#F3F2F1',
          surfaceHover: '#EDEBE9',
          background: '#FEFEFE',
          card: '#FFFFFF',
          cardHover: '#F9F9F9',
          border: '#E1DFDD',
          text: {
            primary: '#323130',
            secondary: '#605E5C',
            tertiary: '#8A8886',
            inverse: '#FFFFFF'
          }
        }
      },
      fontFamily: {
        'segoe': ['Segoe UI', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        'win11': '8px',
        'win11-small': '4px',
        'win11-large': '12px',
      },
      boxShadow: {
        'win11': '0 8px 16px rgba(0, 0, 0, 0.14)',
        'win11-small': '0 2px 4px rgba(0, 0, 0, 0.14)',
        'win11-large': '0 16px 32px rgba(0, 0, 0, 0.18)',
        'win11-elevated': '0 32px 64px rgba(0, 0, 0, 0.24)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}