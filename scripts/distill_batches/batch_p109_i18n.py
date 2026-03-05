"""Internationalization — i18n patterns, locale handling, and translation workflows."""

PAIRS = [
    (
        "patterns/i18n-python",
        "Show Python internationalization patterns: gettext, locale formatting, ICU message format, and translation workflows.",
        '''Python internationalization patterns:

```python
import gettext
import locale
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from babel import numbers, dates
from babel.support import Translations


# --- gettext setup ---

LOCALE_DIR = Path("locales")

def setup_i18n(lang: str = "en") -> gettext.GNUTranslations:
    """Initialize gettext translations."""
    try:
        translations = gettext.translation(
            domain="messages",
            localedir=str(LOCALE_DIR),
            languages=[lang],
        )
        translations.install()
        return translations
    except FileNotFoundError:
        # Fall back to null translations (passthrough)
        return gettext.NullTranslations()


# Usage:
# t = setup_i18n("fr")
# _ = t.gettext
# ngettext = t.ngettext
#
# _("Hello, World!")               # "Bonjour, le monde !"
# ngettext("1 item", "%d items", count) % count


# --- Babel: locale-aware formatting ---

def format_currency(amount: Decimal, currency: str = "USD", loc: str = "en_US") -> str:
    """Format currency for locale."""
    return numbers.format_currency(amount, currency, locale=loc)

# format_currency(Decimal("1234.56"), "USD", "en_US")  # "$1,234.56"
# format_currency(Decimal("1234.56"), "EUR", "de_DE")  # "1.234,56\xa0€"
# format_currency(Decimal("1234.56"), "JPY", "ja_JP")  # "￥1,235"

def format_number(value: float, loc: str = "en_US") -> str:
    return numbers.format_decimal(value, locale=loc)

# format_number(1234567.89, "en_US")  # "1,234,567.89"
# format_number(1234567.89, "de_DE")  # "1.234.567,89"
# format_number(1234567.89, "fr_FR")  # "1 234 567,89"

def format_date_localized(dt: datetime, loc: str = "en_US", fmt: str = "long") -> str:
    return dates.format_date(dt, format=fmt, locale=loc)

# format_date_localized(now, "en_US")  # "June 15, 2024"
# format_date_localized(now, "de_DE")  # "15. Juni 2024"
# format_date_localized(now, "ja_JP")  # "2024年6月15日"

def format_relative(dt: datetime, loc: str = "en_US") -> str:
    return dates.format_timedelta(
        dt - datetime.now(timezone.utc),
        granularity="minute",
        locale=loc,
        add_direction=True,
    )

# format_relative(past, "en_US")  # "3 hours ago"
# format_relative(past, "fr_FR")  # "il y a 3 heures"


# --- Plural rules (ICU-style) ---

from babel.plural import to_python

def pluralize(count: int, forms: dict[str, str], loc: str = "en") -> str:
    """ICU-style pluralization.

    forms keys: 'zero', 'one', 'two', 'few', 'many', 'other'
    """
    from babel import Locale
    locale_obj = Locale.parse(loc)
    # Get plural category for this count in this locale
    category = locale_obj.plural_form(count)
    template = forms.get(category, forms.get("other", ""))
    return template.format(count=count)

# English: zero/one/other
# pluralize(0, {"one": "{count} item", "other": "{count} items"})  # "0 items"
# pluralize(1, {"one": "{count} item", "other": "{count} items"})  # "1 item"
#
# Arabic: zero/one/two/few/many/other (6 plural forms!)
# Russian: one/few/many/other (4 plural forms)


# --- Translation file management ---

# Directory structure:
# locales/
#   en/LC_MESSAGES/messages.po
#   fr/LC_MESSAGES/messages.po
#   de/LC_MESSAGES/messages.po
#
# Workflow:
# 1. Mark strings: _("Hello")
# 2. Extract: pybabel extract -o messages.pot src/
# 3. Init:    pybabel init -i messages.pot -d locales -l fr
# 4. Translate: edit locales/fr/LC_MESSAGES/messages.po
# 5. Compile:  pybabel compile -d locales
# 6. Update:   pybabel update -i messages.pot -d locales


# --- FastAPI i18n middleware ---

from fastapi import FastAPI, Request

app = FastAPI()

SUPPORTED_LOCALES = {"en", "fr", "de", "ja", "es"}
DEFAULT_LOCALE = "en"

@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    # Detect locale from Accept-Language header
    accept = request.headers.get("accept-language", DEFAULT_LOCALE)
    lang = accept.split(",")[0].split("-")[0].strip()

    if lang not in SUPPORTED_LOCALES:
        lang = DEFAULT_LOCALE

    request.state.locale = lang
    request.state.translations = setup_i18n(lang)
    response = await call_next(request)
    response.headers["Content-Language"] = lang
    return response
```

i18n patterns:
1. **`gettext`** — standard `.po/.mo` translation files with `_()` marking
2. **Babel formatting** — locale-aware numbers, currency, dates, and relative time
3. **Plural rules** — ICU categories (one/few/many/other) differ by language
4. **`Accept-Language` header** — detect user locale in middleware
5. **`pybabel` workflow** — extract → init → translate → compile → update'''
    ),
    (
        "frontend/i18n-react",
        "Show React internationalization with react-intl/i18next: message formatting, plurals, and locale switching.",
        '''React internationalization patterns:

```typescript
// --- react-i18next setup ---

import i18n from 'i18next';
import { initReactI18next, useTranslation, Trans } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import Backend from 'i18next-http-backend';

i18n
  .use(Backend)             // Load translations from /locales/
  .use(LanguageDetector)    // Detect user language
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'fr', 'de', 'ja', 'es'],

    interpolation: {
      escapeValue: false,  // React already escapes
    },

    // Namespaces for code splitting
    ns: ['common', 'auth', 'dashboard'],
    defaultNS: 'common',

    // Backend: load translation files
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },

    detection: {
      order: ['querystring', 'cookie', 'localStorage', 'navigator'],
      caches: ['localStorage', 'cookie'],
    },
  });


// --- Translation files ---

// /locales/en/common.json
// {
//   "greeting": "Hello, {{name}}!",
//   "items_count": "{{count}} item",
//   "items_count_plural": "{{count}} items",
//   "nav": {
//     "home": "Home",
//     "settings": "Settings",
//     "logout": "Log out"
//   }
// }

// /locales/fr/common.json
// {
//   "greeting": "Bonjour, {{name}} !",
//   "items_count": "{{count}} article",
//   "items_count_plural": "{{count}} articles",
//   "nav": {
//     "home": "Accueil",
//     "settings": "Paramètres",
//     "logout": "Déconnexion"
//   }
// }


// --- Using translations in components ---

function Dashboard() {
  const { t, i18n } = useTranslation();

  return (
    <div>
      {/* Simple string */}
      <h1>{t('greeting', { name: 'Alice' })}</h1>

      {/* Pluralization (automatic _plural suffix) */}
      <p>{t('items_count', { count: 5 })}</p>

      {/* Nested keys */}
      <nav>
        <a href="/">{t('nav.home')}</a>
        <a href="/settings">{t('nav.settings')}</a>
      </nav>

      {/* Rich text with components */}
      <Trans i18nKey="welcome_message">
        Welcome to <strong>MyApp</strong>.
        Read the <a href="/docs">documentation</a>.
      </Trans>

      {/* Language switcher */}
      <select
        value={i18n.language}
        onChange={(e) => i18n.changeLanguage(e.target.value)}
      >
        <option value="en">English</option>
        <option value="fr">Français</option>
        <option value="de">Deutsch</option>
        <option value="ja">日本語</option>
      </select>
    </div>
  );
}


// --- Number and date formatting with Intl ---

function FormattedPrice({ amount, currency = 'USD' }: {
  amount: number;
  currency?: string;
}) {
  const { i18n } = useTranslation();

  const formatted = new Intl.NumberFormat(i18n.language, {
    style: 'currency',
    currency,
  }).format(amount);

  return <span>{formatted}</span>;
}

function RelativeTime({ date }: { date: Date }) {
  const { i18n } = useTranslation();

  const rtf = new Intl.RelativeTimeFormat(i18n.language, { numeric: 'auto' });
  const diffMs = date.getTime() - Date.now();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));

  let formatted: string;
  if (Math.abs(diffHours) < 24) {
    formatted = rtf.format(diffHours, 'hour');
  } else {
    formatted = rtf.format(Math.round(diffHours / 24), 'day');
  }

  return <time dateTime={date.toISOString()}>{formatted}</time>;
}

// <FormattedPrice amount={1234.56} />
// en: "$1,234.56"  |  de: "1.234,56 $"  |  ja: "$1,234.56"

// <RelativeTime date={threeHoursAgo} />
// en: "3 hours ago"  |  fr: "il y a 3 heures"
```

React i18n patterns:
1. **Namespaced translations** — `common`, `auth`, `dashboard` for code-split loading
2. **`{{count}}`** — automatic pluralization with `_plural` suffix keys
3. **`<Trans>`** — rich text with embedded React components (bold, links)
4. **`Intl.NumberFormat`** — locale-aware currency/number formatting via browser API
5. **`Intl.RelativeTimeFormat`** — "3 hours ago" in any language'''
    ),
]
"""
