PAIRS = [
    (
        "kotlin/coroutines-structured-concurrency-flows",
        "Explain Kotlin coroutines internals including structured concurrency with CoroutineScope, SupervisorJob for failure isolation, Flow operators for reactive streams, and channel-based communication patterns with practical examples",
        '''# Kotlin Coroutines: Structured Concurrency and Reactive Streams

## Coroutine Internals: Continuations and State Machines

Kotlin coroutines are compiled into **state machines** by the compiler. Each `suspend` function is transformed into a function that takes a `Continuation<T>` parameter, with each suspension point becoming a state in a `when` block. This is critical to understand **because** it means coroutines have near-zero allocation overhead compared to threads -- they're just objects on the heap.

### Structured Concurrency Fundamentals

**Structured concurrency** in Kotlin means every coroutine must have a parent scope, and the parent cannot complete until all children complete (or are cancelled). This prevents leaked coroutines -- a problem that plagues callback-based async code. **Therefore**, `GlobalScope.launch` is almost always wrong in production code.

```kotlin
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.channels.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.concurrent.ConcurrentHashMap
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.measureTime

// --- Structured concurrency with scope hierarchy ---

// Best practice: create a dedicated scope per component
class UserRepository(
    private val scope: CoroutineScope,
    private val apiClient: ApiClient,
    private val cache: UserCache,
) {
    // SupervisorJob prevents one child failure from cancelling siblings
    // Trade-off: more resilient but harder to reason about error propagation
    private val repoScope = CoroutineScope(
        scope.coroutineContext + SupervisorJob(scope.coroutineContext.job)
    )

    suspend fun getUser(id: String): User {
        // Check cache first
        cache.get(id)?.let { return it }

        // Fetch from API with timeout
        return withTimeout(5.seconds) {
            val user = apiClient.fetchUser(id)
            // Background cache update -- fire and forget within scope
            repoScope.launch {
                cache.put(id, user)
            }
            user
        }
    }

    suspend fun getUsersParallel(ids: List<String>): List<User> {
        // coroutineScope creates a child scope -- if ANY fetch fails,
        // ALL other fetches are cancelled (fail-fast)
        return coroutineScope {
            ids.map { id ->
                async { getUser(id) }
            }.awaitAll()
        }
    }

    suspend fun getUsersResilient(ids: List<String>): List<Result<User>> {
        // However, sometimes you want partial results
        // supervisorScope allows individual failures without cancelling others
        return supervisorScope {
            ids.map { id ->
                async {
                    runCatching { getUser(id) }
                }
            }.awaitAll()
        }
    }

    fun close() {
        repoScope.cancel()
    }
}

// Pitfall: catching CancellationException breaks structured concurrency
suspend fun riskyFunction() {
    try {
        delay(1000)
    } catch (e: Exception) {
        // Common mistake: this catches CancellationException too!
        // The coroutine appears to "survive" cancellation
        println("Error: $e")
    }
}

// Correct approach: rethrow CancellationException
suspend fun safeFunction() {
    try {
        delay(1000)
    } catch (e: CancellationException) {
        throw e  // Always rethrow
    } catch (e: Exception) {
        println("Error: $e")
    }
}

// Data classes for the examples
data class User(val id: String, val name: String, val email: String)

interface ApiClient {
    suspend fun fetchUser(id: String): User
    suspend fun fetchUserPosts(userId: String): List<Post>
}

interface UserCache {
    suspend fun get(id: String): User?
    suspend fun put(id: String, user: User)
}

data class Post(val id: String, val userId: String, val title: String)
```

### Flow: Reactive Streams Done Right

Kotlin Flow is a **cold** reactive stream -- it doesn't produce values until collected. This is the key **trade-off** versus channels (which are hot). Flows are sequential by default and respect structured concurrency, making them safer and more predictable.

```kotlin
// --- Flow operators and patterns ---

class EventProcessor(
    private val apiClient: ApiClient,
) {
    // Cold flow -- only runs when collected
    fun userActivityStream(userId: String): Flow<ActivityEvent> = flow {
        var cursor: String? = null
        while (currentCoroutineContext().isActive) {
            val page = fetchActivityPage(userId, cursor)
            page.events.forEach { emit(it) }
            cursor = page.nextCursor ?: break
            delay(100.milliseconds) // Rate limiting
        }
    }

    // Flow transformation pipeline
    // Best practice: compose small operators instead of monolithic transforms
    fun processActivities(userId: String): Flow<ProcessedEvent> =
        userActivityStream(userId)
            .filter { it.type != EventType.HEARTBEAT }
            .map { event ->
                // Transform each event
                ProcessedEvent(
                    id = event.id,
                    type = event.type,
                    enrichedData = enrichEvent(event),
                    processedAt = System.currentTimeMillis(),
                )
            }
            .onEach { event ->
                // Side effect: log processing
                println("Processed: ${event.id}")
            }
            .catch { e ->
                // Error handling -- emits downstream, doesn't crash
                // However, catch only handles upstream errors
                println("Error in activity stream: $e")
                emit(ProcessedEvent.error(e.message ?: "unknown"))
            }
            .flowOn(Dispatchers.IO) // Switch context for upstream operators
            .buffer(Channel.BUFFERED) // Decouple producer/consumer speed
            .distinctUntilChangedBy { it.id }

    // Combining multiple flows
    fun dashboardUpdates(userId: String): Flow<DashboardState> {
        val activities = processActivities(userId)
        val notifications = notificationFlow(userId)
        val metrics = metricsFlow(userId)

        // combine emits whenever ANY source emits
        return combine(activities, notifications, metrics) { activity, notif, metric ->
            DashboardState(
                latestActivity = activity,
                unreadCount = notif.unreadCount,
                metrics = metric,
            )
        }.conflate() // Drop intermediate values if collector is slow
    }

    // SharedFlow for hot broadcasting (multiple collectors)
    private val _events = MutableSharedFlow<ActivityEvent>(
        replay = 10,                     // Buffer last 10 for late subscribers
        extraBufferCapacity = 100,       // Additional buffer
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val events: SharedFlow<ActivityEvent> = _events.asSharedFlow()

    // StateFlow for observable state (always has current value)
    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    suspend fun connect() {
        _connectionState.value = ConnectionState.CONNECTING
        try {
            // Simulate connection
            delay(1000)
            _connectionState.value = ConnectionState.CONNECTED
        } catch (e: Exception) {
            _connectionState.value = ConnectionState.ERROR
        }
    }

    // Therefore: use Flow for cold streams, SharedFlow for hot broadcasts,
    // StateFlow for observable state
    private suspend fun fetchActivityPage(userId: String, cursor: String?): ActivityPage {
        delay(50) // Simulate API call
        return ActivityPage(events = emptyList(), nextCursor = null)
    }

    private suspend fun enrichEvent(event: ActivityEvent): Map<String, Any> = mapOf("enriched" to true)
    private fun notificationFlow(userId: String): Flow<NotificationState> = flowOf(NotificationState(0))
    private fun metricsFlow(userId: String): Flow<MetricsSnapshot> = flowOf(MetricsSnapshot())
}

// Supporting types
data class ActivityEvent(val id: String, val type: EventType, val data: Map<String, Any>)
data class ProcessedEvent(
    val id: String, val type: EventType,
    val enrichedData: Map<String, Any>, val processedAt: Long,
) {
    companion object {
        fun error(message: String) = ProcessedEvent("error", EventType.ERROR, mapOf("error" to message), System.currentTimeMillis())
    }
}
enum class EventType { HEARTBEAT, CLICK, PURCHASE, ERROR }
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, ERROR }
data class ActivityPage(val events: List<ActivityEvent>, val nextCursor: String?)
data class DashboardState(val latestActivity: ProcessedEvent, val unreadCount: Int, val metrics: MetricsSnapshot)
data class NotificationState(val unreadCount: Int)
data class MetricsSnapshot(val activeUsers: Int = 0)
```

### Channel-Based Communication Patterns

Channels are Kotlin's equivalent of Go channels -- **hot** communication primitives for coroutines. The **pitfall** is forgetting to close channels, causing receiver coroutines to hang indefinitely.

```kotlin
// --- Channel patterns ---

class WorkerPool<T, R>(
    private val concurrency: Int,
    private val processor: suspend (T) -> R,
) {
    // Fan-out / fan-in pattern
    // Best practice: use produce/consumeEach for lifecycle management
    suspend fun process(items: List<T>): List<R> = coroutineScope {
        val inputChannel = Channel<IndexedValue<T>>(Channel.BUFFERED)
        val outputChannel = Channel<IndexedValue<R>>(Channel.BUFFERED)

        // Fan-out: multiple workers consume from single channel
        val workers = List(concurrency) { workerId ->
            launch(Dispatchers.Default) {
                for ((index, item) in inputChannel) {
                    try {
                        val result = processor(item)
                        outputChannel.send(IndexedValue(index, result))
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        // Common mistake: not handling errors per-item
                        println("Worker $workerId failed on item $index: $e")
                        throw e
                    }
                }
            }
        }

        // Producer: send all items
        launch {
            items.forEachIndexed { index, item ->
                inputChannel.send(IndexedValue(index, item))
            }
            inputChannel.close() // Signal no more items
        }

        // Fan-in: collect results and maintain original order
        val results = arrayOfNulls<Any?>(items.size)
        launch {
            var received = 0
            for ((index, result) in outputChannel) {
                results[index] = result
                received++
                if (received == items.size) {
                    outputChannel.close()
                }
            }
        }.join()

        // Wait for all workers to finish
        workers.forEach { it.join() }

        @Suppress("UNCHECKED_CAST")
        results.map { it as R }
    }
}

// --- Rate-limited channel consumer ---

class RateLimiter(
    private val permitsPerSecond: Int,
) {
    private val mutex = Mutex()
    private var lastPermitTime = 0L
    private val intervalMs = 1000L / permitsPerSecond

    suspend fun acquire() {
        mutex.withLock {
            val now = System.currentTimeMillis()
            val waitTime = lastPermitTime + intervalMs - now
            if (waitTime > 0) {
                delay(waitTime)
            }
            lastPermitTime = System.currentTimeMillis()
        }
    }
}

// Usage example with structured concurrency
suspend fun main() {
    // Therefore, all coroutines are properly scoped and cleaned up
    val pool = WorkerPool<String, Int>(concurrency = 4) { item ->
        delay(100) // Simulate work
        item.length
    }

    val results = pool.process(listOf("hello", "world", "kotlin", "coroutines"))
    println("Results: $results") // [5, 5, 6, 10]
}
```

## Summary and Key Takeaways

- **Structured concurrency** ensures all coroutines have a parent scope -- use `coroutineScope` for fail-fast and `supervisorScope` for resilient parallel work
- **SupervisorJob** prevents one child failure from cancelling siblings -- essential for server-side request handling
- A **common mistake** is catching `CancellationException` in a generic catch block, breaking cancellation propagation
- Use **Flow** for cold streams, **SharedFlow** for hot multi-subscriber broadcasts, **StateFlow** for observable state
- **`flowOn()`** shifts upstream execution context; **`buffer()`** decouples producer/consumer speeds
- Channels are for **hot** coroutine-to-coroutine communication -- always close channels to prevent hanging receivers
- The **pitfall** of `GlobalScope.launch` is that it creates unstructured coroutines that outlive their intended lifecycle'''
    ),
    (
        "kotlin/dsl-builders-type-safe-metaprogramming",
        "Describe Kotlin DSL builder patterns including type-safe builders with receiver lambdas, @DslMarker annotation for scope control, reified generics for inline type operations, and practical DSLs for HTML generation and configuration",
        '''# Kotlin DSL Builders and Type-Safe Metaprogramming

## The Power of Receiver Lambdas

Kotlin's DSL capabilities stem from **lambda with receiver** -- a function type where the lambda body executes in the context of a specified receiver object. This means you can call the receiver's methods without qualification, creating natural-looking domain-specific syntax. This is powerful **because** it combines compile-time type safety with the readability of internal DSLs.

### Building a Type-Safe HTML DSL

```kotlin
import kotlin.properties.ReadWriteProperty
import kotlin.reflect.KProperty

// --- @DslMarker prevents scope leaking ---
// Without it, nested lambdas can access outer receivers
// Best practice: always use @DslMarker for non-trivial DSLs

@DslMarker
annotation class HtmlDsl

// --- Core HTML DSL ---

@HtmlDsl
abstract class Element {
    val children = mutableListOf<Element>()
    val attributes = mutableMapOf<String, String>()

    fun attribute(key: String, value: String) {
        attributes[key] = value
    }

    protected fun <T : Element> initTag(tag: T, init: T.() -> Unit): T {
        tag.init()
        children.add(tag)
        return tag
    }

    open fun render(builder: StringBuilder, indent: String) {
        // Override in subclasses
    }

    protected fun renderAttributes(): String {
        if (attributes.isEmpty()) return ""
        return attributes.entries.joinToString(" ", prefix = " ") {
            "${it.key}=\"${escapeHtml(it.value)}\""
        }
    }

    private fun escapeHtml(text: String): String =
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
}

@HtmlDsl
class TextElement(val text: String) : Element() {
    override fun render(builder: StringBuilder, indent: String) {
        builder.append("$indent$text\n")
    }
}

@HtmlDsl
open class Tag(val name: String) : Element() {
    // Operator overloading for text content: +"some text"
    operator fun String.unaryPlus() {
        children.add(TextElement(this))
    }

    // CSS class helper
    var cssClass: String
        get() = attributes["class"] ?: ""
        set(value) { attributes["class"] = value }

    // ID helper
    var id: String
        get() = attributes["id"] ?: ""
        set(value) { attributes["id"] = value }

    override fun render(builder: StringBuilder, indent: String) {
        builder.append("$indent<$name${renderAttributes()}")
        if (children.isEmpty()) {
            builder.append(" />\n")
        } else {
            builder.append(">\n")
            children.forEach { it.render(builder, "$indent  ") }
            builder.append("$indent</$name>\n")
        }
    }
}

// Specific tag types with type-safe content models
@HtmlDsl
class HTML : Tag("html") {
    fun head(init: Head.() -> Unit) = initTag(Head(), init)
    fun body(init: Body.() -> Unit) = initTag(Body(), init)
}

@HtmlDsl
class Head : Tag("head") {
    fun title(init: Title.() -> Unit) = initTag(Title(), init)
    fun meta(init: Meta.() -> Unit) = initTag(Meta(), init)
    fun link(href: String, rel: String = "stylesheet") {
        val tag = Tag("link")
        tag.attribute("href", href)
        tag.attribute("rel", rel)
        children.add(tag)
    }
}

@HtmlDsl
class Title : Tag("title")

@HtmlDsl
class Meta : Tag("meta") {
    var charset: String by TagAttribute("charset")
    var content: String by TagAttribute("content")
    var name: String by TagAttribute("name")
}

@HtmlDsl
class Body : Tag("body") {
    fun div(init: Div.() -> Unit) = initTag(Div(), init)
    fun h1(init: Tag.() -> Unit) = initTag(Tag("h1"), init)
    fun h2(init: Tag.() -> Unit) = initTag(Tag("h2"), init)
    fun p(init: Tag.() -> Unit) = initTag(Tag("p"), init)
    fun ul(init: UL.() -> Unit) = initTag(UL(), init)
    fun form(action: String = "", method: String = "POST", init: Form.() -> Unit): Form {
        val form = Form()
        form.attribute("action", action)
        form.attribute("method", method)
        return initTag(form, init)
    }
}

@HtmlDsl
class Div : Tag("div") {
    fun div(init: Div.() -> Unit) = initTag(Div(), init)
    fun p(init: Tag.() -> Unit) = initTag(Tag("p"), init)
    fun span(init: Tag.() -> Unit) = initTag(Tag("span"), init)
    fun a(href: String, init: Tag.() -> Unit): Tag {
        val tag = Tag("a")
        tag.attribute("href", href)
        return initTag(tag, init)
    }
}

@HtmlDsl
class UL : Tag("ul") {
    fun li(init: Tag.() -> Unit) = initTag(Tag("li"), init)
}

@HtmlDsl
class Form : Tag("form") {
    fun input(type: String, name: String, init: Tag.() -> Unit = {}) {
        val tag = Tag("input")
        tag.attribute("type", type)
        tag.attribute("name", name)
        initTag(tag, init)
    }
    fun button(type: String = "submit", init: Tag.() -> Unit) {
        val tag = Tag("button")
        tag.attribute("type", type)
        initTag(tag, init)
    }
}

// Delegated property for type-safe attributes
class TagAttribute(private val attrName: String) : ReadWriteProperty<Tag, String> {
    override fun getValue(thisRef: Tag, property: KProperty<*>): String =
        thisRef.attributes[attrName] ?: ""
    override fun setValue(thisRef: Tag, property: KProperty<*>, value: String) {
        thisRef.attributes[attrName] = value
    }
}

// Entry point function
fun html(init: HTML.() -> Unit): HTML {
    val html = HTML()
    html.init()
    return html
}

// Usage -- looks like a markup language but is fully type-safe
fun buildPage(): String {
    val page = html {
        head {
            title { +"My Page" }
            meta { charset = "utf-8" }
            link(href = "/styles.css")
        }
        body {
            div {
                cssClass = "container"
                h1 { +"Welcome" }
                p { +"This is type-safe HTML" }
                // @DslMarker prevents accessing `head` here
                // head { } // Compile error!
            }
            ul {
                li { +"Item 1" }
                li { +"Item 2" }
            }
        }
    }
    val sb = StringBuilder()
    page.render(sb, "")
    return sb.toString()
}
```

### Reified Generics and Inline Functions

**However**, Kotlin's type system has a limitation: generic type parameters are erased at runtime, just like Java. The **trade-off** is that `reified` type parameters (only available in `inline` functions) give you runtime type access at the cost of increased bytecode size. **Therefore**, use `reified` sparingly for framework-level utilities.

```kotlin
// --- Reified generics for type-safe operations ---

// Common mistake: trying to use T::class without reified
// fun <T> create(): T = T::class.createInstance() // Won't compile

// Correct: inline + reified
inline fun <reified T : Any> create(): T {
    return T::class.java.getDeclaredConstructor().newInstance()
}

// --- Type-safe configuration DSL with reified ---

class ServiceRegistry {
    val services = mutableMapOf<String, Any>()

    inline fun <reified T : Any> register(noinline factory: () -> T) {
        services[T::class.qualifiedName ?: T::class.simpleName ?: "unknown"] = factory
    }

    inline fun <reified T : Any> resolve(): T {
        val key = T::class.qualifiedName ?: T::class.simpleName ?: "unknown"
        val factory = services[key] ?: throw IllegalStateException(
            "No factory registered for ${T::class.simpleName}"
        )
        @Suppress("UNCHECKED_CAST")
        return (factory as () -> T).invoke()
    }
}

// --- Configuration DSL ---

@DslMarker
annotation class ConfigDsl

@ConfigDsl
class AppConfig {
    var name: String = ""
    var version: String = "1.0.0"
    var debug: Boolean = false

    private var _database: DatabaseConfig? = null
    private var _server: ServerConfig? = null
    private var _features: MutableSet<String> = mutableSetOf()

    fun database(init: DatabaseConfig.() -> Unit) {
        _database = DatabaseConfig().apply(init)
    }

    fun server(init: ServerConfig.() -> Unit) {
        _server = ServerConfig().apply(init)
    }

    fun features(init: FeatureFlags.() -> Unit) {
        FeatureFlags(_features).apply(init)
    }

    val databaseConfig: DatabaseConfig get() = _database ?: DatabaseConfig()
    val serverConfig: ServerConfig get() = _server ?: ServerConfig()
    val enabledFeatures: Set<String> get() = _features.toSet()
}

@ConfigDsl
class DatabaseConfig {
    var host: String = "localhost"
    var port: Int = 5432
    var name: String = "app"
    var username: String = "postgres"
    var password: String = ""
    var maxPoolSize: Int = 10
    var connectionTimeout: Long = 5000

    // Computed connection string
    val connectionString: String
        get() = "jdbc:postgresql://$host:$port/$name"
}

@ConfigDsl
class ServerConfig {
    var host: String = "0.0.0.0"
    var port: Int = 8080
    var workers: Int = Runtime.getRuntime().availableProcessors()
    var gracefulShutdownTimeout: Long = 30_000
}

@ConfigDsl
class FeatureFlags(private val flags: MutableSet<String>) {
    fun enable(vararg features: String) {
        flags.addAll(features)
    }
    fun disable(vararg features: String) {
        flags.removeAll(features.toSet())
    }
}

fun appConfig(init: AppConfig.() -> Unit): AppConfig =
    AppConfig().apply(init)

// Usage -- clean, readable configuration
val config = appConfig {
    name = "MyService"
    version = "2.1.0"
    debug = false

    database {
        host = "db.production.internal"
        port = 5432
        name = "myservice"
        maxPoolSize = 20
        connectionTimeout = 3000
    }

    server {
        port = 8443
        workers = 8
        gracefulShutdownTimeout = 60_000
    }

    features {
        enable("dark-mode", "beta-search", "new-checkout")
        disable("legacy-api")
    }
}
```

### Builder Pattern with Validation

A **pitfall** of DSL builders is deferring validation until runtime. **Best practice**: validate eagerly in the `build()` method and use sealed classes to represent valid states.

```kotlin
// --- Builder with compile-time and runtime validation ---

sealed class Route {
    abstract val path: String
    abstract val method: HttpMethod
}

enum class HttpMethod { GET, POST, PUT, DELETE, PATCH }

data class EndpointRoute(
    override val path: String,
    override val method: HttpMethod,
    val handler: suspend (Request) -> Response,
    val middleware: List<Middleware> = emptyList(),
    val authenticated: Boolean = false,
) : Route()

data class Request(val path: String, val body: String = "")
data class Response(val status: Int, val body: String)
typealias Middleware = suspend (Request, suspend (Request) -> Response) -> Response

@DslMarker
annotation class RouterDsl

@RouterDsl
class Router {
    private val routes = mutableListOf<EndpointRoute>()
    private val globalMiddleware = mutableListOf<Middleware>()

    fun use(middleware: Middleware) {
        globalMiddleware.add(middleware)
    }

    fun get(path: String, init: RouteBuilder.() -> Unit) =
        addRoute(path, HttpMethod.GET, init)

    fun post(path: String, init: RouteBuilder.() -> Unit) =
        addRoute(path, HttpMethod.POST, init)

    fun put(path: String, init: RouteBuilder.() -> Unit) =
        addRoute(path, HttpMethod.PUT, init)

    fun delete(path: String, init: RouteBuilder.() -> Unit) =
        addRoute(path, HttpMethod.DELETE, init)

    // Nested route groups
    fun group(prefix: String, init: Router.() -> Unit) {
        val nested = Router()
        nested.init()
        nested.routes.forEach { route ->
            routes.add(route.copy(
                path = "$prefix${route.path}",
                middleware = globalMiddleware + route.middleware,
            ))
        }
    }

    private fun addRoute(path: String, method: HttpMethod, init: RouteBuilder.() -> Unit) {
        val builder = RouteBuilder(path, method)
        builder.init()
        routes.add(builder.build(globalMiddleware))
    }

    fun build(): List<EndpointRoute> {
        // Validation at build time
        val duplicates = routes.groupBy { "${it.method} ${it.path}" }
            .filter { it.value.size > 1 }
        require(duplicates.isEmpty()) {
            "Duplicate routes: ${duplicates.keys}"
        }
        return routes.toList()
    }
}

@RouterDsl
class RouteBuilder(
    private val path: String,
    private val method: HttpMethod,
) {
    private var handler: (suspend (Request) -> Response)? = null
    private val middleware = mutableListOf<Middleware>()
    private var authenticated = false

    fun handle(block: suspend (Request) -> Response) {
        handler = block
    }

    fun authenticated() {
        authenticated = true
    }

    fun middleware(mw: Middleware) {
        middleware.add(mw)
    }

    fun build(globalMiddleware: List<Middleware>): EndpointRoute {
        val h = handler ?: throw IllegalStateException(
            "Route $method $path has no handler"
        )
        return EndpointRoute(
            path = path,
            method = method,
            handler = h,
            middleware = globalMiddleware + middleware,
            authenticated = authenticated,
        )
    }
}

fun router(init: Router.() -> Unit): List<EndpointRoute> =
    Router().apply(init).build()

// Usage
val routes = router {
    use { request, next ->
        // Logging middleware
        println("${request.path}")
        next(request)
    }

    get("/health") {
        handle { Response(200, "OK") }
    }

    group("/api/v1") {
        get("/users") {
            authenticated()
            handle { request -> Response(200, "[{\"id\": 1}]") }
        }
        post("/users") {
            authenticated()
            handle { request -> Response(201, request.body) }
        }
    }
}
```

## Summary and Key Takeaways

- **Lambda with receiver** (`T.() -> Unit`) is the foundation of Kotlin DSLs -- it provides implicit `this` access for natural syntax
- **@DslMarker** prevents scope leaking in nested builders -- without it, inner lambdas can accidentally access outer receivers
- A **common mistake** is forgetting `@DslMarker`, allowing nonsensical nesting like calling `head {}` inside a `div {}` builder
- **Reified generics** with `inline` give runtime type access but increase bytecode -- use for framework utilities, not everywhere
- The **trade-off** of DSL builders vs data classes: DSLs read better for complex configuration but add API surface and compile-time cost
- **Validate eagerly** in `build()` methods -- catching errors at construction time is far better than runtime surprises
- **Delegated properties** (`ReadWriteProperty`) bridge DSL syntax with backing storage (attributes, maps, preferences)'''
    ),
    (
        "kotlin/multiplatform-architecture-patterns",
        "Explain Kotlin Multiplatform architecture including expect/actual declarations, shared business logic with platform-specific implementations, KMP dependency injection, Compose Multiplatform UI sharing, and testing strategies for cross-platform code",
        '''# Kotlin Multiplatform Architecture Patterns

## Sharing Code Across Platforms

Kotlin Multiplatform (KMP) enables sharing business logic across Android, iOS, desktop, and web while keeping platform-specific code native. The key insight is the **expect/actual** mechanism: you declare an expected API in common code, then provide actual implementations per platform. This is fundamentally different from cross-platform UI frameworks **because** it doesn't try to abstract away the platform -- it embraces platform strengths while sharing what benefits from sharing.

### expect/actual and Platform Abstraction

```kotlin
// --- Common source set (commonMain) ---

// expect declarations define the API contract
// Actual implementations are provided per platform

expect class PlatformContext

expect class SecureStorage(context: PlatformContext) {
    suspend fun getString(key: String): String?
    suspend fun putString(key: String, value: String)
    suspend fun remove(key: String)
    suspend fun clear()
}

expect class HttpEngine() {
    suspend fun request(
        method: String,
        url: String,
        headers: Map<String, String>,
        body: String?,
    ): HttpResponse
}

data class HttpResponse(
    val statusCode: Int,
    val body: String,
    val headers: Map<String, String>,
)

// Best practice: define interfaces in common, implement per platform
// This is more flexible than expect/actual for complex abstractions
interface PlatformLogger {
    fun debug(tag: String, message: String)
    fun info(tag: String, message: String)
    fun error(tag: String, message: String, throwable: Throwable? = null)
}

// --- Shared business logic (100% common code) ---

// Trade-off: KMP encourages "shared core, native shell"
// Therefore, put all business logic here, keep UI platform-specific

class AuthRepository(
    private val httpEngine: HttpEngine,
    private val storage: SecureStorage,
    private val logger: PlatformLogger,
) {
    companion object {
        private const val TOKEN_KEY = "auth_token"
        private const val REFRESH_KEY = "refresh_token"
    }

    suspend fun login(email: String, password: String): Result<AuthToken> {
        return runCatching {
            val response = httpEngine.request(
                method = "POST",
                url = "/api/auth/login",
                headers = mapOf("Content-Type" to "application/json"),
                body = """{"email":"$email","password":"$password"}""",
            )
            when (response.statusCode) {
                200 -> {
                    val token = parseAuthToken(response.body)
                    storage.putString(TOKEN_KEY, token.accessToken)
                    storage.putString(REFRESH_KEY, token.refreshToken)
                    logger.info("Auth", "Login successful for $email")
                    token
                }
                401 -> throw AuthException("Invalid credentials")
                429 -> throw AuthException("Too many attempts, try later")
                else -> throw AuthException("Login failed: ${response.statusCode}")
            }
        }
    }

    suspend fun getToken(): String? = storage.getString(TOKEN_KEY)

    suspend fun logout() {
        storage.remove(TOKEN_KEY)
        storage.remove(REFRESH_KEY)
        logger.info("Auth", "User logged out")
    }

    // However, parsing logic should be in common code
    // Common mistake: putting JSON parsing in platform code
    private fun parseAuthToken(json: String): AuthToken {
        // In real code, use kotlinx.serialization
        return AuthToken(
            accessToken = extractJsonField(json, "access_token"),
            refreshToken = extractJsonField(json, "refresh_token"),
            expiresIn = extractJsonField(json, "expires_in").toLongOrNull() ?: 3600,
        )
    }

    private fun extractJsonField(json: String, field: String): String {
        val pattern = """"$field"\s*:\s*"([^"]+)"""".toRegex()
        return pattern.find(json)?.groupValues?.get(1) ?: ""
    }
}

data class AuthToken(
    val accessToken: String,
    val refreshToken: String,
    val expiresIn: Long,
)

class AuthException(message: String) : Exception(message)
```

### Platform Implementations and DI

Each platform provides **actual** implementations. The **pitfall** is duplicating logic across actuals -- keep actuals thin and push shared logic into common code. **Therefore**, actuals should be simple wrappers around platform APIs.

```kotlin
// --- Android actual (androidMain) ---
// actual class PlatformContext(val context: android.content.Context)
//
// actual class SecureStorage actual constructor(context: PlatformContext) {
//     private val prefs = EncryptedSharedPreferences.create(
//         context.context, "secure_prefs",
//         MasterKey.Builder(context.context).build(),
//         PrefKeyEncryptionScheme.AES256_SIV,
//         PrefValueEncryptionScheme.AES256_GCM,
//     )
//     actual suspend fun getString(key: String): String? = prefs.getString(key, null)
//     actual suspend fun putString(key: String, value: String) {
//         prefs.edit().putString(key, value).apply()
//     }
//     actual suspend fun remove(key: String) { prefs.edit().remove(key).apply() }
//     actual suspend fun clear() { prefs.edit().clear().apply() }
// }

// --- Dependency injection with expect/actual ---
// Best practice: use a simple DI container in common code

class ServiceLocator private constructor() {
    private val factories = mutableMapOf<String, () -> Any>()
    private val singletons = mutableMapOf<String, Any>()

    fun <T : Any> registerFactory(key: String, factory: () -> T) {
        factories[key] = factory
    }

    fun <T : Any> registerSingleton(key: String, instance: T) {
        singletons[key] = instance
    }

    @Suppress("UNCHECKED_CAST")
    fun <T : Any> resolve(key: String): T {
        singletons[key]?.let { return it as T }
        val factory = factories[key] ?: throw IllegalStateException(
            "No registration for $key"
        )
        return factory() as T
    }

    companion object {
        private var _instance: ServiceLocator? = null
        val instance: ServiceLocator
            get() = _instance ?: ServiceLocator().also { _instance = it }

        fun initialize(init: ServiceLocator.() -> Unit) {
            _instance = ServiceLocator().apply(init)
        }
    }
}

// --- Shared ViewModel pattern (common code) ---

abstract class SharedViewModel {
    private val _stateFlow = kotlinx.coroutines.flow.MutableStateFlow<ViewState>(ViewState.Loading)
    val state: kotlinx.coroutines.flow.StateFlow<ViewState> = _stateFlow

    protected fun updateState(newState: ViewState) {
        _stateFlow.value = newState
    }
}

sealed class ViewState {
    object Loading : ViewState()
    data class Success<T>(val data: T) : ViewState()
    data class Error(val message: String) : ViewState()
}

class LoginViewModel(
    private val authRepo: AuthRepository,
) : SharedViewModel() {
    suspend fun login(email: String, password: String) {
        updateState(ViewState.Loading)
        authRepo.login(email, password)
            .onSuccess { token ->
                updateState(ViewState.Success(token))
            }
            .onFailure { error ->
                updateState(ViewState.Error(error.message ?: "Unknown error"))
            }
    }
}
```

### Testing Cross-Platform Code

Testing KMP code requires a layered approach. **Common tests** run on all platforms, while **platform tests** verify actual implementations. The **trade-off** is that common tests are faster to write but can't test platform-specific behavior.

```kotlin
// --- Common test (commonTest) ---

// import kotlin.test.*
// import kotlinx.coroutines.test.runTest

class AuthRepositoryTest {
    // Fake implementations for testing
    class FakeHttpEngine : HttpEngine() {
        var nextResponse: HttpResponse = HttpResponse(200, "", emptyMap())
        var lastRequest: CapturedRequest? = null

        override suspend fun request(
            method: String, url: String,
            headers: Map<String, String>, body: String?,
        ): HttpResponse {
            lastRequest = CapturedRequest(method, url, headers, body)
            return nextResponse
        }
    }

    data class CapturedRequest(
        val method: String, val url: String,
        val headers: Map<String, String>, val body: String?,
    )

    class FakeSecureStorage : SecureStorage(FakePlatformContext()) {
        val store = mutableMapOf<String, String>()
        override suspend fun getString(key: String) = store[key]
        override suspend fun putString(key: String, value: String) { store[key] = value }
        override suspend fun remove(key: String) { store.remove(key) }
        override suspend fun clear() { store.clear() }
    }

    class FakeLogger : PlatformLogger {
        val logs = mutableListOf<String>()
        override fun debug(tag: String, message: String) { logs.add("D/$tag: $message") }
        override fun info(tag: String, message: String) { logs.add("I/$tag: $message") }
        override fun error(tag: String, message: String, throwable: Throwable?) {
            logs.add("E/$tag: $message ${throwable?.message ?: ""}")
        }
    }

    // Pitfall: platform-specific test classes need expect/actual too
    class FakePlatformContext : PlatformContext()

    // Tests run on ALL platforms
    // @Test
    fun testLoginSuccess() {
        // runTest {
        val engine = FakeHttpEngine()
        val storage = FakeSecureStorage()
        val logger = FakeLogger()

        engine.nextResponse = HttpResponse(
            200,
            """{"access_token":"abc123","refresh_token":"ref456","expires_in":"3600"}""",
            emptyMap(),
        )

        val repo = AuthRepository(engine, storage, logger)
        val result = runBlocking { repo.login("user@test.com", "password") }

        // Verify result
        assert(result.isSuccess)
        val token = result.getOrThrow()
        assert(token.accessToken == "abc123")
        assert(token.refreshToken == "ref456")

        // Verify storage was updated
        assert(storage.store["auth_token"] == "abc123")
        assert(storage.store["refresh_token"] == "ref456")

        // Verify HTTP request
        assert(engine.lastRequest?.method == "POST")
        assert(engine.lastRequest?.url == "/api/auth/login")

        // Verify logging
        assert(logger.logs.any { it.contains("Login successful") })
        // }
    }

    // @Test
    fun testLoginFailure() {
        // runTest {
        val engine = FakeHttpEngine()
        val storage = FakeSecureStorage()
        val logger = FakeLogger()

        engine.nextResponse = HttpResponse(401, """{"error":"invalid"}""", emptyMap())

        val repo = AuthRepository(engine, storage, logger)
        val result = runBlocking { repo.login("user@test.com", "wrong") }

        assert(result.isFailure)
        assert(result.exceptionOrNull() is AuthException)

        // Storage should NOT be updated on failure
        assert(storage.store.isEmpty())
        // }
    }

    // @Test
    fun testLogout() {
        // runTest {
        val engine = FakeHttpEngine()
        val storage = FakeSecureStorage()
        val logger = FakeLogger()

        storage.store["auth_token"] = "abc123"
        storage.store["refresh_token"] = "ref456"

        val repo = AuthRepository(engine, storage, logger)
        runBlocking { repo.logout() }

        assert(storage.store["auth_token"] == null)
        assert(storage.store["refresh_token"] == null)
        // }
    }
}

// Helper for non-coroutine test environments
fun <T> runBlocking(block: suspend () -> T): T {
    var result: T? = null
    var exception: Throwable? = null
    // Simplified -- real impl uses kotlinx.coroutines.runBlocking
    kotlinx.coroutines.runBlocking {
        try {
            result = block()
        } catch (e: Throwable) {
            exception = e
        }
    }
    exception?.let { throw it }
    @Suppress("UNCHECKED_CAST")
    return result as T
}
```

## Summary and Key Takeaways

- **expect/actual** provides compile-time guarantees that all platforms implement required APIs -- missing actuals are compile errors, not runtime crashes
- Keep **actual implementations thin** -- push business logic into common code, actuals should just wrap platform APIs
- A **common mistake** is putting JSON parsing or validation in platform code -- this belongs in `commonMain`
- **Dependency injection** in KMP works best with a simple service locator or constructor injection -- avoid platform-specific DI frameworks in common code
- **SharedViewModel** pattern with `StateFlow` enables reactive UI state management shared across platforms
- The **trade-off** of KMP vs Flutter/React Native: KMP shares logic but keeps native UI, resulting in better platform feel but more UI code
- Test **common code extensively** in `commonTest` -- it runs on all platforms automatically, catching cross-platform issues early
- The **pitfall** of KMP is the iOS interop learning curve -- Swift/Kotlin bridging requires understanding of memory management differences'''
    ),
    (
        "kotlin/arrow-functional-error-handling",
        "Explain Arrow library functional programming patterns in Kotlin including Either for typed error handling, Raise DSL for effect-based composition, Resource for safe acquisition and release, and Schedule for retry policies with practical service layer examples",
        '''# Arrow Functional Programming Patterns in Kotlin

## Why Arrow for Error Handling?

Kotlin's built-in exception handling has a fundamental problem: **exceptions are invisible in type signatures**. A function returning `User` might throw 5 different exceptions, but the caller has no way to know without reading the implementation. Arrow's `Either<Error, Success>` makes errors **explicit in the type system**, which is critical **because** it forces callers to handle every failure path at compile time rather than discovering them through runtime crashes.

### Either and Typed Error Handling

```kotlin
// Arrow 1.2+ with Raise DSL
// import arrow.core.*
// import arrow.core.raise.*
// import arrow.resilience.*
// import arrow.fx.coroutines.*

// --- Domain errors as a sealed hierarchy ---

sealed class DomainError {
    data class NotFound(val resource: String, val id: String) : DomainError()
    data class ValidationError(val field: String, val message: String) : DomainError()
    data class Unauthorized(val reason: String) : DomainError()
    data class Conflict(val message: String) : DomainError()
    data class ExternalServiceError(val service: String, val cause: String) : DomainError()
}

data class User(
    val id: String,
    val name: String,
    val email: String,
    val role: String = "user",
)

data class CreateUserRequest(
    val name: String,
    val email: String,
)

// Either explicitly communicates possible failures
// Best practice: use sealed class for errors, not strings or generic exceptions
typealias DomainResult<T> = arrow.core.Either<DomainError, T>

// --- Repository layer with Either returns ---

interface UserRepository {
    suspend fun findById(id: String): User?
    suspend fun findByEmail(email: String): User?
    suspend fun save(user: User): User
    suspend fun delete(id: String): Boolean
}

class UserService(
    private val repo: UserRepository,
    private val emailService: EmailService,
) {
    // Traditional Either usage
    suspend fun getUser(id: String): DomainResult<User> {
        val user = repo.findById(id)
            ?: return arrow.core.Either.Left(DomainError.NotFound("User", id))
        return arrow.core.Either.Right(user)
    }

    // However, chaining Either manually gets verbose
    // Common mistake: nested when/fold expressions
    suspend fun getUserVerbose(id: String): DomainResult<User> {
        return when (val result = getUser(id)) {
            is arrow.core.Either.Left -> result
            is arrow.core.Either.Right -> {
                if (result.value.role == "banned") {
                    arrow.core.Either.Left(DomainError.Unauthorized("User is banned"))
                } else {
                    result
                }
            }
        }
    }
}

interface EmailService {
    suspend fun sendWelcome(email: String, name: String): Boolean
}
```

### Raise DSL: Elegant Error Composition

The **Raise DSL** (Arrow 1.2+) solves the verbosity problem. Instead of manually wrapping/unwrapping `Either`, you write straight-line code and use `raise()` to signal errors -- similar to exceptions but **type-safe** and tracked by the compiler. **Therefore**, you get the readability of exceptions with the safety of typed errors.

```kotlin
// --- Raise DSL for clean composition ---

// context(Raise<DomainError>) marks a function as "may fail with DomainError"
// This is the Arrow 1.2+ approach -- replaces EitherEffect

class UserServiceRaise(
    private val repo: UserRepository,
    private val emailService: EmailService,
) {
    // Raise context -- reads like imperative code, but errors are tracked
    // Trade-off: less boilerplate but requires understanding of context receivers
    context(arrow.core.raise.Raise<DomainError>)
    suspend fun createUser(request: CreateUserRequest): User {
        // Validation -- raise short-circuits like throw, but type-safe
        ensure(request.name.length >= 2) {
            DomainError.ValidationError("name", "Must be at least 2 characters")
        }
        ensure(request.email.contains("@")) {
            DomainError.ValidationError("email", "Invalid email format")
        }

        // Check for duplicates
        val existing = repo.findByEmail(request.email)
        if (existing != null) {
            raise(DomainError.Conflict("Email ${request.email} already registered"))
        }

        // Create and save
        val user = User(
            id = generateId(),
            name = request.name,
            email = request.email,
        )
        val saved = repo.save(user)

        // Send welcome email -- we might want this to be non-fatal
        // Pitfall: raising here would roll back the user creation
        // Best practice: use Either for non-critical side effects
        val emailResult = arrow.core.raise.either<DomainError, Boolean> {
            val sent = emailService.sendWelcome(saved.email, saved.name)
            ensure(sent) {
                DomainError.ExternalServiceError("email", "Failed to send welcome email")
            }
            sent
        }
        // Log but don't fail if email sending fails
        emailResult.onLeft { error ->
            println("Warning: Welcome email failed: $error")
        }

        return saved
    }

    context(arrow.core.raise.Raise<DomainError>)
    suspend fun getActiveUser(id: String): User {
        // ensureNotNull converts nullable to non-null or raises
        val user = repo.findById(id).let {
            // Simulate ensureNotNull behavior
            it ?: raise(DomainError.NotFound("User", id))
        }
        ensure(user.role != "banned") {
            DomainError.Unauthorized("User $id is banned")
        }
        return user
    }

    context(arrow.core.raise.Raise<DomainError>)
    suspend fun transferRole(fromId: String, toId: String, newRole: String): Pair<User, User> {
        // Compose multiple Raise operations -- any raise propagates up
        val fromUser = getActiveUser(fromId)
        val toUser = getActiveUser(toId)

        ensure(fromUser.role == "admin") {
            DomainError.Unauthorized("Only admins can transfer roles")
        }

        val updatedFrom = repo.save(fromUser.copy(role = "user"))
        val updatedTo = repo.save(toUser.copy(role = newRole))
        return Pair(updatedFrom, updatedTo)
    }

    private fun generateId(): String = java.util.UUID.randomUUID().toString()
}

// --- Converting between Raise and Either at boundaries ---

suspend fun handleCreateUser(
    service: UserServiceRaise,
    request: CreateUserRequest,
): arrow.core.Either<DomainError, User> {
    // either { } enters the Raise context and returns Either
    return arrow.core.raise.either {
        service.createUser(request)
    }
}

// HTTP layer -- map errors to status codes
suspend fun httpHandler(
    service: UserServiceRaise,
    request: CreateUserRequest,
): Pair<Int, String> {
    return handleCreateUser(service, request).fold(
        ifLeft = { error ->
            when (error) {
                is DomainError.ValidationError -> Pair(400, "Validation: ${error.message}")
                is DomainError.NotFound -> Pair(404, "${error.resource} not found")
                is DomainError.Unauthorized -> Pair(403, error.reason)
                is DomainError.Conflict -> Pair(409, error.message)
                is DomainError.ExternalServiceError -> Pair(502, "Service ${error.service} failed")
            }
        },
        ifRight = { user -> Pair(201, "Created user ${user.id}") },
    )
}
```

### Resource Management and Retry Policies

Arrow's **Resource** ensures deterministic cleanup (like Rust's RAII or Python's context managers), and **Schedule** provides composable retry policies -- far more powerful than simple loop-and-sleep patterns.

```kotlin
// --- Resource for safe acquisition/release ---

// Arrow Resource guarantees cleanup even on cancellation
// Therefore, it's safer than try-finally for coroutine contexts

data class DatabaseConnection(val id: Int) {
    var closed = false
    suspend fun execute(query: String): List<Map<String, Any>> {
        if (closed) throw IllegalStateException("Connection closed")
        return listOf(mapOf("result" to "data"))
    }
    suspend fun close() { closed = true }
}

data class FileHandle(val path: String) {
    var closed = false
    suspend fun write(data: String) {
        if (closed) throw IllegalStateException("File closed")
    }
    suspend fun close() { closed = true }
}

// Resource composition -- acquire in order, release in reverse
// Common mistake: releasing resources in wrong order (e.g., closing DB before file)
suspend fun exportData(query: String, outputPath: String): String {
    // Using arrow.fx.coroutines.resource builder
    val dbResource = arrow.fx.coroutines.resource(
        acquire = { DatabaseConnection(1) },
        release = { conn, _ -> conn.close() },
    )
    val fileResource = arrow.fx.coroutines.resource(
        acquire = { FileHandle(outputPath) },
        release = { fh, _ -> fh.close() },
    )

    // Compose resources -- both are acquired, used, then released
    return arrow.fx.coroutines.resource {
        val db = dbResource.bind()
        val file = fileResource.bind()
        // Use both resources
        val results = db.execute(query)
        file.write(results.toString())
        "Exported ${results.size} rows to $outputPath"
    }.use { it }  // Triggers acquire -> use -> release
}

// --- Schedule for retry policies ---

// Arrow Schedule composes retry strategies declaratively
// Trade-off: more expressive than manual retry loops but adds dependency

fun createRetrySchedule(): arrow.resilience.Schedule<Throwable, Long> {
    // Exponential backoff with jitter, max 5 retries, max 30s delay
    return arrow.resilience.Schedule.exponential<Throwable>(250.milliseconds)
        .jittered()
        .doWhile { _, duration -> duration < 30.seconds }
        .zipLeft(arrow.resilience.Schedule.recurs(5))
        .log { input, output ->
            println("Retry attempt after error: ${input.message}")
        }
}

suspend fun <T> retryWithPolicy(
    schedule: arrow.resilience.Schedule<Throwable, *>,
    action: suspend () -> T,
): T {
    return schedule.retry { action() }
}

// Combining Either + Schedule for resilient service calls
context(arrow.core.raise.Raise<DomainError>)
suspend fun fetchExternalData(url: String): String {
    val schedule = arrow.resilience.Schedule.exponential<Throwable>(100.milliseconds)
        .jittered()
        .zipLeft(arrow.resilience.Schedule.recurs(3))

    return try {
        schedule.retry {
            // Simulate external HTTP call
            val response = externalHttpCall(url)
            if (response.statusCode >= 500) {
                throw RuntimeException("Server error: ${response.statusCode}")
            }
            response.body
        }
    } catch (e: Exception) {
        raise(DomainError.ExternalServiceError("http", "Failed after retries: ${e.message}"))
    }
}

suspend fun externalHttpCall(url: String): HttpResponse {
    return HttpResponse(200, "data", emptyMap())
}

data class HttpResponse(val statusCode: Int, val body: String, val headers: Map<String, String>)

// kotlin.time helpers
val Int.milliseconds get() = kotlin.time.Duration.Companion.milliseconds(this)
val Int.seconds get() = kotlin.time.Duration.Companion.seconds(this)
```

## Summary and Key Takeaways

- **Either<Error, Success>** makes errors visible in type signatures -- callers must handle every failure path at compile time
- The **Raise DSL** eliminates Either boilerplate -- write straight-line code with `raise()` for errors, compose naturally
- A **common mistake** is using exceptions for expected business errors (validation, not found) -- `Either` is for expected failures, exceptions for unexpected ones
- **`ensure()`** and **`ensureNotNull()`** are the Raise equivalents of `require()` -- they short-circuit with typed errors
- **Resource** provides deterministic cleanup with cancellation safety -- superior to `try-finally` in coroutine contexts
- **Schedule** composes retry policies declaratively -- exponential backoff, jitter, max retries, and logging in a single expression
- The **pitfall** of Arrow is the learning curve -- teams need to understand context receivers and functional composition
- At HTTP boundaries, **fold** `Either` into status codes -- keep domain errors clean and map to HTTP only at the edge'''
    ),
    (
        "kotlin/testing-kotest-mockk-patterns",
        "Describe comprehensive Kotlin testing patterns using Kotest framework with property-based testing, MockK for coroutine mocking, test containers for integration testing, and snapshot testing for serialization verification",
        '''# Kotlin Testing Patterns: Kotest, MockK, and Beyond

## Test Architecture for Kotlin Projects

Effective Kotlin testing requires a different approach than Java testing **because** Kotlin has coroutines, sealed classes, extension functions, and data classes that need specialized testing strategies. Kotest provides a more Kotlin-idiomatic testing framework than JUnit, while MockK handles coroutine mocking natively.

### Kotest Styles and Property-Based Testing

```kotlin
// import io.kotest.core.spec.style.*
// import io.kotest.matchers.*
// import io.kotest.matchers.collections.*
// import io.kotest.matchers.string.*
// import io.kotest.property.*
// import io.kotest.property.arbitrary.*
// import io.mockk.*

// --- Domain types ---

data class Email private constructor(val value: String) {
    companion object {
        fun create(raw: String): Result<Email> {
            if (raw.isBlank()) return Result.failure(
                IllegalArgumentException("Email cannot be blank")
            )
            if (!raw.contains("@")) return Result.failure(
                IllegalArgumentException("Email must contain @")
            )
            if (raw.length > 254) return Result.failure(
                IllegalArgumentException("Email too long")
            )
            return Result.success(Email(raw.trim().lowercase()))
        }
    }
}

data class Money(val amount: Long, val currency: String) {
    // amount in cents to avoid floating point issues
    operator fun plus(other: Money): Money {
        require(currency == other.currency) { "Cannot add different currencies" }
        return Money(amount + other.amount, currency)
    }
    operator fun minus(other: Money): Money {
        require(currency == other.currency) { "Cannot subtract different currencies" }
        return Money(amount - other.amount, currency)
    }
    operator fun times(factor: Int): Money = Money(amount * factor, currency)

    companion object {
        fun usd(dollars: Long, cents: Long = 0) = Money(dollars * 100 + cents, "USD")
        fun eur(euros: Long, cents: Long = 0) = Money(euros * 100 + cents, "EUR")
    }
}

// --- Kotest BehaviorSpec for domain logic ---

class EmailTest { // : BehaviorSpec({
    // Given/When/Then style -- great for business logic
    fun testValidEmails() {
        // given("a valid email string") {
        val validEmails = listOf("user@example.com", "test+tag@domain.co", "A@B.C")
        for (input in validEmails) {
            // `when`("creating Email from '$input'") {
            val result = Email.create(input)
            // then("it should succeed") {
            assert(result.isSuccess)
            // }
            // then("it should be lowercase") {
            assert(result.getOrThrow().value == input.trim().lowercase())
            // }
        }
    }

    fun testInvalidEmails() {
        // given("an invalid email string") {
        val invalidCases = mapOf(
            "" to "blank",
            "   " to "whitespace only",
            "noatsign" to "missing @",
            "a".repeat(255) + "@b.com" to "too long",
        )
        for ((input, reason) in invalidCases) {
            // `when`("creating Email from invalid input ($reason)") {
            val result = Email.create(input)
            // then("it should fail") {
            assert(result.isFailure)
            // }
        }
    }
}

// --- Property-based testing ---
// Best practice: use property tests to find edge cases you wouldn't think of

class MoneyPropertyTest { // : FunSpec({
    // Trade-off: property tests are slower but find edge cases
    // Therefore, use them for core domain logic, not I/O

    fun testAdditionIsCommutative() {
        // forAll(Arb.long(-1_000_000..1_000_000), Arb.long(-1_000_000..1_000_000)) { a, b ->
        //     val m1 = Money(a, "USD")
        //     val m2 = Money(b, "USD")
        //     m1 + m2 == m2 + m1
        // }

        // Manual property test simulation
        val cases = listOf(
            Pair(100L, 200L), Pair(-50L, 50L), Pair(0L, 0L),
            Pair(Long.MAX_VALUE / 2, Long.MAX_VALUE / 2),
        )
        for ((a, b) in cases) {
            val m1 = Money(a, "USD")
            val m2 = Money(b, "USD")
            assert(m1 + m2 == m2 + m1) { "Commutativity failed for $a, $b" }
        }
    }

    fun testAdditionIsAssociative() {
        val cases = listOf(
            Triple(100L, 200L, 300L),
            Triple(-50L, 0L, 50L),
        )
        for ((a, b, c) in cases) {
            val m1 = Money(a, "USD")
            val m2 = Money(b, "USD")
            val m3 = Money(c, "USD")
            assert((m1 + m2) + m3 == m1 + (m2 + m3)) {
                "Associativity failed for $a, $b, $c"
            }
        }
    }

    fun testZeroIsIdentity() {
        val amounts = listOf(0L, 100L, -100L, 999999L)
        for (amount in amounts) {
            val m = Money(amount, "USD")
            val zero = Money(0, "USD")
            assert(m + zero == m) { "Zero identity failed for $amount" }
        }
    }

    // Common mistake: not testing overflow behavior
    fun testMultiplicationOverflow() {
        // Property test would catch this:
        // forAll(Arb.long(), Arb.int(1..1000)) { amount, factor ->
        //     shouldNotThrow { Money(amount, "USD") * factor }
        // }
        // Reveals that Long overflow causes silent corruption
    }
}
```

### MockK for Coroutine Testing

**However**, testing code that uses coroutines requires a mocking library that understands suspend functions. MockK is the de facto choice for Kotlin **because** it supports `coEvery`/`coVerify` for suspend functions natively.

```kotlin
// --- MockK patterns for service testing ---

interface OrderRepository {
    suspend fun findById(id: String): Order?
    suspend fun save(order: Order): Order
    suspend fun findByUserId(userId: String): List<Order>
}

interface PaymentClient {
    suspend fun charge(amount: Money, token: String): PaymentResult
    suspend fun refund(paymentId: String, amount: Money): PaymentResult
}

data class Order(
    val id: String,
    val userId: String,
    val items: List<OrderItem>,
    val status: OrderStatus,
    val paymentId: String? = null,
) {
    val total: Money get() = items.fold(Money.usd(0)) { acc, item ->
        acc + Money(item.priceInCents * item.quantity, "USD")
    }
}

data class OrderItem(val productId: String, val priceInCents: Long, val quantity: Int)

enum class OrderStatus { PENDING, PAID, SHIPPED, CANCELLED, REFUNDED }

data class PaymentResult(val success: Boolean, val paymentId: String?, val error: String?)

class OrderService(
    private val orderRepo: OrderRepository,
    private val paymentClient: PaymentClient,
) {
    suspend fun placeOrder(order: Order, paymentToken: String): Result<Order> {
        if (order.items.isEmpty()) {
            return Result.failure(IllegalArgumentException("Order must have items"))
        }
        val paymentResult = paymentClient.charge(order.total, paymentToken)
        if (!paymentResult.success) {
            return Result.failure(RuntimeException("Payment failed: ${paymentResult.error}"))
        }
        val paidOrder = order.copy(
            status = OrderStatus.PAID,
            paymentId = paymentResult.paymentId,
        )
        return Result.success(orderRepo.save(paidOrder))
    }

    suspend fun cancelOrder(orderId: String): Result<Order> {
        val order = orderRepo.findById(orderId)
            ?: return Result.failure(NoSuchElementException("Order $orderId not found"))
        if (order.status != OrderStatus.PAID) {
            return Result.failure(IllegalStateException("Can only cancel paid orders"))
        }
        // Refund payment
        val refundResult = order.paymentId?.let {
            paymentClient.refund(it, order.total)
        } ?: return Result.failure(IllegalStateException("No payment to refund"))
        if (!refundResult.success) {
            return Result.failure(RuntimeException("Refund failed: ${refundResult.error}"))
        }
        return Result.success(orderRepo.save(order.copy(status = OrderStatus.REFUNDED)))
    }
}

// --- Test class using MockK ---

class OrderServiceTest { // : FunSpec({
    // Pitfall: forgetting to clear mocks between tests
    // Best practice: use beforeTest { clearAllMocks() }

    fun testPlaceOrderSuccess() {
        // val orderRepo = mockk<OrderRepository>()
        // val paymentClient = mockk<PaymentClient>()
        // val service = OrderService(orderRepo, paymentClient)

        val order = Order(
            id = "ord-1",
            userId = "user-1",
            items = listOf(OrderItem("prod-1", 2500, 2)),
            status = OrderStatus.PENDING,
        )

        // coEvery for suspend function mocking
        // coEvery { paymentClient.charge(any(), "tok_visa") } returns
        //     PaymentResult(success = true, paymentId = "pay-1", error = null)
        // coEvery { orderRepo.save(any()) } answers { firstArg() }

        // runTest {
        //     val result = service.placeOrder(order, "tok_visa")
        //     result.isSuccess shouldBe true
        //     result.getOrThrow().status shouldBe OrderStatus.PAID
        //     result.getOrThrow().paymentId shouldBe "pay-1"
        //
        //     // Verify interactions
        //     coVerify(exactly = 1) { paymentClient.charge(Money(5000, "USD"), "tok_visa") }
        //     coVerify(exactly = 1) { orderRepo.save(match { it.status == OrderStatus.PAID }) }
        // }
    }

    fun testPlaceOrderPaymentFailure() {
        // val orderRepo = mockk<OrderRepository>()
        // val paymentClient = mockk<PaymentClient>()
        // val service = OrderService(orderRepo, paymentClient)

        val order = Order(
            id = "ord-2",
            userId = "user-1",
            items = listOf(OrderItem("prod-1", 1000, 1)),
            status = OrderStatus.PENDING,
        )

        // coEvery { paymentClient.charge(any(), any()) } returns
        //     PaymentResult(success = false, paymentId = null, error = "card_declined")

        // runTest {
        //     val result = service.placeOrder(order, "tok_declined")
        //     result.isFailure shouldBe true
        //     result.exceptionOrNull()?.message shouldContain "Payment failed"
        //
        //     // Verify order was NOT saved
        //     coVerify(exactly = 0) { orderRepo.save(any()) }
        // }
    }

    fun testCancelOrderRefundsPayment() {
        // val orderRepo = mockk<OrderRepository>()
        // val paymentClient = mockk<PaymentClient>()
        // val service = OrderService(orderRepo, paymentClient)

        val paidOrder = Order(
            id = "ord-3", userId = "user-1",
            items = listOf(OrderItem("prod-1", 3000, 1)),
            status = OrderStatus.PAID,
            paymentId = "pay-3",
        )

        // coEvery { orderRepo.findById("ord-3") } returns paidOrder
        // coEvery { paymentClient.refund("pay-3", Money(3000, "USD")) } returns
        //     PaymentResult(success = true, paymentId = "ref-3", error = null)
        // coEvery { orderRepo.save(any()) } answers { firstArg() }

        // runTest {
        //     val result = service.cancelOrder("ord-3")
        //     result.isSuccess shouldBe true
        //     result.getOrThrow().status shouldBe OrderStatus.REFUNDED
        //
        //     coVerifyOrder {
        //         orderRepo.findById("ord-3")
        //         paymentClient.refund("pay-3", any())
        //         orderRepo.save(match { it.status == OrderStatus.REFUNDED })
        //     }
        // }
    }
}
```

### Snapshot Testing for Serialization

A **best practice** for API development is snapshot testing -- verifying that serialized output matches a known-good baseline. This catches accidental breaking changes to JSON contracts.

```kotlin
// --- Snapshot testing for JSON serialization ---

// import kotlinx.serialization.*
// import kotlinx.serialization.json.*

// @Serializable
data class ApiResponse(
    val status: String,
    val data: UserDto?,
    val errors: List<ErrorDto> = emptyList(),
    val metadata: ResponseMetadata = ResponseMetadata(),
)

// @Serializable
data class UserDto(
    val id: String,
    val name: String,
    val email: String,
    val createdAt: String,
)

// @Serializable
data class ErrorDto(val code: String, val message: String, val field: String? = null)

// @Serializable
data class ResponseMetadata(val version: String = "1.0", val requestId: String = "test-id")

class SerializationSnapshotTest {
    // private val json = Json { prettyPrint = true; encodeDefaults = true }

    fun testSuccessResponseShape() {
        val response = ApiResponse(
            status = "success",
            data = UserDto(
                id = "user-123",
                name = "Alice",
                email = "alice@example.com",
                createdAt = "2024-01-15T10:30:00Z",
            ),
        )

        // Snapshot test: compare against known-good JSON
        // Therefore, any accidental field rename, removal, or type change is caught
        val expectedJson = """{
    "status": "success",
    "data": {
        "id": "user-123",
        "name": "Alice",
        "email": "alice@example.com",
        "createdAt": "2024-01-15T10:30:00Z"
    },
    "errors": [],
    "metadata": {
        "version": "1.0",
        "requestId": "test-id"
    }
}"""
        // val actual = json.encodeToString(response)
        // actual shouldBe expectedJson
        // Or use a snapshot library that auto-updates on first run
    }

    fun testErrorResponseShape() {
        val response = ApiResponse(
            status = "error",
            data = null,
            errors = listOf(
                ErrorDto("VALIDATION_ERROR", "Email is required", "email"),
                ErrorDto("VALIDATION_ERROR", "Name too short", "name"),
            ),
        )

        // Verify structure without exact string matching
        // Common mistake: snapshot tests that break on field ordering
        // val serialized = json.encodeToString(response)
        // val parsed = json.parseToJsonElement(serialized).jsonObject
        // parsed["status"]?.jsonPrimitive?.content shouldBe "error"
        // parsed["data"] shouldBe JsonNull
        // parsed["errors"]?.jsonArray?.size shouldBe 2
    }
}
```

## Summary and Key Takeaways

- **Kotest** provides Kotlin-idiomatic test styles (BehaviorSpec, FunSpec, StringSpec) with powerful matchers
- **Property-based testing** finds edge cases humans miss -- use for core domain logic where invariants must hold
- A **common mistake** is not clearing MockK mocks between tests -- use `clearAllMocks()` in `beforeTest`
- **`coEvery`/`coVerify`** handle suspend functions natively -- never use `every`/`verify` for coroutines
- The **trade-off** of snapshot testing: catches accidental changes but requires maintenance when intentional changes occur
- **`coVerifyOrder`** validates call ordering -- critical for testing workflows like order->payment->save
- The **pitfall** of over-mocking is that tests become coupled to implementation, not behavior -- prefer testing outcomes over interactions'''
    ),
]
