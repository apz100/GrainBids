import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#121317",
        paper: "#fbf7ef",
        brass: "#b88b2a",
        slate: "#4a5568"
      }
    }
  },
  plugins: []
} satisfies Config;
