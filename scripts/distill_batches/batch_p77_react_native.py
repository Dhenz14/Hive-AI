"""Mobile development — React Native patterns and Flutter basics."""

PAIRS = [
    (
        "mobile/react-native-patterns",
        "Show React Native patterns: navigation, state management, platform-specific code, and performance.",
        """React Native patterns:

```typescript
// --- Navigation with React Navigation ---

import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

// Type-safe navigation params
type RootStackParams = {
  Home: undefined;
  Profile: { userId: string };
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParams>();
const Tab = createBottomTabNavigator();

function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Home">
        <Stack.Screen name="Home" component={HomeScreen} />
        <Stack.Screen
          name="Profile"
          component={ProfileScreen}
          options={({ route }) => ({ title: route.params.userId })}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}


// --- Typed navigation hook ---

import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

type ProfileNavProp = NativeStackNavigationProp<RootStackParams, 'Profile'>;
type ProfileRouteProp = RouteProp<RootStackParams, 'Profile'>;

function ProfileScreen() {
  const navigation = useNavigation<ProfileNavProp>();
  const route = useRoute<ProfileRouteProp>();
  const { userId } = route.params;

  return (
    <View style={styles.container}>
      <Text>User: {userId}</Text>
      <Button
        title="Go to Settings"
        onPress={() => navigation.navigate('Settings')}
      />
    </View>
  );
}


// --- Platform-specific code ---

import { Platform, StyleSheet } from 'react-native';

const styles = StyleSheet.create({
  container: {
    paddingTop: Platform.OS === 'ios' ? 44 : 0,
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 4 },
    }),
  },
});

// Platform-specific files: Button.ios.tsx / Button.android.tsx
// import Button from './Button'; // auto-resolves per platform


// --- FlatList with performance optimization ---

import { FlatList, View, Text } from 'react-native';
import { memo, useCallback } from 'react';

interface User { id: string; name: string; email: string }

const UserItem = memo(({ user }: { user: User }) => (
  <View style={styles.item}>
    <Text>{user.name}</Text>
    <Text>{user.email}</Text>
  </View>
));

function UserList({ users }: { users: User[] }) {
  const renderItem = useCallback(
    ({ item }: { item: User }) => <UserItem user={item} />,
    [],
  );

  const keyExtractor = useCallback((item: User) => item.id, []);

  return (
    <FlatList
      data={users}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      // Performance optimizations
      removeClippedSubviews={true}
      maxToRenderPerBatch={10}
      windowSize={5}
      initialNumToRender={10}
      getItemLayout={(_, index) => ({
        length: 72, offset: 72 * index, index,
      })}
    />
  );
}


// --- Custom hook for API calls ---

import { useState, useEffect } from 'react';

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

function useApi<T>(url: string): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [trigger, setTrigger] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetch(url)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(json => { if (!cancelled) setData(json); })
      .catch(err => { if (!cancelled) setError(err); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [url, trigger]);

  const refetch = useCallback(() => setTrigger(t => t + 1), []);
  return { data, loading, error, refetch };
}
```

React Native patterns:
1. **Type-safe navigation** — typed params prevent runtime route errors
2. **`Platform.select()`** — platform-specific styles without file splitting
3. **`memo` + `useCallback`** — prevent FlatList re-renders
4. **`getItemLayout`** — skip measurement for fixed-height items (faster scroll)
5. **Cancellable fetches** — cleanup prevents setState on unmounted components"""
    ),
    (
        "mobile/flutter-basics",
        "Show Flutter patterns: widgets, state management, navigation, and platform channels.",
        """Flutter widget and state patterns:

```dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// --- Stateless widget ---

class UserCard extends StatelessWidget {
  final String name;
  final String email;
  final VoidCallback? onTap;

  const UserCard({
    super.key,
    required this.name,
    required this.email,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(child: Text(name[0])),
        title: Text(name),
        subtitle: Text(email),
        onTap: onTap,
      ),
    );
  }
}


// --- Stateful widget with lifecycle ---

class CounterPage extends StatefulWidget {
  const CounterPage({super.key});

  @override
  State<CounterPage> createState() => _CounterPageState();
}

class _CounterPageState extends State<CounterPage> {
  int _count = 0;

  @override
  void initState() {
    super.initState();
    // Initialize resources
  }

  @override
  void dispose() {
    // Clean up controllers, subscriptions
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Counter')),
      body: Center(
        child: Text('Count: $_count', style: Theme.of(context).textTheme.headlineMedium),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => setState(() => _count++),
        child: const Icon(Icons.add),
      ),
    );
  }
}


// --- State management with ChangeNotifier + Provider ---

class CartModel extends ChangeNotifier {
  final List<String> _items = [];

  List<String> get items => List.unmodifiable(_items);
  int get count => _items.length;

  void add(String item) {
    _items.add(item);
    notifyListeners();
  }

  void remove(String item) {
    _items.remove(item);
    notifyListeners();
  }
}

// In widget tree:
// ChangeNotifierProvider(
//   create: (_) => CartModel(),
//   child: Consumer<CartModel>(
//     builder: (context, cart, child) => Text('Items: ${cart.count}'),
//   ),
// )


// --- Navigation with GoRouter ---

// final router = GoRouter(
//   routes: [
//     GoRoute(path: '/', builder: (_, __) => const HomePage()),
//     GoRoute(
//       path: '/user/:id',
//       builder: (_, state) => UserPage(id: state.pathParameters['id']!),
//     ),
//   ],
// );
// MaterialApp.router(routerConfig: router)


// --- Async data loading ---

class UserListPage extends StatelessWidget {
  const UserListPage({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<User>>(
      future: fetchUsers(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text('Error: ${snapshot.error}'));
        }
        final users = snapshot.data!;
        return ListView.builder(
          itemCount: users.length,
          itemBuilder: (context, index) => UserCard(
            name: users[index].name,
            email: users[index].email,
          ),
        );
      },
    );
  }
}


// --- Platform channel (call native code) ---

class BatteryLevel {
  static const _channel = MethodChannel('com.app/battery');

  static Future<int> getBatteryLevel() async {
    final level = await _channel.invokeMethod<int>('getBatteryLevel');
    return level ?? -1;
  }
}
```

Flutter patterns:
1. **`const` constructors** — compile-time constant widgets skip rebuilds
2. **`ChangeNotifier`** — simple reactive state with Provider
3. **`FutureBuilder`** — declarative async data loading in widget tree
4. **`GoRouter`** — declarative URL-based navigation with path parameters
5. **`MethodChannel`** — bridge to native iOS/Android code for platform APIs"""
    ),
    (
        "frontend/pwa-patterns",
        "Show Progressive Web App patterns: service workers, caching strategies, offline support, and installability.",
        """Progressive Web App patterns:

```javascript
// --- Service Worker registration ---

// main.js
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js', {
        scope: '/',
      });
      console.log('SW registered:', reg.scope);

      // Check for updates
      reg.addEventListener('updatefound', () => {
        const newWorker = reg.installing;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'activated') {
            // New version available — prompt user to refresh
            showUpdateBanner();
          }
        });
      });
    } catch (err) {
      console.error('SW registration failed:', err);
    }
  });
}


// --- Service Worker (sw.js) ---

const CACHE_NAME = 'app-v2';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/offline.html',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting(); // Activate immediately
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim(); // Take control of open pages
});


// --- Caching strategies ---

// Strategy 1: Cache First (static assets)
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
  }
  return response;
}

// Strategy 2: Network First (API data)
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response('Offline', { status: 503 });
  }
}

// Strategy 3: Stale While Revalidate (semi-dynamic content)
async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  });

  return cached || fetchPromise;
}

// Route requests to strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
  } else if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
  } else {
    event.respondWith(staleWhileRevalidate(request));
  }
});


// --- Web App Manifest (manifest.json) ---

// {
//   "name": "My App",
//   "short_name": "App",
//   "start_url": "/",
//   "display": "standalone",
//   "background_color": "#ffffff",
//   "theme_color": "#1976d2",
//   "icons": [
//     { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
//     { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
//   ]
// }


// --- Background sync (retry failed requests) ---

// In main app:
async function saveData(data) {
  try {
    await fetch('/api/save', { method: 'POST', body: JSON.stringify(data) });
  } catch {
    // Queue for background sync
    const reg = await navigator.serviceWorker.ready;
    await reg.sync.register('sync-save');
    // Store data in IndexedDB for later
    await storeInIDB('pending-saves', data);
  }
}

// In service worker:
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-save') {
    event.waitUntil(retrySaves());
  }
});

async function retrySaves() {
  const pending = await getFromIDB('pending-saves');
  for (const data of pending) {
    await fetch('/api/save', { method: 'POST', body: JSON.stringify(data) });
    await removeFromIDB('pending-saves', data.id);
  }
}
```

PWA patterns:
1. **Cache First** — serve static assets from cache, fall back to network
2. **Network First** — try network for fresh data, fall back to cache offline
3. **Stale While Revalidate** — serve cached immediately, update in background
4. **Background Sync** — retry failed requests when connectivity returns
5. **`skipWaiting()` + `clients.claim()`** — activate new SW version immediately"""
    ),
]
