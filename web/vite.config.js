import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
// Dev server proxies /api/* to the FastAPI backend (api/main.py), so the
// browser only ever talks to one origin. `npm run build`'s output (dist/)
// is served directly by FastAPI in a production-shaped run - see the
// StaticFiles mount in api/main.py.
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api": {
                target: "http://localhost:8001",
                changeOrigin: true,
            },
        },
    },
});
