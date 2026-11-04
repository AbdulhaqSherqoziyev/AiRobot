# Quant Lab web

Next.js control centre built from the QuantLab Claude Design project. Everything shown comes from
the backend API: no demo data is displayed. Run instructions are in `../quantlab/README.md`.

- `design-source/`: the design files as exported. Do not edit; change `PATCH` in the codemod.
- `scripts/dc2tsx.mjs`: codemod from `.dc.html` to TSX (`npm run gen:screens`). `PATCH` lists the
  deliberate changes to the design, `OVERRIDE` the screens replaced or extended.
- `src/screens/generated/`: codemod output. Do not edit by hand.
- `src/screens/live/`: subclasses connecting design screens to the API.
- `src/screens/*.tsx`: screens not in the design or hard-wired to demo data: Login, Optimizer,
  Evaluation, Live, Monitoring, Settings.
- `src/lib/backend.ts`: puts API data into the design's `QL` object, the seam for all screens.
- `src/app/api/q/`: proxy to the API. Secrets stay on the server.

Preview a state: `?demoState=loading|empty|error`.
