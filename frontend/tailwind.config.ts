import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#1a365d",
          50: "#f0f4f8",
          100: "#d9e2ec",
          200: "#bcccdc",
          300: "#9fb3c8",
          400: "#829ab1",
          500: "#627d98",
          600: "#486581",
          700: "#334e68",
          800: "#243b53",
          900: "#1a365d",
        },
        blue: {
          light: "#2c5282",
        },
        gold: {
          DEFAULT: "#d4a574",
          50: "#fdf8f0",
          100: "#f9edd8",
          200: "#f0d8b0",
          300: "#e5c088",
          400: "#d4a574",
          500: "#c28a52",
          600: "#a8703c",
          700: "#8a5930",
          800: "#6e4727",
          900: "#5a3b21",
        },
      },
      fontFamily: {
        serif: ["Georgia", "Times New Roman", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
