"""Build tools — Vite, webpack, esbuild configuration and optimization."""

PAIRS = [
    (
        "tooling/vite-config",
        "Show Vite configuration patterns: plugins, aliases, env variables, proxy, and build optimization.",
        """Vite configuration patterns:

```typescript
// vite.config.ts
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      react({
        babel: {
          plugins: [
            ['babel-plugin-styled-components', { displayName: true }],
          ],
        },
      }),
      tsconfigPaths(),
      mode === 'analyze' && visualizer({
        open: true,
        gzipSize: true,
        filename: 'dist/stats.html',
      }),
    ],

    resolve: {
      alias: {
        '@': '/src',
        '@components': '/src/components',
        '@lib': '/src/lib',
      },
    },

    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: env.API_URL || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
        },
      },
    },

    build: {
      target: 'es2020',
      sourcemap: mode === 'production' ? 'hidden' : true,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            router: ['react-router-dom'],
            ui: ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu'],
          },
        },
      },
      chunkSizeWarningLimit: 500,
    },

    css: {
      modules: {
        localsConvention: 'camelCase',
      },
      preprocessorOptions: {
        scss: {
          additionalData: `@use "@/styles/variables" as *;`,
        },
      },
    },

    define: {
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
    },

    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov'],
        exclude: ['**/*.test.ts', '**/*.d.ts'],
      },
    },
  }
})
```

```typescript
// Custom Vite plugin
import type { Plugin } from 'vite'

function apiMockPlugin(): Plugin {
  return {
    name: 'api-mock',
    configureServer(server) {
      server.middlewares.use('/api/health', (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ status: 'ok' }))
      })
    },
  }
}

function buildTimestampPlugin(): Plugin {
  return {
    name: 'build-timestamp',
    transformIndexHtml(html) {
      return html.replace(
        '<!--BUILD_TIME-->',
        `<meta name="build-time" content="${new Date().toISOString()}">`
      )
    },
  }
}
```

Vite best practices:
1. **`manualChunks`** — split vendor code for better caching
2. **Proxy** — forward API calls to backend during development
3. **`loadEnv`** — access env vars in config (only `VITE_` prefixed in client)
4. **Conditional plugins** — only add analysis tools in specific modes
5. **CSS modules** — scoped styles with camelCase convention"""
    ),
    (
        "tooling/webpack-config",
        "Show webpack 5 configuration: module federation, code splitting, loaders, and optimization.",
        """Webpack 5 configuration patterns:

```javascript
// webpack.config.js
const path = require('path')
const HtmlWebpackPlugin = require('html-webpack-plugin')
const MiniCssExtractPlugin = require('mini-css-extract-plugin')
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin')
const { ModuleFederationPlugin } = require('webpack').container
const { BundleAnalyzerPlugin } = require('webpack-bundle-analyzer')

module.exports = (env, argv) => {
  const isProd = argv.mode === 'production'

  return {
    entry: './src/index.tsx',
    output: {
      path: path.resolve(__dirname, 'dist'),
      filename: isProd ? '[name].[contenthash:8].js' : '[name].js',
      chunkFilename: isProd ? '[name].[contenthash:8].chunk.js' : '[name].chunk.js',
      clean: true,
      publicPath: 'auto',
    },

    resolve: {
      extensions: ['.tsx', '.ts', '.js'],
      alias: { '@': path.resolve(__dirname, 'src') },
    },

    module: {
      rules: [
        {
          test: /\.tsx?$/,
          use: 'swc-loader',  // Faster than ts-loader or babel
          exclude: /node_modules/,
        },
        {
          test: /\.css$/,
          use: [
            isProd ? MiniCssExtractPlugin.loader : 'style-loader',
            {
              loader: 'css-loader',
              options: {
                modules: { auto: /\.module\.css$/ },
              },
            },
            'postcss-loader',
          ],
        },
        {
          test: /\.(png|jpe?g|gif|webp|avif)$/,
          type: 'asset',
          parser: { dataUrlCondition: { maxSize: 8 * 1024 } },
        },
        {
          test: /\.svg$/,
          use: ['@svgr/webpack'],
        },
      ],
    },

    plugins: [
      new HtmlWebpackPlugin({
        template: './public/index.html',
        minify: isProd,
      }),
      isProd && new MiniCssExtractPlugin({
        filename: '[name].[contenthash:8].css',
      }),
      env.analyze && new BundleAnalyzerPlugin(),
    ].filter(Boolean),

    optimization: {
      splitChunks: {
        chunks: 'all',
        cacheGroups: {
          vendor: {
            test: /[\\/]node_modules[\\/]/,
            name: 'vendor',
            chunks: 'all',
            priority: 10,
          },
          common: {
            minChunks: 2,
            priority: 5,
            reuseExistingChunk: true,
          },
        },
      },
      minimizer: ['...', new CssMinimizerPlugin()],
      runtimeChunk: 'single',
    },

    devServer: {
      port: 3000,
      hot: true,
      historyApiFallback: true,
      proxy: [
        {
          context: ['/api'],
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      ],
    },

    devtool: isProd ? 'source-map' : 'eval-source-map',
    cache: { type: 'filesystem' },
  }
}
```

```javascript
// Module Federation (micro-frontends)
// host/webpack.config.js
new ModuleFederationPlugin({
  name: 'host',
  remotes: {
    productApp: 'product@http://localhost:3001/remoteEntry.js',
    cartApp: 'cart@http://localhost:3002/remoteEntry.js',
  },
  shared: {
    react: { singleton: true, requiredVersion: '^18.0.0' },
    'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
  },
})

// remote/webpack.config.js
new ModuleFederationPlugin({
  name: 'product',
  filename: 'remoteEntry.js',
  exposes: {
    './ProductList': './src/components/ProductList',
    './ProductDetail': './src/components/ProductDetail',
  },
  shared: {
    react: { singleton: true },
    'react-dom': { singleton: true },
  },
})
```

Webpack tips:
1. **`contenthash`** — cache-bust only when file content changes
2. **`splitChunks`** — separate vendor code for long-term caching
3. **`swc-loader`** — 20x faster than babel-loader for TypeScript
4. **`filesystem` cache** — persistent cache across builds
5. **Module Federation** — share code between independently deployed apps"""
    ),
    (
        "tooling/esbuild-bundling",
        "Show esbuild patterns: fast bundling, plugins, and build scripts for production.",
        """Esbuild fast bundling patterns:

```typescript
// build.ts
import * as esbuild from 'esbuild'
import { copy } from 'esbuild-plugin-copy'

const isProd = process.env.NODE_ENV === 'production'

// --- Library build ---
async function buildLibrary() {
  // ESM output
  await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle: true,
    format: 'esm',
    outfile: 'dist/index.mjs',
    external: ['react', 'react-dom'],  // Peer deps
    sourcemap: true,
    minify: isProd,
    target: 'es2020',
    treeShaking: true,
  })

  // CJS output
  await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle: true,
    format: 'cjs',
    outfile: 'dist/index.cjs',
    external: ['react', 'react-dom'],
    sourcemap: true,
    minify: isProd,
    target: 'node18',
    platform: 'node',
  })
}


// --- Application build ---
async function buildApp() {
  const result = await esbuild.build({
    entryPoints: ['src/main.tsx'],
    bundle: true,
    format: 'esm',
    splitting: true,          // Code splitting
    outdir: 'dist',
    sourcemap: isProd ? 'external' : 'inline',
    minify: isProd,
    target: ['es2020', 'chrome90', 'firefox88', 'safari14'],
    metafile: true,           // Bundle analysis
    define: {
      'process.env.NODE_ENV': `"${process.env.NODE_ENV}"`,
      'process.env.API_URL': `"${process.env.API_URL || ''}"`,
    },
    loader: {
      '.png': 'file',
      '.svg': 'text',
      '.woff2': 'file',
    },
    plugins: [
      copy({ assets: [{ from: 'public/**/*', to: '.' }] }),
      envPlugin(),
    ],
  })

  // Print bundle analysis
  if (result.metafile) {
    const text = await esbuild.analyzeMetafile(result.metafile)
    console.log(text)
  }
}


// --- Custom plugin ---
function envPlugin(): esbuild.Plugin {
  return {
    name: 'env',
    setup(build) {
      // Replace process.env.* with actual values
      build.onResolve({ filter: /^env$/ }, () => ({
        path: 'env',
        namespace: 'env-ns',
      }))

      build.onLoad({ filter: /.*/, namespace: 'env-ns' }, () => ({
        contents: JSON.stringify(process.env),
        loader: 'json',
      }))
    },
  }
}

function cssModulesPlugin(): esbuild.Plugin {
  return {
    name: 'css-modules',
    setup(build) {
      build.onLoad({ filter: /\.module\.css$/ }, async (args) => {
        const css = await Bun.file(args.path).text()
        // Transform CSS module to JS with class name mapping
        const classNames: Record<string, string> = {}
        const transformed = css.replace(
          /\.([a-zA-Z_][\w-]*)/g,
          (_, name) => {
            const hash = name + '_' + Math.random().toString(36).slice(2, 6)
            classNames[name] = hash
            return '.' + hash
          },
        )
        return {
          contents: `
            const style = document.createElement('style')
            style.textContent = ${JSON.stringify(transformed)}
            document.head.appendChild(style)
            export default ${JSON.stringify(classNames)}
          `,
          loader: 'js',
        }
      })
    },
  }
}


// --- Dev server with live reload ---
async function devServer() {
  const ctx = await esbuild.context({
    entryPoints: ['src/main.tsx'],
    bundle: true,
    outdir: 'dist',
    sourcemap: 'inline',
    define: {
      'process.env.NODE_ENV': '"development"',
    },
  })

  await ctx.watch()
  const { host, port } = await ctx.serve({
    servedir: 'dist',
    port: 3000,
  })
  console.log(`Dev server: http://${host}:${port}`)
}


// --- Entry point ---
const command = process.argv[2]
if (command === 'dev') devServer()
else if (command === 'lib') buildLibrary()
else buildApp()
```

esbuild patterns:
1. **Dual format** — build ESM + CJS for library compatibility
2. **`splitting`** — code splitting for dynamic imports (ESM only)
3. **`metafile`** — analyze bundle size and dependencies
4. **`context` + `watch`** — incremental rebuilds for development
5. **10-100x faster** than webpack/rollup for most builds"""
    ),
]
