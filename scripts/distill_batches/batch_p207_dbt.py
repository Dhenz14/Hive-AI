"""dbt (data build tool) and data lineage — models, testing, macros, Jinja, documentation."""

PAIRS = [
    (
        "data-engineering/dbt-models",
        "Show dbt model patterns including staging models, marts, incremental models, and ephemeral models with proper project structure and configuration.",
        '''dbt models: staging, marts, incremental, and ephemeral patterns:

```
dbt Project Structure:
models/
  staging/              # 1:1 with source tables
    stg_orders.sql
    stg_customers.sql
    stg_payments.sql
    _stg_models.yml     # schema + tests
  intermediate/         # Business logic joins
    int_orders_with_payments.sql
  marts/                # Business-facing models
    core/
      dim_customers.sql
      fct_orders.sql
    finance/
      fct_revenue.sql
    _core_models.yml
  _sources.yml          # Source definitions
```

```sql
-- models/_sources.yml (source definitions)

-- sources:
--   - name: raw
--     database: analytics
--     schema: raw_data
--     description: "Raw data from production database CDC"
--     loader: fivetran
--     loaded_at_field: _fivetran_synced
--     freshness:
--       warn_after: {count: 12, period: hour}
--       error_after: {count: 24, period: hour}
--     tables:
--       - name: orders
--         description: "Raw orders from e-commerce platform"
--         columns:
--           - name: id
--             tests: [unique, not_null]
--       - name: customers
--       - name: payments

-- models/staging/stg_orders.sql
-- Staging: rename, cast, and clean source data

WITH source AS (
    SELECT * FROM {{ source('raw', 'orders') }}
),

renamed AS (
    SELECT
        id                              AS order_id,
        customer_id,
        order_date::TIMESTAMP           AS ordered_at,
        status                          AS order_status,
        NULLIF(shipping_address, '')    AS shipping_address,
        total_amount_cents / 100.0      AS total_amount,
        currency,
        _fivetran_synced                AS synced_at
    FROM source
    WHERE id IS NOT NULL
      AND _fivetran_deleted = FALSE
)

SELECT * FROM renamed


-- models/staging/stg_customers.sql

WITH source AS (
    SELECT * FROM {{ source('raw', 'customers') }}
),

renamed AS (
    SELECT
        id                          AS customer_id,
        LOWER(TRIM(email))          AS email,
        first_name,
        last_name,
        CONCAT(first_name, ' ', last_name) AS full_name,
        UPPER(country_code)         AS country_code,
        created_at::TIMESTAMP       AS created_at,
        updated_at::TIMESTAMP       AS updated_at,
        CASE
            WHEN is_active = TRUE THEN 'active'
            ELSE 'inactive'
        END AS customer_status
    FROM source
    WHERE id IS NOT NULL
)

SELECT * FROM renamed


-- models/staging/stg_payments.sql

WITH source AS (
    SELECT * FROM {{ source('raw', 'payments') }}
),

renamed AS (
    SELECT
        id              AS payment_id,
        order_id,
        payment_method,
        amount_cents / 100.0 AS amount,
        status          AS payment_status,
        created_at::TIMESTAMP AS paid_at
    FROM source
    WHERE id IS NOT NULL
)

SELECT * FROM renamed
```

```sql
-- models/intermediate/int_orders_with_payments.sql
-- Intermediate: join and aggregate across staging models

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

payments AS (
    SELECT * FROM {{ ref('stg_payments') }}
),

order_payments AS (
    SELECT
        orders.order_id,
        orders.customer_id,
        orders.ordered_at,
        orders.order_status,
        orders.total_amount AS order_total,
        COALESCE(SUM(payments.amount), 0)     AS payment_total,
        COUNT(payments.payment_id)            AS payment_count,
        BOOL_OR(payments.payment_status = 'success') AS has_successful_payment,
        MIN(payments.paid_at)                 AS first_payment_at,
        MAX(payments.paid_at)                 AS last_payment_at
    FROM orders
    LEFT JOIN payments ON orders.order_id = payments.order_id
    GROUP BY 1, 2, 3, 4, 5
)

SELECT * FROM order_payments


-- models/marts/core/fct_orders.sql
-- Mart: business-facing fact table

{{
    config(
        materialized='table',
        schema='core',
        tags=['daily', 'core'],
        meta={'owner': 'analytics-team', 'pii': false},
    )
}}

WITH orders_with_payments AS (
    SELECT * FROM {{ ref('int_orders_with_payments') }}
),

customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
),

final AS (
    SELECT
        o.order_id,
        o.customer_id,
        c.full_name           AS customer_name,
        c.country_code,
        o.ordered_at,
        o.order_status,
        o.order_total,
        o.payment_total,
        o.payment_count,
        o.has_successful_payment,
        o.first_payment_at,
        CASE
            WHEN o.order_status = 'completed'
                AND o.has_successful_payment THEN 'fulfilled'
            WHEN o.order_status = 'cancelled' THEN 'cancelled'
            WHEN o.payment_total >= o.order_total THEN 'paid'
            WHEN o.payment_total > 0 THEN 'partially_paid'
            ELSE 'pending'
        END AS fulfillment_status,
        -- Jinja macro for surrogate key
        {{ dbt_utils.generate_surrogate_key(['o.order_id']) }}
            AS order_key
    FROM orders_with_payments o
    LEFT JOIN customers c ON o.customer_id = c.customer_id
)

SELECT * FROM final
```

```sql
-- models/marts/core/fct_orders_incremental.sql
-- Incremental model: only process new/changed data

{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns',
        cluster_by=['ordered_at'],
        tags=['hourly'],
    )
}}

WITH source_data AS (
    SELECT * FROM {{ ref('int_orders_with_payments') }}

    {% if is_incremental() %}
    -- Only process rows newer than the latest in target
    WHERE ordered_at > (
        SELECT MAX(ordered_at) FROM {{ this }}
    )
    -- Also catch late-arriving updates
    OR order_id IN (
        SELECT order_id FROM {{ ref('stg_orders') }}
        WHERE synced_at > (
            SELECT COALESCE(MAX(_dbt_loaded_at), '1970-01-01')
            FROM {{ this }}
        )
    )
    {% endif %}
),

final AS (
    SELECT
        *,
        CURRENT_TIMESTAMP() AS _dbt_loaded_at
    FROM source_data
)

SELECT * FROM final


-- models/marts/core/dim_customers.sql
-- Dimension table with SCD Type 2

{{
    config(
        materialized='table',
        schema='core',
    )
}}

WITH customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
),

orders AS (
    SELECT * FROM {{ ref('fct_orders') }}
),

customer_metrics AS (
    SELECT
        customer_id,
        COUNT(order_id)            AS total_orders,
        SUM(order_total)           AS lifetime_value,
        AVG(order_total)           AS avg_order_value,
        MIN(ordered_at)            AS first_order_at,
        MAX(ordered_at)            AS last_order_at,
        COUNT(DISTINCT DATE_TRUNC('month', ordered_at)) AS active_months
    FROM orders
    GROUP BY 1
),

final AS (
    SELECT
        c.customer_id,
        c.full_name,
        c.email,
        c.country_code,
        c.customer_status,
        c.created_at,
        COALESCE(m.total_orders, 0)    AS total_orders,
        COALESCE(m.lifetime_value, 0)  AS lifetime_value,
        COALESCE(m.avg_order_value, 0) AS avg_order_value,
        m.first_order_at,
        m.last_order_at,
        COALESCE(m.active_months, 0)   AS active_months,
        CASE
            WHEN m.lifetime_value > 10000 THEN 'premium'
            WHEN m.lifetime_value > 1000  THEN 'standard'
            WHEN m.lifetime_value > 0     THEN 'basic'
            ELSE 'prospect'
        END AS customer_segment,
        {{ dbt_utils.generate_surrogate_key(['c.customer_id']) }}
            AS customer_key
    FROM customers c
    LEFT JOIN customer_metrics m ON c.customer_id = m.customer_id
)

SELECT * FROM final
```

| Model Type | Materialization | When to Use | Performance |
|---|---|---|---|
| Staging (stg_) | View / ephemeral | 1:1 source, rename + cast | No storage cost (view) |
| Intermediate (int_) | Ephemeral / view | Cross-model joins, logic | No storage (ephemeral) |
| Fact (fct_) | Table / incremental | Business events | Full rebuild or merge |
| Dimension (dim_) | Table | Entity attributes | Full rebuild |
| Incremental | Incremental | Large tables, append/merge | Process only new rows |

Key patterns:

1. **Staging = source mirror** -- one staging model per source table, rename and cast only
2. **Intermediate = reusable logic** -- joins and business logic between staging and marts
3. **Marts = business-facing** -- fact and dimension tables organized by business domain
4. **Incremental for scale** -- use `is_incremental()` to process only new data
5. **merge strategy** -- use `unique_key` + `merge` for upsert semantics on incremental
6. **on_schema_change** -- `sync_all_columns` auto-handles new columns in incremental
7. **ref() everywhere** -- always use `ref()` to build the dependency DAG automatically'''
    ),
    (
        "data-engineering/dbt-testing",
        "Show dbt testing strategies including schema tests, custom tests, dbt-expectations, and data quality assertions in the CI/CD pipeline.",
        '''dbt testing: schema tests, custom tests, dbt-expectations, and CI/CD:

```yaml
# models/marts/core/_core_models.yml
# Schema-level tests

version: 2

models:
  - name: fct_orders
    description: "Fact table containing all processed orders with payment info"
    meta:
      owner: analytics-team
      pii: false
      sla: daily
    columns:
      - name: order_id
        description: "Primary key - unique order identifier"
        tests:
          - unique
          - not_null

      - name: customer_id
        description: "Foreign key to dim_customers"
        tests:
          - not_null
          - relationships:
              to: ref('dim_customers')
              field: customer_id

      - name: order_total
        description: "Total order amount in dollars"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000
              inclusive: true

      - name: order_status
        description: "Current order status"
        tests:
          - accepted_values:
              values: ['pending', 'processing', 'completed', 'cancelled', 'refunded']

      - name: ordered_at
        description: "Timestamp when order was placed"
        tests:
          - not_null
          - dbt_utils.not_null_proportion:
              at_least: 0.99

      - name: fulfillment_status
        tests:
          - accepted_values:
              values: ['fulfilled', 'cancelled', 'paid', 'partially_paid', 'pending']

      - name: country_code
        tests:
          - not_null:
              where: "order_status != 'cancelled'"

  - name: dim_customers
    description: "Customer dimension with lifetime metrics"
    columns:
      - name: customer_id
        tests:
          - unique
          - not_null

      - name: email
        tests:
          - unique
          - not_null
          # dbt-expectations for regex validation
          - dbt_expectations.expect_column_values_to_match_regex:
              regex: "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$"
              row_condition: "email IS NOT NULL"

      - name: lifetime_value
        tests:
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 0
              max_value: 1000000
              row_condition: "customer_status = 'active'"

      - name: customer_segment
        tests:
          - accepted_values:
              values: ['premium', 'standard', 'basic', 'prospect']
```

```sql
-- tests/generic/test_row_count_minimum.sql
-- Custom generic test: ensure minimum row count

{% test row_count_minimum(model, min_rows) %}

WITH row_count AS (
    SELECT COUNT(*) AS cnt FROM {{ model }}
)

SELECT cnt
FROM row_count
WHERE cnt < {{ min_rows }}

{% endtest %}


-- tests/generic/test_freshness_check.sql
-- Custom generic test: ensure data is fresh

{% test freshness_check(model, column_name, max_hours=24) %}

WITH latest AS (
    SELECT MAX({{ column_name }}) AS latest_value
    FROM {{ model }}
)

SELECT latest_value
FROM latest
WHERE latest_value < CURRENT_TIMESTAMP - INTERVAL '{{ max_hours }} hours'
   OR latest_value IS NULL

{% endtest %}


-- tests/generic/test_referential_integrity_percentage.sql
-- Allow a small percentage of orphaned records

{% test referential_integrity_pct(model, column_name, to, field, min_pct=99.0) %}

WITH total AS (
    SELECT COUNT(*) AS total_rows FROM {{ model }}
),
matched AS (
    SELECT COUNT(*) AS matched_rows
    FROM {{ model }} m
    INNER JOIN {{ to }} t ON m.{{ column_name }} = t.{{ field }}
),
result AS (
    SELECT
        (matched.matched_rows::FLOAT / NULLIF(total.total_rows, 0)) * 100
            AS match_pct
    FROM total, matched
)

SELECT match_pct
FROM result
WHERE match_pct < {{ min_pct }}

{% endtest %}


-- tests/singular/test_revenue_sanity_check.sql
-- Singular test: business rule validation

-- Revenue should not spike more than 5x day-over-day
WITH daily_revenue AS (
    SELECT
        DATE_TRUNC('day', ordered_at) AS order_day,
        SUM(order_total) AS revenue
    FROM {{ ref('fct_orders') }}
    WHERE ordered_at >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY 1
),

revenue_with_prev AS (
    SELECT
        order_day,
        revenue,
        LAG(revenue) OVER (ORDER BY order_day) AS prev_day_revenue
    FROM daily_revenue
)

SELECT
    order_day,
    revenue,
    prev_day_revenue,
    revenue / NULLIF(prev_day_revenue, 0) AS ratio
FROM revenue_with_prev
WHERE revenue / NULLIF(prev_day_revenue, 0) > 5.0
  AND prev_day_revenue > 100  -- Exclude low-volume days
```

```yaml
# dbt_project.yml - test configuration

name: analytics
version: '2.0.0'

vars:
  # dbt-expectations config
  dbt_expectations:
    dbt_date_src: dbt_date

# Test severity and thresholds
tests:
  +severity: warn  # Default to warn (override per-test)

# Model-specific test config
models:
  analytics:
    staging:
      +materialized: view
      +tags: ['staging']
    marts:
      core:
        +materialized: table
        +tags: ['core', 'daily']
        +tests:
          - row_count_minimum:
              min_rows: 1000
          - freshness_check:
              column_name: ordered_at
              max_hours: 24
              severity: error

---
# CI/CD: GitHub Actions for dbt testing

# .github/workflows/dbt-ci.yml
name: dbt CI
on:
  pull_request:
    paths: ['models/**', 'tests/**', 'macros/**']

jobs:
  dbt-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dbt
        run: pip install dbt-postgres dbt-utils dbt-expectations

      - name: dbt deps
        run: dbt deps

      - name: dbt build (compile + run + test)
        run: |
          dbt build \
            --target ci \
            --select state:modified+ \
            --defer --state ./prod-manifest/ \
            --fail-fast

      - name: dbt test (run all tests)
        run: |
          dbt test \
            --target ci \
            --select state:modified+ \
            --defer --state ./prod-manifest/

      - name: dbt docs generate
        run: dbt docs generate

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: dbt-test-results
          path: target/run_results.json
```

| Test Type | Scope | Defined In | Example |
|---|---|---|---|
| Schema (generic) | Column-level | _models.yml | `unique`, `not_null`, `accepted_values` |
| dbt-expectations | Column-level | _models.yml | `expect_column_values_to_match_regex` |
| Custom generic | Column/model | tests/generic/ | `row_count_minimum`, `freshness_check` |
| Singular | Model-specific | tests/singular/ | Business rule validation (SQL file) |
| Source freshness | Source table | _sources.yml | `freshness: warn_after: {count: 12, period: hour}` |

Key patterns:

1. **Test every primary key** -- `unique` + `not_null` on every model's primary key
2. **Test every foreign key** -- `relationships` test ensures referential integrity
3. **dbt-expectations** -- use for regex, range, distribution, and statistical tests
4. **Singular tests for business rules** -- SQL-based tests for domain-specific validations
5. **state:modified+** -- in CI, only test models affected by the PR (speed + relevance)
6. **Severity levels** -- `error` blocks deployment, `warn` logs but continues
7. **Freshness checks** -- monitor source and model freshness to catch pipeline failures'''
    ),
    (
        "data-engineering/dbt-macros-jinja",
        "Show dbt macros and Jinja templating including reusable SQL, dynamic model generation, cross-database compatibility, and custom materializations.",
        '''dbt macros and Jinja templating: reusable SQL, dynamic models, and cross-DB support:

```sql
-- macros/generate_surrogate_key.sql
-- Custom surrogate key generator (alternative to dbt_utils)

{% macro generate_surrogate_key(field_list) %}
    {%- set fields = [] -%}
    {%- for field in field_list -%}
        {%- do fields.append(
            "COALESCE(CAST(" ~ field ~ " AS VARCHAR), '_null_')"
        ) -%}
    {%- endfor -%}

    {{ dbt.hash(dbt.concat(fields)) }}
{% endmacro %}


-- macros/cents_to_dollars.sql
-- Simple conversion macro

{% macro cents_to_dollars(column_name, precision=2) %}
    ROUND({{ column_name }} / 100.0, {{ precision }})
{% endmacro %}


-- macros/safe_divide.sql
-- Prevent division by zero

{% macro safe_divide(numerator, denominator, default=0) %}
    CASE
        WHEN {{ denominator }} = 0 OR {{ denominator }} IS NULL
        THEN {{ default }}
        ELSE {{ numerator }}::FLOAT / {{ denominator }}
    END
{% endmacro %}


-- Usage in a model:
-- SELECT
--     order_id,
--     {{ cents_to_dollars('amount_cents') }} AS amount,
--     {{ safe_divide('revenue', 'order_count') }} AS avg_revenue,
--     {{ generate_surrogate_key(['order_id', 'customer_id']) }} AS order_key
-- FROM orders
```

```sql
-- macros/generate_schema_name.sql
-- Custom schema naming strategy

{% macro generate_schema_name(custom_schema_name, node) %}
    {%- set default_schema = target.schema -%}

    {%- if target.name == 'production' -%}
        {# In production, use the custom schema directly #}
        {%- if custom_schema_name is not none -%}
            {{ custom_schema_name | trim }}
        {%- else -%}
            {{ default_schema }}
        {%- endif -%}
    {%- else -%}
        {# In dev/CI, prefix with target schema #}
        {%- if custom_schema_name is not none -%}
            {{ default_schema }}_{{ custom_schema_name | trim }}
        {%- else -%}
            {{ default_schema }}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}


-- macros/grant_select.sql
-- Post-hook macro to grant access after model builds

{% macro grant_select(schema, role) %}
    {% set grant_sql %}
        GRANT USAGE ON SCHEMA {{ schema }} TO ROLE {{ role }};
        GRANT SELECT ON ALL TABLES IN SCHEMA {{ schema }} TO ROLE {{ role }};
    {% endset %}
    {% do run_query(grant_sql) %}
    {{ log("Granted SELECT on " ~ schema ~ " to " ~ role, info=True) }}
{% endmacro %}


-- macros/date_spine.sql
-- Generate a date dimension

{% macro date_spine(start_date, end_date) %}
    WITH date_spine AS (
        {{ dbt_utils.date_spine(
            datepart="day",
            start_date="'" ~ start_date ~ "'",
            end_date="'" ~ end_date ~ "'"
        ) }}
    )

    SELECT
        date_day,
        EXTRACT(YEAR FROM date_day)     AS year,
        EXTRACT(MONTH FROM date_day)    AS month,
        EXTRACT(DAY FROM date_day)      AS day_of_month,
        EXTRACT(DOW FROM date_day)      AS day_of_week,
        TO_CHAR(date_day, 'Day')        AS day_name,
        TO_CHAR(date_day, 'Month')      AS month_name,
        EXTRACT(QUARTER FROM date_day)  AS quarter,
        CASE
            WHEN EXTRACT(DOW FROM date_day) IN (0, 6) THEN FALSE
            ELSE TRUE
        END AS is_weekday,
        DATE_TRUNC('week', date_day)    AS week_start,
        DATE_TRUNC('month', date_day)   AS month_start,
        DATE_TRUNC('quarter', date_day) AS quarter_start
    FROM date_spine
{% endmacro %}
```

```sql
-- macros/dynamic_union.sql
-- Dynamically union tables matching a pattern

{% macro union_tables_by_prefix(schema, prefix) %}
    {%- set tables = dbt_utils.get_relations_by_prefix(
        schema=schema,
        prefix=prefix,
    ) -%}

    {%- if tables | length == 0 -%}
        {{ exceptions.raise_compiler_error(
            "No tables found with prefix '" ~ prefix ~ "' in schema '" ~ schema ~ "'"
        ) }}
    {%- endif -%}

    {%- for table in tables -%}
        SELECT
            '{{ table.identifier }}' AS source_table,
            *
        FROM {{ table }}
        {%- if not loop.last %} UNION ALL {% endif -%}
    {%- endfor -%}
{% endmacro %}


-- macros/pivot_metrics.sql
-- Dynamic pivot macro

{% macro pivot_metric(column, values, agg='SUM', alias_prefix='') %}
    {%- for val in values %}
        {{ agg }}(
            CASE WHEN {{ column }} = '{{ val }}' THEN 1 ELSE 0 END
        ) AS {{ alias_prefix }}{{ val | replace(' ', '_') | lower }}
        {%- if not loop.last %},{% endif -%}
    {%- endfor -%}
{% endmacro %}


-- Usage:
-- SELECT
--     customer_id,
--     {{ pivot_metric(
--         column='order_status',
--         values=['pending', 'completed', 'cancelled'],
--         agg='COUNT',
--         alias_prefix='orders_'
--     ) }}
-- FROM orders
-- GROUP BY 1


-- macros/cross_db_compat.sql
-- Cross-database compatibility macros

{% macro current_timestamp_utc() %}
    {%- if target.type == 'postgres' -%}
        CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
    {%- elif target.type == 'snowflake' -%}
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())
    {%- elif target.type == 'bigquery' -%}
        CURRENT_TIMESTAMP()
    {%- elif target.type == 'redshift' -%}
        GETDATE()
    {%- else -%}
        CURRENT_TIMESTAMP
    {%- endif -%}
{% endmacro %}

{% macro string_agg(column, separator=', ', order_by=none) %}
    {%- if target.type == 'postgres' -%}
        STRING_AGG({{ column }}, '{{ separator }}'
            {% if order_by %} ORDER BY {{ order_by }} {% endif %})
    {%- elif target.type == 'snowflake' -%}
        LISTAGG({{ column }}, '{{ separator }}')
            {% if order_by %} WITHIN GROUP (ORDER BY {{ order_by }}) {% endif %}
    {%- elif target.type == 'bigquery' -%}
        STRING_AGG({{ column }}, '{{ separator }}'
            {% if order_by %} ORDER BY {{ order_by }} {% endif %})
    {%- endif -%}
{% endmacro %}
```

```yaml
# dbt_project.yml - macro configuration

name: analytics
version: '2.0.0'

# Global vars accessible in macros
vars:
  start_date: '2024-01-01'
  default_currency: 'USD'
  environments:
    production:
      schema_prefix: ''
    development:
      schema_prefix: 'dev_'

# Post-hooks for access control
models:
  analytics:
    marts:
      +post-hook:
        - "{{ grant_select(this.schema, 'analytics_readers') }}"
      core:
        +materialized: table
      finance:
        +materialized: table
        +post-hook:
          - "{{ grant_select(this.schema, 'finance_team') }}"

# Dispatch config for cross-db macros
dispatch:
  - macro_namespace: dbt
    search_order: ['analytics', 'dbt']
```

| Macro Category | Example | Purpose |
|---|---|---|
| Data transformation | `cents_to_dollars`, `safe_divide` | Reusable column transforms |
| Key generation | `generate_surrogate_key` | Consistent primary keys |
| Schema management | `generate_schema_name` | Environment-specific schemas |
| Dynamic SQL | `union_tables_by_prefix`, `pivot_metric` | Code generation from metadata |
| Cross-database | `current_timestamp_utc`, `string_agg` | Warehouse-agnostic SQL |
| Access control | `grant_select` | Post-hook permission grants |
| Date utilities | `date_spine` | Generate date dimensions |

Key patterns:

1. **Thin staging, thick macros** -- keep staging models simple; push reusable logic into macros
2. **Cross-DB dispatch** -- use `dispatch` config to override macros per database adapter
3. **generate_schema_name** -- customize schema naming to separate dev/prod without duplicating code
4. **Post-hooks for grants** -- auto-grant SELECT after model materializes
5. **Dynamic unions** -- use `get_relations_by_prefix` to union similarly named tables
6. **var() for config** -- use `var()` for environment-specific values, not hardcoded strings
7. **Macro testing** -- test macros by creating models that exercise them and adding schema tests'''
    ),
    (
        "data-engineering/dbt-lineage-documentation",
        "Show dbt data lineage, documentation generation, exposures, and how to build a data catalog from dbt metadata.",
        '''dbt data lineage, documentation, exposures, and data catalog:

```yaml
# models/marts/core/_core_models.yml
# Complete documentation with lineage metadata

version: 2

models:
  - name: fct_orders
    description: |
      **Fact table containing all processed orders with payment info.**

      This model joins staging orders with payment aggregations to produce
      a single row per order with fulfillment status and payment details.

      ### Grain
      One row per `order_id`.

      ### Update Frequency
      Daily at 06:00 UTC via Airflow DAG `dbt_daily_build`.

      ### Known Issues
      - Orders from legacy system (pre-2024) may have NULL `country_code`
      - Refund amounts are negative in `payment_total`
    meta:
      owner: analytics-team
      contains_pii: false
      data_classification: internal
      sla:
        freshness_hours: 24
        completeness_pct: 99.5
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [order_id]
      - row_count_minimum:
          min_rows: 10000

    columns:
      - name: order_id
        description: "Primary key. Unique identifier for each order."
        meta:
          is_primary_key: true
        tests:
          - unique
          - not_null

      - name: customer_id
        description: "Foreign key to `dim_customers`."
        meta:
          is_foreign_key: true
          references: dim_customers.customer_id

      - name: fulfillment_status
        description: |
          Derived fulfillment status based on order status and payment:
          - `fulfilled`: Order completed with successful payment
          - `paid`: Payment received, awaiting fulfillment
          - `partially_paid`: Some payment received
          - `pending`: No payment yet
          - `cancelled`: Order cancelled
        tests:
          - accepted_values:
              values: ['fulfilled', 'cancelled', 'paid', 'partially_paid', 'pending']


# --- Exposures: document downstream consumers ---

exposures:
  - name: weekly_revenue_dashboard
    type: dashboard
    description: |
      Executive dashboard showing weekly revenue metrics,
      customer acquisition, and fulfillment rates.
    maturity: high
    url: https://looker.example.com/dashboards/42
    owner:
      name: Analytics Team
      email: analytics@example.com
    depends_on:
      - ref('fct_orders')
      - ref('dim_customers')
      - ref('fct_revenue')
    tags: ['executive', 'revenue']

  - name: churn_prediction_model
    type: ml
    description: |
      ML model predicting customer churn probability.
      Trained weekly on customer lifetime metrics.
    maturity: medium
    url: https://mlflow.example.com/experiments/15
    owner:
      name: ML Team
      email: ml-team@example.com
    depends_on:
      - ref('dim_customers')
      - ref('fct_orders')

  - name: order_api
    type: application
    description: |
      REST API serving order data to the customer-facing portal.
      Reads from the `fct_orders` table in real-time.
    maturity: high
    owner:
      name: Backend Team
      email: backend@example.com
    depends_on:
      - ref('fct_orders')
```

```python
# --- Parse dbt manifest for lineage analysis ---

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DbtNode:
    """Parsed dbt node from manifest.json."""
    unique_id: str
    name: str
    resource_type: str  # "model", "source", "test", "exposure"
    schema: str
    database: str
    materialized: str
    description: str
    columns: dict[str, dict]
    depends_on: list[str]
    tags: list[str]
    meta: dict
    owner: str = ""


class DbtLineageParser:
    """Parse dbt manifest.json for lineage analysis."""

    def __init__(self, manifest_path: Path) -> None:
        with open(manifest_path) as f:
            self.manifest = json.load(f)

        self.nodes: dict[str, DbtNode] = {}
        self._parse_nodes()

    def _parse_nodes(self) -> None:
        """Parse all nodes from manifest."""
        for uid, node_data in self.manifest.get("nodes", {}).items():
            self.nodes[uid] = DbtNode(
                unique_id=uid,
                name=node_data.get("name", ""),
                resource_type=node_data.get("resource_type", ""),
                schema=node_data.get("schema", ""),
                database=node_data.get("database", ""),
                materialized=node_data.get("config", {}).get(
                    "materialized", "view"
                ),
                description=node_data.get("description", ""),
                columns=node_data.get("columns", {}),
                depends_on=node_data.get("depends_on", {}).get("nodes", []),
                tags=node_data.get("tags", []),
                meta=node_data.get("meta", {}),
            )

        # Parse sources
        for uid, source_data in self.manifest.get("sources", {}).items():
            self.nodes[uid] = DbtNode(
                unique_id=uid,
                name=source_data.get("name", ""),
                resource_type="source",
                schema=source_data.get("schema", ""),
                database=source_data.get("database", ""),
                materialized="source",
                description=source_data.get("description", ""),
                columns=source_data.get("columns", {}),
                depends_on=[],
                tags=source_data.get("tags", []),
                meta=source_data.get("meta", {}),
            )

        # Parse exposures
        for uid, exp_data in self.manifest.get("exposures", {}).items():
            self.nodes[uid] = DbtNode(
                unique_id=uid,
                name=exp_data.get("name", ""),
                resource_type="exposure",
                schema="",
                database="",
                materialized="exposure",
                description=exp_data.get("description", ""),
                columns={},
                depends_on=exp_data.get("depends_on", {}).get("nodes", []),
                tags=exp_data.get("tags", []),
                meta=exp_data.get("meta", {}),
                owner=exp_data.get("owner", {}).get("name", ""),
            )

    def get_upstream(self, node_id: str, depth: int = -1) -> list[str]:
        """Get all upstream dependencies (ancestors)."""
        visited = set()

        def _walk(nid: str, current_depth: int) -> None:
            if nid in visited:
                return
            if depth >= 0 and current_depth > depth:
                return
            visited.add(nid)
            node = self.nodes.get(nid)
            if node:
                for dep in node.depends_on:
                    _walk(dep, current_depth + 1)

        _walk(node_id, 0)
        visited.discard(node_id)
        return list(visited)

    def get_downstream(self, node_id: str) -> list[str]:
        """Get all downstream dependents (children)."""
        downstream = set()
        for uid, node in self.nodes.items():
            if node_id in node.depends_on:
                downstream.add(uid)
                # Recurse
                downstream.update(self.get_downstream(uid))
        return list(downstream)

    def impact_analysis(self, model_name: str) -> dict:
        """Analyze impact of changing a model."""
        node_id = f"model.analytics.{model_name}"
        downstream = self.get_downstream(node_id)

        affected_models = [
            n for n in downstream
            if self.nodes[n].resource_type == "model"
        ]
        affected_exposures = [
            n for n in downstream
            if self.nodes[n].resource_type == "exposure"
        ]
        affected_tests = [
            uid for uid, node in self.nodes.items()
            if node.resource_type == "test" and node_id in node.depends_on
        ]

        return {
            "model": model_name,
            "affected_models": len(affected_models),
            "affected_exposures": len(affected_exposures),
            "affected_tests": len(affected_tests),
            "downstream_models": [
                self.nodes[n].name for n in affected_models
            ],
            "downstream_exposures": [
                self.nodes[n].name for n in affected_exposures
            ],
        }

    def generate_catalog_entry(self, node_id: str) -> dict:
        """Generate a data catalog entry from dbt metadata."""
        node = self.nodes.get(node_id)
        if not node:
            return {}

        return {
            "name": node.name,
            "type": node.resource_type,
            "schema": f"{node.database}.{node.schema}",
            "materialized": node.materialized,
            "description": node.description,
            "owner": node.meta.get("owner", node.owner or "unassigned"),
            "tags": node.tags,
            "pii": node.meta.get("contains_pii", False),
            "classification": node.meta.get("data_classification", "internal"),
            "columns": {
                name: {
                    "description": col.get("description", ""),
                    "is_pk": col.get("meta", {}).get("is_primary_key", False),
                    "is_fk": col.get("meta", {}).get("is_foreign_key", False),
                }
                for name, col in node.columns.items()
            },
            "upstream_count": len(node.depends_on),
            "downstream_count": len(self.get_downstream(node_id)),
        }
```

```bash
# dbt docs generation and serving

# Generate documentation site
dbt docs generate

# Serve locally
dbt docs serve --port 8080

# Generate and upload to S3 for team access
dbt docs generate
aws s3 sync target/ s3://dbt-docs-bucket/latest/ \
  --exclude "*.json" --exclude "*.sql" \
  --include "catalog.json" --include "manifest.json" \
  --include "index.html" --include "*.css" --include "*.js"

# CI: generate docs on every merge to main
# and deploy to internal documentation site
```

| Metadata Source | What It Contains | Use Case |
|---|---|---|
| manifest.json | Full DAG, compiled SQL, configs | Lineage analysis, impact analysis |
| catalog.json | Column types, row counts, stats | Data catalog, profiling |
| run_results.json | Test results, timing, status | Monitoring, CI/CD gates |
| sources.json | Source freshness results | Data pipeline monitoring |
| exposures | Dashboard/ML/API dependencies | Impact analysis, ownership |

Key patterns:

1. **Exposures for consumers** -- document every dashboard, ML model, and API that reads from dbt models
2. **Impact analysis** -- trace downstream from any model to know what breaks if it changes
3. **Meta for governance** -- use `meta` for owner, PII flag, classification, SLA
4. **Column descriptions** -- document every column with business meaning, not just technical type
5. **manifest.json as API** -- parse manifest for custom lineage tools, catalogs, and monitors
6. **Docs in CI** -- generate and deploy dbt docs on every merge for self-service discovery
7. **Grain documentation** -- always document the grain (one row per X) in model descriptions'''
    ),
]
"""
