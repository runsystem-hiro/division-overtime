/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NOTIFICATION_HISTORY_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
