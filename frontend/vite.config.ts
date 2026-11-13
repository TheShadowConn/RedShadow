import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { target: "es2022", sourcemap: false },
  server: {
    // Local `npm run dev` only; production traffic goes through nginx.
    proxy: { "/api": { target: "https://localhost", secure: false } },
  },
});
