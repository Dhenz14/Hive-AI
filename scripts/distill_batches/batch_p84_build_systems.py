"""Build systems — monorepos, Turborepo, Nx, and build optimization."""

PAIRS = [
    (
        "devops/monorepo-patterns",
        "Show monorepo patterns: workspace organization, dependency management, and shared packages.",
        """Monorepo organization patterns:

```
# --- Monorepo structure ---

monorepo/
├── package.json             # Root workspace config
├── turbo.json               # Turborepo pipeline
├── tsconfig.base.json       # Shared TypeScript config
├── .github/
│   └── workflows/
│       └── ci.yml
├── apps/
│   ├── web/                 # Next.js frontend
│   │   ├── package.json
│   │   ├── tsconfig.json    # Extends base
│   │   └── src/
│   ├── api/                 # Express backend
│   │   ├── package.json
│   │   └── src/
│   └── mobile/              # React Native
│       ├── package.json
│       └── src/
├── packages/
│   ├── ui/                  # Shared component library
│   │   ├── package.json
│   │   └── src/
│   ├── utils/               # Shared utilities
│   │   ├── package.json
│   │   └── src/
│   ├── config-eslint/       # Shared ESLint config
│   │   ├── package.json
│   │   └── index.js
│   └── config-typescript/   # Shared TS config
│       ├── package.json
│       └── base.json
└── tooling/
    └── scripts/
```

```json
// Root package.json (pnpm workspaces)
{
  "name": "monorepo",
  "private": true,
  "scripts": {
    "build": "turbo build",
    "dev": "turbo dev",
    "lint": "turbo lint",
    "test": "turbo test",
    "clean": "turbo clean"
  },
  "devDependencies": {
    "turbo": "^2.0"
  }
}
```

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
  - "tooling/*"
```

```json
// packages/ui/package.json
{
  "name": "@monorepo/ui",
  "version": "0.1.0",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts",
    "./button": "./src/button.tsx",
    "./input": "./src/input.tsx"
  },
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "@monorepo/config-typescript": "workspace:*",
    "typescript": "^5.4"
  }
}
```

```json
// apps/web/package.json
{
  "name": "@monorepo/web",
  "dependencies": {
    "@monorepo/ui": "workspace:*",
    "@monorepo/utils": "workspace:*",
    "next": "^14.0"
  }
}
```

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],      // Build dependencies first
      "outputs": ["dist/**", ".next/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "lint": {
      "dependsOn": ["^build"]
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "clean": {
      "cache": false
    }
  }
}
```

Monorepo patterns:
1. **`workspace:*`** — internal package references, auto-resolved by pnpm
2. **`^build` dependsOn** — build dependencies before dependent packages
3. **Shared configs** — ESLint, TypeScript, Prettier as internal packages
4. **`exports` field** — explicit public API for internal packages
5. **Turborepo caching** — skip rebuilding unchanged packages"""
    ),
    (
        "devops/ci-optimization",
        "Show CI/CD optimization patterns: caching, parallel jobs, conditional builds, and matrix strategies.",
        """CI/CD optimization (GitHub Actions):

```yaml
# .github/workflows/ci.yml

name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

# Cancel in-progress runs for same PR
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # --- Detect changes (skip unnecessary jobs) ---
  changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
      docs: ${{ steps.filter.outputs.docs }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'apps/api/**'
              - 'packages/utils/**'
            frontend:
              - 'apps/web/**'
              - 'packages/ui/**'
            docs:
              - 'docs/**'
              - '*.md'

  # --- Backend tests (only if backend changed) ---
  backend-test:
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      # Cache dependencies
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync --frozen
      - run: uv run pytest --cov --junitxml=results.xml

      # Upload test results
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results-${{ matrix.python-version }}
          path: results.xml

  # --- Frontend build + test ---
  frontend:
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Cache pnpm store
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      # Turborepo remote cache
      - run: pnpm turbo build lint test --filter=@monorepo/web...
        env:
          TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
          TURBO_TEAM: ${{ vars.TURBO_TEAM }}

  # --- Deploy (only on main, after tests pass) ---
  deploy:
    needs: [backend-test, frontend]
    if: |
      always() &&
      github.ref == 'refs/heads/main' &&
      !contains(needs.*.result, 'failure')
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/deploy.sh

  # --- Reusable workflow call ---
  # security-scan:
  #   uses: ./.github/workflows/security.yml
  #   secrets: inherit
```

```yaml
# --- Reusable workflow ---
# .github/workflows/security.yml

name: Security Scan
on:
  workflow_call:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: python, javascript
      - uses: github/codeql-action/analyze@v3
```

CI/CD optimization patterns:
1. **Path filtering** — skip jobs when irrelevant files changed
2. **Concurrency groups** — cancel superseded runs on same PR
3. **Dependency caching** — `cache: 'pnpm'` / `enable-cache: true`
4. **Matrix strategy** — test across multiple Python/Node versions in parallel
5. **Reusable workflows** — `workflow_call` for shared security/deploy logic"""
    ),
    (
        "devops/github-actions-patterns",
        "Show GitHub Actions patterns: composite actions, environment protection, and artifact management.",
        """GitHub Actions advanced patterns:

```yaml
# --- Composite action (reusable step) ---
# .github/actions/setup-project/action.yml

name: Setup Project
description: Install dependencies and setup environment

inputs:
  node-version:
    description: Node.js version
    default: '20'
  install-playwright:
    description: Install Playwright browsers
    default: 'false'

runs:
  using: composite
  steps:
    - uses: pnpm/action-setup@v4
      shell: bash

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}
        cache: 'pnpm'

    - run: pnpm install --frozen-lockfile
      shell: bash

    - if: inputs.install-playwright == 'true'
      run: pnpm exec playwright install --with-deps chromium
      shell: bash

# Usage in workflow:
# - uses: ./.github/actions/setup-project
#   with:
#     install-playwright: 'true'


# --- Environment protection rules ---
# Configure in repo Settings > Environments

# production:
#   - Required reviewers: 2 team leads
#   - Wait timer: 5 minutes
#   - Deployment branches: main only
#   - Environment secrets: DEPLOY_KEY, AWS_ROLE_ARN


# --- Release workflow ---
# .github/workflows/release.yml

name: Release
on:
  push:
    tags: ['v*']

permissions:
  contents: write    # Create releases
  packages: write    # Push container images
  id-token: write    # OIDC for cloud auth

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build artifacts
        run: |
          pnpm install --frozen-lockfile
          pnpm build

      - name: Build Docker image
        run: |
          docker build -t ghcr.io/${{ github.repository }}:${{ github.ref_name }} .

      - name: Push to GHCR
        run: |
          echo ${{ secrets.GITHUB_TOKEN }} | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker push ghcr.io/${{ github.repository }}:${{ github.ref_name }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: |
            dist/*.tar.gz
            dist/*.whl


# --- Scheduled maintenance ---

name: Maintenance
on:
  schedule:
    - cron: '0 6 * * 1'  # Every Monday 6am UTC

jobs:
  dependency-update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - run: |
          pnpm update --latest
          pnpm audit

      - uses: peter-evans/create-pull-request@v6
        with:
          title: 'chore: weekly dependency updates'
          branch: deps/weekly-update
          commit-message: 'chore: update dependencies'
          body: |
            Automated weekly dependency update.
            Review changelog for breaking changes.


# --- Matrix with include/exclude ---

strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    node: [18, 20, 22]
    exclude:
      - os: windows-latest
        node: 18
    include:
      - os: ubuntu-latest
        node: 22
        experimental: true
```

GitHub Actions patterns:
1. **Composite actions** — reusable multi-step actions in `.github/actions/`
2. **Environment protection** — required reviewers + wait timers for production
3. **OIDC auth** — `id-token: write` for keyless cloud authentication
4. **`create-pull-request`** — automated PRs for dependency updates
5. **Matrix `include`/`exclude`** — fine-tune test combinations"""
    ),
]
