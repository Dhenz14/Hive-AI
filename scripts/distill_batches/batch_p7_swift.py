PAIRS = [
    (
        "swift/swiftui-mvvm-architecture-navigation-state",
        "Explain SwiftUI architecture patterns including MVVM with ObservableObject, the lifecycle differences between @StateObject and @ObservedObject, NavigationStack with typed destinations, and environment injection with practical complete module examples",
        r"""# SwiftUI Architecture Patterns: MVVM, Navigation, and State Management

## Understanding MVVM in SwiftUI

SwiftUI's declarative paradigm pairs naturally with the **Model-View-ViewModel (MVVM)** pattern, **because** the framework's reactive data-binding primitives (`@Published`, `ObservableObject`, `@StateObject`) map directly to ViewModel responsibilities. **However**, blindly porting UIKit-era MVVM into SwiftUI is a **common mistake** — SwiftUI views are value types recreated frequently, so ViewModel lifecycle must be handled with care to avoid data loss, duplicate network requests, or zombie references.

The **best practice** is to let each screen-level view own exactly one ViewModel via `@StateObject`, while child views that merely *read* the ViewModel receive it through `@ObservedObject` or the environment. **Therefore**, the ownership hierarchy mirrors the view hierarchy and the framework handles memory automatically.

### @StateObject vs @ObservedObject Lifecycle

The distinction between `@StateObject` and `@ObservedObject` is subtle but critical. `@StateObject` creates and **owns** the observable object — SwiftUI guarantees the instance persists across view re-renders for the lifetime of the view's identity. `@ObservedObject`, in contrast, does **not** own the object; if the parent view recreates, the `@ObservedObject` reference may point to a freshly initialized instance, losing state. A **pitfall** many developers encounter is using `@ObservedObject` at the top-level screen view, which causes the ViewModel to reset every time the parent body is re-evaluated.

```swift
import SwiftUI
import Combine
import Foundation

// MARK: - Models

struct User: Identifiable, Codable, Hashable {
    let id: UUID
    var name: String
    var email: String
    var avatarURL: URL?
}

struct UserDetail: Codable {
    let user: User
    let posts: [Post]
    let followerCount: Int
}

struct Post: Identifiable, Codable, Hashable {
    let id: UUID
    let title: String
    let body: String
    let createdAt: Date
}

// MARK: - Service Layer (injected via Environment)

protocol UserServiceProtocol {
    func fetchUsers() async throws -> [User]
    func fetchUserDetail(id: UUID) async throws -> UserDetail
    func updateUser(_ user: User) async throws -> User
}

class UserService: UserServiceProtocol {
    private let session: URLSession
    private let baseURL: URL

    init(session: URLSession = .shared, baseURL: URL = URL(string: "https://api.example.com")!) {
        self.session = session
        self.baseURL = baseURL
    }

    func fetchUsers() async throws -> [User] {
        let url = baseURL.appendingPathComponent("users")
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else {
            throw ServiceError.invalidResponse
        }
        return try JSONDecoder().decode([User].self, from: data)
    }

    func fetchUserDetail(id: UUID) async throws -> UserDetail {
        let url = baseURL.appendingPathComponent("users/\(id.uuidString)")
        let (data, _) = try await session.data(from: url)
        return try JSONDecoder().decode(UserDetail.self, from: data)
    }

    func updateUser(_ user: User) async throws -> User {
        var request = URLRequest(url: baseURL.appendingPathComponent("users/\(user.id.uuidString)"))
        request.httpMethod = "PUT"
        request.httpBody = try JSONEncoder().encode(user)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (data, _) = try await session.data(for: request)
        return try JSONDecoder().decode(User.self, from: data)
    }
}

enum ServiceError: LocalizedError {
    case invalidResponse
    case notFound
    case networkUnavailable

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Server returned an invalid response"
        case .notFound: return "Resource not found"
        case .networkUnavailable: return "Network is unavailable"
        }
    }
}
```

## ViewModel Design: Observable State Container

The ViewModel conforms to `ObservableObject` and exposes `@Published` properties that the view binds to. **Best practice** dictates keeping ViewModels focused — one per screen or major feature, not one giant ViewModel for the whole app. The **trade-off** is between granularity (many small ViewModels) and simplicity (fewer larger ones). For most apps, one ViewModel per navigation destination strikes the right balance.

```swift
// MARK: - ViewModels

@MainActor
class UserListViewModel: ObservableObject {
    @Published var users: [User] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var searchText = ""

    private let service: UserServiceProtocol

    // Best practice: inject dependencies for testability
    init(service: UserServiceProtocol) {
        self.service = service
    }

    var filteredUsers: [User] {
        if searchText.isEmpty { return users }
        return users.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

    func loadUsers() async {
        isLoading = true
        errorMessage = nil
        do {
            users = try await service.fetchUsers()
        } catch {
            // Therefore, surface errors to the UI layer for display
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func deleteUser(at offsets: IndexSet) {
        users.remove(atOffsets: offsets)
    }
}

@MainActor
class UserDetailViewModel: ObservableObject {
    @Published var detail: UserDetail?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let userID: UUID
    private let service: UserServiceProtocol

    init(userID: UUID, service: UserServiceProtocol) {
        self.userID = userID
        self.service = service
    }

    func loadDetail() async {
        isLoading = true
        do {
            detail = try await service.fetchUserDetail(id: userID)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

@MainActor
class EditUserViewModel: ObservableObject {
    @Published var name: String
    @Published var email: String
    @Published var isSaving = false
    @Published var didSave = false
    @Published var errorMessage: String?

    private var user: User
    private let service: UserServiceProtocol

    init(user: User, service: UserServiceProtocol) {
        self.user = user
        self.name = user.name
        self.email = user.email
        self.service = service
    }

    func save() async {
        isSaving = true
        var updated = user
        updated.name = name
        updated.email = email
        do {
            user = try await service.updateUser(updated)
            didSave = true
        } catch {
            errorMessage = error.localizedDescription
        }
        isSaving = false
    }
}
```

### NavigationStack with Typed Destinations

Since iOS 16, `NavigationStack` with `navigationDestination(for:)` replaces the old `NavigationLink(destination:)` pattern. The typed approach is superior **because** it decouples navigation from the view hierarchy, making deep linking and programmatic navigation straightforward. A **common mistake** is mixing the old and new navigation APIs, which causes undefined behavior.

```swift
// MARK: - Navigation Types

enum AppRoute: Hashable {
    case userDetail(UUID)
    case editUser(User)
    case settings
    case postDetail(Post)
}

// MARK: - Environment Key for Service Injection

struct UserServiceKey: EnvironmentKey {
    static let defaultValue: UserServiceProtocol = UserService()
}

extension EnvironmentValues {
    var userService: UserServiceProtocol {
        get { self[UserServiceKey.self] }
        set { self[UserServiceKey.self] = newValue }
    }
}

// MARK: - Router (centralized navigation state)

@MainActor
class Router: ObservableObject {
    @Published var path = NavigationPath()

    func navigate(to route: AppRoute) {
        path.append(route)
    }

    func popToRoot() {
        path = NavigationPath()
    }

    func pop() {
        guard !path.isEmpty else { return }
        path.removeLast()
    }
}

// MARK: - Views

struct ContentView: View {
    @StateObject private var router = Router()
    @Environment(\.userService) private var service

    var body: some View {
        NavigationStack(path: $router.path) {
            UserListScreen()
                .navigationDestination(for: AppRoute.self) { route in
                    switch route {
                    case .userDetail(let id):
                        UserDetailScreen(userID: id)
                    case .editUser(let user):
                        EditUserScreen(user: user)
                    case .settings:
                        SettingsScreen()
                    case .postDetail(let post):
                        PostDetailScreen(post: post)
                    }
                }
        }
        .environmentObject(router)
    }
}

struct UserListScreen: View {
    // @StateObject: this view OWNS the ViewModel
    // It persists across body re-evaluations
    @Environment(\.userService) private var service
    @StateObject private var viewModel: UserListViewModel

    @EnvironmentObject private var router: Router

    // However, @StateObject init requires a closure-based approach
    // because we need to capture the environment service
    init() {
        // Pitfall: cannot use @Environment in init directly
        // Therefore, use a default and re-assign in .task or onAppear
        _viewModel = StateObject(wrappedValue: UserListViewModel(service: UserService()))
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.users.isEmpty {
                ProgressView("Loading users...")
            } else if let error = viewModel.errorMessage {
                ErrorBannerView(message: error) {
                    Task { await viewModel.loadUsers() }
                }
            } else {
                List {
                    ForEach(viewModel.filteredUsers) { user in
                        Button {
                            router.navigate(to: .userDetail(user.id))
                        } label: {
                            UserRowView(user: user)
                        }
                    }
                    .onDelete(perform: viewModel.deleteUser)
                }
                .searchable(text: $viewModel.searchText, prompt: "Search users")
                .refreshable {
                    await viewModel.loadUsers()
                }
            }
        }
        .navigationTitle("Users")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { router.navigate(to: .settings) } label: {
                    Image(systemName: "gear")
                }
            }
        }
        .task {
            await viewModel.loadUsers()
        }
    }
}

struct UserRowView: View {
    let user: User

    var body: some View {
        HStack {
            AsyncImage(url: user.avatarURL) { image in
                image.resizable().clipShape(Circle())
            } placeholder: {
                Circle().fill(.gray.opacity(0.3))
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading) {
                Text(user.name).font(.headline)
                Text(user.email).font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct UserDetailScreen: View {
    let userID: UUID
    @Environment(\.userService) private var service
    @StateObject private var viewModel: UserDetailViewModel
    @EnvironmentObject private var router: Router

    init(userID: UUID) {
        self.userID = userID
        _viewModel = StateObject(wrappedValue: UserDetailViewModel(
            userID: userID, service: UserService()
        ))
    }

    var body: some View {
        ScrollView {
            if let detail = viewModel.detail {
                VStack(alignment: .leading, spacing: 16) {
                    Text(detail.user.name).font(.largeTitle)
                    Text("\(detail.followerCount) followers").foregroundStyle(.secondary)

                    Divider()

                    ForEach(detail.posts) { post in
                        Button {
                            router.navigate(to: .postDetail(post))
                        } label: {
                            PostCardView(post: post)
                        }
                    }
                }
                .padding()
            } else if viewModel.isLoading {
                ProgressView()
            }
        }
        .navigationTitle("Profile")
        .toolbar {
            if let detail = viewModel.detail {
                Button("Edit") {
                    router.navigate(to: .editUser(detail.user))
                }
            }
        }
        .task { await viewModel.loadDetail() }
    }
}

struct EditUserScreen: View {
    let user: User
    @StateObject private var viewModel: EditUserViewModel
    @EnvironmentObject private var router: Router
    @Environment(\.dismiss) private var dismiss

    init(user: User) {
        self.user = user
        _viewModel = StateObject(wrappedValue: EditUserViewModel(
            user: user, service: UserService()
        ))
    }

    var body: some View {
        Form {
            Section("Personal Info") {
                TextField("Name", text: $viewModel.name)
                TextField("Email", text: $viewModel.email)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
            }

            if let error = viewModel.errorMessage {
                Section { Text(error).foregroundStyle(.red) }
            }
        }
        .navigationTitle("Edit User")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    Task { await viewModel.save() }
                }
                .disabled(viewModel.isSaving)
            }
        }
        .onChange(of: viewModel.didSave) { _, saved in
            if saved { dismiss() }
        }
    }
}

// Placeholder views
struct SettingsScreen: View { var body: some View { Text("Settings") } }
struct PostDetailScreen: View { let post: Post; var body: some View { Text(post.title) } }
struct PostCardView: View { let post: Post; var body: some View { Text(post.title) } }
struct ErrorBannerView: View {
    let message: String
    let retry: () -> Void
    var body: some View {
        VStack { Text(message); Button("Retry", action: retry) }
    }
}
```

## Environment Injection for Dependency Inversion

The `@Environment` property wrapper combined with custom `EnvironmentKey` types provides a SwiftUI-native dependency injection mechanism. This is the **best practice** for sharing services across the view hierarchy **because** it avoids singletons and makes testing straightforward — you simply inject a mock service at the root of your test view hierarchy.

### Testing with Preview and Unit Tests

The **trade-off** with environment injection is discoverability — crashes at runtime if a required environment object is missing. **Therefore**, always provide sensible defaults in your `EnvironmentKey` conformance, and use Xcode Previews to catch missing dependencies early.

## Summary and Key Takeaways

- **@StateObject** owns the ViewModel; use it at the screen level where the ViewModel is created. **@ObservedObject** borrows it; use it in child views that receive the ViewModel from a parent.
- **NavigationStack** with typed `navigationDestination(for:)` decouples navigation from views, enabling programmatic routing, deep linking, and a centralized `Router` pattern.
- **Environment injection** via custom `EnvironmentKey` is the preferred dependency injection strategy in SwiftUI **because** it leverages the framework's built-in propagation and avoids global singletons.
- A **common mistake** is putting business logic directly in SwiftUI views. ViewModels marked `@MainActor` keep UI-bound state on the main thread while delegating work to injected services.
- The `Router` pattern with `NavigationPath` gives you imperative navigation control (push, pop, pop-to-root) while remaining compatible with SwiftUI's declarative model.
- Always annotate ViewModels with `@MainActor` **because** `@Published` property changes must occur on the main thread to avoid runtime warnings and potential data races.
"""
    ),
    (
        "swift/concurrency-async-await-actors-structured",
        "Explain Swift concurrency in depth including async/await mechanics, structured concurrency with task groups, actor isolation and reentrancy, Sendable conformance requirements, MainActor usage, and async sequence patterns with cancellation handling",
        r"""# Swift Concurrency: Async/Await, Actors, and Structured Concurrency

## The Foundation: Async/Await in Swift

Swift's concurrency model, introduced in Swift 5.5, is built on **structured concurrency** — the principle that concurrent tasks form a tree where parent tasks cannot complete until all child tasks finish. This is fundamentally different from GCD's fire-and-forget dispatch model **because** it gives the compiler and runtime the ability to enforce cancellation propagation, priority inheritance, and data-race safety at compile time.

**However**, adopting Swift concurrency is not merely replacing `DispatchQueue.async` with `Task {}`. The model introduces new concepts — **actors**, **Sendable**, **isolation domains** — that require rethinking how data flows through your application. A **common mistake** is wrapping existing callback-based code in `withCheckedContinuation` everywhere instead of redesigning the data flow to be naturally async.

### How Suspension Works

When a function hits an `await` expression, the current task **suspends** and yields its thread back to the cooperative thread pool. The runtime is free to schedule other work on that thread. When the awaited operation completes, the task resumes — potentially on a **different** thread. **Therefore**, you must never hold locks, semaphores, or thread-local storage across `await` boundaries. This is a critical **pitfall** that causes deadlocks when migrating from GCD.

```swift
import Foundation

// MARK: - Data Transfer Objects (Sendable)

// Best practice: make DTOs struct + Sendable for safe cross-isolation transfer
struct WeatherData: Sendable, Codable {
    let city: String
    let temperatureCelsius: Double
    let humidity: Double
    let conditions: String
    let timestamp: Date
}

struct ForecastDay: Sendable, Codable {
    let date: Date
    let high: Double
    let low: Double
    let conditions: String
}

struct Forecast: Sendable, Codable {
    let city: String
    let days: [ForecastDay]
}

enum WeatherError: Error, Sendable {
    case networkFailure(String)
    case decodingError
    case cancelled
    case rateLimited(retryAfter: TimeInterval)
    case cityNotFound(String)
}

// MARK: - Actor-Isolated Cache

// Actors serialize access to mutable state — no data races by construction
// Trade-off: serialization means potential contention under high load
actor WeatherCache {
    private var store: [String: (data: WeatherData, expiry: Date)] = [:]
    private let ttl: TimeInterval

    init(ttl: TimeInterval = 300) { // 5-minute default
        self.ttl = ttl
    }

    func get(_ city: String) -> WeatherData? {
        guard let entry = store[city], entry.expiry > Date.now else {
            store.removeValue(forKey: city)
            return nil
        }
        return entry.data
    }

    func set(_ city: String, data: WeatherData) {
        store[city] = (data, Date.now.addingTimeInterval(ttl))
    }

    func invalidate(_ city: String) {
        store.removeValue(forKey: city)
    }

    func invalidateAll() {
        store.removeAll()
    }

    // nonisolated properties don't require await
    nonisolated var cacheTTL: TimeInterval { ttl }
}
```

## Actor Isolation and Reentrancy

Actors protect their mutable state by ensuring only one task executes within the actor at a time. **However**, actor methods are **reentrant** — when an actor method hits an `await`, other callers can enter the actor. This means the actor's state may change between suspension points. A **common mistake** is assuming that state read before an `await` is still valid after:

```swift
// MARK: - Weather Service Actor

actor WeatherService {
    private let cache: WeatherCache
    private let session: URLSession
    private let baseURL: URL
    private var inFlightRequests: [String: Task<WeatherData, Error>] = [:]

    init(
        cache: WeatherCache = WeatherCache(),
        session: URLSession = .shared,
        baseURL: URL = URL(string: "https://api.weather.example.com/v2")!
    ) {
        self.cache = cache
        self.session = session
        self.baseURL = baseURL
    }

    // Best practice: deduplicate in-flight requests to the same resource
    // This prevents the "thundering herd" problem when multiple callers
    // request the same city simultaneously
    func fetchWeather(for city: String) async throws -> WeatherData {
        // Check cache first (cross-actor call requires await)
        if let cached = await cache.get(city) {
            return cached
        }

        // Deduplicate: if a request for this city is already in flight, await it
        if let existing = inFlightRequests[city] {
            return try await existing.value
        }

        // Create new request task
        let task = Task<WeatherData, Error> {
            let url = baseURL.appendingPathComponent("current")
                .appending(queryItems: [URLQueryItem(name: "city", value: city)])
            let (data, response) = try await session.data(from: url)

            guard let http = response as? HTTPURLResponse else {
                throw WeatherError.networkFailure("Invalid response")
            }

            // Pitfall: actor reentrancy — after the await above,
            // another caller may have already populated the cache.
            // However, this is safe because we deduplicate via inFlightRequests.

            switch http.statusCode {
            case 200:
                let decoder = JSONDecoder()
                decoder.dateDecodingStrategy = .iso8601
                let weather = try decoder.decode(WeatherData.self, from: data)
                await cache.set(city, data: weather)
                return weather
            case 404:
                throw WeatherError.cityNotFound(city)
            case 429:
                let retryAfter = Double(http.value(forHTTPHeaderField: "Retry-After") ?? "60") ?? 60
                throw WeatherError.rateLimited(retryAfter: retryAfter)
            default:
                throw WeatherError.networkFailure("HTTP \(http.statusCode)")
            }
        }

        inFlightRequests[city] = task

        // Therefore, always clean up in-flight tracking regardless of success/failure
        defer { inFlightRequests.removeValue(forKey: city) }

        return try await task.value
    }

    // MARK: - Task Group: parallel fetch with partial failure handling

    func fetchWeatherBatch(cities: [String]) async -> [String: Result<WeatherData, Error>] {
        await withTaskGroup(of: (String, Result<WeatherData, Error>).self) { group in
            for city in cities {
                group.addTask {
                    do {
                        let data = try await self.fetchWeather(for: city)
                        return (city, .success(data))
                    } catch {
                        return (city, .failure(error))
                    }
                }
            }

            var results: [String: Result<WeatherData, Error>] = [:]
            for await (city, result) in group {
                results[city] = result
            }
            return results
        }
    }

    // MARK: - Throwing task group with cancellation

    func fetchAllOrFail(cities: [String]) async throws -> [WeatherData] {
        // Trade-off: withThrowingTaskGroup cancels ALL remaining children
        // if any child throws. Use this when partial results are useless.
        try await withThrowingTaskGroup(of: WeatherData.self) { group in
            for city in cities {
                group.addTask {
                    // Cooperative cancellation: check before expensive work
                    try Task.checkCancellation()
                    return try await self.fetchWeather(for: city)
                }
            }

            var allData: [WeatherData] = []
            for try await data in group {
                allData.append(data)
            }
            return allData
        }
    }
}
```

### Sendable Conformance and Data Safety

The `Sendable` protocol marks types as safe to share across concurrency domains. Value types (structs, enums) with all-Sendable stored properties are implicitly Sendable. Classes must be `final` and either immutable or use internal synchronization. The compiler enforces Sendable at actor boundaries — **therefore**, any value passed into or out of an actor must be Sendable.

## AsyncSequence for Streaming Data

`AsyncSequence` generalizes async iteration, enabling patterns like polling, server-sent events, or WebSocket streams. Combined with `for await...in`, it provides a clean syntax for consuming streaming data with built-in cancellation support.

```swift
// MARK: - AsyncSequence: Periodic Weather Polling

struct WeatherPollingSequence: AsyncSequence {
    typealias Element = WeatherData

    let city: String
    let service: WeatherService
    let interval: TimeInterval

    struct AsyncIterator: AsyncIteratorProtocol {
        let city: String
        let service: WeatherService
        let interval: TimeInterval

        mutating func next() async throws -> WeatherData? {
            // Cooperative cancellation: exit cleanly when task is cancelled
            guard !Task.isCancelled else { return nil }

            // Best practice: check cancellation AND use Task.sleep
            // (which throws CancellationError automatically)
            if interval > 0 {
                try await Task.sleep(for: .seconds(interval))
            }

            return try await service.fetchWeather(for: city)
        }
    }

    func makeAsyncIterator() -> AsyncIterator {
        AsyncIterator(city: city, service: service, interval: interval)
    }
}

// MARK: - MainActor ViewModel consuming async sequences

@MainActor
class WeatherDashboardViewModel: ObservableObject {
    @Published var cityWeather: [String: WeatherData] = [:]
    @Published var errors: [String: String] = [:]
    @Published var isLoading = false

    private let service: WeatherService
    private var pollingTasks: [String: Task<Void, Never>] = [:]

    init(service: WeatherService = WeatherService()) {
        self.service = service
    }

    func startPolling(city: String, interval: TimeInterval = 60) {
        // Cancel existing polling for this city
        pollingTasks[city]?.cancel()

        pollingTasks[city] = Task {
            let sequence = WeatherPollingSequence(
                city: city, service: service, interval: interval
            )
            do {
                for try await weather in sequence {
                    // Because we are @MainActor, this update is safe
                    self.cityWeather[city] = weather
                    self.errors.removeValue(forKey: city)
                }
            } catch is CancellationError {
                // Expected — task was cancelled, clean exit
            } catch {
                self.errors[city] = error.localizedDescription
            }
        }
    }

    func stopPolling(city: String) {
        pollingTasks[city]?.cancel()
        pollingTasks.removeValue(forKey: city)
    }

    func stopAllPolling() {
        pollingTasks.values.forEach { $0.cancel() }
        pollingTasks.removeAll()
    }

    func loadInitialData(cities: [String]) async {
        isLoading = true
        let results = await service.fetchWeatherBatch(cities: cities)
        for (city, result) in results {
            switch result {
            case .success(let data):
                cityWeather[city] = data
            case .failure(let error):
                errors[city] = error.localizedDescription
            }
        }
        isLoading = false
    }

    deinit {
        // However, deinit runs on an arbitrary thread.
        // Therefore, capture tasks locally to cancel without actor hop.
        let tasks = pollingTasks.values
        for task in tasks { task.cancel() }
    }
}
```

### Cancellation Handling Best Practices

Cooperative cancellation is a cornerstone of structured concurrency. Tasks do not forcibly terminate — they must **check** for cancellation via `Task.isCancelled` or `try Task.checkCancellation()`. **Best practice** is to check cancellation before expensive operations (network calls, disk I/O) and at loop boundaries. `Task.sleep` automatically throws `CancellationError` when cancelled, making it an ideal suspension point for polling loops.

## Summary and Key Takeaways

- **Actors** serialize access to mutable state, eliminating data races by construction. The **trade-off** is potential contention; design actors to hold minimal state and release control quickly.
- **Actor reentrancy** means state can change across `await` boundaries inside an actor. Always re-validate assumptions after suspension points.
- **Sendable** enforcement ensures data passed across isolation boundaries is safe. Prefer structs for DTOs and mark classes `@Sendable` only when truly thread-safe.
- **Task groups** (`withTaskGroup` / `withThrowingTaskGroup`) enable structured fan-out. The throwing variant cancels siblings on first failure; the non-throwing variant allows partial results.
- **AsyncSequence** is the streaming primitive for Swift concurrency. Combined with structured tasks, it supports clean polling, event streams, and cancellation.
- **MainActor** isolates ViewModel state to the main thread, making `@Published` updates safe without manual dispatch. Always annotate ViewModels with `@MainActor`.
- **Cooperative cancellation** requires explicit checks. A **pitfall** is forgetting cancellation checks in long-running loops, causing tasks to run indefinitely after the user navigates away.
"""
    ),
    (
        "swift/combine-framework-reactive-networking-operators",
        "Explain the Combine framework in depth covering publishers, subscribers, key operators like map/flatMap/tryMap, custom publishers, backpressure with Subscribers.Demand, error handling with mapError, memory management with AnyCancellable, and implement a reactive network layer with retry debounce and error recovery",
        r"""# Combine Framework Deep Dive: Reactive Networking, Operators, and Error Recovery

## Understanding the Combine Publisher-Subscriber Contract

Apple's **Combine** framework implements the Reactive Streams specification with a strongly typed twist: every publisher declares both its `Output` and `Failure` types at compile time. This is a significant advantage over RxSwift **because** type mismatches between publishers are caught at compile time rather than causing runtime crashes. **However**, this strictness introduces complexity when composing publishers with different error types — you must explicitly convert errors using `mapError` or `setFailureType`.

The core contract works as follows: a **Subscriber** requests demand from a **Publisher** via `Subscribers.Demand`. The publisher then emits at most that many values. This **backpressure** mechanism prevents unbounded buffering — a **common mistake** with RxSwift's `Observable` where producers can overwhelm consumers. **Therefore**, understanding demand is essential for building robust Combine pipelines.

### Key Operator Categories

Combine operators fall into several categories: **transforming** (`map`, `flatMap`, `compactMap`), **filtering** (`filter`, `removeDuplicates`, `debounce`), **combining** (`merge`, `combineLatest`, `zip`), **error handling** (`catch`, `retry`, `mapError`, `tryMap`), and **timing** (`throttle`, `debounce`, `delay`, `timeout`). The **best practice** is to compose small, focused operator chains rather than building monolithic pipelines.

```swift
import Combine
import Foundation

// MARK: - API Types

struct APIEndpoint {
    let path: String
    let method: String
    let queryItems: [URLQueryItem]
    let headers: [String: String]
    let body: Data?

    init(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        headers: [String: String] = [:],
        body: Data? = nil
    ) {
        self.path = path
        self.method = method
        self.queryItems = queryItems
        self.headers = headers
        self.body = body
    }
}

enum APIError: Error, LocalizedError {
    case invalidURL
    case httpError(statusCode: Int, data: Data)
    case decodingError(DecodingError)
    case networkError(URLError)
    case unauthorized
    case rateLimited(retryAfter: TimeInterval)
    case unknown(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL configuration"
        case .httpError(let code, _): return "HTTP error \(code)"
        case .decodingError(let err): return "Decoding failed: \(err.localizedDescription)"
        case .networkError(let err): return "Network error: \(err.localizedDescription)"
        case .unauthorized: return "Authentication required"
        case .rateLimited(let t): return "Rate limited, retry after \(t)s"
        case .unknown(let err): return err.localizedDescription
        }
    }
}

struct APIResponse<T: Decodable> {
    let data: T
    let statusCode: Int
    let headers: [AnyHashable: Any]
}

// MARK: - Reactive Network Layer

class NetworkClient {
    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder

    init(
        baseURL: URL,
        session: URLSession = .shared,
        decoder: JSONDecoder = {
            let d = JSONDecoder()
            d.dateDecodingStrategy = .iso8601
            d.keyDecodingStrategy = .convertFromSnakeCase
            return d
        }()
    ) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = decoder
    }

    // Core request publisher — all other methods build on this
    // Best practice: return AnyPublisher to hide implementation details
    func request<T: Decodable>(
        _ endpoint: APIEndpoint,
        as type: T.Type
    ) -> AnyPublisher<APIResponse<T>, APIError> {
        // Build URLRequest
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(endpoint.path),
            resolvingAgainstBaseURL: true
        ) else {
            return Fail(error: APIError.invalidURL).eraseToAnyPublisher()
        }

        if !endpoint.queryItems.isEmpty {
            components.queryItems = endpoint.queryItems
        }

        guard let url = components.url else {
            return Fail(error: APIError.invalidURL).eraseToAnyPublisher()
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method
        request.httpBody = endpoint.body
        for (key, value) in endpoint.headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        return session.dataTaskPublisher(for: request)
            // Map URLError to our APIError domain
            .mapError { APIError.networkError($0) }
            // Validate HTTP status code
            .tryMap { output -> (data: Data, response: HTTPURLResponse) in
                guard let http = output.response as? HTTPURLResponse else {
                    throw APIError.unknown(
                        NSError(domain: "Invalid response type", code: -1)
                    )
                }
                // Therefore, handle specific HTTP errors before decoding
                switch http.statusCode {
                case 200...299:
                    return (output.data, http)
                case 401:
                    throw APIError.unauthorized
                case 429:
                    let retryAfter = Double(
                        http.value(forHTTPHeaderField: "Retry-After") ?? "60"
                    ) ?? 60
                    throw APIError.rateLimited(retryAfter: retryAfter)
                default:
                    throw APIError.httpError(
                        statusCode: http.statusCode, data: output.data
                    )
                }
            }
            .mapError { error -> APIError in
                // Convert any stray errors to APIError
                // Pitfall: tryMap erases the Failure type to Error
                // Therefore we must mapError to restore our typed error
                if let apiErr = error as? APIError { return apiErr }
                return .unknown(error)
            }
            // Decode the response body
            .tryMap { (data, response) -> APIResponse<T> in
                do {
                    let decoded = try self.decoder.decode(T.self, from: data)
                    return APIResponse(
                        data: decoded,
                        statusCode: response.statusCode,
                        headers: response.allHeaderFields
                    )
                } catch let err as DecodingError {
                    throw APIError.decodingError(err)
                }
            }
            .mapError { ($0 as? APIError) ?? .unknown($0) }
            .eraseToAnyPublisher()
    }
}
```

## Retry, Debounce, and Error Recovery Patterns

Building production-ready networking requires handling transient failures, user input debouncing, and graceful error recovery. Combine's operator composition makes these patterns elegant but there are **pitfalls** in getting the retry scope right.

### Retry with Exponential Backoff

The built-in `.retry(n)` operator simply resubscribes to the upstream publisher on failure. **However**, it retries immediately with no delay, which is rarely what you want for network requests. A **best practice** is to build a custom retry-with-delay operator.

```swift
// MARK: - Custom Retry with Exponential Backoff

extension Publisher {
    // Best practice: custom operator for exponential backoff retry
    // Trade-off: more complex than .retry(3) but much more production-ready
    func retryWithBackoff(
        maxRetries: Int,
        initialDelay: TimeInterval = 1.0,
        multiplier: Double = 2.0,
        scheduler: some Scheduler = DispatchQueue.global()
    ) -> AnyPublisher<Output, Failure> {
        self.catch { error -> AnyPublisher<Output, Failure> in
            guard maxRetries > 0 else {
                return Fail(error: error).eraseToAnyPublisher()
            }
            // Therefore, delay then retry with decremented count
            return Just(())
                .delay(for: .seconds(initialDelay), scheduler: scheduler)
                .flatMap { _ in
                    self.retryWithBackoff(
                        maxRetries: maxRetries - 1,
                        initialDelay: initialDelay * multiplier,
                        multiplier: multiplier,
                        scheduler: scheduler
                    )
                }
                .eraseToAnyPublisher()
        }
        .eraseToAnyPublisher()
    }
}

// MARK: - Search with Debounce and Error Recovery

class SearchService {
    private let client: NetworkClient
    private var cancellables = Set<AnyCancellable>()

    // Subject acts as both publisher and subscriber — bridge from imperative to reactive
    private let searchSubject = PassthroughSubject<String, Never>()
    private let resultsSubject = CurrentValueSubject<[SearchResult], Never>([])
    private let errorSubject = PassthroughSubject<APIError, Never>()
    private let isLoadingSubject = CurrentValueSubject<Bool, Never>(false)

    // Public read-only publishers
    var results: AnyPublisher<[SearchResult], Never> { resultsSubject.eraseToAnyPublisher() }
    var errors: AnyPublisher<APIError, Never> { errorSubject.eraseToAnyPublisher() }
    var isLoading: AnyPublisher<Bool, Never> { isLoadingSubject.eraseToAnyPublisher() }

    init(client: NetworkClient) {
        self.client = client
        setupSearchPipeline()
    }

    func search(_ query: String) {
        searchSubject.send(query)
    }

    private func setupSearchPipeline() {
        searchSubject
            // Debounce: wait 300ms after user stops typing
            // Common mistake: using throttle instead of debounce for search
            // Debounce waits for silence; throttle emits at fixed intervals
            .debounce(for: .milliseconds(300), scheduler: DispatchQueue.main)
            // Remove duplicate consecutive queries
            .removeDuplicates()
            // Filter out empty/short queries
            .filter { $0.count >= 2 }
            // Show loading indicator
            .handleEvents(receiveOutput: { [weak self] _ in
                self?.isLoadingSubject.send(true)
            })
            // flatMap(maxPublishers:) controls concurrency
            // .max(1) cancels the previous request when a new query arrives
            // Trade-off: prevents stale results but may discard valid responses
            .map { [weak self] query -> AnyPublisher<[SearchResult], Never> in
                guard let self else {
                    return Just([]).eraseToAnyPublisher()
                }
                let endpoint = APIEndpoint(
                    path: "search",
                    queryItems: [URLQueryItem(name: "q", value: query)]
                )
                return self.client.request(endpoint, as: [SearchResult].self)
                    .map(\.data)
                    .retryWithBackoff(maxRetries: 2, initialDelay: 0.5)
                    // catch converts the publisher to Never failure type
                    // However, we still want to surface errors to the UI
                    .catch { [weak self] error -> Just<[SearchResult]> in
                        self?.errorSubject.send(error)
                        return Just([])
                    }
                    .eraseToAnyPublisher()
            }
            .switchToLatest()
            .receive(on: DispatchQueue.main)
            .handleEvents(receiveOutput: { [weak self] _ in
                self?.isLoadingSubject.send(false)
            })
            .sink { [weak self] results in
                self?.resultsSubject.send(results)
            }
            .store(in: &cancellables) // Pitfall: forgetting to store causes immediate cancellation
    }
}

struct SearchResult: Decodable, Identifiable {
    let id: String
    let title: String
    let snippet: String
    let relevanceScore: Double
}

// MARK: - Memory Management: AnyCancellable Patterns

class DataSyncManager {
    // Best practice: use Set<AnyCancellable> for multiple subscriptions
    private var cancellables = Set<AnyCancellable>()
    private let client: NetworkClient

    init(client: NetworkClient) {
        self.client = client
    }

    func startPeriodicSync() {
        // Timer publisher for periodic operations
        Timer.publish(every: 30, on: .main, in: .common)
            .autoconnect()
            .flatMap { [weak self] _ -> AnyPublisher<Void, Never> in
                guard let self else {
                    return Empty().eraseToAnyPublisher()
                }
                return self.performSync()
                    .catch { _ in Just(()) }
                    .eraseToAnyPublisher()
            }
            .sink { _ in }
            .store(in: &cancellables)
    }

    func stopAllSync() {
        // Cancelling all subscriptions is as simple as clearing the set
        // Because AnyCancellable calls cancel() on deinit
        cancellables.removeAll()
    }

    private func performSync() -> AnyPublisher<Void, APIError> {
        let endpoint = APIEndpoint(path: "sync", method: "POST")
        return client.request(endpoint, as: EmptyResponse.self)
            .map { _ in () }
            .eraseToAnyPublisher()
    }
}

struct EmptyResponse: Decodable {}
```

### Custom Publisher for Backpressure Control

When you need fine-grained control over emission timing and demand, you can build a custom `Publisher` and `Subscription`. This is an advanced pattern but essential for understanding how Combine works under the hood.

```swift
// MARK: - Custom Publisher: Chunked Array Publisher

// Emits array elements in chunks, respecting subscriber demand
struct ChunkedPublisher<Element>: Publisher {
    typealias Output = [Element]
    typealias Failure = Never

    let elements: [Element]
    let chunkSize: Int

    func receive<S: Subscriber>(subscriber: S)
    where S.Input == [Element], S.Failure == Never {
        let subscription = ChunkedSubscription(
            subscriber: subscriber,
            elements: elements,
            chunkSize: chunkSize
        )
        subscriber.receive(subscription: subscription)
    }
}

class ChunkedSubscription<S: Subscriber, Element>: Subscription
where S.Input == [Element], S.Failure == Never {
    private var subscriber: S?
    private let elements: [Element]
    private let chunkSize: Int
    private var currentIndex = 0

    init(subscriber: S, elements: [Element], chunkSize: Int) {
        self.subscriber = subscriber
        self.elements = elements
        self.chunkSize = chunkSize
    }

    func request(_ demand: Subscribers.Demand) {
        guard let subscriber, demand > 0 else { return }

        var emitted = 0
        var remaining = demand

        while currentIndex < elements.count, remaining > 0 {
            let end = min(currentIndex + chunkSize, elements.count)
            let chunk = Array(elements[currentIndex..<end])
            currentIndex = end

            // Therefore, respect the demand returned by receive(_:)
            let additionalDemand = subscriber.receive(chunk)
            remaining = remaining - 1 + additionalDemand
            emitted += 1
        }

        if currentIndex >= elements.count {
            subscriber.receive(completion: .finished)
        }
    }

    func cancel() {
        subscriber = nil
    }
}

// MARK: - Combining Multiple Publishers

class DashboardDataLoader {
    private let client: NetworkClient
    private var cancellables = Set<AnyCancellable>()

    init(client: NetworkClient) {
        self.client = client
    }

    // CombineLatest: emit when ANY source updates, using latest from each
    // Best practice for dashboard-style UIs with independent data sources
    func loadDashboard() -> AnyPublisher<DashboardData, APIError> {
        let userPub = client.request(
            APIEndpoint(path: "user/profile"), as: UserProfile.self
        ).map(\.data)

        let statsPub = client.request(
            APIEndpoint(path: "user/stats"), as: UserStats.self
        ).map(\.data)

        let notifPub = client.request(
            APIEndpoint(path: "notifications"), as: [Notification].self
        ).map(\.data)

        // However, combineLatest requires all publishers to have the same Failure type
        // which they do here (all APIError), so this works directly
        return Publishers.CombineLatest3(userPub, statsPub, notifPub)
            .map { profile, stats, notifications in
                DashboardData(
                    profile: profile,
                    stats: stats,
                    notifications: notifications
                )
            }
            .eraseToAnyPublisher()
    }
}

struct UserProfile: Decodable { let name: String; let email: String }
struct UserStats: Decodable { let totalPosts: Int; let followers: Int }
struct Notification: Decodable, Identifiable { let id: String; let message: String }
struct DashboardData {
    let profile: UserProfile
    let stats: UserStats
    let notifications: [Notification]
}
```

## Summary and Key Takeaways

- Combine's **typed error system** catches publisher composition mistakes at compile time, but requires explicit `mapError` calls when combining publishers with different failure types. The **trade-off** is verbosity for safety.
- **Backpressure** via `Subscribers.Demand` prevents unbounded buffering. Custom publishers must respect demand to avoid memory issues.
- **`tryMap` erases the `Failure` type** to `Error`, which is a **pitfall** that requires a subsequent `mapError` to restore typed errors.
- Use **`debounce`** for search-as-you-type (waits for silence), **`throttle`** for rate-limiting continuous events (emits at intervals). A **common mistake** is confusing these two operators.
- **`switchToLatest`** combined with `flatMap` cancels previous inner publishers, preventing stale results from overwriting fresh ones in search scenarios.
- **AnyCancellable** must be stored — letting it go out of scope immediately cancels the subscription. **Best practice** is `Set<AnyCancellable>` with `.store(in:)`.
- Use `.retry()` sparingly and prefer custom exponential backoff **because** immediate retries can overwhelm servers and waste bandwidth.
- Combine and async/await coexist well: use `values` property on any publisher to bridge to `AsyncSequence`.
"""
    ),
    (
        "swift/protocol-oriented-programming-type-erasure",
        "Explain Swift protocol-oriented programming in depth including protocol extensions with default implementations, associated types with constraints, type erasure patterns using AnyPublisher-style wrappers, opaque return types with some keyword, existential types with any keyword, and implement a plugin architecture with full type safety",
        r"""# Swift Protocol-Oriented Programming: Extensions, Type Erasure, and Plugin Architectures

## Protocols as the Foundation of Swift Design

Swift is often described as a **protocol-oriented** language — a design philosophy Apple articulated at WWDC 2015. Unlike class-based inheritance where you build taxonomies top-down, protocol-oriented programming (POP) builds capabilities bottom-up. You define small, focused protocols and compose them via conformance and extension. This matters **because** it avoids the fragile base class problem, enables value-type polymorphism, and allows retroactive conformance on types you don't own.

**However**, protocols with associated types (PATs) introduce significant complexity. They cannot be used as existential types directly (before Swift 5.7), leading to the need for **type erasure**. Understanding when to use `some Protocol` (opaque types), `any Protocol` (existential types), and manual type-erased wrappers is essential for writing idiomatic Swift.

### Protocol Extensions and Default Implementations

Protocol extensions let you provide default method implementations without inheritance. **Best practice** is to put behavioral defaults in extensions and keep the protocol declaration itself minimal — only require what truly varies across conforming types.

```swift
import Foundation

// MARK: - Core Plugin Protocol Hierarchy

// Minimal protocol — only what MUST vary per conforming type
protocol Plugin: Identifiable, Sendable {
    associatedtype Configuration: Codable & Sendable
    associatedtype Output: Sendable

    var id: String { get }
    var name: String { get }
    var version: String { get }

    // Only these two methods MUST be implemented by conformers
    func configure(with config: Configuration) throws
    func execute(input: Data) async throws -> Output
}

// Default implementations via protocol extension
// Best practice: put shared behavior here, not in a base class
extension Plugin {
    var description: String {
        "\(name) v\(version) [id: \(id)]"
    }

    // Therefore, conformers get logging for free but can override
    func executeWithLogging(input: Data) async throws -> Output {
        let start = Date()
        print("[\(name)] Starting execution...")
        let result = try await execute(input: input)
        let elapsed = Date().timeIntervalSince(start)
        print("[\(name)] Completed in \(String(format: "%.3f", elapsed))s")
        return result
    }
}

// MARK: - Protocol Composition and Refinement

// Pitfall: don't create deep protocol hierarchies — compose instead
protocol Configurable {
    associatedtype Configuration: Codable & Sendable
    var currentConfig: Configuration? { get }
    func configure(with config: Configuration) throws
}

protocol HealthCheckable {
    func healthCheck() async -> HealthStatus
}

enum HealthStatus: String, Sendable {
    case healthy
    case degraded
    case unhealthy
}

protocol LifecycleManaged {
    func start() async throws
    func stop() async throws
    var isRunning: Bool { get }
}

// Compose protocols to build rich capability sets
// Trade-off: more protocols = more flexibility but more conformance boilerplate
protocol ManagedPlugin: Plugin, HealthCheckable, LifecycleManaged {}

// Default implementation for health check based on lifecycle state
extension ManagedPlugin {
    func healthCheck() async -> HealthStatus {
        isRunning ? .healthy : .unhealthy
    }
}
```

## Associated Types and Constraints

**Associated types** make protocols generic — they define placeholder types that conformers specify. Unlike generic parameters on the protocol itself (which Swift doesn't support), associated types let each conforming type choose its own concrete types while maintaining the protocol contract.

The **trade-off** is that protocols with associated types cannot be used as existential types in many contexts. `let plugins: [Plugin]` doesn't compile **because** the compiler doesn't know what `Configuration` and `Output` are. This is where type erasure becomes necessary.

```swift
// MARK: - Concrete Plugin Implementations

struct ImageProcessorConfig: Codable, Sendable {
    var maxWidth: Int
    var maxHeight: Int
    var quality: Double
    var format: String
}

struct ProcessedImage: Sendable {
    let data: Data
    let width: Int
    let height: Int
    let format: String
}

// Concrete plugin with specific associated types
class ImageProcessorPlugin: ManagedPlugin {
    typealias Configuration = ImageProcessorConfig
    typealias Output = ProcessedImage

    let id: String
    let name = "ImageProcessor"
    let version = "2.1.0"
    private(set) var isRunning = false
    private(set) var currentConfig: ImageProcessorConfig?

    init(id: String = UUID().uuidString) {
        self.id = id
    }

    func configure(with config: ImageProcessorConfig) throws {
        guard config.quality > 0 && config.quality <= 1.0 else {
            throw PluginError.invalidConfiguration("Quality must be 0..1")
        }
        currentConfig = config
    }

    func execute(input: Data) async throws -> ProcessedImage {
        guard let config = currentConfig else {
            throw PluginError.notConfigured
        }
        guard isRunning else {
            throw PluginError.notRunning
        }
        // Simulate image processing
        try await Task.sleep(for: .milliseconds(100))
        return ProcessedImage(
            data: input, width: config.maxWidth,
            height: config.maxHeight, format: config.format
        )
    }

    func start() async throws { isRunning = true }
    func stop() async throws { isRunning = false }
}

struct TextAnalysisConfig: Codable, Sendable {
    var language: String
    var maxTokens: Int
}

struct TextAnalysisResult: Sendable {
    let sentiment: Double
    let keywords: [String]
    let summary: String
}

class TextAnalysisPlugin: ManagedPlugin {
    typealias Configuration = TextAnalysisConfig
    typealias Output = TextAnalysisResult

    let id: String
    let name = "TextAnalysis"
    let version = "1.3.0"
    private(set) var isRunning = false
    private(set) var currentConfig: TextAnalysisConfig?

    init(id: String = UUID().uuidString) {
        self.id = id
    }

    func configure(with config: TextAnalysisConfig) throws {
        currentConfig = config
    }

    func execute(input: Data) async throws -> TextAnalysisResult {
        guard isRunning else { throw PluginError.notRunning }
        let text = String(data: input, encoding: .utf8) ?? ""
        return TextAnalysisResult(
            sentiment: 0.75, keywords: ["swift", "protocol"],
            summary: String(text.prefix(100))
        )
    }

    func start() async throws { isRunning = true }
    func stop() async throws { isRunning = false }
}

enum PluginError: Error, LocalizedError {
    case invalidConfiguration(String)
    case notConfigured
    case notRunning
    case pluginNotFound(String)
    case executionFailed(String)

    var errorDescription: String? {
        switch self {
        case .invalidConfiguration(let msg): return "Invalid config: \(msg)"
        case .notConfigured: return "Plugin not configured"
        case .notRunning: return "Plugin not running"
        case .pluginNotFound(let id): return "Plugin \(id) not found"
        case .executionFailed(let msg): return "Execution failed: \(msg)"
        }
    }
}
```

### Type Erasure: The AnyPlugin Pattern

**Type erasure** hides the associated types behind a uniform interface, allowing heterogeneous collections. The pattern wraps a concrete conformer in a box that forwards calls through closures or an internal protocol. This is the same technique Apple uses for `AnyPublisher`, `AnySequence`, and `AnyHashable`.

```swift
// MARK: - Type Erasure via Closure Boxing

// Because Plugin has associated types, we can't write [any Plugin] and call execute
// Therefore, we erase the specific Configuration and Output types
// The type-erased wrapper works with Data in / Data out

struct AnyPlugin: Identifiable, Sendable {
    let id: String
    let name: String
    let version: String

    private let _execute: @Sendable (Data) async throws -> Data
    private let _healthCheck: @Sendable () async -> HealthStatus
    private let _start: @Sendable () async throws -> Void
    private let _stop: @Sendable () async throws -> Void

    // Generic initializer captures the concrete type
    init<P: ManagedPlugin>(_ plugin: P, encoder: JSONEncoder = JSONEncoder())
    where P.Output: Encodable {
        self.id = plugin.id
        self.name = plugin.name
        self.version = plugin.version

        // Closures capture the concrete plugin and erase associated types
        _execute = { input in
            let output = try await plugin.execute(input: input)
            return try encoder.encode(output)
        }
        _healthCheck = { await plugin.healthCheck() }
        _start = { try await plugin.start() }
        _stop = { try await plugin.stop() }
    }

    func execute(input: Data) async throws -> Data {
        try await _execute(input)
    }

    func healthCheck() async -> HealthStatus {
        await _healthCheck()
    }

    func start() async throws { try await _start() }
    func stop() async throws { try await _stop() }
}

// MARK: - Opaque Return Types (some Protocol) vs Existential (any Protocol)

// `some Plugin` — opaque type: caller doesn't know the concrete type,
// but the compiler does. Enables optimizations and preserves associated types.
// Best practice: use `some` for return types when the concrete type is fixed

func makeImagePlugin() -> some ManagedPlugin {
    // However, the concrete type is fixed — every call returns ImageProcessorPlugin
    ImageProcessorPlugin()
}

// `any Protocol` (Swift 5.7+) — existential type: runtime polymorphism
// Trade-off: existentials have boxing overhead and erase associated types
// Therefore, prefer `some` when you can, `any` when you need heterogeneity

func allPluginNames(plugins: [any HealthCheckable & LifecycleManaged]) -> [HealthStatus] {
    // Common mistake: trying to access associated types through existentials
    // This only works because HealthCheckable has no associated types
    []
}

// MARK: - Plugin Registry and Manager

actor PluginManager {
    private var plugins: [String: AnyPlugin] = [:]

    func register(_ plugin: AnyPlugin) {
        plugins[plugin.id] = plugin
    }

    func unregister(id: String) {
        plugins.removeValue(forKey: id)
    }

    func get(id: String) -> AnyPlugin? {
        plugins[id]
    }

    var allPlugins: [AnyPlugin] {
        Array(plugins.values)
    }

    func startAll() async {
        for (_, plugin) in plugins {
            do {
                try await plugin.start()
                print("Started \(plugin.name)")
            } catch {
                print("Failed to start \(plugin.name): \(error)")
            }
        }
    }

    func stopAll() async {
        for (_, plugin) in plugins {
            do {
                try await plugin.stop()
            } catch {
                print("Failed to stop \(plugin.name): \(error)")
            }
        }
    }

    func healthReport() async -> [String: HealthStatus] {
        var report: [String: HealthStatus] = [:]
        for (id, plugin) in plugins {
            report[id] = await plugin.healthCheck()
        }
        return report
    }

    func execute(pluginID: String, input: Data) async throws -> Data {
        guard let plugin = plugins[pluginID] else {
            throw PluginError.pluginNotFound(pluginID)
        }
        return try await plugin.execute(input: input)
    }
}

// MARK: - Pipeline: Chaining plugins with protocol composition

struct PluginPipeline {
    private var steps: [(id: String, transform: (Data) -> Data)]
    private let manager: PluginManager

    init(manager: PluginManager) {
        self.manager = manager
        self.steps = []
    }

    mutating func addStep(pluginID: String) {
        steps.append((pluginID, { $0 }))
    }

    func run(input: Data) async throws -> Data {
        var current = input
        for step in steps {
            current = try await manager.execute(pluginID: step.id, input: current)
        }
        return current
    }
}
```

## Choosing Between some, any, and Type Erasure

The decision tree is straightforward: use `some` when the concrete type is determined at compile time and doesn't need to vary. Use `any` when you need heterogeneous collections but don't access associated types. Use manual type erasure (like `AnyPlugin`) when you need heterogeneous collections **and** must call methods that involve associated types. The **trade-off** is complexity: `some` is simplest and most performant, `any` adds boxing overhead, and manual erasure adds implementation overhead.

## Summary and Key Takeaways

- **Protocol extensions** provide default implementations without inheritance, enabling code reuse across value types and reference types alike. The **best practice** is to keep protocol requirements minimal and put shared behavior in extensions.
- **Associated types** make protocols generic but prevent direct use as existential types. **Therefore**, design protocols to minimize associated type exposure in public API surfaces.
- **Type erasure** (the `AnyPlugin` pattern) uses closures to hide associated types behind a uniform interface. This is the same pattern Apple uses for `AnyPublisher` and `AnySequence`.
- **`some Protocol`** (opaque types) preserves type identity and enables compiler optimizations. Use it for return types when the concrete type is fixed. A **common mistake** is using `any` when `some` would suffice.
- **`any Protocol`** (existential types) enables runtime polymorphism with boxing overhead. Since Swift 5.7, you can use `any` explicitly to signal intent.
- **Protocol composition** (`ManagedPlugin: Plugin, HealthCheckable, LifecycleManaged`) is preferred over deep protocol hierarchies. The **pitfall** of deep hierarchies is rigid coupling and difficulty in partial conformance.
- For plugin architectures, combine **actor isolation** (for thread-safe registration) with **type erasure** (for heterogeneous storage) and **protocol composition** (for capability-based design).
"""
    ),
    (
        "swift/coredata-swiftdata-persistence-migration-cloudkit",
        "Explain CoreData and SwiftData persistence patterns including NSManagedObjectContext threading rules, NSFetchedResultsController for efficient UI binding, lightweight and heavyweight migration strategies, CloudKit sync setup, and implement a complete persistence layer with CRUD operations background contexts and migration support",
        r"""# CoreData and SwiftData Persistence: Threading, Migrations, and CloudKit Sync

## CoreData Architecture Fundamentals

**CoreData** is Apple's object-graph persistence framework — it is **not** a database, although it typically uses SQLite as its backing store. Understanding this distinction matters **because** CoreData manages an in-memory object graph with change tracking, undo support, and relationship management, features that go far beyond simple SQL queries. The persistence layer (the `NSPersistentStore`) is an implementation detail that CoreData abstracts away.

The most critical concept is the **managed object context** (`NSManagedObjectContext`). Every `NSManagedObject` is registered with exactly one context, and **contexts are not thread-safe**. Accessing a managed object from a thread other than its context's thread is a guaranteed data corruption bug — one of the most **common mistakes** in CoreData development. **Therefore**, CoreData provides two mechanisms for multi-threaded access: child contexts and `perform`/`performAndWait` blocks.

### NSPersistentContainer Setup

`NSPersistentContainer` (iOS 10+) encapsulates the Core Data stack — the model, the persistent store coordinator, and the main-queue context. **Best practice** is to configure it once at app launch and inject it into your persistence layer.

```swift
import CoreData
import SwiftUI
import CloudKit

// MARK: - Persistent Container Configuration

class PersistenceController {
    static let shared = PersistenceController()

    let container: NSPersistentCloudKitContainer

    // Main-queue context for UI reads
    var viewContext: NSManagedObjectContext {
        container.viewContext
    }

    // Because CloudKit sync requires NSPersistentCloudKitContainer,
    // we use that subclass even if CloudKit is disabled initially
    init(inMemory: Bool = false) {
        container = NSPersistentCloudKitContainer(name: "AppModel")

        if inMemory {
            // Best practice: in-memory store for previews and tests
            let description = NSPersistentStoreDescription()
            description.type = NSInMemoryStoreType
            container.persistentStoreDescriptions = [description]
        } else {
            guard let description = container.persistentStoreDescriptions.first else {
                fatalError("No persistent store descriptions found")
            }

            // CloudKit configuration
            description.cloudKitContainerOptions = NSPersistentCloudKitContainerOptions(
                containerIdentifier: "iCloud.com.example.myapp"
            )

            // Trade-off: remote change notifications enable reactive UI updates
            // but add complexity to change merging
            description.setOption(
                true as NSNumber,
                forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey
            )

            // Enable persistent history tracking (required for CloudKit)
            description.setOption(
                true as NSNumber,
                forKey: NSPersistentHistoryTrackingKey
            )
        }

        container.loadPersistentStores { description, error in
            if let error = error as NSError? {
                // Pitfall: fatalError in production is wrong here
                // However, for initial setup, surface the error clearly
                print("CoreData load error: \(error), \(error.userInfo)")
            }
        }

        // Automatically merge changes from background contexts
        container.viewContext.automaticallyMergesChangesFromParent = true
        // Therefore, UI updates happen automatically when background saves complete
        container.viewContext.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
    }

    // Best practice: dedicated background context for write operations
    func newBackgroundContext() -> NSManagedObjectContext {
        let context = container.newBackgroundContext()
        context.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        return context
    }

    // Convenience for performing background work
    func performBackgroundTask<T: Sendable>(
        _ block: @escaping (NSManagedObjectContext) throws -> T
    ) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            let context = newBackgroundContext()
            context.perform {
                do {
                    let result = try block(context)
                    if context.hasChanges {
                        try context.save()
                    }
                    continuation.resume(returning: result)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    // Preview helper for SwiftUI Previews
    static var preview: PersistenceController = {
        let controller = PersistenceController(inMemory: true)
        let context = controller.viewContext
        // Populate sample data
        for i in 0..<10 {
            let task = TaskItem(context: context)
            task.id = UUID()
            task.title = "Sample Task \(i)"
            task.createdAt = Date()
            task.isCompleted = i % 3 == 0
            task.priority = Int16(i % 4)
        }
        try? context.save()
        return controller
    }()
}
```

## CRUD Operations with Background Contexts

All write operations should occur on background contexts to avoid blocking the main thread. This is a **best practice** that prevents UI jank, especially when saving large changesets. The view context should be read-only for the UI.

```swift
// MARK: - Repository Pattern for CRUD Operations

// Because NSManagedObject is not Sendable, we use a DTO for cross-context transfer
struct TaskDTO: Identifiable, Sendable {
    let id: UUID
    var title: String
    var notes: String
    var isCompleted: Bool
    var priority: Int
    var dueDate: Date?
    var createdAt: Date
    var updatedAt: Date

    // Common mistake: exposing NSManagedObject to the view layer
    // Therefore, always convert to DTOs at the repository boundary
}

// Extension on the managed object for DTO conversion
// (Assume TaskItem is generated from the .xcdatamodeld)
extension TaskItem {
    func toDTO() -> TaskDTO {
        TaskDTO(
            id: id ?? UUID(),
            title: title ?? "",
            notes: notes ?? "",
            isCompleted: isCompleted,
            priority: Int(priority),
            dueDate: dueDate,
            createdAt: createdAt ?? Date(),
            updatedAt: updatedAt ?? Date()
        )
    }

    func update(from dto: TaskDTO) {
        title = dto.title
        notes = dto.notes
        isCompleted = dto.isCompleted
        priority = Int16(dto.priority)
        dueDate = dto.dueDate
        updatedAt = Date()
    }
}

class TaskRepository {
    private let persistence: PersistenceController

    init(persistence: PersistenceController = .shared) {
        self.persistence = persistence
    }

    // MARK: - Create

    func createTask(title: String, notes: String = "", priority: Int = 0, dueDate: Date? = nil) async throws -> TaskDTO {
        try await persistence.performBackgroundTask { context in
            let task = TaskItem(context: context)
            task.id = UUID()
            task.title = title
            task.notes = notes
            task.priority = Int16(priority)
            task.dueDate = dueDate
            task.isCompleted = false
            task.createdAt = Date()
            task.updatedAt = Date()
            // Save happens automatically in performBackgroundTask
            return task.toDTO()
        }
    }

    // MARK: - Read (on viewContext for UI)

    func fetchAll(sortedBy keyPath: String = "createdAt", ascending: Bool = false) -> [TaskDTO] {
        let request = TaskItem.fetchRequest()
        request.sortDescriptors = [NSSortDescriptor(key: keyPath, ascending: ascending)]
        do {
            let results = try persistence.viewContext.fetch(request)
            return results.map { $0.toDTO() }
        } catch {
            print("Fetch error: \(error)")
            return []
        }
    }

    func fetch(id: UUID) -> TaskDTO? {
        let request = TaskItem.fetchRequest()
        request.predicate = NSPredicate(format: "id == %@", id as CVarArg)
        request.fetchLimit = 1
        return try? persistence.viewContext.fetch(request).first?.toDTO()
    }

    // MARK: - Update

    func updateTask(_ dto: TaskDTO) async throws {
        try await persistence.performBackgroundTask { context in
            let request = TaskItem.fetchRequest()
            request.predicate = NSPredicate(format: "id == %@", dto.id as CVarArg)
            request.fetchLimit = 1

            guard let task = try context.fetch(request).first else {
                throw PersistenceError.notFound(dto.id)
            }
            task.update(from: dto)
        }
    }

    // MARK: - Delete

    func deleteTask(id: UUID) async throws {
        try await persistence.performBackgroundTask { context in
            let request = TaskItem.fetchRequest()
            request.predicate = NSPredicate(format: "id == %@", id as CVarArg)
            request.fetchLimit = 1

            guard let task = try context.fetch(request).first else {
                throw PersistenceError.notFound(id)
            }
            context.delete(task)
        }
    }

    // Batch delete for efficiency
    func deleteCompleted() async throws {
        try await persistence.performBackgroundTask { context in
            let request = NSBatchDeleteRequest(
                fetchRequest: {
                    let fr = TaskItem.fetchRequest()
                    fr.predicate = NSPredicate(format: "isCompleted == YES")
                    return fr as! NSFetchRequest<NSFetchRequestResult>
                }()
            )
            // Best practice: merge batch delete changes into viewContext
            request.resultType = .resultTypeObjectIDs
            let result = try context.execute(request) as? NSBatchDeleteResult
            let objectIDs = result?.result as? [NSManagedObjectID] ?? []

            // Therefore, manually merge batch changes since they bypass the context
            NSManagedObjectContext.mergeChanges(
                fromRemoteContextSave: [NSDeletedObjectsKey: objectIDs],
                into: [self.persistence.viewContext]
            )
        }
    }
}

enum PersistenceError: Error, LocalizedError {
    case notFound(UUID)
    case saveFailed(Error)
    case migrationFailed(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let id): return "Object with id \(id) not found"
        case .saveFailed(let err): return "Save failed: \(err.localizedDescription)"
        case .migrationFailed(let msg): return "Migration failed: \(msg)"
        }
    }
}
```

### NSFetchedResultsController for Efficient UI Binding

`NSFetchedResultsController` monitors a fetch request and notifies its delegate of changes — insertions, deletions, updates, and moves. This is far more efficient than re-fetching the entire dataset **because** it leverages CoreData's change tracking to deliver granular diffs. For SwiftUI, wrapping it in an `ObservableObject` bridges the delegate-based API to the reactive world.

```swift
// MARK: - FetchedResultsController Wrapper for SwiftUI

@MainActor
class FetchedResultsObserver<T: NSManagedObject>: NSObject,
    ObservableObject, NSFetchedResultsControllerDelegate {

    @Published var items: [T] = []
    @Published var sections: [NSFetchedResultsSectionInfo] = []

    private let controller: NSFetchedResultsController<T>

    init(
        fetchRequest: NSFetchRequest<T>,
        context: NSManagedObjectContext,
        sectionKeyPath: String? = nil
    ) {
        controller = NSFetchedResultsController(
            fetchRequest: fetchRequest,
            managedObjectContext: context,
            sectionNameKeyPath: sectionKeyPath,
            cacheName: nil // Pitfall: caches cause crashes if fetch request changes
        )
        super.init()
        controller.delegate = self

        do {
            try controller.performFetch()
            items = controller.fetchedObjects ?? []
            sections = controller.sections ?? []
        } catch {
            print("FetchedResults error: \(error)")
        }
    }

    // NSFetchedResultsControllerDelegate
    nonisolated func controllerDidChangeContent(
        _ controller: NSFetchedResultsController<any NSFetchRequestResult>
    ) {
        // However, delegate callbacks may arrive on any thread
        // Therefore, dispatch to main actor for @Published updates
        Task { @MainActor in
            self.items = (controller.fetchedObjects as? [T]) ?? []
            self.sections = controller.sections ?? []
        }
    }
}

// MARK: - SwiftUI View Using FetchedResultsObserver

struct TaskListView: View {
    @StateObject private var observer: FetchedResultsObserver<TaskItem>
    @StateObject private var viewModel: TaskListViewModel

    init(persistence: PersistenceController = .shared) {
        let request = TaskItem.fetchRequest()
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \TaskItem.priority, ascending: false),
            NSSortDescriptor(keyPath: \TaskItem.createdAt, ascending: false)
        ]
        _observer = StateObject(wrappedValue: FetchedResultsObserver(
            fetchRequest: request,
            context: persistence.viewContext
        ))
        _viewModel = StateObject(wrappedValue: TaskListViewModel(
            repository: TaskRepository(persistence: persistence)
        ))
    }

    var body: some View {
        List {
            ForEach(observer.items) { task in
                TaskRowView(task: task)
            }
            .onDelete { offsets in
                let ids = offsets.compactMap { observer.items[$0].id }
                Task {
                    for id in ids {
                        try? await viewModel.delete(id: id)
                    }
                }
            }
        }
    }
}

struct TaskRowView: View {
    @ObservedObject var task: TaskItem
    var body: some View {
        HStack {
            Image(systemName: task.isCompleted ? "checkmark.circle.fill" : "circle")
            Text(task.title ?? "Untitled")
            Spacer()
            if task.priority > 2 {
                Text("HIGH").font(.caption).foregroundStyle(.red)
            }
        }
    }
}

@MainActor
class TaskListViewModel: ObservableObject {
    private let repository: TaskRepository
    init(repository: TaskRepository) { self.repository = repository }
    func delete(id: UUID) async throws { try await repository.deleteTask(id: id) }
}
```

## Migration Strategies

CoreData supports two migration approaches: **lightweight** (automatic) and **heavyweight** (custom mapping models). **Best practice** is to design your schema changes to qualify for lightweight migration wherever possible **because** heavyweight migrations are complex, error-prone, and slow on large datasets.

Lightweight migration handles: adding/removing attributes, adding/removing entities, renaming (with a renaming identifier), making attributes optional/required (with defaults), and adding/removing relationships. **However**, it cannot handle: changing attribute types, splitting entities, or complex data transformations. **Therefore**, plan your schema evolution carefully.

### CloudKit Sync Considerations

`NSPersistentCloudKitContainer` adds automatic CloudKit sync, but imposes constraints. All attributes must be optional (CloudKit records have no concept of required fields), you cannot use unique constraints, and ordered relationships are not supported. The **trade-off** is simplicity of setup versus flexibility of schema design. A **common mistake** is enabling CloudKit sync after designing a schema with required fields and unique constraints, forcing a disruptive migration.

## Summary and Key Takeaways

- **NSManagedObjectContext is not thread-safe**. Always use `perform`/`performAndWait` or create dedicated background contexts for off-main-thread work. A **common mistake** is passing managed objects between threads.
- **Background contexts** should handle all write operations to avoid blocking the UI. The repository pattern with DTOs provides a clean boundary between CoreData and the view layer.
- **NSFetchedResultsController** provides granular change notifications, making it far more efficient than polling or re-fetching. Wrap it in an `ObservableObject` for SwiftUI integration.
- **Lightweight migration** is the **best practice** for schema evolution — it handles most common changes automatically. Design schemas with migration in mind from day one.
- **CloudKit sync** via `NSPersistentCloudKitContainer` requires persistent history tracking, optional attributes, and no unique constraints. The **trade-off** is seamless sync versus schema restrictions.
- **Batch operations** (`NSBatchDeleteRequest`, `NSBatchUpdateRequest`) bypass the context for performance but require manual change merging — a **pitfall** that causes stale UI if forgotten.
- **SwiftData** (iOS 17+) simplifies the stack with `@Model` macros and `ModelContainer`, but CoreData remains essential for apps supporting older iOS versions and for advanced features like sectioned fetch results.
"""
    ),
]
