import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// On Vercel the backend runs elsewhere, so the build must be told where (see docs/DEPLOY.md).
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
if (env.VERCEL && !(env.VITE_API_BASE || "").startsWith("https://")) {
  throw new Error("Set the VITE_API_BASE environment variable in Vercel to your backend's https:// address, then redeploy.");
}

// In development the API runs on :8000; Vite proxies /api and /sandbox to it.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/sandbox": "http://127.0.0.1:8000",
    },
  },
});
