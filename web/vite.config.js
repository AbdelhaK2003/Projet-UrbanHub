import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// en developpement, les appels /api sont transmis a l'API Python (port 8000)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
