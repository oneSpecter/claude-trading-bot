/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg:     '#080d1a',
          card:   '#0a1020',
          border: '#1a2744',
          muted:  '#6b7fa3',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(59,130,246,0.4)' },
          '50%':      { boxShadow: '0 0 20px rgba(59,130,246,0.8)' },
        },
        'pulse-green': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(34,197,94,0.4)' },
          '50%':      { boxShadow: '0 0 20px rgba(34,197,94,0.8)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-4px)' },
        },
        'scan': {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        'border-spin': {
          '0%':   { '--angle': '0deg' },
          '100%': { '--angle': '360deg' },
        },
      },
      animation: {
        'pulse-glow':  'pulse-glow 2s ease-in-out infinite',
        'pulse-green': 'pulse-green 2s ease-in-out infinite',
        'float':       'float 3s ease-in-out infinite',
        'scan':        'scan 8s linear infinite',
      },
      backgroundImage: {
        'grid-pattern': "linear-gradient(rgba(30,45,74,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(30,45,74,0.3) 1px, transparent 1px)",
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
    },
  },
  plugins: [],
}
