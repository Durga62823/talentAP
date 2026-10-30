/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Strict Office Blue & White Design System Tokens
        office: {
          navy: "#123B67",
          primary: "#1D5FA7",
          secondary: "#3478C8",
          light: "#EAF2FB",
          pale: "#F4F8FD",
          white: "#FFFFFF",
          bg: "#F5F8FC",
          text: "#172B45",
          textSecondary: "#64748B",
          border: "#DCE5F0",
          muted: "#EEF3F9",
        },
        // Theme Aliases mapped to the Office Blue and White System
        ink: {
          950: "#F5F8FC", // Main page background
          900: "#FFFFFF", // Primary card and panel surface
          850: "#FFFFFF", // Modal and dropdown surface
          800: "#F4F8FD", // Subtle panel / table header background
          700: "#EEF3F9", // Muted surface / hover background
          600: "#DCE5F0", // Primary border
          500: "#64748B", // Secondary / caption text
        },
        fog: {
          100: "#172B45", // High-contrast primary text
          200: "#1A365D", // Dark navy body text
          300: "#2B4764", // Subheading text
          400: "#4B617E", // Medium text
          500: "#64748B", // Secondary text / placeholder
        },
        accent: {
          DEFAULT: "#1D5FA7",
          strong: "#123B67",
          soft: "#EAF2FB",
        },
        cyan: {
          DEFAULT: "#3478C8",
          soft: "#EAF2FB",
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI Variable", "Segoe UI", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(18, 59, 103, 0.06), 0 1px 2px -1px rgba(18, 59, 103, 0.04)",
        dropdown: "0 10px 25px -5px rgba(18, 59, 103, 0.1), 0 8px 10px -6px rgba(18, 59, 103, 0.06)",
        modal: "0 20px 25px -5px rgba(18, 59, 103, 0.15), 0 10px 10px -5px rgba(18, 59, 103, 0.08)",
      },
      keyframes: {
        fadein: { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: { fadein: "fadein .2s ease-out both" },
    },
  },
  plugins: [],
};
