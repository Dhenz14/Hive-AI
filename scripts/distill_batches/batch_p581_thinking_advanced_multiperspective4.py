"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 4/5)
Evaluate decisions from 5+ stakeholder or technical perspectives:
TypeScript adoption, database sharding, open source strategy, mobile architecture."""

PAIRS = [
    (
        "thinking/multiperspective-typescript-adoption",
        "We have a large JavaScript codebase (200K lines). Some team members want to migrate to TypeScript. Others say it's not worth the effort. How should we decide?",
        r'''<think>
Let me analyze TypeScript adoption from multiple stakeholder perspectives.

Perspective 1: Developer who supports TypeScript
- Types catch bugs before runtime: null reference, wrong argument types, missing properties
- IDE autocomplete and refactoring become vastly better
- Self-documenting: function signatures tell you what's expected
- "Every bug I catch with types is a bug that doesn't reach production"
- For 200K lines: types would have caught hundreds of existing bugs

Perspective 2: Developer who opposes TypeScript
- 200K lines = massive migration effort (months? years?)
- Learning curve: not everyone knows TypeScript
- Build complexity: need to set up tsc, deal with type definitions for dependencies
- Types slow down rapid prototyping: "I just want to try something quickly"
- "We've shipped this JS codebase successfully for years"

Perspective 3: Tech Lead / Architect
- Type safety at scale is nearly essential: 200K lines without types means refactoring is scary
- But: incremental migration is possible (TypeScript is a superset of JS)
- tsconfig can be set to "loose" initially, tightened over time
- Key question: what's our bug rate? If low, less urgency. If high, types help.

Perspective 4: Engineering Manager
- Migration time = time NOT building features
- But: bug fix time might decrease enough to offset
- Hiring: TypeScript is now the default for frontend — candidates expect it
- Team morale: developers who want TS may leave if denied
- Risk: forced migration on resistant team members causes resentment

Perspective 5: Product Manager
- "I don't care what language you use, I care about velocity and reliability"
- If types reduce bugs → fewer regressions → less re-work → faster feature delivery
- If migration slows feature delivery → bad for the business RIGHT NOW
- Need to see concrete ROI: "How many bugs per month would this prevent?"

Perspective 6: QA / Testing
- Types eliminate an entire category of bugs (type errors)
- Might reduce manual test coverage needed for happy-path type checking
- But: types don't replace tests for logic bugs
- Integration tests still needed

My synthesis:
- For 200K lines: gradual migration is the only sane approach
- Don't try to convert everything at once
- Start with: new code in TypeScript, gradually convert hot files
- The "TypeScript tax" (setup, learning) is front-loaded; benefits compound over time
- Hiring pressure alone may force the decision
</think>

This is ultimately a cost-benefit analysis where different stakeholders weight the factors differently. Here's the full picture.

**The perspective matrix:**

| Stakeholder | For TS | Against TS | Core concern |
|---|---|---|---|
| Pro-TS developer | Strong | — | Bug prevention, DX |
| Anti-TS developer | — | Strong | Migration effort, speed |
| Tech Lead | Moderate | — | Long-term maintainability |
| Eng Manager | — | Moderate | Feature velocity, team dynamics |
| Product Manager | Neutral | — | Wants data: bugs prevented vs time invested |
| QA | Moderate | — | Fewer type-related bugs to test for |

**Data to gather before deciding:**

```bash
# How many type-related bugs have you had?
# Search your bug tracker for: TypeError, "undefined is not a function",
# null reference, wrong argument, missing property

# If you find 5+ type-related bugs per month in production:
#   → TypeScript ROI is clear, migration justified
# If you find < 1 per month:
#   → TypeScript is nice-to-have, not urgent
```

**The only sane approach for 200K lines — gradual migration:**

```jsonc
// tsconfig.json — start loose, tighten over time
{
  "compilerOptions": {
    "allowJs": true,           // JS and TS coexist
    "checkJs": false,          // Don't type-check existing JS (yet)
    "strict": false,           // Start loose
    "noImplicitAny": false,    // Allow 'any' during migration
    "target": "ES2020",
    "module": "ESNext",
    "outDir": "./dist"
  },
  "include": ["src/**/*"]
}
```

```
Migration strategy:
Month 1:    Set up TypeScript toolchain, all NEW files in .ts
Month 2-3:  Convert the most-edited files (highest bug density)
Month 4-6:  Convert shared utilities and libraries
Month 6-12: Convert remaining files as they're touched
Month 12+:  Enable strict mode, tighten tsconfig

NEVER: "Stop all feature work, convert everything to TypeScript"
```

**Addressing each perspective's concern:**

```typescript
// For the anti-TS developer: "It slows me down"
// Reality: TypeScript is JavaScript + types. You can be as loose as you want.
function quickPrototype(data: any) {  // 'any' = opt out of types
    return data.whatever.you.want;     // No type checking here
}
// When the prototype is validated, add proper types later

// For the manager: "We need features, not migration"
// Strategy: convert files when you touch them for feature work
// git diff shows you changed 5 files for this feature
// Convert those 5 files to TypeScript as part of the PR
// Zero additional migration time — it happens naturally

// For the PM: "Show me the ROI"
// Track: bugs caught by TypeScript before production
// tsconfig: set "noImplicitAny": true on converted files
// After 3 months: report how many errors tsc caught that would have been bugs
```

**Decision framework:**

```
If team is > 5 developers AND codebase > 100K lines:
  → Gradual migration recommended (maintainability at scale)

If team is 2-3 developers AND codebase < 50K lines:
  → Optional (team preference matters more)

If hiring is a concern (competing for talent):
  → TypeScript helps attract frontend developers

If team is 50% against:
  → Start with "new files only in TS" — let the benefits prove themselves
  → Forcing migration on unwilling developers creates bad code

If rapid prototyping is critical (early-stage startup):
  → Keep JS for now, revisit when codebase stabilizes
```

The honest answer: for 200K lines with a growing team, you'll end up on TypeScript eventually. The question is just how quickly and how painfully. Gradual migration with "new code in TS" is the lowest-risk path.'''
    ),
    (
        "thinking/multiperspective-mobile-architecture",
        "We're building a mobile app. Should we go native (Swift/Kotlin), cross-platform (React Native/Flutter), or progressive web app (PWA)? Our team is 3 web developers and 1 mobile developer.",
        r'''<think>
Let me analyze this from multiple perspectives, especially considering their team composition: 3 web devs, 1 mobile dev.

Perspective 1: The 3 Web Developers
- React Native: STRONG PREFER — they already know React
- Flutter: MODERATE — new language (Dart) but familiar concepts
- Native (Swift/Kotlin): PAIN — completely new languages and ecosystems × 2
- PWA: STRONG PREFER — literally their existing skills
- Key tension: want to use existing skills vs learning new ones

Perspective 2: The 1 Mobile Developer
- Native: STRONG PREFER — this is their expertise
- React Native: MODERATE — different paradigm, but usable
- Flutter: MODERATE — new language but good mobile primitives
- PWA: PAIN — not "real" mobile development
- Key tension: wants to use their expertise, might feel sidelined by cross-platform

Perspective 3: Product Manager
- Time to market is key — which ships fastest?
- Cross-platform: 1 codebase for iOS + Android = faster
- Native: 2 codebases = roughly 2x development time
- Feature parity: cross-platform can lag behind native APIs
- "Can we access the camera, push notifications, offline mode?"

Perspective 4: Users
- They don't care what technology you used
- They care about: speed, smoothness, battery life, native feel
- Native: best performance and UX (users can tell)
- Cross-platform: good enough for most apps (90% case)
- PWA: weakest on iOS (limited push notifications, no App Store presence)

Perspective 5: CTO / Long-term thinking
- Hiring: easier to find React devs than Swift+Kotlin devs
- Maintenance: 1 codebase vs 2 codebases long-term
- Performance: if the app needs heavy graphics/animation, native wins
- Cost: cross-platform saves 30-50% on development

Perspective 6: Business model
- If app revenue depends on App Store (in-app purchases): need native/RN/Flutter
- If app is B2B internal: PWA might be sufficient
- If targeting specific platform features (AR, health sensors): native

Given their team (3 web, 1 mobile):
- React Native is the strongest fit: leverages 3 web devs, mobile dev can bridge native modules
- Flutter is second: everyone learns Dart, more mobile-native feel
- Native would leave 3 devs unable to contribute effectively
- PWA might not meet mobile feature requirements

My recommendation: React Native (or Expo) for their team composition, unless they need heavy native features.
</think>

With 3 web devs and 1 mobile dev, your team composition strongly influences this decision. Here's each option evaluated from every angle.

**Team capability vs. technology match:**

| Technology | 3 Web Devs | 1 Mobile Dev | Ramp-up time |
|---|---|---|---|
| React Native | Use existing React skills | Can write native modules | 2-3 weeks |
| Flutter | Learn Dart (moderate) | Learn Dart (moderate) | 4-6 weeks |
| Native (×2) | Learn Swift + Kotlin (hard) | Productive immediately | 3-6 months |
| PWA | Use existing skills | Underutilized | 0 weeks |

**Full perspective analysis:**

```
Users (what they experience):
  Native:       Smoothest, fastest, most "phone-like"
  React Native: 95% native feel, occasional jank
  Flutter:      Smooth animations, slightly non-native UI
  PWA:          Feels like a website in an app wrapper

Time to market (3 web + 1 mobile dev):
  React Native: ~3 months (leverages existing skills)
  Flutter:      ~4 months (learning Dart adds time)
  PWA:          ~2 months (existing skills, limited features)
  Native ×2:    ~8 months (most devs learning new platforms)

Long-term maintenance:
  React Native: 1 codebase, large npm ecosystem, Facebook-backed
  Flutter:      1 codebase, growing ecosystem, Google-backed
  PWA:          1 codebase, web ecosystem, limited mobile APIs
  Native:       2 codebases, 2 ecosystems, 2× maintenance

Hiring future developers:
  React Native: Easy (huge React talent pool)
  Flutter:      Moderate (growing fast but smaller pool)
  Native:       Hard (need separate iOS + Android specialists)
  PWA:          Easiest (any web developer)
```

**Decision based on what you're building:**

```
If your app is:                           Recommendation:
─────────────────────────────────────────────────────────
Content/social (feeds, profiles, forms)   React Native (Expo)
E-commerce (browse, cart, checkout)       React Native (Expo)
B2B dashboard / internal tool             PWA or React Native
Heavy animations / games                  Flutter or Native
Camera/AR/health sensors intensive        Native
Offline-first with complex sync           React Native or Native
Simple with push notifications            React Native (Expo)
```

**My recommendation for your team:**

```
React Native with Expo:

Why:
1. 3 of 4 developers are immediately productive (React)
2. Mobile developer writes native modules when needed
3. Expo handles 90% of native features without native code
4. Single codebase for iOS + Android
5. Hot reload for rapid iteration (web-developer friendly)
6. Largest cross-platform ecosystem (npm)

The 1 mobile developer's role:
  - Writes custom native modules for platform-specific features
  - Reviews bridge code and performance-sensitive components
  - Handles App Store / Play Store submissions
  - Mentors web devs on mobile UX patterns
```

```bash
# Get started in 5 minutes:
npx create-expo-app@latest MyApp
cd MyApp
npx expo start
# Scan QR code → app running on phone
# Your React devs can start building immediately
```

**When to NOT choose React Native:**

```
Choose Native if:
  ✗ You need AR/VR features (ARKit/ARCore)
  ✗ You need complex custom animations at 120fps
  ✗ You have budget for 2 separate native teams
  ✗ Your app IS the product (Snapchat-level native experience)

Choose Flutter if:
  ✗ Your team has no React experience
  ✗ You want pixel-perfect custom UI (Flutter's widget system is superior)
  ✗ You're building for mobile + web + desktop from one codebase

Choose PWA if:
  ✗ You don't need App Store distribution
  ✗ You don't need push notifications on iOS (limited)
  ✗ The app is essentially a mobile-optimized website
  ✗ Budget is extremely tight
```

For 3 web devs + 1 mobile dev building a typical app: React Native with Expo. Ship in 3 months, iterate from there.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
