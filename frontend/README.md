# Frontend

React + Vite + TypeScript + TailwindCSS + shadcn/ui application for the
Accessibility Remediation Framework.

## Setup

```bash
npm install
cp .env.example .env   # then fill in values
npm run dev            # http://localhost:5173
```

## Scripts

| Command                | Purpose                                   |
| ---------------------- | ----------------------------------------- |
| `npm run dev`          | Start the Vite dev server                 |
| `npm run build`        | Type-check and produce a production build |
| `npm run lint`         | Run ESLint                                |
| `npm run format`       | Format with Prettier                      |
| `npm run format:check` | Verify formatting                         |

## Conventions

- UI primitives live in `src/components/ui/` and are generated with the
  shadcn CLI: `npx shadcn@latest add <component>`.
- The `@/` path alias resolves to `src/`.
- Data fetching is centralized with React Query; routing uses React Router.
