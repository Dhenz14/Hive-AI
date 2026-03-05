"""Ruby on Rails 8 -- Solid Queue, Solid Cache, Solid Cable, Kamal deployment, import maps, Hotwire Turbo, authentication generator, Propshaft."""

PAIRS = [
    (
        "rails/solid-queue-background-jobs",
        "Show how to use Solid Queue in Rails 8 for background job processing, including job definition, queue configuration, recurring jobs, concurrency controls, and how it replaces Sidekiq/Redis for most use cases.",
        '''Solid Queue is Rails 8's default Active Job backend, using your existing SQL database instead of Redis. It supports recurring jobs, concurrency controls, and priorities out of the box.

```ruby
# --- config/database.yml: dedicated queue database (recommended) ---
# production:
#   primary:
#     <<: *default
#     database: myapp_production
#   queue:
#     <<: *default
#     database: myapp_queue_production
#     migrations_paths: db/queue_migrate

# --- config/solid_queue.yml ---
# default: &default
#   dispatchers:
#     - polling_interval: 1
#       batch_size: 500
#   workers:
#     - queues: "*"
#       threads: 5
#       processes: 1
#       polling_interval: 0.1
#
# production:
#   <<: *default
#   dispatchers:
#     - polling_interval: 1
#       batch_size: 500
#   workers:
#     - queues: [critical, default]
#       threads: 5
#       processes: 2
#       polling_interval: 0.1
#     - queues: [low_priority, bulk]
#       threads: 3
#       processes: 1
#       polling_interval: 1

# --- config/application.rb ---
# config.active_job.queue_adapter = :solid_queue
# config.solid_queue.connects_to = { database: { writing: :queue } }

# --- app/jobs/order_processing_job.rb ---
class OrderProcessingJob < ApplicationJob
  queue_as :critical
  retry_on StandardError, wait: :polynomially_longer, attempts: 5
  discard_on ActiveRecord::RecordNotFound

  # Concurrency control: only one job per order at a time
  limits_concurrency to: 1, key: ->(order_id) { "order-#{order_id}" },
                    duration: 30.minutes

  def perform(order_id)
    order = Order.find(order_id)

    ActiveRecord::Base.transaction do
      order.process_payment!
      order.update!(status: :paid, processed_at: Time.current)
      order.line_items.each(&:reserve_inventory!)
    end

    # Enqueue downstream jobs
    OrderConfirmationMailer.with(order: order).confirmation.deliver_later
    InventoryUpdateJob.perform_later(order_id)
    AnalyticsEventJob.perform_later("order_completed", order_id: order_id)

    Rails.logger.info "Order #{order_id} processed successfully"
  rescue PaymentGateway::DeclinedError => e
    order.update!(status: :payment_failed, error_message: e.message)
    OrderFailureNotificationJob.perform_later(order_id, e.message)
    raise # re-raise so retry logic kicks in
  end
end

# --- app/jobs/bulk_email_job.rb ---
class BulkEmailJob < ApplicationJob
  queue_as :bulk

  # Concurrency: max 5 bulk email jobs running simultaneously
  limits_concurrency to: 5, key: -> { "bulk-emails" }

  def perform(campaign_id)
    campaign = EmailCampaign.find(campaign_id)
    recipients = campaign.recipients.where(sent: false)

    recipients.find_each(batch_size: 100) do |recipient|
      CampaignMailer.with(
        campaign: campaign,
        recipient: recipient
      ).campaign_email.deliver_later(queue: :low_priority)

      recipient.update!(sent: true, sent_at: Time.current)
    end

    campaign.update!(completed_at: Time.current)
  end
end

# --- app/jobs/data_cleanup_job.rb ---
class DataCleanupJob < ApplicationJob
  queue_as :low_priority

  def perform
    # Delete old sessions
    deleted = Session.where("updated_at < ?", 30.days.ago).delete_all
    Rails.logger.info "Cleaned up #{deleted} expired sessions"

    # Archive old orders
    Order.where(status: :completed)
         .where("completed_at < ?", 1.year.ago)
         .find_each do |order|
      OrderArchiver.new(order).archive!
    end
  end
end
```

```ruby
# --- config/recurring.yml: scheduled/cron jobs ---
# (replaces whenever/cron or Sidekiq scheduled jobs)

# production:
#   data_cleanup:
#     class: DataCleanupJob
#     queue: low_priority
#     schedule: every day at 3am
#
#   report_generation:
#     class: DailyReportJob
#     args: ["daily"]
#     queue: default
#     schedule: "0 6 * * *"  # cron syntax also supported
#
#   cache_warming:
#     class: CacheWarmingJob
#     queue: default
#     schedule: every 15 minutes
#
#   heartbeat_check:
#     class: HealthCheckJob
#     queue: critical
#     schedule: every 1 minute

# --- app/jobs/daily_report_job.rb ---
class DailyReportJob < ApplicationJob
  queue_as :default

  def perform(report_type = "daily")
    date = Date.yesterday
    report = ReportGenerator.new(type: report_type, date: date)

    data = report.generate
    report_record = Report.create!(
      report_type: report_type,
      date: date,
      data: data,
      generated_at: Time.current
    )

    AdminMailer.with(report: report_record)
               .daily_summary
               .deliver_later
  end
end

# --- Monitoring Solid Queue ---
# In Rails console or admin dashboard:

# Check queue sizes
SolidQueue::Job.where(queue_name: "critical").count
SolidQueue::Job.where(queue_name: "default").pending.count

# Check failed jobs
SolidQueue::FailedExecution.count
SolidQueue::FailedExecution.last(10).each do |fe|
  puts "#{fe.job.class_name}: #{fe.error.message}"
end

# Retry failed jobs
SolidQueue::FailedExecution.last(10).each(&:retry)

# Clear completed jobs (housekeeping)
SolidQueue::Job.finished.where("finished_at < ?", 7.days.ago).delete_all

# Mission Control dashboard (optional web UI)
# gem "mission_control-jobs"
# mount MissionControl::Jobs::Engine, at: "/jobs"
```

Solid Queue vs Sidekiq comparison:

| Feature | Solid Queue | Sidekiq |
|---|---|---|
| Backend | SQL database | Redis |
| Infrastructure | No extra services | Requires Redis |
| Concurrency control | Built-in `limits_concurrency` | Requires sidekiq-unique-jobs |
| Recurring jobs | Built-in (recurring.yml) | Requires sidekiq-cron |
| Web UI | Mission Control (optional) | Sidekiq Web |
| Performance | Good for most apps | Higher throughput |
| Transactions | Full ACID (same DB) | Eventual consistency |
| Best for | Most Rails apps | High-throughput (>10k jobs/min) |

Key patterns:
- **Solid Queue uses your existing database** -- no Redis needed
- **`limits_concurrency`** prevents duplicate processing (replaces sidekiq-unique-jobs)
- **`recurring.yml`** replaces cron/whenever for scheduled jobs
- **Separate database** recommended for production to avoid locking contention
- **Mission Control** provides a web dashboard for monitoring and retrying jobs
- **Polynomially longer retries** with `retry_on` for graceful error handling'''
    ),
    (
        "rails/solid-cache-cable",
        "Show how to use Solid Cache and Solid Cable in Rails 8, replacing Redis for caching and WebSocket pub/sub with database-backed alternatives.",
        '''Solid Cache and Solid Cable replace Redis for caching and Action Cable pub/sub respectively, using your SQL database. This eliminates Redis as a dependency for most Rails applications.

```ruby
# --- Solid Cache Configuration ---

# config/cache.yml
# production:
#   database: cache
#   store_options:
#     max_age: 1.week
#     max_size: 256.megabytes
#     namespace: myapp
#   encrypt: false

# config/database.yml (add cache database)
# production:
#   primary:
#     <<: *default
#     database: myapp_production
#   cache:
#     <<: *default
#     database: myapp_cache_production
#     migrations_paths: db/cache_migrate

# config/environments/production.rb
# config.cache_store = :solid_cache_store

# --- Using Rails caching with Solid Cache ---

# app/controllers/products_controller.rb
class ProductsController < ApplicationController
  def index
    @products = Rails.cache.fetch("products/index", expires_in: 15.minutes) do
      Product.includes(:category).order(created_at: :desc).limit(50).to_a
    end
  end

  def show
    @product = Rails.cache.fetch(["product", params[:id]], expires_in: 1.hour) do
      Product.includes(:reviews, :variants).find(params[:id])
    end
  end
end

# app/models/product.rb
class Product < ApplicationRecord
  belongs_to :category
  has_many :reviews
  has_many :variants

  # Automatic cache invalidation via touch
  after_commit :invalidate_cache

  def cached_average_rating
    Rails.cache.fetch("#{cache_key_with_version}/avg_rating", expires_in: 6.hours) do
      reviews.average(:rating)&.round(1) || 0.0
    end
  end

  def cached_stock_count
    Rails.cache.fetch("#{cache_key_with_version}/stock", expires_in: 5.minutes) do
      variants.sum(:stock_count)
    end
  end

  private

  def invalidate_cache
    Rails.cache.delete_matched("product*#{id}*")
  end
end

# --- Fragment caching in views ---
# app/views/products/index.html.erb
# <% cache ["products-list", @products.maximum(:updated_at)] do %>
#   <% @products.each do |product| %>
#     <% cache product do %>
#       <%= render partial: "product", locals: { product: product } %>
#     <% end %>
#   <% end %>
# <% end %>

# --- Cache write-through pattern ---
class CatalogService
  def update_product(product, params)
    product.update!(params)

    # Write-through: update cache immediately after DB write
    Rails.cache.write(
      ["product", product.id],
      product.reload,
      expires_in: 1.hour
    )

    # Invalidate list caches
    Rails.cache.delete("products/index")

    product
  end
end
```

```ruby
# --- Solid Cable Configuration ---

# config/cable.yml
# production:
#   adapter: solid_cable
#   silence_polling: true
#   polling_interval: 0.1.seconds
#   connects_to:
#     database:
#       writing: cable

# config/database.yml (add cable database)
# production:
#   cable:
#     <<: *default
#     database: myapp_cable_production
#     migrations_paths: db/cable_migrate

# --- Action Cable channel with Solid Cable ---

# app/channels/chat_channel.rb
class ChatChannel < ApplicationCable::Channel
  def subscribed
    @room = ChatRoom.find(params[:room_id])

    # Authorization check
    reject unless current_user.can_access?(@room)

    stream_for @room
  end

  def speak(data)
    message = @room.messages.create!(
      user: current_user,
      body: data["body"],
      message_type: data["type"] || "text"
    )

    # Broadcast to all subscribers (via Solid Cable / database)
    ChatChannel.broadcast_to(@room, {
      id: message.id,
      body: message.body,
      user: {
        id: current_user.id,
        name: current_user.name,
        avatar_url: current_user.avatar_url
      },
      created_at: message.created_at.iso8601,
      type: message.message_type
    })
  end

  def typing(data)
    ChatChannel.broadcast_to(@room, {
      type: "typing",
      user_id: current_user.id,
      user_name: current_user.name,
      is_typing: data["is_typing"]
    })
  end

  def unsubscribed
    # Notify room that user left
    ChatChannel.broadcast_to(@room, {
      type: "presence",
      user_id: current_user.id,
      status: "offline"
    })
  end
end

# app/channels/notification_channel.rb
class NotificationChannel < ApplicationCable::Channel
  def subscribed
    stream_for current_user
  end

  # Broadcast from anywhere in the app
  # NotificationChannel.broadcast_to(user, { title: "New order", body: "..." })
end

# --- Broadcasting from models/services ---

# app/models/order.rb
class Order < ApplicationRecord
  after_create_commit :notify_admin

  private

  def notify_admin
    # Broadcast to admin dashboard
    ActionCable.server.broadcast("admin_orders", {
      type: "new_order",
      order_id: id,
      total: total.to_f,
      customer: user.name
    })

    # Notify the specific user
    NotificationChannel.broadcast_to(user, {
      type: "order_confirmation",
      title: "Order ##{id} confirmed",
      body: "Your order for #{total} has been placed."
    })
  end
end
```

Solid Stack comparison with Redis:

| Component | Redis-based | Solid (Database) | Trade-off |
|---|---|---|---|
| Background jobs | Sidekiq | Solid Queue | DB queries vs Redis memory |
| Caching | Redis cache store | Solid Cache | Slightly slower, no Redis needed |
| WebSocket pub/sub | Redis adapter | Solid Cable | Polling vs push, simpler infra |
| Session store | Redis session | DB sessions | Already standard in Rails |

Key patterns:
- **Solid Cache uses database-backed storage** with configurable max_age and max_size
- **Solid Cable uses database polling** instead of Redis pub/sub (0.1s polling default)
- **Separate databases** for cache and cable prevent contention with primary
- **Fragment caching** works identically whether backed by Redis or Solid Cache
- **Cache versioning** via `cache_key_with_version` handles model updates automatically
- **All three Solid gems are default in Rails 8** -- no Redis needed for typical apps'''
    ),
    (
        "rails/kamal-deployment",
        "Show how to deploy a Rails 8 application with Kamal 2, including configuration, zero-downtime deploys, SSL with Let's Encrypt, and multi-server setup.",
        '''Kamal 2 is Rails 8 default deployment tool. It deploys Docker containers to bare servers via SSH, with zero-downtime rollouts, built-in SSL, and no Kubernetes required.

```yaml
# --- config/deploy.yml ---

service: myapp
image: myregistry/myapp

servers:
  web:
    hosts:
      - 203.0.113.10
      - 203.0.113.11
    labels:
      traefik.http.routers.myapp.rule: Host(`myapp.com`)
      traefik.http.routers.myapp.tls.certresolver: letsencrypt
    options:
      memory: 512m
      cpus: "1.0"
  job:
    hosts:
      - 203.0.113.12
    cmd: bin/jobs  # runs Solid Queue workers

proxy:
  ssl: true
  host: myapp.com
  # Kamal 2 uses kamal-proxy instead of Traefik
  # Automatic Let's Encrypt SSL certificates

registry:
  server: ghcr.io
  username: myorg
  password:
    - KAMAL_REGISTRY_PASSWORD  # from .kamal/secrets

builder:
  arch: amd64
  # Multi-platform builds
  # multiarch: true
  # Remote builder for faster CI builds
  # remote:
  #   arch: amd64
  #   host: ssh://builder@build-server

env:
  clear:
    RAILS_ENV: production
    RAILS_LOG_TO_STDOUT: "1"
    RAILS_SERVE_STATIC_FILES: "1"
    SOLID_QUEUE_IN_PUMA: "0"
  secret:
    - RAILS_MASTER_KEY
    - DATABASE_URL
    - SMTP_PASSWORD

accessories:
  db:
    image: postgres:16-alpine
    host: 203.0.113.12
    port: "5432:5432"
    env:
      clear:
        POSTGRES_DB: myapp_production
      secret:
        - POSTGRES_PASSWORD
    directories:
      - data:/var/lib/postgresql/data
    options:
      memory: 1g

  redis:
    image: redis:7-alpine
    host: 203.0.113.12
    port: "6379:6379"
    directories:
      - data:/data

healthcheck:
  path: /up
  port: 3000
  max_attempts: 10
  interval: 5s
```

```ruby
# --- .kamal/secrets (encrypted or from env) ---
# KAMAL_REGISTRY_PASSWORD=$GITHUB_TOKEN
# RAILS_MASTER_KEY=$(cat config/master.key)
# DATABASE_URL=postgres://myapp:secret@203.0.113.12/myapp_production
# POSTGRES_PASSWORD=secret
# SMTP_PASSWORD=smtp_secret

# --- Dockerfile (Rails 8 default, optimized for production) ---

# syntax=docker/dockerfile:1
# check=error=true

ARG RUBY_VERSION=3.3.6
FROM docker.io/library/ruby:$RUBY_VERSION-slim AS base

WORKDIR /rails

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
      curl libjemalloc2 libvips postgresql-client && \
    rm -rf /var/lib/apt/lists /var/cache/apt/archives

ENV RAILS_ENV="production" \
    BUNDLE_DEPLOYMENT="1" \
    BUNDLE_PATH="/usr/local/bundle" \
    BUNDLE_WITHOUT="development:test"

FROM base AS build

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
      build-essential git libpq-dev node-gyp pkg-config python-is-python3 && \
    rm -rf /var/lib/apt/lists /var/cache/apt/archives

COPY Gemfile Gemfile.lock ./
RUN bundle install && \
    rm -rf ~/.bundle/ "${BUNDLE_PATH}"/ruby/*/cache

COPY . .

RUN SECRET_KEY_BASE_DUMMY=1 ./bin/rails assets:precompile

FROM base

COPY --from=build "${BUNDLE_PATH}" "${BUNDLE_PATH}"
COPY --from=build /rails /rails

RUN groupadd --system --gid 1000 rails && \
    useradd rails --uid 1000 --gid 1000 --create-home --shell /bin/bash && \
    chown -R rails:rails db log storage tmp

USER 1000:1000

ENTRYPOINT ["/rails/bin/docker-entrypoint"]
EXPOSE 3000
CMD ["./bin/thrust", "./bin/rails", "server"]
```

```bash
# --- Kamal deployment commands ---

# Initial setup: install Docker on servers, start accessories
kamal setup

# Deploy new version (zero-downtime)
kamal deploy

# Deployment flow:
# 1. Build Docker image locally (or on remote builder)
# 2. Push to container registry
# 3. Pull image on all servers
# 4. Start new containers alongside old ones
# 5. Wait for health check to pass
# 6. Switch proxy to new containers
# 7. Stop old containers
# 8. Total downtime: 0 seconds

# Rollback to previous version
kamal rollback

# View logs from all servers
kamal app logs -f

# Run console on a web server
kamal app exec -i "bin/rails console"

# Run migrations
kamal app exec "bin/rails db:migrate"

# Restart just the job workers
kamal app boot --roles=job

# View running containers
kamal details

# Lock deployments (during maintenance)
kamal lock acquire -m "Database migration in progress"
kamal lock release

# Environment variable management
kamal env push  # push secrets to servers
```

Kamal 2 deployment architecture:

| Component | Role | Details |
|---|---|---|
| kamal-proxy | Reverse proxy + SSL | Replaces Traefik, automatic Let's Encrypt |
| Web servers | Run Rails app containers | Zero-downtime rolling deploys |
| Job servers | Run Solid Queue workers | Separate role in deploy.yml |
| Accessories | Managed services (DB, Redis) | Docker containers on specified hosts |
| Registry | Container image storage | Docker Hub, GHCR, ECR, etc. |
| Builder | Builds Docker images | Local, remote, or CI |

Key patterns:
- **Kamal deploys Docker containers to bare servers via SSH** -- no Kubernetes
- **Zero-downtime deploys** via blue-green container switching through kamal-proxy
- **Automatic SSL** with Let's Encrypt via kamal-proxy
- **Accessories** manage databases, Redis, and other services as Docker containers
- **Secrets** are stored in `.kamal/secrets` (gitignored) and pushed to servers
- **Health checks** verify the app is ready before routing traffic
- **Rollback** is instant -- just switches back to the previous container image'''
    ),
    (
        "rails/hotwire-turbo",
        "Show Rails 8 Hotwire patterns including Turbo Drive, Turbo Frames, Turbo Streams, and Stimulus controllers for building reactive UIs without writing JavaScript SPAs.",
        '''Hotwire (HTML Over The Wire) is Rails default frontend framework. It sends HTML fragments instead of JSON, enabling reactive UIs with minimal JavaScript. Turbo handles navigation, frames, and streams; Stimulus adds behavior.

```ruby
# --- Turbo Frames: partial page updates ---

# app/views/products/index.html.erb
<h1>Products</h1>

<!-- Turbo Frame: search form updates only the product list -->
<%= turbo_frame_tag "product_search" do %>
  <%= form_with url: products_path, method: :get, data: {
    turbo_frame: "products_list",
    controller: "debounce",
    action: "input->debounce#search"
  } do |f| %>
    <%= f.search_field :q, value: params[:q],
        placeholder: "Search products...",
        data: { debounce_target: "input" } %>
    <%= f.select :category, Category.pluck(:name, :id),
        { include_blank: "All Categories" },
        { data: { action: "change->debounce#search" } } %>
  <% end %>
<% end %>

<!-- This frame gets replaced when the form submits -->
<%= turbo_frame_tag "products_list" do %>
  <div id="products" class="grid grid-cols-3 gap-4">
    <%= render @products %>
  </div>

  <%# Turbo Frame pagination -- only updates the frame %>
  <% if @products.next_page? %>
    <%= link_to "Load more", products_path(page: @products.next_page),
        data: { turbo_frame: "products_list" } %>
  <% end %>
<% end %>

# --- Turbo Frame for inline editing ---
# app/views/products/_product.html.erb
<%= turbo_frame_tag dom_id(product) do %>
  <div class="product-card">
    <h3><%= product.name %></h3>
    <p><%= number_to_currency(product.price) %></p>

    <!-- Clicking edit loads the edit form INTO this frame -->
    <%= link_to "Edit", edit_product_path(product),
        class: "btn btn-sm" %>
  </div>
<% end %>

# app/views/products/edit.html.erb
<%= turbo_frame_tag dom_id(@product) do %>
  <%= form_with model: @product, class: "product-form" do |f| %>
    <%= f.text_field :name %>
    <%= f.number_field :price, step: 0.01 %>
    <%= f.submit "Save" %>
    <%= link_to "Cancel", product_path(@product) %>
  <% end %>
<% end %>
```

```ruby
# --- Turbo Streams: real-time DOM updates ---

# app/controllers/products_controller.rb
class ProductsController < ApplicationController
  def create
    @product = Product.new(product_params)

    if @product.save
      respond_to do |format|
        format.turbo_stream  # renders create.turbo_stream.erb
        format.html { redirect_to products_path }
      end
    else
      render :new, status: :unprocessable_entity
    end
  end

  def destroy
    @product = Product.find(params[:id])
    @product.destroy

    respond_to do |format|
      format.turbo_stream {
        render turbo_stream: turbo_stream.remove(dom_id(@product))
      }
      format.html { redirect_to products_path }
    end
  end
end

# app/views/products/create.turbo_stream.erb
<%= turbo_stream.prepend "products" do %>
  <%= render @product %>
<% end %>

<%= turbo_stream.update "product_count" do %>
  <%= Product.count %> products
<% end %>

<%= turbo_stream.replace "product_search" do %>
  <%= render "search_form", query: "" %>
<% end %>

# --- Turbo Streams via Action Cable (real-time) ---

# app/models/product.rb
class Product < ApplicationRecord
  # Automatically broadcast to all connected clients
  broadcasts_to ->(product) { "products" },
    inserts_by: :prepend,
    target: "products"

  # Or with more control:
  after_create_commit -> {
    broadcast_prepend_to "products",
      target: "products",
      partial: "products/product",
      locals: { product: self }
  }

  after_update_commit -> {
    broadcast_replace_to "products",
      target: dom_id(self),
      partial: "products/product",
      locals: { product: self }
  }

  after_destroy_commit -> {
    broadcast_remove_to "products",
      target: dom_id(self)
  }
end

# app/views/products/index.html.erb (subscribe to broadcasts)
<%= turbo_stream_from "products" %>
<div id="products">
  <%= render @products %>
</div>
# Any create/update/delete from ANY user updates ALL connected browsers
```

```ruby
# --- Stimulus Controllers: JavaScript behavior ---

# app/javascript/controllers/debounce_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["input"]

  connect() {
    this.timeout = null
  }

  search() {
    clearTimeout(this.timeout)
    this.timeout = setTimeout(() => {
      this.element.requestSubmit()
    }, 300)
  }

  disconnect() {
    clearTimeout(this.timeout)
  }
}

# app/javascript/controllers/clipboard_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["source", "button"]
  static values = { successMessage: { type: String, default: "Copied!" } }

  async copy() {
    const text = this.sourceTarget.value || this.sourceTarget.textContent
    await navigator.clipboard.writeText(text.trim())

    const original = this.buttonTarget.textContent
    this.buttonTarget.textContent = this.successMessageValue
    setTimeout(() => {
      this.buttonTarget.textContent = original
    }, 2000)
  }
}

# app/javascript/controllers/auto_submit_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { delay: { type: Number, default: 200 } }

  submit() {
    clearTimeout(this.timeout)
    this.timeout = setTimeout(() => {
      this.element.requestSubmit()
    }, this.delayValue)
  }
}

# Usage in HTML:
# <form data-controller="auto-submit" data-action="input->auto-submit#submit">
#   <select data-action="change->auto-submit#submit">...</select>
# </form>
```

Hotwire architecture:

| Component | Purpose | Replaces |
|---|---|---|
| Turbo Drive | SPA-like navigation | Turbolinks / full page reloads |
| Turbo Frames | Partial page updates | AJAX + manual DOM updates |
| Turbo Streams | Targeted DOM mutations | React/Vue state management |
| Stimulus | Lightweight JS behavior | jQuery / heavy JS frameworks |

Key patterns:
- **Turbo Drive** intercepts all link clicks and form submissions, replacing the body via fetch
- **Turbo Frames** scope updates to a specific area of the page (like an iframe but better)
- **Turbo Streams** allow the server to append/prepend/replace/remove DOM elements
- **Broadcasting** via Action Cable pushes Turbo Streams to all connected clients in real-time
- **Stimulus** controllers add just enough JavaScript for interactivity (toggles, debounce, clipboard)
- **No JSON API needed** -- the server renders HTML fragments directly
- **Progressive enhancement** -- works without JavaScript, enhanced with it'''
    ),
    (
        "rails/authentication-propshaft",
        "Show the Rails 8 authentication generator and Propshaft asset pipeline, including session-based auth setup, password reset flows, and how Propshaft replaces Sprockets.",
        '''Rails 8 includes a built-in authentication generator that creates a complete session-based auth system, and Propshaft replaces Sprockets as the default asset pipeline.

```ruby
# --- Generate authentication scaffolding ---
# rails generate authentication
#
# This creates:
# - User model with has_secure_password
# - Session model for tracking sessions
# - Authentication concern for controllers
# - Login/logout controllers and views
# - Password reset flow with mailer

# --- app/models/user.rb (generated + customized) ---
class User < ApplicationRecord
  has_secure_password
  has_many :sessions, dependent: :destroy

  validates :email_address,
    presence: true,
    uniqueness: { case_sensitive: false },
    format: { with: URI::MailTo::EMAIL_REGEXP }
  validates :password,
    length: { minimum: 12 },
    allow_nil: true  # nil on update when not changing password

  normalizes :email_address, with: ->(e) { e.strip.downcase }

  # Generate password reset token
  generates_token_for :password_reset, expires_in: 15.minutes do
    password_salt&.last(10)  # invalidated when password changes
  end

  generates_token_for :email_verification, expires_in: 24.hours do
    email_address
  end
end

# --- app/models/session.rb ---
class Session < ApplicationRecord
  belongs_to :user

  before_create do
    self.ip_address = Current.ip_address
    self.user_agent = Current.user_agent
  end

  # Expire sessions after 30 days of inactivity
  scope :active, -> { where("updated_at > ?", 30.days.ago) }
end

# --- app/controllers/concerns/authentication.rb ---
module Authentication
  extend ActiveSupport::Concern

  included do
    before_action :require_authentication
    helper_method :authenticated?
  end

  class_methods do
    def allow_unauthenticated_access(**options)
      skip_before_action :require_authentication, **options
    end
  end

  private

  def authenticated?
    resume_session.present?
  end

  def require_authentication
    resume_session || request_authentication
  end

  def resume_session
    Current.session ||= find_session_by_cookie
  end

  def find_session_by_cookie
    Session.find_by(id: cookies.signed[:session_id])
  end

  def request_authentication
    session[:return_to_after_authenticating] = request.url
    redirect_to new_session_url
  end

  def after_authentication_url
    session.delete(:return_to_after_authenticating) || root_url
  end

  def start_new_session_for(user)
    user.sessions.create!(
      ip_address: request.remote_ip,
      user_agent: request.user_agent
    ).tap do |session|
      Current.session = session
      cookies.signed.permanent[:session_id] = {
        value: session.id,
        httponly: true,
        same_site: :lax
      }
    end
  end

  def terminate_session
    Current.session&.destroy
    cookies.delete(:session_id)
  end
end
```

```ruby
# --- app/controllers/sessions_controller.rb ---
class SessionsController < ApplicationController
  allow_unauthenticated_access only: %i[new create]
  rate_limit to: 10, within: 3.minutes, only: :create,
    with: -> { redirect_to new_session_url, alert: "Try again later." }

  def new
  end

  def create
    if user = User.authenticate_by(
      email_address: params[:email_address],
      password: params[:password]
    )
      start_new_session_for(user)
      redirect_to after_authentication_url
    else
      redirect_to new_session_url,
        alert: "Invalid email or password."
    end
  end

  def destroy
    terminate_session
    redirect_to new_session_url
  end
end

# --- app/controllers/passwords_controller.rb ---
class PasswordsController < ApplicationController
  allow_unauthenticated_access
  before_action :set_user_by_token, only: %i[edit update]

  def new
  end

  def create
    if user = User.find_by(email_address: params[:email_address])
      PasswordsMailer.reset(user).deliver_later
    end
    # Always show success to prevent email enumeration
    redirect_to new_session_url,
      notice: "Check your email for reset instructions."
  end

  def edit
  end

  def update
    if @user.update(password_params)
      redirect_to new_session_url,
        notice: "Password updated. Please sign in."
    else
      render :edit, status: :unprocessable_entity
    end
  end

  private

  def set_user_by_token
    @user = User.find_by_token_for!(:password_reset, params[:token])
  rescue ActiveSupport::MessageVerifier::InvalidSignature
    redirect_to new_password_url,
      alert: "Reset link is invalid or has expired."
  end

  def password_params
    params.permit(:password, :password_confirmation)
  end
end

# --- app/mailers/passwords_mailer.rb ---
class PasswordsMailer < ApplicationMailer
  def reset(user)
    @user = user
    @signed_token = @user.generate_token_for(:password_reset)

    mail to: @user.email_address,
         subject: "Reset your password"
  end
end
```

```ruby
# --- Propshaft Asset Pipeline (replaces Sprockets) ---

# Propshaft is simpler than Sprockets:
# - No compilation (no Sass, CoffeeScript built-in)
# - Just fingerprints and serves static assets
# - Use Import Maps for JavaScript (no webpack/esbuild needed)

# config/importmap.rb
pin "application"
pin "@hotwired/turbo-rails", to: "turbo.min.js"
pin "@hotwired/stimulus", to: "stimulus.min.js"
pin "@hotwired/stimulus-loading", to: "stimulus-loading.js"

# Pin all stimulus controllers
pin_all_from "app/javascript/controllers", under: "controllers"

# Pin from CDN (jspm.org or unpkg)
pin "sortablejs", to: "https://ga.jspm.io/npm:sortablejs@1.15.6/Sortable.min.js"
pin "chart.js", to: "https://ga.jspm.io/npm:chart.js@4.4.7/dist/chart.js"
pin "lodash/debounce", to: "https://ga.jspm.io/npm:lodash.debounce@4.0.8/index.js"

# --- app/javascript/application.js ---
# import "@hotwired/turbo-rails"
# import "controllers"

# --- CSS with Propshaft ---
# app/assets/stylesheets/application.css
# Just use standard CSS (or Tailwind CSS via tailwindcss-rails gem)
# Propshaft fingerprints and serves the files

# In layouts:
# <%= stylesheet_link_tag "application", data: { turbo_track: "reload" } %>
# <%= javascript_importmap_tags %>

# Asset helpers work the same:
# image_tag "logo.svg"
# asset_path "icons/check.svg"

# Propshaft config (config/application.rb):
# config.assets.paths << Rails.root.join("vendor/assets")
```

Rails 8 default stack:

| Component | Rails 7 Default | Rails 8 Default |
|---|---|---|
| Asset pipeline | Sprockets | Propshaft |
| JavaScript | Importmap (or esbuild) | Import Maps |
| CSS | Sprockets | Propshaft + Tailwind |
| Background jobs | None (add Sidekiq) | Solid Queue |
| Caching | Redis | Solid Cache |
| WebSocket pub/sub | Redis | Solid Cable |
| Deployment | Capistrano | Kamal 2 |
| Authentication | Devise (gem) | Built-in generator |
| Frontend | Turbo + Stimulus | Turbo + Stimulus |

Key patterns:
- **Authentication generator** provides secure session-based auth with password resets
- **`has_secure_password`** uses bcrypt for password hashing
- **`generates_token_for`** creates purpose-specific, expiring tokens (no separate token table)
- **Rate limiting** is built into controllers with `rate_limit`
- **Propshaft** is simpler than Sprockets -- just fingerprinting, no compilation
- **Import Maps** eliminate the need for Node.js, webpack, or esbuild for most apps
- **The entire Rails 8 stack requires no Redis and no Node.js** -- just Ruby and a database'''
    ),
]
