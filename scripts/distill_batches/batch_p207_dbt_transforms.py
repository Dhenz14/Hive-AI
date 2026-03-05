"""dbt (data build tool) — model definitions, incremental models, snapshots, testing, macros, documentation generation, data lineage."""

PAIRS = [
    (
        "data-engineering/dbt-model-definitions",
        "Show how to structure a production dbt project with model layers (staging, intermediate, marts), proper ref() usage, materializations, and configuration best practices.",
        '''Production dbt project structure with model layers and materializations:

```sql
-- ============================================================
-- Project structure (dbt_project.yml)
-- ============================================================
-- dbt_project.yml

-- name: 'analytics'
-- version: '1.0.0'
-- profile: 'analytics_warehouse'
--
-- model-paths: ["models"]
-- analysis-paths: ["analyses"]
-- test-paths: ["tests"]
-- seed-paths: ["seeds"]
-- macro-paths: ["macros"]
-- snapshot-paths: ["snapshots"]
--
-- models:
--   analytics:
--     staging:
--       +materialized: view
--       +schema: staging
--       +tags: ['staging', 'daily']
--     intermediate:
--       +materialized: ephemeral
--       +tags: ['intermediate']
--     marts:
--       core:
--         +materialized: table
--         +schema: analytics
--         +tags: ['marts', 'core']
--       finance:
--         +materialized: table
--         +schema: finance
--         +tags: ['marts', 'finance']

-- ============================================================
-- models/staging/stripe/stg_stripe__payments.sql
-- ============================================================

{{
    config(
        materialized='view',
        schema='staging',
        tags=['stripe', 'payments']
    )
}}

with source as (
    select * from {{ source('stripe', 'payments') }}
),

renamed as (
    select
        -- Primary key
        id as payment_id,

        -- Foreign keys
        customer_id,
        invoice_id,
        subscription_id,

        -- Dimensions
        status as payment_status,
        currency,
        payment_method_type,
        case
            when payment_method_type in ('card', 'credit_card')
                then 'card'
            when payment_method_type in ('bank_transfer', 'ach')
                then 'bank'
            when payment_method_type = 'paypal'
                then 'digital_wallet'
            else 'other'
        end as payment_method_category,

        -- Measures (Stripe stores amounts in cents)
        amount / 100.0 as amount,
        amount_refunded / 100.0 as amount_refunded,
        (amount - amount_refunded) / 100.0 as net_amount,

        -- Flags
        case when amount_refunded > 0 then true else false end
            as has_refund,
        case when status = 'succeeded' then true else false end
            as is_successful,

        -- Timestamps
        created as payment_created_at,
        {{ dbt_utils.safe_cast('metadata_order_date', 'date') }}
            as order_date,

        -- Metadata
        _fivetran_synced as _loaded_at

    from source
    where _fivetran_deleted is false
)

select * from renamed


-- ============================================================
-- models/staging/stripe/_stripe__sources.yml
-- ============================================================

-- version: 2
--
-- sources:
--   - name: stripe
--     database: raw_data
--     schema: stripe
--     description: "Stripe payment processing data via Fivetran"
--     loader: fivetran
--     loaded_at_field: _fivetran_synced
--     freshness:
--       warn_after: {count: 12, period: hour}
--       error_after: {count: 24, period: hour}
--     tables:
--       - name: payments
--         description: "Payment transactions from Stripe"
--         columns:
--           - name: id
--             description: "Stripe payment ID"
--             data_tests:
--               - unique
--               - not_null
--       - name: customers
--         description: "Stripe customer records"
--       - name: subscriptions
--         description: "Active and historical subscriptions"


-- ============================================================
-- models/intermediate/int_payments__pivoted_by_method.sql
-- ============================================================

{{
    config(materialized='ephemeral')
}}

with payments as (
    select * from {{ ref('stg_stripe__payments') }}
    where is_successful = true
),

pivoted as (
    select
        customer_id,
        order_date,

        -- Pivot payment methods into columns
        {{ dbt_utils.pivot(
            'payment_method_category',
            dbt_utils.get_column_values(
                ref('stg_stripe__payments'),
                'payment_method_category'
            ),
            agg='sum',
            then_value='net_amount',
            else_value='0',
            suffix='_revenue'
        ) }},

        sum(net_amount) as total_revenue,
        count(*) as payment_count

    from payments
    group by 1, 2
)

select * from pivoted


-- ============================================================
-- models/marts/core/fct_orders.sql
-- ============================================================

{{
    config(
        materialized='table',
        schema='analytics',
        cluster_by=['order_date', 'customer_id'],
        tags=['core', 'daily'],
        meta={
            'owner': 'data-team',
            'contains_pii': false,
            'sla': 'daily by 6am UTC'
        }
    )
}}

with payments as (
    select * from {{ ref('stg_stripe__payments') }}
),

customers as (
    select * from {{ ref('stg_stripe__customers') }}
),

orders as (
    select * from {{ ref('stg_app__orders') }}
),

final as (
    select
        -- Grain: one row per order
        orders.order_id,
        orders.customer_id,
        customers.customer_name,
        customers.customer_segment,
        customers.signup_date as customer_signup_date,

        orders.order_date,
        orders.order_status,
        orders.shipping_method,

        payments.payment_id,
        payments.payment_status,
        payments.payment_method_category,
        payments.net_amount as order_amount,

        -- Derived metrics
        {{ dbt_utils.datediff(
            'customers.signup_date',
            'orders.order_date',
            'day'
        ) }} as days_since_signup,

        row_number() over (
            partition by orders.customer_id
            order by orders.order_date
        ) as customer_order_sequence,

        -- Is this the customer's first order?
        case
            when row_number() over (
                partition by orders.customer_id
                order by orders.order_date
            ) = 1 then true
            else false
        end as is_first_order

    from orders
    left join payments
        on orders.payment_id = payments.payment_id
    left join customers
        on orders.customer_id = customers.customer_id
)

select * from final
```

**dbt model layer conventions:**

| Layer | Materialization | Purpose | Naming |
|---|---|---|---|
| Staging | View | Clean raw sources, rename, cast | `stg_{source}__{entity}` |
| Intermediate | Ephemeral | Complex logic, joins, pivots | `int_{entity}__{verb}` |
| Marts | Table | Business-ready facts and dims | `fct_{entity}`, `dim_{entity}` |

**Key patterns:**
- Stage every source once (single source of truth), then reference with `ref()`
- Staging models: rename, cast, filter deleted rows, convert units (cents to dollars)
- Intermediate models: use `ephemeral` to avoid materializing transitional logic
- Mart models: use `table` materialization with clustering for query performance
- Define sources with freshness checks in YAML for monitoring data pipeline health
- Add `meta` tags for ownership, PII classification, and SLA documentation
- Use `dbt_utils` macros for common patterns (pivot, datediff, safe_cast)'''
    ),
    (
        "data-engineering/dbt-incremental-models",
        "Demonstrate dbt incremental models with different strategies (append, delete+insert, merge), handling late-arriving data, and optimizing incremental performance.",
        '''dbt incremental models: strategies, late data handling, and performance optimization:

```sql
-- ============================================================
-- Incremental model: append strategy (simplest)
-- models/marts/core/fct_page_views.sql
-- ============================================================

{{
    config(
        materialized='incremental',
        unique_key='page_view_id',
        incremental_strategy='append',
        on_schema_change='append_new_columns',
        tags=['incremental', 'hourly'],
        post_hook=[
            "{{ optimize_table() }}"
        ]
    )
}}

with source_events as (
    select * from {{ ref('stg_snowplow__page_views') }}

    {% if is_incremental() %}
    -- Only process new events since last run
    -- Use a lookback window to catch late-arriving data
    where event_timestamp > (
        select
            dateadd(hour, -3, max(event_timestamp))
        from {{ this }}
    )
    {% endif %}
),

deduplicated as (
    -- Handle duplicates from overlapping lookback window
    select *,
        row_number() over (
            partition by page_view_id
            order by collector_timestamp desc
        ) as _row_num
    from source_events
    qualify _row_num = 1
)

select
    page_view_id,
    session_id,
    user_id,
    page_url,
    page_title,
    referrer_url,
    device_type,
    browser_family,
    country,
    event_timestamp,
    time_on_page_seconds,
    is_bounce,
    current_timestamp() as _loaded_at

from deduplicated


-- ============================================================
-- Incremental model: merge strategy (upsert)
-- models/marts/core/fct_subscriptions.sql
-- ============================================================

{{
    config(
        materialized='incremental',
        unique_key='subscription_id',
        incremental_strategy='merge',
        merge_update_columns=[
            'subscription_status',
            'current_period_end',
            'cancel_at',
            'canceled_at',
            'mrr',
            '_updated_at'
        ],
        cluster_by=['subscription_status', 'customer_id'],
        tags=['incremental', 'hourly']
    )
}}

with subscriptions as (
    select * from {{ ref('stg_stripe__subscriptions') }}

    {% if is_incremental() %}
    where updated_at > (
        select coalesce(max(_updated_at), '1970-01-01')
        from {{ this }}
    )
    {% endif %}
),

enriched as (
    select
        subscription_id,
        customer_id,
        plan_id,
        plan_name,
        subscription_status,
        billing_interval,
        current_period_start,
        current_period_end,
        cancel_at,
        canceled_at,
        trial_start,
        trial_end,

        -- MRR calculation
        case
            when subscription_status = 'active' then
                case billing_interval
                    when 'month' then amount
                    when 'year' then amount / 12.0
                    when 'quarter' then amount / 3.0
                end
            else 0
        end as mrr,

        -- Subscription age
        {{ dbt_utils.datediff(
            'created_at', 'current_date()', 'day'
        ) }} as subscription_age_days,

        created_at as subscription_started_at,
        updated_at as _updated_at

    from subscriptions
)

select * from enriched


-- ============================================================
-- Incremental model: delete+insert strategy
-- models/marts/core/fct_daily_active_users.sql
-- ============================================================

{{
    config(
        materialized='incremental',
        unique_key='date_day || user_id',
        incremental_strategy='delete+insert',
        incremental_predicates=[
            "DBT_INTERNAL_DEST.date_day >= dateadd(day, -3, current_date())"
        ],
        cluster_by=['date_day'],
        tags=['incremental', 'daily']
    )
}}

with events as (
    select * from {{ ref('stg_app__user_events') }}

    {% if is_incremental() %}
    -- Recompute last 3 days (late data window)
    where event_date >= dateadd(day, -3, current_date())
    {% endif %}
),

daily_active as (
    select
        event_date as date_day,
        user_id,

        count(*) as event_count,
        count(distinct session_id) as session_count,
        min(event_timestamp) as first_event_at,
        max(event_timestamp) as last_event_at,

        {{ dbt_utils.datediff(
            'min(event_timestamp)',
            'max(event_timestamp)',
            'minute'
        ) }} as active_minutes,

        -- Feature flags for user segmentation
        max(case when event_type = 'purchase' then 1 else 0 end)
            as had_purchase,
        max(case when event_type = 'search' then 1 else 0 end)
            as had_search,
        sum(case when event_type = 'page_view' then 1 else 0 end)
            as page_view_count

    from events
    group by 1, 2
)

select
    *,
    current_timestamp() as _computed_at

from daily_active


-- ============================================================
-- Incremental model: microbatch strategy (dbt 1.9+)
-- models/marts/core/fct_events_microbatch.sql
-- ============================================================

{{
    config(
        materialized='incremental',
        incremental_strategy='microbatch',
        unique_key='event_id',
        event_time='event_timestamp',
        begin='2024-01-01',
        batch_size='day',
        lookback=3,
        tags=['incremental', 'microbatch']
    )
}}

-- With microbatch, dbt automatically:
-- 1. Determines which time batches need processing
-- 2. Processes each batch independently
-- 3. Handles late-arriving data via lookback parameter
-- 4. Supports parallel batch processing

select
    event_id,
    user_id,
    event_type,
    event_timestamp,
    properties,
    session_id,
    current_timestamp() as _loaded_at

from {{ ref('stg_app__events') }}
```

**Incremental strategy comparison:**

| Strategy | How It Works | Best For | Duplicates |
|---|---|---|---|
| Append | INSERT new rows only | Immutable event streams | Possible without dedup |
| Merge | MERGE (upsert) by unique_key | Mutable dimension updates | Handled by unique_key |
| Delete+Insert | DELETE matching, then INSERT | Recompute date partitions | Handled by predicate |
| Microbatch | Auto-batch by event_time | Large event tables, parallelism | Handled by lookback |

**Late data handling strategies:**

| Strategy | Implementation | Trade-off |
|---|---|---|
| Lookback window | `max(ts) - interval '3 hours'` | Reprocesses some data |
| Incremental predicates | Limit target scan to recent partitions | Reduces merge cost |
| Microbatch lookback | `lookback=3` (days) | Auto reprocesses recent batches |
| Full refresh fallback | `dbt run --full-refresh -s model` | Rebuilds entire table |

**Key patterns:**
- Use `is_incremental()` to conditionally filter source data on incremental runs
- Add lookback window (e.g., 3 hours) to catch late-arriving events
- Use `merge_update_columns` to only update specific columns, not all fields
- `incremental_predicates` limit the target table scan to recent partitions
- Deduplicate within the incremental window using `row_number()` + `qualify`
- `on_schema_change='append_new_columns'` handles upstream schema evolution
- Microbatch strategy (dbt 1.9+) automates batch processing and parallel execution'''
    ),
    (
        "data-engineering/dbt-snapshots-testing",
        "Show dbt snapshot configurations for SCD Type 2 tracking, and comprehensive testing strategies including schema tests, data tests, unit tests, and custom generic tests.",
        '''dbt snapshots for SCD Type 2 and comprehensive testing strategies:

```sql
-- ============================================================
-- Snapshot: SCD Type 2 for customer dimension
-- snapshots/snap_customers.sql
-- ============================================================

{% snapshot snap_customers %}

{{
    config(
        target_database='analytics',
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='timestamp',
        updated_at='updated_at',
        invalidate_hard_deletes=True,
    )
}}

select
    customer_id,
    customer_name,
    email,
    plan_type,
    customer_segment,
    is_active,
    billing_country,
    account_manager_id,
    updated_at

from {{ source('app_db', 'customers') }}

{% endsnapshot %}


-- ============================================================
-- Snapshot: check strategy (when no updated_at column)
-- snapshots/snap_product_pricing.sql
-- ============================================================

{% snapshot snap_product_pricing %}

{{
    config(
        target_schema='snapshots',
        unique_key='product_id',
        strategy='check',
        check_cols=['price', 'currency', 'discount_pct', 'is_active'],
    )
}}

select
    product_id,
    product_name,
    price,
    currency,
    discount_pct,
    is_active,
    category

from {{ source('catalog', 'products') }}

{% endsnapshot %}


-- ============================================================
-- Using snapshot in a dimension model
-- models/marts/core/dim_customers.sql
-- ============================================================

{{
    config(materialized='table')
}}

with snapshot as (
    select * from {{ ref('snap_customers') }}
),

current_records as (
    select
        customer_id,
        customer_name,
        email,
        plan_type,
        customer_segment,
        is_active,
        billing_country,
        account_manager_id,

        -- SCD2 metadata from snapshot
        dbt_valid_from as valid_from,
        dbt_valid_to as valid_to,
        case
            when dbt_valid_to is null then true
            else false
        end as is_current,

        -- Track version number
        row_number() over (
            partition by customer_id
            order by dbt_valid_from
        ) as version_number

    from snapshot
)

select * from current_records
```

```yaml
# ============================================================
# models/marts/core/_core__models.yml
# Schema tests and documentation
# ============================================================

version: 2

models:
  - name: fct_orders
    description: >
      Order fact table at the grain of one row per order.
      Joins payment and customer data for complete order context.
    meta:
      owner: data-team
      contains_pii: false
      sla: "daily by 6am UTC"

    columns:
      - name: order_id
        description: "Unique order identifier"
        data_tests:
          - unique
          - not_null

      - name: customer_id
        description: "Foreign key to dim_customers"
        data_tests:
          - not_null
          - relationships:
              to: ref('dim_customers')
              field: customer_id
              config:
                severity: warn

      - name: order_amount
        description: "Order total in USD"
        data_tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000
              inclusive: true

      - name: order_status
        description: "Current order status"
        data_tests:
          - accepted_values:
              values: ['pending', 'confirmed', 'shipped',
                       'delivered', 'cancelled', 'refunded']

      - name: order_date
        description: "Date the order was placed"
        data_tests:
          - not_null
          - dbt_utils.not_null_proportion:
              at_least: 0.99

      - name: customer_order_sequence
        description: "Nth order for this customer (1-indexed)"
        data_tests:
          - dbt_utils.sequential_values:
              group_by_columns: ['customer_id']

  - name: dim_customers
    description: "Customer dimension with SCD Type 2 history"
    columns:
      - name: customer_id
        data_tests:
          - not_null
      - name: is_current
        data_tests:
          - not_null
      # Exactly one current record per customer
      - name: customer_id
        data_tests:
          - dbt_utils.unique_combination_of_columns:
              combination_of_columns:
                - customer_id
                - is_current
              config:
                where: "is_current = true"
```

```sql
-- ============================================================
-- Custom generic test: referential integrity with threshold
-- tests/generic/test_referential_integrity.sql
-- ============================================================

{% test referential_integrity_threshold(
    model, column_name, to, field, threshold=0.01
) %}

with parent as (
    select distinct {{ field }} as parent_key
    from {{ to }}
),

child as (
    select {{ column_name }} as child_key
    from {{ model }}
    where {{ column_name }} is not null
),

orphans as (
    select child_key
    from child
    left join parent on child.child_key = parent.parent_key
    where parent.parent_key is null
)

select
    count(*) as orphan_count,
    (select count(*) from child) as total_count,
    count(*) * 1.0 / nullif((select count(*) from child), 0)
        as orphan_rate

from orphans
having orphan_rate > {{ threshold }}

{% endtest %}


-- ============================================================
-- Singular test: business rule validation
-- tests/assert_revenue_not_negative.sql
-- ============================================================

-- Orders should never have negative net revenue
-- unless they are fully refunded

select
    order_id,
    order_amount,
    order_status

from {{ ref('fct_orders') }}

where order_amount < 0
    and order_status != 'refunded'


-- ============================================================
-- Unit test (dbt 1.8+)
-- tests/unit/test_mrr_calculation.yml
-- ============================================================

-- unit_tests:
--   - name: test_mrr_monthly_active
--     description: "Active monthly sub should have MRR = amount"
--     model: fct_subscriptions
--     given:
--       - input: ref('stg_stripe__subscriptions')
--         rows:
--           - {subscription_id: 'sub-1', subscription_status: 'active',
--              billing_interval: 'month', amount: 99.0,
--              created_at: '2024-01-01', updated_at: '2024-06-01'}
--     expect:
--       rows:
--         - {subscription_id: 'sub-1', mrr: 99.0}
--
--   - name: test_mrr_yearly_active
--     description: "Active yearly sub should have MRR = amount/12"
--     model: fct_subscriptions
--     given:
--       - input: ref('stg_stripe__subscriptions')
--         rows:
--           - {subscription_id: 'sub-2', subscription_status: 'active',
--              billing_interval: 'year', amount: 1200.0,
--              created_at: '2024-01-01', updated_at: '2024-06-01'}
--     expect:
--       rows:
--         - {subscription_id: 'sub-2', mrr: 100.0}
--
--   - name: test_mrr_canceled
--     description: "Canceled sub should have MRR = 0"
--     model: fct_subscriptions
--     given:
--       - input: ref('stg_stripe__subscriptions')
--         rows:
--           - {subscription_id: 'sub-3', subscription_status: 'canceled',
--              billing_interval: 'month', amount: 99.0,
--              created_at: '2024-01-01', updated_at: '2024-06-01'}
--     expect:
--       rows:
--         - {subscription_id: 'sub-3', mrr: 0}
```

**dbt testing hierarchy:**

| Test Type | Scope | Example | Runs |
|---|---|---|---|
| Schema tests | Column-level | `unique`, `not_null`, `accepted_values` | Every `dbt test` |
| Generic tests | Reusable logic | `referential_integrity_threshold` | Every `dbt test` |
| Singular tests | Business rules | `assert_revenue_not_negative.sql` | Every `dbt test` |
| Unit tests | Model logic | Mock inputs, assert outputs | `dbt test --select unit_tests` |
| Source freshness | Data pipeline | `loaded_at_field` + `warn_after` | `dbt source freshness` |

**Key patterns:**
- Snapshot with `timestamp` strategy when source has `updated_at` column
- Snapshot with `check` strategy when comparing specific column values for changes
- `invalidate_hard_deletes=True` to track when source rows are deleted
- Schema tests on every column in mart models for data quality contracts
- Custom generic tests for domain-specific validations (orphan rate thresholds)
- Singular tests for complex business rule assertions
- Unit tests (dbt 1.8+) mock inputs and assert outputs without running on real data'''
    ),
    (
        "data-engineering/dbt-macros-packages",
        "Show advanced dbt macros including Jinja control flow, custom materializations, cross-database macros, and how to build reusable macro packages.",
        '''Advanced dbt macros: Jinja patterns, custom logic, and reusable packages:

```sql
-- ============================================================
-- Macro: generate surrogate key (deterministic hash)
-- macros/generate_surrogate_key.sql
-- ============================================================

{% macro generate_surrogate_key(field_list) %}

    {%- set fields = [] -%}
    {%- for field in field_list -%}
        {%- do fields.append(
            "coalesce(cast(" ~ field ~ " as " ~
            dbt.type_string() ~ "), '_null_')"
        ) -%}
    {%- endfor -%}

    {{ dbt.hash(dbt_utils.concat(fields)) }}

{% endmacro %}


-- ============================================================
-- Macro: pivot with dynamic column detection
-- macros/dynamic_pivot.sql
-- ============================================================

{% macro dynamic_pivot(
    relation, pivot_column, value_column,
    agg_function='sum', then_value=None,
    prefix='', suffix='', quote_identifiers=True
) %}

    {%- set pivot_values = dbt_utils.get_column_values(
        table=relation, column=pivot_column
    ) -%}

    {% for value in pivot_values %}
        {{ agg_function }}(
            case
                when {{ pivot_column }} = '{{ value }}'
                then {{ then_value or value_column }}
            end
        ) as {{ prefix }}{{ value | replace(' ', '_') | lower }}{{ suffix }}
        {%- if not loop.last %},{% endif -%}
    {% endfor %}

{% endmacro %}


-- ============================================================
-- Macro: cross-database date spine generator
-- macros/date_spine.sql
-- ============================================================

{% macro generate_date_spine(
    start_date, end_date, datepart='day'
) %}

    {{ adapter.dispatch('generate_date_spine', 'analytics')(
        start_date, end_date, datepart
    ) }}

{% endmacro %}


{% macro default__generate_date_spine(
    start_date, end_date, datepart
) %}

    with recursive date_spine as (
        select
            cast('{{ start_date }}' as date) as date_day
        union all
        select
            dateadd('{{ datepart }}', 1, date_day)
        from date_spine
        where date_day < cast('{{ end_date }}' as date)
    )

    select date_day from date_spine

{% endmacro %}


{% macro bigquery__generate_date_spine(
    start_date, end_date, datepart
) %}

    select date_day
    from unnest(
        generate_date_array(
            cast('{{ start_date }}' as date),
            cast('{{ end_date }}' as date),
            interval 1 {{ datepart }}
        )
    ) as date_day

{% endmacro %}


-- ============================================================
-- Macro: grant permissions after model build
-- macros/grants.sql
-- ============================================================

{% macro grant_select_to_role(role_name) %}

    {% set grant_sql %}
        grant select on {{ this }} to role {{ role_name }};
    {% endset %}

    {% if execute %}
        {{ log("Granting SELECT to " ~ role_name ~ " on " ~ this, info=True) }}
        {% do run_query(grant_sql) %}
    {% endif %}

{% endmacro %}


-- Usage in model config:
-- {{ config(post_hook=[grant_select_to_role('analyst_role')]) }}


-- ============================================================
-- Macro: audit columns for all models
-- macros/audit_columns.sql
-- ============================================================

{% macro add_audit_columns() %}

    current_timestamp() as _dbt_loaded_at,
    '{{ invocation_id }}' as _dbt_invocation_id,
    '{{ this.name }}' as _dbt_model_name,
    '{{ env_var("DBT_CLOUD_RUN_ID", "local") }}' as _dbt_run_id

{% endmacro %}


-- Usage in model:
-- select
--     order_id,
--     amount,
--     {{ add_audit_columns() }}
-- from source_data


-- ============================================================
-- Macro: dynamic union of relations
-- macros/union_relations.sql
-- ============================================================

{% macro union_source_tables(
    source_name, table_prefix, exclude_tables=[]
) %}

    {%- set tables = [] -%}

    {%- for node in graph.sources.values() -%}
        {%- if node.source_name == source_name
            and node.name.startswith(table_prefix)
            and node.name not in exclude_tables -%}
            {%- do tables.append(
                source(source_name, node.name)
            ) -%}
        {%- endif -%}
    {%- endfor -%}

    {% if tables | length == 0 %}
        {{ exceptions.raise_compiler_error(
            "No tables found for source '" ~ source_name ~
            "' with prefix '" ~ table_prefix ~ "'"
        ) }}
    {% endif %}

    {% for table in tables %}
        select
            *,
            '{{ table }}' as _source_table
        from {{ table }}
        {% if not loop.last %}union all{% endif %}
    {% endfor %}

{% endmacro %}


-- ============================================================
-- Macro: optimize table (post-hook)
-- macros/optimize_table.sql
-- ============================================================

{% macro optimize_table(
    z_order_columns=None, vacuum_hours=168
) %}

    {% if target.type == 'databricks' %}

        {% if z_order_columns %}
            optimize {{ this }}
            zorder by ({{ z_order_columns | join(', ') }});
        {% else %}
            optimize {{ this }};
        {% endif %}

    {% elif target.type == 'snowflake' %}
        -- Snowflake auto-clusters; no-op
    {% endif %}

{% endmacro %}


-- ============================================================
-- Macro: conditional materializations
-- macros/conditional_config.sql
-- ============================================================

{% macro dev_limit() %}
    {# Limit data in development for fast iteration #}
    {% if target.name == 'dev' %}
        limit 10000
    {% endif %}
{% endmacro %}


{% macro table_or_view() %}
    {# Use views in dev, tables in prod #}
    {% if target.name == 'dev' %}
        {{ return('view') }}
    {% else %}
        {{ return('table') }}
    {% endif %}
{% endmacro %}

-- Usage:
-- {{ config(materialized=table_or_view()) }}
-- select * from {{ ref('stg_orders') }}
-- {{ dev_limit() }}
```

**Macro pattern reference:**

| Pattern | Macro | Purpose |
|---|---|---|
| Cross-DB dispatch | `adapter.dispatch()` | Write once, run on any warehouse |
| Dynamic SQL | `run_query()` + `execute` | Execute arbitrary SQL at compile time |
| Column discovery | `get_column_values()` | Dynamically detect column values for pivots |
| Environment-aware | `target.name`, `env_var()` | Dev vs prod behavior switching |
| Post-hooks | `post_hook=[macro()]` | Run SQL after model materializes |
| Audit metadata | `invocation_id`, `this.name` | Track which run built each row |
| Error handling | `exceptions.raise_compiler_error()` | Fail fast on invalid configurations |

**Key patterns:**
- Use `adapter.dispatch()` for cross-database compatibility (Snowflake, BigQuery, etc.)
- Dynamic pivot macros detect column values at compile time, not runtime
- Add audit columns (`_dbt_loaded_at`, `_dbt_invocation_id`) to every mart model
- Use `target.name` to vary behavior between dev and prod (limits, materializations)
- Post-hook macros for permissions grants, table optimization, and cleanup
- `generate_surrogate_key()` creates deterministic hash keys for dimension tables
- Union macros with graph introspection dynamically find and combine source tables'''
    ),
    (
        "data-engineering/dbt-documentation-lineage",
        "Show how to build comprehensive dbt documentation with model descriptions, column-level docs, doc blocks, exposure definitions, and how to leverage the built-in lineage graph.",
        '''dbt documentation, exposures, and data lineage:

```yaml
# ============================================================
# models/marts/core/_core__models.yml
# Comprehensive model documentation
# ============================================================

version: 2

models:
  - name: fct_orders
    description: >
      {{ doc("fct_orders_description") }}

    meta:
      owner: data-team
      slack_channel: "#data-eng"
      contains_pii: false
      tier: 1
      sla: "Updated daily by 06:00 UTC"
      update_frequency: daily

    columns:
      - name: order_id
        description: >
          Unique identifier for each order. Sourced from
          the application database `orders.id` column.
        meta:
          dimension_type: identifier
        data_tests:
          - unique
          - not_null

      - name: customer_id
        description: "FK to dim_customers"
        meta:
          dimension_type: foreign_key
        data_tests:
          - not_null
          - relationships:
              to: ref('dim_customers')
              field: customer_id

      - name: order_amount
        description: >
          Total order amount in USD after discounts
          but before tax. Converted from cents to dollars
          in the staging layer.
        meta:
          measure_type: additive
          unit: USD
        data_tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000

      - name: order_date
        description: "Date the order was placed (UTC)"
        meta:
          dimension_type: date
          grain: day

      - name: customer_order_sequence
        description: >
          Sequential order number for this customer.
          1 = first order (acquisition), 2+ = repeat orders.
        meta:
          measure_type: non_additive

      - name: is_first_order
        description: >
          Boolean flag indicating if this is the customer's
          first-ever order. Used for acquisition vs retention
          analysis.
        meta:
          dimension_type: boolean


# ============================================================
# models/docs/docs_blocks.md
# Reusable documentation blocks
# ============================================================

# {% docs fct_orders_description %}
#
# ## Orders Fact Table
#
# This model represents the core order fact table at the grain
# of **one row per order**. It combines data from:
#
# - Application database (`orders` table)
# - Stripe payments (`payments` table)
# - Customer dimension (`dim_customers`)
#
# ### Business Rules
#
# 1. **Order amount**: Converted from cents to USD in staging
# 2. **Customer sequence**: Calculated using `ROW_NUMBER()`
#    partitioned by customer, ordered by order date
# 3. **First order flag**: Derived from customer_order_sequence = 1
#
# ### Grain
#
# One row per order (`order_id` is the primary key).
#
# ### Update Frequency
#
# Updated daily at 06:00 UTC via scheduled dbt Cloud job.
#
# ### Known Limitations
#
# - Refunded orders retain their original `order_amount`
# - Orders in `pending` status may be incomplete
#
# {% enddocs %}


# ============================================================
# models/exposures/_exposures.yml
# Downstream consumers documentation
# ============================================================

version: 2

exposures:
  - name: weekly_revenue_dashboard
    type: dashboard
    maturity: high
    url: "https://bi.company.com/dashboards/42"
    description: >
      Weekly revenue dashboard used by the executive team.
      Shows revenue trends, customer acquisition, and
      geographic breakdown. Updated daily by 7am UTC.
    depends_on:
      - ref('fct_orders')
      - ref('dim_customers')
      - ref('fct_daily_revenue')
    owner:
      name: Analytics Team
      email: analytics@company.com

  - name: churn_prediction_model
    type: ml
    maturity: medium
    url: "https://mlflow.company.com/experiments/churn-v3"
    description: >
      Customer churn prediction model trained weekly.
      Features are pulled from the customer 360 and
      subscription facts tables.
    depends_on:
      - ref('dim_customers')
      - ref('fct_subscriptions')
      - ref('fct_orders')
    owner:
      name: ML Engineering
      email: ml-eng@company.com

  - name: customer_data_api
    type: application
    maturity: high
    url: "https://api.company.com/docs#customers"
    description: >
      REST API serving customer profile data.
      Reads directly from the analytics.dim_customers table.
    depends_on:
      - ref('dim_customers')
    owner:
      name: Backend Team
      email: backend@company.com


# ============================================================
# models/metrics/_metrics.yml
# Semantic layer metric definitions
# ============================================================

version: 2

metrics:
  - name: monthly_revenue
    label: Monthly Revenue
    description: "Total net revenue aggregated monthly"
    type: simple
    type_params:
      measure: total_revenue
    filter: |
      {{ Dimension('order_status') }} = 'completed'

  - name: customer_acquisition_cost
    label: CAC
    description: >
      Customer acquisition cost = marketing spend / new customers
    type: derived
    type_params:
      expr: marketing_spend / new_customers
      metrics:
        - name: marketing_spend
        - name: new_customers
```

```python
# ============================================================
# scripts/generate_docs.py
# Automated documentation generation
# ============================================================

"""
Script to generate and deploy dbt documentation.
Run after dbt build to ensure docs reflect latest state.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def generate_dbt_docs(
    project_dir: str = ".",
    target_dir: str = "target",
    deploy_bucket: str = "s3://docs.company.com/dbt",
) -> dict:
    """Generate dbt docs and extract lineage metadata."""

    # Step 1: Generate docs
    result = subprocess.run(
        ["dbt", "docs", "generate", "--no-compile"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dbt docs generate failed: {result.stderr}")

    # Step 2: Load manifest for lineage analysis
    manifest_path = Path(project_dir) / target_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    # Step 3: Extract lineage summary
    lineage = extract_lineage(manifest)

    # Step 4: Generate freshness report
    catalog_path = Path(project_dir) / target_dir / "catalog.json"
    with open(catalog_path) as f:
        catalog = json.load(f)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_models": len(manifest.get("nodes", {})),
        "total_sources": len(manifest.get("sources", {})),
        "total_exposures": len(manifest.get("exposures", {})),
        "total_tests": sum(
            1 for k in manifest.get("nodes", {})
            if k.startswith("test.")
        ),
        "lineage": lineage,
    }

    return summary


def extract_lineage(manifest: dict) -> dict:
    """Extract data lineage from dbt manifest."""
    nodes = manifest.get("nodes", {})
    parent_map = manifest.get("parent_map", {})
    child_map = manifest.get("child_map", {})

    lineage = {
        "root_models": [],  # Models with no parents (sources only)
        "leaf_models": [],  # Models with no children
        "critical_path": [],  # Most-depended-on models
    }

    dependency_count: dict[str, int] = {}

    for node_id, children in child_map.items():
        if node_id.startswith("model."):
            model_name = node_id.split(".")[-1]
            dependency_count[model_name] = len(children)

    # Root models: depend only on sources
    for node_id, parents in parent_map.items():
        if node_id.startswith("model."):
            model_name = node_id.split(".")[-1]
            parent_types = set(
                p.split(".")[0] for p in parents
            )
            if parent_types == {"source"} or not parents:
                lineage["root_models"].append(model_name)

    # Leaf models: no child models
    for node_id in nodes:
        if node_id.startswith("model."):
            model_name = node_id.split(".")[-1]
            children = child_map.get(node_id, [])
            model_children = [
                c for c in children if c.startswith("model.")
            ]
            if not model_children:
                lineage["leaf_models"].append(model_name)

    # Critical path: most depended-on models
    lineage["critical_path"] = sorted(
        dependency_count.items(),
        key=lambda x: -x[1],
    )[:10]

    return lineage
```

**dbt documentation components:**

| Component | Purpose | File Location |
|---|---|---|
| Model descriptions | Document what each model represents | `_models.yml` |
| Column descriptions | Document each column's meaning and rules | `_models.yml` |
| Doc blocks | Reusable markdown documentation | `docs/docs_blocks.md` |
| Exposures | Document downstream consumers | `_exposures.yml` |
| Source freshness | Monitor pipeline data age | `_sources.yml` |
| Metrics | Semantic layer metric definitions | `_metrics.yml` |
| Meta tags | Machine-readable metadata (PII, owner, SLA) | Any YAML |

**Key patterns:**
- Use doc blocks (`{% docs %}`) for long model descriptions to keep YAML clean
- Define exposures for every downstream consumer (dashboards, ML models, APIs)
- Add `meta` tags for PII classification, ownership, SLA, and update frequency
- Use column-level `meta` for dimension/measure type annotation (semantic layer)
- Extract lineage from `manifest.json` to identify critical path and orphaned models
- Exposure dependencies create lineage links from dbt models to business tools
- Generate docs after every production run to keep documentation current'''
    ),
]
