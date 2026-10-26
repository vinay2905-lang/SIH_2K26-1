/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin (e.g. https://pramaan.example.org) when the frontend is hosted separately, as on Vercel. */
  readonly VITE_API_BASE?: string;
}
