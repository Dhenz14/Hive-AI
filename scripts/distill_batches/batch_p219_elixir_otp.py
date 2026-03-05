"""Elixir/OTP -- GenServer patterns, supervision trees, Phoenix LiveView, distributed Elixir with libcluster, Broadway for data pipelines, Nx for ML."""

PAIRS = [
    (
        "elixir/genserver-patterns",
        "Show advanced GenServer patterns in Elixir including state management, call vs cast semantics, handle_continue, timeouts, and production-ready patterns for building stateful services.",
        '''GenServer is the fundamental building block of OTP applications. It provides a process that maintains state, handles synchronous and asynchronous messages, and integrates with supervisors for fault tolerance.

```elixir
# --- Production-ready GenServer: Rate Limiter ---

defmodule RateLimiter do
  @moduledoc """
  Token bucket rate limiter implemented as a GenServer.
  Each bucket is identified by a key (e.g., user_id or IP).
  """
  use GenServer

  # Client API (runs in the caller's process)

  def start_link(opts) do
    name = Keyword.get(opts, :name, __MODULE__)
    config = %{
      max_tokens: Keyword.get(opts, :max_tokens, 100),
      refill_rate: Keyword.get(opts, :refill_rate, 10),  # tokens per second
      refill_interval: Keyword.get(opts, :refill_interval, 1_000),  # ms
      cleanup_interval: Keyword.get(opts, :cleanup_interval, 60_000)  # ms
    }
    GenServer.start_link(__MODULE__, config, name: name)
  end

  @doc "Check if a request is allowed. Returns :ok or {:error, :rate_limited}"
  def check_rate(server \\\\ __MODULE__, key, cost \\\\ 1) do
    GenServer.call(server, {:check_rate, key, cost})
  end

  @doc "Get current bucket status for a key"
  def get_bucket(server \\\\ __MODULE__, key) do
    GenServer.call(server, {:get_bucket, key})
  end

  @doc "Reset a specific bucket"
  def reset(server \\\\ __MODULE__, key) do
    GenServer.cast(server, {:reset, key})
  end

  # Server callbacks (runs in the GenServer process)

  @impl true
  def init(config) do
    # Schedule periodic refill and cleanup
    Process.send_after(self(), :refill, config.refill_interval)
    Process.send_after(self(), :cleanup, config.cleanup_interval)

    state = %{
      config: config,
      buckets: %{},  # key => %{tokens: integer, last_access: DateTime}
      stats: %{total_requests: 0, total_limited: 0}
    }

    {:ok, state}
  end

  @impl true
  def handle_call({:check_rate, key, cost}, _from, state) do
    {result, new_state} = consume_tokens(state, key, cost)
    {:reply, result, new_state}
  end

  def handle_call({:get_bucket, key}, _from, state) do
    bucket = Map.get(state.buckets, key, default_bucket(state.config))
    {:reply, bucket, state}
  end

  @impl true
  def handle_cast({:reset, key}, state) do
    new_buckets = Map.delete(state.buckets, key)
    {:noreply, %{state | buckets: new_buckets}}
  end

  @impl true
  def handle_info(:refill, state) do
    # Refill all buckets
    max = state.config.max_tokens
    rate = state.config.refill_rate

    new_buckets =
      Map.new(state.buckets, fn {key, bucket} ->
        new_tokens = min(bucket.tokens + rate, max)
        {key, %{bucket | tokens: new_tokens}}
      end)

    Process.send_after(self(), :refill, state.config.refill_interval)
    {:noreply, %{state | buckets: new_buckets}}
  end

  def handle_info(:cleanup, state) do
    # Remove buckets not accessed in the last 5 minutes
    cutoff = DateTime.add(DateTime.utc_now(), -300, :second)

    new_buckets =
      state.buckets
      |> Enum.reject(fn {_key, bucket} ->
        DateTime.compare(bucket.last_access, cutoff) == :lt
      end)
      |> Map.new()

    Process.send_after(self(), :cleanup, state.config.cleanup_interval)
    {:noreply, %{state | buckets: new_buckets}}
  end

  # Private functions

  defp consume_tokens(state, key, cost) do
    bucket = Map.get(state.buckets, key, default_bucket(state.config))

    if bucket.tokens >= cost do
      new_bucket = %{bucket |
        tokens: bucket.tokens - cost,
        last_access: DateTime.utc_now()
      }
      new_state = %{state |
        buckets: Map.put(state.buckets, key, new_bucket),
        stats: %{state.stats | total_requests: state.stats.total_requests + 1}
      }
      {:ok, new_state}
    else
      new_state = %{state |
        stats: %{state.stats |
          total_requests: state.stats.total_requests + 1,
          total_limited: state.stats.total_limited + 1
        }
      }
      {{:error, :rate_limited, bucket.tokens}, new_state}
    end
  end

  defp default_bucket(config) do
    %{tokens: config.max_tokens, last_access: DateTime.utc_now()}
  end
end
```

```elixir
# --- GenServer with handle_continue for async initialization ---

defmodule CacheWarmer do
  use GenServer

  def start_link(opts) do
    GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  end

  def get(key) do
    GenServer.call(__MODULE__, {:get, key})
  end

  @impl true
  def init(opts) do
    # Return immediately, then do expensive initialization async
    # handle_continue runs before any call/cast is processed
    {:ok, %{data: %{}, status: :initializing}, {:continue, :warm_cache}}
  end

  @impl true
  def handle_continue(:warm_cache, state) do
    # This runs asynchronously but BEFORE any handle_call
    data = expensive_data_load()
    {:noreply, %{state | data: data, status: :ready}}
  end

  @impl true
  def handle_call({:get, key}, _from, %{status: :ready} = state) do
    {:reply, Map.get(state.data, key), state}
  end

  def handle_call({:get, _key}, _from, %{status: :initializing} = state) do
    {:reply, {:error, :not_ready}, state}
  end

  defp expensive_data_load do
    # Simulate loading data from database or external API
    Process.sleep(2_000)
    %{"users" => 1000, "products" => 5000}
  end
end

# --- GenServer with timeout (idle shutdown) ---

defmodule SessionWorker do
  use GenServer

  @idle_timeout :timer.minutes(30)

  def start_link(session_id) do
    GenServer.start_link(__MODULE__, session_id,
      name: via_tuple(session_id))
  end

  def get_data(session_id) do
    GenServer.call(via_tuple(session_id), :get_data)
  end

  def put_data(session_id, key, value) do
    GenServer.call(via_tuple(session_id), {:put_data, key, value})
  end

  defp via_tuple(session_id) do
    {:via, Registry, {SessionRegistry, session_id}}
  end

  @impl true
  def init(session_id) do
    state = %{
      session_id: session_id,
      data: %{},
      created_at: DateTime.utc_now()
    }
    # Timeout: if no message received within @idle_timeout,
    # handle_info(:timeout, state) is called
    {:ok, state, @idle_timeout}
  end

  @impl true
  def handle_call(:get_data, _from, state) do
    {:reply, state.data, state, @idle_timeout}
  end

  def handle_call({:put_data, key, value}, _from, state) do
    new_data = Map.put(state.data, key, value)
    {:reply, :ok, %{state | data: new_data}, @idle_timeout}
  end

  @impl true
  def handle_info(:timeout, state) do
    # Process has been idle for @idle_timeout — shut down
    {:stop, :normal, state}
  end
end
```

GenServer callback flow:

| Callback | Triggered By | Returns | Semantics |
|---|---|---|---|
| `init/1` | `start_link` | `{:ok, state}` | Initialize state |
| `handle_call/3` | `GenServer.call` | `{:reply, reply, state}` | Synchronous, caller waits |
| `handle_cast/2` | `GenServer.cast` | `{:noreply, state}` | Asynchronous, fire-and-forget |
| `handle_info/2` | `send` / timer / monitor | `{:noreply, state}` | Raw messages |
| `handle_continue/2` | Return `{:continue, term}` | `{:noreply, state}` | Post-init async work |
| `terminate/2` | Process shutdown | Ignored | Cleanup resources |

Key patterns:
- **`call`** for queries (synchronous, returns a value, caller blocks)
- **`cast`** for commands (asynchronous, fire-and-forget)
- **`handle_continue`** for expensive initialization without blocking start_link
- **Timeouts** enable idle process shutdown (useful for per-session workers)
- **`Process.send_after`** for periodic work (heartbeats, cleanup, refill)
- **Registry** for dynamic process naming (via tuples)
- Always design for crash recovery -- state should be reconstructable from the database'''
    ),
    (
        "elixir/supervision-trees",
        "Show how to design Elixir/OTP supervision trees for fault-tolerant applications, including different supervisor strategies, dynamic supervisors, task supervisors, and application architecture patterns.",
        '''Supervision trees are the core of OTP fault tolerance. Supervisors monitor child processes and restart them according to a strategy when they crash, providing self-healing applications.

```elixir
# --- Application supervision tree ---

defmodule MyApp.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      # Static children started in order (dependencies first)

      # 1. Telemetry and metrics
      MyApp.Telemetry,

      # 2. Database repos
      MyApp.Repo,

      # 3. Pub/sub for inter-process communication
      {Phoenix.PubSub, name: MyApp.PubSub},

      # 4. Registry for named dynamic processes
      {Registry, keys: :unique, name: MyApp.SessionRegistry},
      {Registry, keys: :duplicate, name: MyApp.EventRegistry},

      # 5. Core services (supervised individually)
      {MyApp.CacheServer, max_size: 10_000},
      {MyApp.RateLimiter, max_tokens: 100, refill_rate: 10},

      # 6. Dynamic supervisor for per-user session workers
      {DynamicSupervisor,
        name: MyApp.SessionSupervisor,
        strategy: :one_for_one,
        max_children: 10_000},

      # 7. Task supervisor for fire-and-forget async work
      {Task.Supervisor, name: MyApp.TaskSupervisor},

      # 8. Phoenix endpoint (web server)
      MyAppWeb.Endpoint
    ]

    opts = [strategy: :one_for_one, name: MyApp.Supervisor]
    Supervisor.start_link(children, opts)
  end
end

# --- Custom supervisor with rest_for_one strategy ---

defmodule MyApp.DataPipeline.Supervisor do
  use Supervisor

  def start_link(opts) do
    Supervisor.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    children = [
      # rest_for_one: if the producer crashes, restart it AND all
      # consumers that depend on it (everything after it in the list)
      {MyApp.DataPipeline.Producer, []},
      {MyApp.DataPipeline.Transformer, []},
      {MyApp.DataPipeline.Consumer, []},
      {MyApp.DataPipeline.Metrics, []}
    ]

    Supervisor.init(children, strategy: :rest_for_one)
  end
end

# --- one_for_all: if any child crashes, restart ALL children ---

defmodule MyApp.ConsensusCluster.Supervisor do
  use Supervisor

  def start_link(opts) do
    Supervisor.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    # All nodes must be consistent, so restart all if one fails
    children = [
      {MyApp.ConsensusCluster.Node, id: :node_1, name: :node_1},
      {MyApp.ConsensusCluster.Node, id: :node_2, name: :node_2},
      {MyApp.ConsensusCluster.Node, id: :node_3, name: :node_3}
    ]

    Supervisor.init(children,
      strategy: :one_for_all,
      max_restarts: 5,
      max_seconds: 60  # max 5 restarts per 60 seconds
    )
  end
end
```

```elixir
# --- DynamicSupervisor for on-demand process creation ---

defmodule MyApp.SessionManager do
  @moduledoc "Manages per-user session worker processes"

  @supervisor MyApp.SessionSupervisor

  def start_session(user_id) do
    spec = {MyApp.SessionWorker, user_id}
    case DynamicSupervisor.start_child(@supervisor, spec) do
      {:ok, pid} -> {:ok, pid}
      {:error, {:already_started, pid}} -> {:ok, pid}
      {:error, reason} -> {:error, reason}
    end
  end

  def stop_session(user_id) do
    case Registry.lookup(MyApp.SessionRegistry, user_id) do
      [{pid, _}] -> DynamicSupervisor.terminate_child(@supervisor, pid)
      [] -> {:error, :not_found}
    end
  end

  def active_sessions do
    DynamicSupervisor.count_children(@supervisor)
  end

  def all_session_ids do
    Registry.select(MyApp.SessionRegistry, [{{:"$1", :_, :_}, [], [:"$1"]}])
  end
end

# --- Task.Supervisor for supervised async work ---

defmodule MyApp.BackgroundWork do
  @task_sup MyApp.TaskSupervisor

  # Fire-and-forget: if it crashes, log it, do not retry
  def send_notification(user_id, message) do
    Task.Supervisor.start_child(@task_sup, fn ->
      MyApp.Notifications.send(user_id, message)
    end)
  end

  # Async with result: await the response
  def fetch_external_data(urls) when is_list(urls) do
    tasks =
      Enum.map(urls, fn url ->
        Task.Supervisor.async(@task_sup, fn ->
          MyApp.HttpClient.get!(url)
        end)
      end)

    # Wait up to 10 seconds for all results
    Task.await_many(tasks, 10_000)
  end

  # Async with error handling
  def fetch_with_fallback(urls) do
    tasks =
      Enum.map(urls, fn url ->
        Task.Supervisor.async_nolink(@task_sup, fn ->
          MyApp.HttpClient.get!(url)
        end)
      end)

    Enum.map(tasks, fn task ->
      case Task.yield(task, 5_000) || Task.shutdown(task) do
        {:ok, result} -> {:ok, result}
        {:exit, reason} -> {:error, reason}
        nil -> {:error, :timeout}
      end
    end)
  end
end
```

```elixir
# --- Nested supervision tree architecture ---

# Application
# |
# +-- MyApp.Supervisor (one_for_one)
#     |
#     +-- MyApp.Repo (Ecto database pool)
#     +-- Phoenix.PubSub
#     +-- MyApp.Core.Supervisor (rest_for_one)
#     |   +-- MyApp.CacheServer
#     |   +-- MyApp.RateLimiter
#     |   +-- MyApp.EventBus
#     |
#     +-- MyApp.Workers.Supervisor (one_for_one)
#     |   +-- DynamicSupervisor (sessions)
#     |   +-- Task.Supervisor (background tasks)
#     |   +-- MyApp.SchedulerWorker (periodic jobs)
#     |
#     +-- MyApp.DataPipeline.Supervisor (rest_for_one)
#     |   +-- Producer -> Transformer -> Consumer
#     |
#     +-- MyAppWeb.Endpoint (Phoenix web server)

defmodule MyApp.Core.Supervisor do
  use Supervisor

  def start_link(opts) do
    Supervisor.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    children = [
      {MyApp.CacheServer, []},
      {MyApp.RateLimiter, []},
      {MyApp.EventBus, []}
    ]

    # rest_for_one: EventBus depends on RateLimiter and CacheServer
    Supervisor.init(children, strategy: :rest_for_one)
  end
end

defmodule MyApp.Workers.Supervisor do
  use Supervisor

  def start_link(opts) do
    Supervisor.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    children = [
      {DynamicSupervisor, name: MyApp.SessionSupervisor, strategy: :one_for_one},
      {Task.Supervisor, name: MyApp.TaskSupervisor},
      MyApp.SchedulerWorker
    ]

    Supervisor.init(children, strategy: :one_for_one)
  end
end
```

Supervisor strategies:

| Strategy | Behavior | Use Case |
|---|---|---|
| `:one_for_one` | Restart only the crashed child | Independent workers |
| `:one_for_all` | Restart ALL children | Tightly coupled processes |
| `:rest_for_one` | Restart crashed + all after it | Pipeline/dependency chain |

Key patterns:
- **Let it crash**: Processes should crash on unexpected errors; supervisors handle recovery
- **Supervision trees are hierarchical**: Nest supervisors to isolate failure domains
- **DynamicSupervisor** for processes created at runtime (sessions, connections, game rooms)
- **Task.Supervisor** for fire-and-forget or async-with-await background work
- **Registry** for naming dynamic processes instead of global names or ETS
- **max_restarts/max_seconds** prevent restart loops (supervisor shuts down if exceeded)
- **Start order matters**: dependencies must start before dependents'''
    ),
    (
        "elixir/phoenix-liveview",
        "Show Phoenix LiveView patterns for building real-time interactive UIs, including lifecycle callbacks, live components, streams for large collections, uploads, and PubSub integration.",
        '''Phoenix LiveView enables rich, real-time UIs rendered on the server with automatic DOM patching over WebSocket. No JavaScript framework needed for most interactive features.

```elixir
# --- LiveView with streams for efficient large list rendering ---

defmodule MyAppWeb.ProductLive.Index do
  use MyAppWeb, :live_view

  alias MyApp.Catalog

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      # Subscribe to real-time updates
      Phoenix.PubSub.subscribe(MyApp.PubSub, "products")
    end

    socket =
      socket
      |> assign(:page_title, "Products")
      |> assign(:filter, %{category: nil, search: ""})
      |> assign(:sort_by, :name)
      |> assign(:sort_order, :asc)
      |> stream(:products, Catalog.list_products())

    {:ok, socket}
  end

  @impl true
  def handle_params(params, _uri, socket) do
    # URL-driven state (browser back/forward works)
    filter = %{
      category: params["category"],
      search: params["q"] || ""
    }

    products = Catalog.list_products(filter)

    socket =
      socket
      |> assign(:filter, filter)
      |> stream(:products, products, reset: true)

    {:noreply, socket}
  end

  @impl true
  def handle_event("search", %{"q" => query}, socket) do
    # Push URL params so search is bookmarkable
    {:noreply, push_patch(socket,
      to: ~p"/products?#{%{q: query, category: socket.assigns.filter.category}}")}
  end

  def handle_event("delete", %{"id" => id}, socket) do
    product = Catalog.get_product!(id)
    {:ok, _} = Catalog.delete_product(product)

    # stream_delete removes from the DOM efficiently
    {:noreply, stream_delete(socket, :products, product)}
  end

  def handle_event("sort", %{"field" => field}, socket) do
    field = String.to_existing_atom(field)
    order = if socket.assigns.sort_by == field do
      toggle_order(socket.assigns.sort_order)
    else
      :asc
    end

    products = Catalog.list_products(socket.assigns.filter,
      sort_by: field, sort_order: order)

    socket =
      socket
      |> assign(:sort_by, field)
      |> assign(:sort_order, order)
      |> stream(:products, products, reset: true)

    {:noreply, socket}
  end

  # Handle real-time broadcasts from other users
  @impl true
  def handle_info({:product_created, product}, socket) do
    {:noreply, stream_insert(socket, :products, product, at: 0)}
  end

  def handle_info({:product_updated, product}, socket) do
    {:noreply, stream_insert(socket, :products, product)}
  end

  def handle_info({:product_deleted, product}, socket) do
    {:noreply, stream_delete(socket, :products, product)}
  end

  defp toggle_order(:asc), do: :desc
  defp toggle_order(:desc), do: :asc

  @impl true
  def render(assigns) do
    ~H"""
    <div class="container">
      <h1><%= @page_title %></h1>

      <form phx-change="search" phx-submit="search">
        <input type="text" name="q" value={@filter.search}
               placeholder="Search products..."
               phx-debounce="300" />
      </form>

      <table>
        <thead>
          <tr>
            <th phx-click="sort" phx-value-field="name">
              Name <%= sort_indicator(:name, @sort_by, @sort_order) %>
            </th>
            <th phx-click="sort" phx-value-field="price">
              Price <%= sort_indicator(:price, @sort_by, @sort_order) %>
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="products" phx-update="stream">
          <tr :for={{dom_id, product} <- @streams.products} id={dom_id}>
            <td><%= product.name %></td>
            <td><%= product.price %></td>
            <td>
              <.link navigate={~p"/products/#{product}"}>View</.link>
              <button phx-click="delete" phx-value-id={product.id}
                      data-confirm="Are you sure?">
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    """
  end

  defp sort_indicator(field, current_field, order) when field == current_field do
    if order == :asc, do: "^", else: "v"
  end
  defp sort_indicator(_, _, _), do: ""
end
```

```elixir
# --- Live Components for reusable UI elements ---

defmodule MyAppWeb.ProductLive.FormComponent do
  use MyAppWeb, :live_component

  alias MyApp.Catalog

  @impl true
  def render(assigns) do
    ~H"""
    <div>
      <.header>
        <%= @title %>
      </.header>

      <.simple_form
        for={@form}
        id="product-form"
        phx-target={@myself}
        phx-change="validate"
        phx-submit="save"
      >
        <.input field={@form[:name]} type="text" label="Name" />
        <.input field={@form[:description]} type="textarea" label="Description" />
        <.input field={@form[:price]} type="number" label="Price" step="0.01" />
        <.input field={@form[:category_id]} type="select" label="Category"
                options={@categories} />

        <:actions>
          <.button phx-disable-with="Saving...">Save Product</.button>
        </:actions>
      </.simple_form>
    </div>
    """
  end

  @impl true
  def update(%{product: product} = assigns, socket) do
    changeset = Catalog.change_product(product)
    categories = Catalog.list_categories() |> Enum.map(&{&1.name, &1.id})

    socket =
      socket
      |> assign(assigns)
      |> assign(:categories, categories)
      |> assign_form(changeset)

    {:ok, socket}
  end

  @impl true
  def handle_event("validate", %{"product" => params}, socket) do
    changeset =
      socket.assigns.product
      |> Catalog.change_product(params)
      |> Map.put(:action, :validate)

    {:noreply, assign_form(socket, changeset)}
  end

  def handle_event("save", %{"product" => params}, socket) do
    save_product(socket, socket.assigns.action, params)
  end

  defp save_product(socket, :edit, params) do
    case Catalog.update_product(socket.assigns.product, params) do
      {:ok, product} ->
        notify_parent({:saved, product})
        {:noreply,
         socket
         |> put_flash(:info, "Product updated")
         |> push_patch(to: socket.assigns.patch)}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign_form(socket, changeset)}
    end
  end

  defp save_product(socket, :new, params) do
    case Catalog.create_product(params) do
      {:ok, product} ->
        notify_parent({:saved, product})
        {:noreply,
         socket
         |> put_flash(:info, "Product created")
         |> push_patch(to: socket.assigns.patch)}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign_form(socket, changeset)}
    end
  end

  defp assign_form(socket, changeset) do
    assign(socket, :form, to_form(changeset))
  end

  defp notify_parent(msg), do: send(self(), {__MODULE__, msg})
end

# --- File uploads in LiveView ---

defmodule MyAppWeb.AvatarLive do
  use MyAppWeb, :live_view

  @impl true
  def mount(_params, _session, socket) do
    socket =
      socket
      |> allow_upload(:avatar,
        accept: ~w(.jpg .jpeg .png .webp),
        max_entries: 1,
        max_file_size: 5_000_000,  # 5 MB
        auto_upload: true)

    {:ok, socket}
  end

  @impl true
  def handle_event("save", _params, socket) do
    uploaded_files =
      consume_uploaded_entries(socket, :avatar, fn %{path: path}, entry ->
        dest = Path.join(["priv/static/uploads", entry.client_name])
        File.cp!(path, dest)
        {:ok, ~p"/uploads/#{entry.client_name}"}
      end)

    {:noreply, update(socket, :uploaded_files, &(&1 ++ uploaded_files))}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <form phx-submit="save" phx-change="validate">
      <.live_file_input upload={@uploads.avatar} />

      <%= for entry <- @uploads.avatar.entries do %>
        <div>
          <.live_img_preview entry={entry} width="100" />
          <progress value={entry.progress} max="100"><%= entry.progress %>%</progress>
          <button phx-click="cancel-upload" phx-value-ref={entry.ref}>Cancel</button>
        </div>

        <%= for err <- upload_errors(@uploads.avatar, entry) do %>
          <p class="error"><%= inspect(err) %></p>
        <% end %>
      <% end %>

      <button type="submit">Upload</button>
    </form>
    """
  end

  def handle_event("validate", _params, socket) do
    {:noreply, socket}
  end

  def handle_event("cancel-upload", %{"ref" => ref}, socket) do
    {:noreply, cancel_upload(socket, :avatar, ref)}
  end
end
```

LiveView lifecycle:

| Callback | When | Use For |
|---|---|---|
| `mount/3` | First connect + reconnect | Initial state, subscriptions |
| `handle_params/3` | URL changes (navigate/patch) | URL-driven state |
| `handle_event/3` | User interactions | Form submits, clicks, key presses |
| `handle_info/2` | Server-side messages | PubSub, timer, process messages |
| `update/2` (component) | Parent assigns change | Derive component state |
| `render/1` | After any state change | Return HEEx template |

Key patterns:
- **Streams** (`stream/3`) for efficient rendering of large collections (only diffs sent to client)
- **PubSub** for real-time updates across users (product changes, notifications)
- **Live Components** for reusable, encapsulated UI with their own event handling
- **`push_patch`** updates URL without full page reload (back button works)
- **`phx-debounce`** prevents excessive server calls during typing
- **File uploads** with progress tracking, validation, and live preview
- **`phx-disable-with`** prevents double-submit during form processing'''
    ),
    (
        "elixir/broadway-data-pipelines",
        "Show how to use Broadway in Elixir for building concurrent, multi-stage data processing pipelines with backpressure, including SQS, Kafka, and RabbitMQ producers.",
        '''Broadway is an Elixir library for building concurrent, multi-stage data ingestion and processing pipelines with built-in backpressure, batching, and fault tolerance.

```elixir
# --- Broadway pipeline: process events from SQS ---

defmodule MyApp.EventPipeline do
  use Broadway

  alias Broadway.Message

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [
        module: {
          BroadwaySQS.Producer,
          queue_url: System.get_env("SQS_QUEUE_URL"),
          config: [
            region: "us-east-1",
            access_key_id: System.get_env("AWS_ACCESS_KEY_ID"),
            secret_access_key: System.get_env("AWS_SECRET_ACCESS_KEY")
          ]
        },
        concurrency: 2,  # number of producer processes
        transformer: {__MODULE__, :transform, []}
      ],
      processors: [
        default: [
          concurrency: 10,  # number of processor stages
          max_demand: 20     # batch size per processor
        ]
      ],
      batchers: [
        analytics: [
          concurrency: 3,
          batch_size: 50,
          batch_timeout: 5_000  # flush after 5 seconds even if batch not full
        ],
        notifications: [
          concurrency: 2,
          batch_size: 10,
          batch_timeout: 2_000
        ]
      ]
    )
  end

  # Transform raw SQS messages into Broadway messages
  def transform(event, _opts) do
    %Message{
      data: event.data,
      metadata: event.metadata,
      acknowledger: event.acknowledger
    }
  end

  # --- Processor: runs for each individual message ---
  @impl true
  def handle_message(:default, message, _context) do
    case Jason.decode(message.data) do
      {:ok, event} ->
        processed = process_event(event)

        message
        |> Message.update_data(fn _ -> processed end)
        |> Message.put_batcher(select_batcher(event))

      {:error, _reason} ->
        Message.failed(message, "invalid JSON")
    end
  end

  # --- Batchers: process messages in groups ---
  @impl true
  def handle_batch(:analytics, messages, _batch_info, _context) do
    # Batch insert into analytics database
    events =
      Enum.map(messages, fn msg ->
        %{
          event_type: msg.data.type,
          user_id: msg.data.user_id,
          payload: msg.data.payload,
          occurred_at: msg.data.timestamp,
          inserted_at: DateTime.utc_now()
        }
      end)

    # Bulk insert (much faster than individual inserts)
    MyApp.Repo.insert_all(AnalyticsEvent, events,
      on_conflict: :nothing,
      conflict_target: [:event_type, :user_id, :occurred_at])

    messages
  end

  @impl true
  def handle_batch(:notifications, messages, _batch_info, _context) do
    # Send notifications in batch
    Enum.each(messages, fn msg ->
      case msg.data do
        %{type: "order_completed", user_id: user_id} ->
          MyApp.Notifications.send_order_confirmation(user_id, msg.data.payload)

        %{type: "payment_failed", user_id: user_id} ->
          MyApp.Notifications.send_payment_alert(user_id, msg.data.payload)

        _ ->
          :ok
      end
    end)

    messages
  end

  # --- Error handling ---
  @impl true
  def handle_failed(messages, _context) do
    Enum.each(messages, fn
      %{status: {:failed, reason}} = message ->
        Logger.error("Message failed: #{inspect(reason)}, data: #{inspect(message.data)}")
        # Optionally send to dead letter queue
        MyApp.DeadLetterQueue.push(message.data, reason)
    end)

    messages
  end

  # Private helpers

  defp process_event(raw_event) do
    %{
      type: raw_event["type"],
      user_id: raw_event["user_id"],
      payload: raw_event["payload"],
      timestamp: parse_timestamp(raw_event["timestamp"])
    }
  end

  defp select_batcher(%{type: type}) when type in ~w(page_view click search) do
    :analytics
  end
  defp select_batcher(%{type: type}) when type in ~w(order_completed payment_failed) do
    :notifications
  end
  defp select_batcher(_), do: :analytics

  defp parse_timestamp(ts) when is_binary(ts) do
    case DateTime.from_iso8601(ts) do
      {:ok, dt, _} -> dt
      _ -> DateTime.utc_now()
    end
  end
  defp parse_timestamp(_), do: DateTime.utc_now()
end
```

```elixir
# --- Broadway with Kafka producer ---

defmodule MyApp.OrderPipeline do
  use Broadway

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [
        module: {
          BroadwayKafka.Producer,
          hosts: [localhost: 9092],
          group_id: "myapp-order-processor",
          topics: ["orders"],
          group_config: [
            offset_commit_interval_seconds: 5,
            rejoin_delay_seconds: 2
          ]
        },
        concurrency: 4
      ],
      processors: [
        default: [concurrency: 8, max_demand: 10]
      ],
      batchers: [
        database: [batch_size: 100, batch_timeout: 2_000],
        search_index: [batch_size: 50, batch_timeout: 5_000]
      ]
    )
  end

  @impl true
  def handle_message(:default, message, _context) do
    order = Jason.decode!(message.data)

    enriched = %{
      order_id: order["id"],
      customer: fetch_customer(order["customer_id"]),
      items: order["items"],
      total: calculate_total(order["items"]),
      processed_at: DateTime.utc_now()
    }

    message
    |> Message.update_data(fn _ -> enriched end)
    |> Message.put_batcher(:database)
    |> Message.put_batcher(:search_index)
  end

  @impl true
  def handle_batch(:database, messages, _batch_info, _context) do
    orders = Enum.map(messages, & &1.data)

    # Bulk upsert with Ecto
    MyApp.Repo.insert_all(
      ProcessedOrder,
      Enum.map(orders, &Map.take(&1, [:order_id, :total, :processed_at])),
      on_conflict: {:replace, [:total, :processed_at]},
      conflict_target: :order_id
    )

    messages
  end

  @impl true
  def handle_batch(:search_index, messages, _batch_info, _context) do
    # Bulk index to Elasticsearch
    docs = Enum.map(messages, fn msg ->
      %{index: %{_id: msg.data.order_id, data: msg.data}}
    end)

    MyApp.Search.bulk_index("orders", docs)
    messages
  end

  defp fetch_customer(id), do: MyApp.Customers.get(id)
  defp calculate_total(items) do
    Enum.reduce(items, Decimal.new(0), fn item, acc ->
      Decimal.add(acc, Decimal.mult(item["price"], item["quantity"]))
    end)
  end
end

# --- Supervision tree for pipelines ---

defmodule MyApp.Pipelines.Supervisor do
  use Supervisor

  def start_link(opts) do
    Supervisor.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    children = [
      MyApp.EventPipeline,
      MyApp.OrderPipeline
    ]

    Supervisor.init(children, strategy: :one_for_one)
  end
end
```

Broadway architecture:

| Stage | Concurrency | Purpose |
|---|---|---|
| Producer | 1-4 processes | Fetch messages from source (SQS, Kafka, RabbitMQ) |
| Processor | 1-N processes | Transform, validate, route individual messages |
| Batcher | 1-N per batcher | Group messages by destination |
| Batch handler | Per batch | Bulk operations (DB insert, API call) |

Key patterns:
- **Backpressure** is automatic: producers only fetch when processors have capacity
- **Batching** amortizes I/O cost (bulk DB inserts instead of individual)
- **Fault tolerance**: failed messages are nacked (returned to queue for retry)
- **Message routing**: `Message.put_batcher` routes to different batch handlers
- **Concurrency is tunable**: adjust processor/batcher concurrency per workload
- **Acknowledgment**: messages are acked only after successful batch processing
- **Dead letter handling**: `handle_failed/2` captures permanently failed messages'''
    ),
    (
        "elixir/distributed-cluster",
        "Show how to build a distributed Elixir cluster using libcluster, distributed process registries with Horde, and cross-node communication patterns.",
        '''Elixir and the BEAM VM have built-in distributed computing primitives. With libcluster for auto-discovery and Horde for distributed registries and supervisors, you can build fault-tolerant clusters.

```elixir
# --- Cluster formation with libcluster ---

# mix.exs deps:
# {:libcluster, "~> 3.4"},
# {:horde, "~> 0.9"}

# config/runtime.exs
config :libcluster,
  topologies: [
    # Strategy 1: Kubernetes DNS-based discovery
    k8s: [
      strategy: Cluster.Strategy.Kubernetes.DNS,
      config: [
        service: "myapp-headless",
        application_name: "myapp",
        namespace: "production",
        polling_interval: 5_000
      ]
    ],

    # Strategy 2: gossip protocol for dynamic environments
    gossip: [
      strategy: Cluster.Strategy.Gossip,
      config: [
        port: 45892,
        multicast_ttl: 1
      ]
    ],

    # Strategy 3: explicit node list (for known hosts)
    static: [
      strategy: Cluster.Strategy.Epmd,
      config: [
        hosts: [
          :"myapp@server1.example.com",
          :"myapp@server2.example.com",
          :"myapp@server3.example.com"
        ]
      ]
    ]
  ]

# application.ex -- add to supervision tree
defmodule MyApp.Application do
  use Application

  def start(_type, _args) do
    topologies = Application.get_env(:libcluster, :topologies, [])

    children = [
      # Cluster supervisor for automatic node discovery
      {Cluster.Supervisor, [topologies, [name: MyApp.ClusterSupervisor]]},

      # Distributed registry (replaces single-node Registry)
      {Horde.Registry, [name: MyApp.DistRegistry, keys: :unique,
                         members: :auto]},

      # Distributed supervisor (replaces DynamicSupervisor)
      {Horde.DynamicSupervisor, [name: MyApp.DistSupervisor,
                                  strategy: :one_for_one,
                                  members: :auto]},

      # Application services
      MyApp.Repo,
      {Phoenix.PubSub, name: MyApp.PubSub},
      MyAppWeb.Endpoint
    ]

    Supervisor.start_link(children,
      strategy: :one_for_one,
      name: MyApp.Supervisor)
  end
end
```

```elixir
# --- Distributed processes with Horde ---

defmodule MyApp.GameRoom do
  @moduledoc """
  A game room process that runs on exactly one node in the cluster.
  Horde ensures uniqueness and handles node failures.
  """
  use GenServer

  def start_link(room_id) do
    GenServer.start_link(__MODULE__, room_id,
      name: via_tuple(room_id))
  end

  # Horde distributed registry naming
  defp via_tuple(room_id) do
    {:via, Horde.Registry, {MyApp.DistRegistry, room_id}}
  end

  def join(room_id, player) do
    GenServer.call(via_tuple(room_id), {:join, player})
  end

  def leave(room_id, player_id) do
    GenServer.cast(via_tuple(room_id), {:leave, player_id})
  end

  def get_state(room_id) do
    GenServer.call(via_tuple(room_id), :get_state)
  end

  @impl true
  def init(room_id) do
    state = %{
      room_id: room_id,
      players: %{},
      created_at: DateTime.utc_now(),
      game_state: :waiting
    }
    {:ok, state}
  end

  @impl true
  def handle_call({:join, player}, _from, state) do
    if map_size(state.players) >= 4 do
      {:reply, {:error, :room_full}, state}
    else
      new_players = Map.put(state.players, player.id, player)
      new_state = %{state | players: new_players}

      # Broadcast to all connected clients (across nodes)
      Phoenix.PubSub.broadcast(MyApp.PubSub,
        "room:#{state.room_id}",
        {:player_joined, player})

      {:reply, :ok, new_state}
    end
  end

  @impl true
  def handle_call(:get_state, _from, state) do
    {:reply, state, state}
  end

  @impl true
  def handle_cast({:leave, player_id}, state) do
    new_players = Map.delete(state.players, player_id)
    new_state = %{state | players: new_players}

    Phoenix.PubSub.broadcast(MyApp.PubSub,
      "room:#{state.room_id}",
      {:player_left, player_id})

    if map_size(new_players) == 0 do
      {:stop, :normal, new_state}
    else
      {:noreply, new_state}
    end
  end
end

# --- Room Manager: start/find rooms across the cluster ---

defmodule MyApp.RoomManager do
  @supervisor MyApp.DistSupervisor
  @registry MyApp.DistRegistry

  def find_or_create_room(room_id) do
    case Horde.Registry.lookup(@registry, room_id) do
      [{pid, _}] ->
        {:ok, pid}

      [] ->
        # Start on the least loaded node (Horde handles placement)
        spec = {MyApp.GameRoom, room_id}
        case Horde.DynamicSupervisor.start_child(@supervisor, spec) do
          {:ok, pid} -> {:ok, pid}
          {:error, {:already_started, pid}} -> {:ok, pid}
          error -> error
        end
    end
  end

  def list_rooms do
    Horde.Registry.select(@registry, [{{:"$1", :"$2", :_}, [], [{{:"$1", :"$2"}}]}])
  end

  def count_rooms do
    Horde.DynamicSupervisor.count_children(@supervisor).active
  end
end
```

```elixir
# --- Cross-node communication patterns ---

defmodule MyApp.ClusterUtils do
  @doc "Call a function on all nodes in the cluster"
  def multi_call(module, function, args, timeout \\\\ 5_000) do
    nodes = [Node.self() | Node.list()]

    tasks = Enum.map(nodes, fn node ->
      Task.async(fn ->
        try do
          :rpc.call(node, module, function, args, timeout)
        catch
          :exit, reason -> {:error, node, reason}
        end
      end)
    end)

    Task.await_many(tasks, timeout + 1_000)
  end

  @doc "Get cluster-wide metrics"
  def cluster_metrics do
    nodes = [Node.self() | Node.list()]

    Enum.map(nodes, fn node ->
      memory = :rpc.call(node, :erlang, :memory, [])
      process_count = :rpc.call(node, :erlang, :system_info, [:process_count])

      %{
        node: node,
        memory_mb: div(memory[:total], 1_048_576),
        processes: process_count,
        connected: Node.ping(node) == :pong
      }
    end)
  end

  @doc "Monitor cluster membership changes"
  def subscribe_to_cluster_events do
    :net_kernel.monitor_nodes(true, [node_type: :visible])
  end

  # Handle in a GenServer:
  # def handle_info({:nodeup, node, _info}, state) do
  #   Logger.info("Node joined: #{node}")
  #   {:noreply, state}
  # end
  #
  # def handle_info({:nodedown, node, _info}, state) do
  #   Logger.warning("Node left: #{node}")
  #   {:noreply, state}
  # end
end

# --- Distributed PubSub (built into Phoenix) ---

# Phoenix.PubSub automatically distributes messages across nodes
# when using the default PG adapter.

# Subscribe (in LiveView or GenServer):
Phoenix.PubSub.subscribe(MyApp.PubSub, "notifications:user:123")

# Broadcast (reaches ALL subscribers on ALL nodes):
Phoenix.PubSub.broadcast(MyApp.PubSub, "notifications:user:123", %{
  type: :new_message,
  from: "Alice",
  body: "Hello!"
})

# Direct broadcast to a specific node:
Phoenix.PubSub.direct_broadcast(
  :"myapp@server2.example.com",
  MyApp.PubSub,
  "admin:alerts",
  %{type: :node_warning, details: "High memory"}
)
```

Distributed Elixir architecture:

| Component | Library | Purpose |
|---|---|---|
| Node discovery | libcluster | Automatic cluster formation |
| Distributed registry | Horde.Registry | Unique process names across cluster |
| Distributed supervisor | Horde.DynamicSupervisor | Start processes on any node |
| Pub/sub | Phoenix.PubSub | Cross-node message broadcast |
| RPC | :rpc / :erpc | Direct cross-node function calls |
| Process groups | :pg | Group processes across nodes |

Key patterns:
- **libcluster** handles node discovery (K8s, DNS, gossip, static)
- **Horde** distributes GenServer processes across nodes with automatic failover
- **Phoenix.PubSub** broadcasts to all subscribers on all nodes transparently
- **Process placement** is automatic -- Horde picks the least-loaded node
- **Node failure handling**: Horde restarts orphaned processes on surviving nodes
- **CRDT-based**: Horde uses CRDTs for eventually consistent cluster state
- **`:rpc.call/4`** for direct cross-node function invocation when needed'''
    ),
]
