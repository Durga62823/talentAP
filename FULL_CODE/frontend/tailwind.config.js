/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#070B16", 900: "#0B1120", 850: "#0F172A", 800: "#131C33", 700: "#1B2642", 600: "#26324F", 500: "#3A4766" },
        fog: { 100: "#E7ECF5", 300: "#B4BED2", 400: "#8C97AF", 500: "#6B7690" },
        accent: { DEFAULT: "#7C83FF", strong: "#6366F1", soft: "#7C83FF1F" },
        cyan: { DEFAULT: "#22D3EE", soft: "#22D3EE1A" },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI Variable", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "ui-monospace", "monospace"],
      },
      boxShadow: { card: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)" },
      keyframes: {
        fadein: { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: { fadein: "fadein .25s ease-out both" },
    },
  },
  plugins: [],
};
