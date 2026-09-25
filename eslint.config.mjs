import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({
  baseDirectory: import.meta.dirname,
});

const config = [
  {
    ignores: [
      "**/.next/**",
      "**/dist/**",
      "**/node_modules/**",
      "**/coverage/**",
      "packages/api-client/src/schema.d.ts",
      // Next.js regenerates this on every `next dev`/`next build` (it says
      // "should not be edited") and, on newer Next 15.x, adds a triple-slash
      // reference to the gitignored .next/types directory that trips
      // @typescript-eslint/triple-slash-reference. Not hand-edited either way.
      "**/next-env.d.ts",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;
