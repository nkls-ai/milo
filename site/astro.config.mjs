import { defineConfig, fontProviders } from 'astro/config';

// Fonts come from the @fontsource packages and are copied into the build, so the page makes no
// requests to anyone else.
const fs = (path) => `./node_modules/@fontsource-variable/${path}`;

export default defineConfig({
  // Where the page lives. The GitHub Pages workflow sets both (https://nkls-ai.github.io and /milo); a real
  // domain later only changes the workflow. `site` is only used for the share-card URL.
  site: process.env.SITE_URL ?? 'https://milo.example',
  base: process.env.SITE_BASE ?? '/',
  build: { inlineStylesheets: 'always', format: 'file' },
  devToolbar: { enabled: false },
  fonts: [
    {
      provider: fontProviders.local(),
      name: 'Fraunces',
      cssVariable: '--font-display',
      fallbacks: ['Georgia', 'serif'],
      options: { variants: [{ src: [fs('fraunces/files/fraunces-latin-soft-normal.woff2')], weight: '100 900', style: 'normal' }] },
    },
    {
      provider: fontProviders.local(),
      name: 'Atkinson Hyperlegible Next',
      cssVariable: '--font-text',
      fallbacks: ['Arial', 'sans-serif'],
      options: {
        variants: [
          { src: [fs('atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-normal.woff2')], weight: '200 800', style: 'normal' },
          { src: [fs('atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-italic.woff2')], weight: '200 800', style: 'italic' },
        ],
      },
    },
  ],
});
