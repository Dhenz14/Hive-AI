"""Geospatial databases — PostGIS queries, spatial indexing (R-tree), point-in-polygon, nearest neighbor, geofencing, tile-based systems (H3)."""

PAIRS = [
    (
        "databases/postgis-spatial-queries",
        "Show PostGIS spatial queries: point-in-polygon, distance calculations, spatial joins, buffer analysis, and geometry operations.",
        '''PostGIS spatial queries for geospatial analytics:

```sql
-- === Setup: enable PostGIS and create spatial tables ===
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Store locations with geography type (lat/lon, meters-based calculations)
CREATE TABLE stores (
    store_id    SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    address     VARCHAR(500),
    city        VARCHAR(100),
    state       VARCHAR(2),
    location    GEOGRAPHY(POINT, 4326) NOT NULL,  -- WGS84
    capacity    INTEGER,
    opened_at   DATE
);

-- Store delivery zones as polygons
CREATE TABLE delivery_zones (
    zone_id     SERIAL PRIMARY KEY,
    store_id    INTEGER REFERENCES stores(store_id),
    zone_name   VARCHAR(100),
    zone_type   VARCHAR(20),  -- 'express', 'standard', 'extended'
    boundary    GEOGRAPHY(POLYGON, 4326) NOT NULL,
    max_delivery_minutes INTEGER
);

-- Administrative boundaries (neighborhoods, districts)
CREATE TABLE neighborhoods (
    neighborhood_id  SERIAL PRIMARY KEY,
    name            VARCHAR(200),
    borough         VARCHAR(100),
    boundary        GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    population      INTEGER,
    area_sq_km      NUMERIC(10, 3)
);

-- Customer locations
CREATE TABLE customers (
    customer_id  SERIAL PRIMARY KEY,
    name         VARCHAR(200),
    location     GEOGRAPHY(POINT, 4326),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial indexes (critical for query performance)
CREATE INDEX idx_stores_location ON stores USING GIST (location);
CREATE INDEX idx_delivery_boundary ON delivery_zones USING GIST (boundary);
CREATE INDEX idx_neighborhoods_boundary ON neighborhoods USING GIST (boundary);
CREATE INDEX idx_customers_location ON customers USING GIST (location);


-- === 1. Point-in-Polygon: which zone/neighborhood contains a point? ===

-- Find which delivery zone a customer address falls in
SELECT
    dz.zone_name,
    dz.zone_type,
    dz.max_delivery_minutes,
    s.name AS store_name
FROM delivery_zones dz
JOIN stores s ON dz.store_id = s.store_id
WHERE ST_Covers(
    dz.boundary,
    ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326)::GEOGRAPHY
);

-- Find neighborhood for each customer
SELECT
    c.name AS customer_name,
    n.name AS neighborhood,
    n.borough
FROM customers c
JOIN neighborhoods n
    ON ST_Within(
        c.location::GEOMETRY,
        n.boundary
    );


-- === 2. Distance calculations ===

-- Find 5 nearest stores to a location (KNN operator)
SELECT
    s.name,
    s.address,
    ROUND(
        ST_Distance(
            s.location,
            ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326)::GEOGRAPHY
        )::NUMERIC
    ) AS distance_meters
FROM stores s
ORDER BY s.location <->   -- KNN index-based operator
    ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326)::GEOGRAPHY
LIMIT 5;

-- Find all stores within 2km radius
SELECT
    s.name,
    s.address,
    ROUND(ST_Distance(
        s.location,
        ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326)::GEOGRAPHY
    )::NUMERIC) AS distance_m
FROM stores s
WHERE ST_DWithin(
    s.location,
    ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326)::GEOGRAPHY,
    2000  -- meters (geography type uses meters)
)
ORDER BY distance_m;


-- === 3. Spatial joins and aggregation ===

-- Count customers per neighborhood
SELECT
    n.name AS neighborhood,
    n.borough,
    COUNT(c.customer_id) AS customer_count,
    ROUND(
        COUNT(c.customer_id)::NUMERIC /
        NULLIF(n.population, 0) * 1000, 2
    ) AS customers_per_1000_residents
FROM neighborhoods n
LEFT JOIN customers c
    ON ST_Within(c.location::GEOMETRY, n.boundary)
GROUP BY n.neighborhood_id, n.name, n.borough, n.population
ORDER BY customer_count DESC;

-- Revenue heatmap: aggregate orders by neighborhood
SELECT
    n.name AS neighborhood,
    n.borough,
    COUNT(o.order_id) AS order_count,
    SUM(o.total) AS total_revenue,
    ROUND(AVG(o.total)::NUMERIC, 2) AS avg_order_value,
    ROUND(
        SUM(o.total)::NUMERIC / ST_Area(n.boundary::GEOGRAPHY) * 1e6,
        2
    ) AS revenue_per_sq_km
FROM neighborhoods n
JOIN customers c ON ST_Within(c.location::GEOMETRY, n.boundary)
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.created_at >= NOW() - INTERVAL '30 days'
GROUP BY n.neighborhood_id, n.name, n.borough, n.boundary
ORDER BY total_revenue DESC
LIMIT 20;


-- === 4. Buffer analysis and geometry operations ===

-- Create 500m buffer around each store
SELECT
    s.name,
    ST_Buffer(s.location::GEOMETRY, 0.0045) AS buffer_500m,
    -- 0.0045 degrees ≈ 500m at mid-latitudes. Better:
    ST_Buffer(s.location::GEOGRAPHY, 500)::GEOMETRY AS exact_500m_buffer
FROM stores s;

-- Find overlap between two store delivery zones
SELECT
    dz1.zone_name AS zone_a,
    dz2.zone_name AS zone_b,
    ST_Area(
        ST_Intersection(dz1.boundary::GEOMETRY, dz2.boundary::GEOMETRY)::GEOGRAPHY
    ) / 1e6 AS overlap_sq_km,
    ROUND(
        ST_Area(ST_Intersection(dz1.boundary::GEOMETRY, dz2.boundary::GEOMETRY)::GEOGRAPHY) /
        LEAST(ST_Area(dz1.boundary), ST_Area(dz2.boundary)) * 100,
        1
    ) AS overlap_pct
FROM delivery_zones dz1
JOIN delivery_zones dz2
    ON dz1.zone_id < dz2.zone_id  -- avoid self and duplicate pairs
    AND ST_Intersects(dz1.boundary::GEOMETRY, dz2.boundary::GEOMETRY)
ORDER BY overlap_sq_km DESC;

-- Convex hull: smallest polygon enclosing all stores
SELECT ST_AsGeoJSON(
    ST_ConvexHull(ST_Collect(location::GEOMETRY))
) AS store_coverage_area
FROM stores;


-- === 5. Line operations: routes and distances ===

-- Create a delivery route between two points
SELECT
    ST_MakeLine(
        s.location::GEOMETRY,
        c.location::GEOMETRY
    ) AS route_line,
    ST_Distance(s.location, c.location)::INTEGER AS distance_m,
    -- Bearing from store to customer (degrees from north)
    DEGREES(ST_Azimuth(s.location::GEOMETRY, c.location::GEOMETRY)) AS bearing
FROM stores s, customers c
WHERE s.store_id = 1 AND c.customer_id = 42;
```

Key patterns:
1. **Geography vs Geometry** -- use `GEOGRAPHY` for lat/lon data with meter-based distances; `GEOMETRY` for projected coordinates or when you need more functions
2. **KNN operator `<->`** -- index-based nearest neighbor is orders of magnitude faster than `ORDER BY ST_Distance`; requires GIST index
3. **ST_DWithin for radius** -- uses spatial index efficiently (unlike `WHERE ST_Distance < X` which computes all distances first)
4. **Always create GIST indexes** -- spatial queries without GIST indexes degrade to sequential scan; index creation: `USING GIST (column)`
5. **ST_Covers vs ST_Within** -- `ST_Covers(polygon, point)` is preferred over `ST_Within(point, polygon)` for geography types; same logic, better index usage'''
    ),
    (
        "databases/spatial-indexing-rtree",
        "Explain spatial indexing strategies: R-tree, GiST indexes in PostGIS, index-only scans, and how to optimize spatial query performance.",
        '''Spatial indexing with R-tree / GiST and query optimization:

```sql
-- === R-tree / GiST index internals and configuration ===

-- Standard GIST index on geometry column
CREATE INDEX idx_parcels_geom ON parcels USING GIST (geom);

-- GIST index with specific operator class for geography
CREATE INDEX idx_events_location ON events
    USING GIST (location geography_ops);

-- Partial spatial index (only active records)
CREATE INDEX idx_active_stores_location ON stores
    USING GIST (location)
    WHERE is_active = true;

-- Multi-column spatial + attribute index
-- PostGIS cannot combine GIST + B-tree in one index, but
-- you can use a GIST index on geometry + include B-tree columns
CREATE INDEX idx_stores_geo_capacity ON stores
    USING GIST (location)
    INCLUDE (capacity, store_type);  -- for index-only scans


-- === Index usage analysis ===

-- Check if spatial queries use the index
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT s.name, s.address
FROM stores s
WHERE ST_DWithin(
    s.location,
    ST_SetSRID(ST_MakePoint(-73.985, 40.748), 4326)::GEOGRAPHY,
    1000
);
-- Should show: "Index Scan using idx_stores_location"
-- NOT: "Seq Scan" (means index not used)


-- === Bounding box optimization ===

-- R-tree stores bounding boxes (MBR: Minimum Bounding Rectangle)
-- Phase 1: coarse filter using bounding box (fast, from index)
-- Phase 2: exact geometry test (slower, on candidate rows)

-- The && operator does bounding-box-only intersection (faster)
SELECT * FROM parcels p
WHERE p.geom && ST_MakeEnvelope(-74.0, 40.7, -73.9, 40.8, 4326);

-- ST_Intersects adds the exact geometry refinement
SELECT * FROM parcels p
WHERE p.geom && ST_MakeEnvelope(-74.0, 40.7, -73.9, 40.8, 4326)
  AND ST_Intersects(p.geom, ST_MakeEnvelope(-74.0, 40.7, -73.9, 40.8, 4326));


-- === KNN (K-Nearest Neighbor) with distance operator ===

-- The <-> operator uses index for efficient KNN
-- Only works in ORDER BY (not WHERE)
SELECT
    store_id,
    name,
    location <-> ST_SetSRID(ST_MakePoint(-73.985, 40.748), 4326)::GEOGRAPHY
        AS distance_m
FROM stores
ORDER BY location <->
    ST_SetSRID(ST_MakePoint(-73.985, 40.748), 4326)::GEOGRAPHY
LIMIT 10;

-- WRONG: this forces full distance computation, then sort
-- SELECT * FROM stores
-- WHERE ST_Distance(location, target) < 5000
-- ORDER BY ST_Distance(location, target)
-- LIMIT 10;

-- RIGHT: KNN operator + post-filter for distance cap
SELECT * FROM (
    SELECT
        store_id, name, address,
        location <-> ST_SetSRID(
            ST_MakePoint(-73.985, 40.748), 4326
        )::GEOGRAPHY AS dist
    FROM stores
    ORDER BY location <-> ST_SetSRID(
        ST_MakePoint(-73.985, 40.748), 4326
    )::GEOGRAPHY
    LIMIT 50  -- fetch more than needed
) sub
WHERE dist < 5000  -- then filter by actual distance
LIMIT 10;


-- === Spatial index statistics and maintenance ===

-- Check index size
SELECT
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan AS times_used,
    idx_tup_read AS rows_read
FROM pg_stat_user_indexes
WHERE indexrelname LIKE 'idx_%geom%'
    OR indexrelname LIKE 'idx_%location%'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Reindex after bulk loading (rebuilds R-tree optimally)
REINDEX INDEX CONCURRENTLY idx_parcels_geom;

-- Cluster table by spatial index (physically orders rows)
CLUSTER parcels USING idx_parcels_geom;
-- After clustering, nearby geometries are on the same disk pages
-- Dramatically improves range scan and spatial join performance

-- Analyze for query planner statistics
ANALYZE parcels;


-- === Spatial partitioning for large tables ===

-- Partition by geographic region for multi-billion row tables
CREATE TABLE events (
    event_id    BIGSERIAL,
    event_time  TIMESTAMPTZ NOT NULL,
    location    GEOGRAPHY(POINT, 4326),
    data        JSONB
) PARTITION BY LIST (
    -- Region derived from location
    CASE
        WHEN ST_X(location::GEOMETRY) < -100 THEN 'west'
        WHEN ST_X(location::GEOMETRY) < -80 THEN 'central'
        ELSE 'east'
    END
);

-- Alternative: partition by geohash prefix
CREATE TABLE events_partitioned (
    event_id    BIGSERIAL,
    event_time  TIMESTAMPTZ NOT NULL,
    location    GEOGRAPHY(POINT, 4326),
    geohash_3   VARCHAR(3) GENERATED ALWAYS AS (
        LEFT(ST_GeoHash(location::GEOMETRY), 3)
    ) STORED,
    data        JSONB
) PARTITION BY LIST (geohash_3);

-- Create partitions for each geohash prefix
CREATE TABLE events_p_dr6 PARTITION OF events_partitioned
    FOR VALUES IN ('dr6', 'dr7');  -- NYC area
CREATE TABLE events_p_9q8 PARTITION OF events_partitioned
    FOR VALUES IN ('9q8', '9q9');  -- SF area


-- === Covering index for index-only spatial scans ===

-- Include frequently accessed columns to avoid heap access
CREATE INDEX idx_stores_covering ON stores
    USING GIST (location)
    INCLUDE (name, store_type, is_active);

-- This query can now be satisfied entirely from the index
EXPLAIN (ANALYZE)
SELECT name, store_type
FROM stores
WHERE ST_DWithin(
    location,
    ST_SetSRID(ST_MakePoint(-73.985, 40.748), 4326)::GEOGRAPHY,
    500
)
AND is_active = true;
-- Expect: "Index Only Scan using idx_stores_covering"
```

Key patterns:
1. **R-tree two-phase filter** -- GIST index stores bounding boxes for coarse filtering; exact geometry test runs only on candidates (100x fewer rows)
2. **KNN operator `<->`** -- only works in ORDER BY + LIMIT; the index returns nearest neighbors without computing all distances; use subquery + WHERE for distance cap
3. **CLUSTER by spatial index** -- physically reorders table rows to match spatial locality; nearby geometries on same disk pages means fewer I/O operations
4. **Covering spatial indexes** -- `INCLUDE (columns)` enables index-only scans; avoids heap table access for common spatial + attribute queries
5. **Geohash partitioning** -- partition billion-row tables by geohash prefix; queries for a city only scan that city's partition; combine with per-partition GIST indexes'''
    ),
    (
        "databases/geospatial-nearest-neighbor",
        "Implement efficient nearest neighbor queries: PostGIS KNN, spatial data structures, bounding box pre-filtering, and distance matrix computation.",
        '''Nearest neighbor patterns for geospatial applications:

```python
import asyncpg
import math
from dataclasses import dataclass
from typing import Optional
from heapq import nsmallest


@dataclass
class Location:
    lat: float
    lon: float

    def to_wkt(self) -> str:
        return f"POINT({self.lon} {self.lat})"


@dataclass
class NearbyResult:
    id: int
    name: str
    distance_m: float
    lat: float
    lon: float
    metadata: dict


class SpatialNearestNeighbor:
    """Efficient nearest neighbor queries using PostGIS
    with progressive search strategies."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def find_nearest_k(
        self, point: Location, k: int = 10,
        max_distance_m: float = None,
        category: str = None,
    ) -> list[NearbyResult]:
        """Find K nearest locations using PostGIS KNN index.

        Uses the <-> operator for index-accelerated KNN.
        """
        filters = ["TRUE"]
        params = [point.lon, point.lat, k * 2]  # fetch extra for post-filter

        if category:
            filters.append(f"category = ${len(params) + 1}")
            params.append(category)

        async with self.pool.acquire() as conn:
            # Phase 1: KNN from index (fast, approximate distances)
            rows = await conn.fetch(f"""
                SELECT
                    poi_id,
                    name,
                    ST_Y(location::GEOMETRY) AS lat,
                    ST_X(location::GEOMETRY) AS lon,
                    -- Exact distance in meters
                    ST_Distance(
                        location,
                        ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY
                    ) AS distance_m,
                    metadata
                FROM pois
                WHERE {' AND '.join(filters)}
                ORDER BY location <->
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY
                LIMIT $3
            """, *params)

        results = [
            NearbyResult(
                id=r["poi_id"],
                name=r["name"],
                distance_m=r["distance_m"],
                lat=r["lat"],
                lon=r["lon"],
                metadata=r["metadata"] or {},
            )
            for r in rows
        ]

        # Phase 2: Filter by max distance and trim to k
        if max_distance_m:
            results = [r for r in results if r.distance_m <= max_distance_m]

        return results[:k]

    async def find_nearest_expanding_ring(
        self, point: Location, k: int = 10,
        initial_radius_m: float = 1000,
        max_radius_m: float = 50000,
    ) -> list[NearbyResult]:
        """Expanding ring search: start small, grow until K found.

        More efficient than large-radius search when results are nearby.
        Uses ST_DWithin which leverages the spatial index.
        """
        radius = initial_radius_m
        results = []

        async with self.pool.acquire() as conn:
            while radius <= max_radius_m and len(results) < k:
                rows = await conn.fetch("""
                    SELECT
                        poi_id, name,
                        ST_Y(location::GEOMETRY) AS lat,
                        ST_X(location::GEOMETRY) AS lon,
                        ST_Distance(
                            location,
                            ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY
                        ) AS distance_m,
                        metadata
                    FROM pois
                    WHERE ST_DWithin(
                        location,
                        ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY,
                        $3
                    )
                    ORDER BY distance_m
                    LIMIT $4
                """, point.lon, point.lat, radius, k)

                results = [
                    NearbyResult(
                        id=r["poi_id"], name=r["name"],
                        distance_m=r["distance_m"],
                        lat=r["lat"], lon=r["lon"],
                        metadata=r["metadata"] or {},
                    )
                    for r in rows
                ]

                if len(results) >= k:
                    break

                radius *= 2  # double the search radius

        return results[:k]

    async def distance_matrix(
        self, origins: list[Location],
        destinations: list[Location],
    ) -> list[list[float]]:
        """Compute NxM distance matrix using PostGIS.

        Uses a cross join with ST_Distance for all pairs.
        For large matrices, consider batching.
        """
        async with self.pool.acquire() as conn:
            # Build origin and destination arrays
            origin_points = [
                f"ST_SetSRID(ST_MakePoint({o.lon}, {o.lat}), 4326)::GEOGRAPHY"
                for o in origins
            ]
            dest_points = [
                f"ST_SetSRID(ST_MakePoint({d.lon}, {d.lat}), 4326)::GEOGRAPHY"
                for d in destinations
            ]

            rows = await conn.fetch(f"""
                WITH origins AS (
                    SELECT
                        ordinality - 1 AS origin_idx,
                        unnest AS geog
                    FROM UNNEST(ARRAY[{','.join(origin_points)}])
                    WITH ORDINALITY
                ),
                destinations AS (
                    SELECT
                        ordinality - 1 AS dest_idx,
                        unnest AS geog
                    FROM UNNEST(ARRAY[{','.join(dest_points)}])
                    WITH ORDINALITY
                )
                SELECT
                    o.origin_idx,
                    d.dest_idx,
                    ST_Distance(o.geog, d.geog) AS distance_m
                FROM origins o
                CROSS JOIN destinations d
                ORDER BY o.origin_idx, d.dest_idx
            """)

        # Build matrix
        matrix = [[0.0] * len(destinations) for _ in origins]
        for r in rows:
            matrix[r["origin_idx"]][r["dest_idx"]] = r["distance_m"]

        return matrix

    async def nearest_within_category_groups(
        self, point: Location,
        categories: list[str],
        k_per_category: int = 3,
        max_distance_m: float = 5000,
    ) -> dict[str, list[NearbyResult]]:
        """Find K nearest for each category in a single query.

        Uses LATERAL join for efficient per-group KNN.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    cat.category,
                    p.poi_id,
                    p.name,
                    ST_Y(p.location::GEOMETRY) AS lat,
                    ST_X(p.location::GEOMETRY) AS lon,
                    ST_Distance(
                        p.location,
                        ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY
                    ) AS distance_m,
                    p.metadata
                FROM UNNEST($3::TEXT[]) AS cat(category)
                CROSS JOIN LATERAL (
                    SELECT *
                    FROM pois
                    WHERE category = cat.category
                      AND ST_DWithin(
                          location,
                          ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY,
                          $4
                      )
                    ORDER BY location <->
                        ST_SetSRID(ST_MakePoint($1, $2), 4326)::GEOGRAPHY
                    LIMIT $5
                ) p
            """, point.lon, point.lat, categories,
                max_distance_m, k_per_category)

        results: dict[str, list[NearbyResult]] = {c: [] for c in categories}
        for r in rows:
            results[r["category"]].append(NearbyResult(
                id=r["poi_id"], name=r["name"],
                distance_m=r["distance_m"],
                lat=r["lat"], lon=r["lon"],
                metadata=r["metadata"] or {},
            ))

        return results


# === Haversine for client-side distance (when PostGIS unavailable) ===

def haversine_distance(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(d_lambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# === Usage ===
async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/geodb")
    nn = SpatialNearestNeighbor(pool)

    user_location = Location(lat=40.7484, lon=-73.9857)

    # K nearest restaurants
    nearby = await nn.find_nearest_k(
        user_location, k=5, max_distance_m=2000, category="restaurant"
    )
    for r in nearby:
        print(f"  {r.name}: {r.distance_m:.0f}m")

    # Multi-category search (restaurants, cafes, pharmacies)
    grouped = await nn.nearest_within_category_groups(
        user_location,
        categories=["restaurant", "cafe", "pharmacy"],
        k_per_category=3,
        max_distance_m=1500,
    )

    # Distance matrix for delivery routing
    stores = [Location(40.71, -74.00), Location(40.75, -73.98)]
    customers = [Location(40.72, -73.99), Location(40.74, -73.97)]
    matrix = await nn.distance_matrix(stores, customers)
```

Key patterns:
1. **KNN operator `<->`** -- index-accelerated nearest neighbor that avoids full table scan; always use in ORDER BY + LIMIT, never in WHERE
2. **Expanding ring** -- start with small ST_DWithin radius, double until K results found; efficient when data is dense near the query point
3. **LATERAL join for per-group KNN** -- `CROSS JOIN LATERAL` runs a KNN subquery for each category; single query instead of N separate queries
4. **Distance matrix** -- CROSS JOIN with ST_Distance computes all pairs; for N>1000 origins, batch into chunks to avoid memory pressure
5. **Haversine fallback** -- client-side great-circle distance for rough estimates when PostGIS is unavailable; accurate to ~0.3% for distances under 1000km'''
    ),
    (
        "databases/geospatial-geofencing",
        "Implement geofencing with PostGIS: zone entry/exit detection, real-time location tracking, polygon-based alerts, and spatial event processing.",
        '''Geofencing system with PostGIS for zone monitoring and alerts:

```python
import asyncpg
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class GeofenceEvent(Enum):
    ENTER = "enter"
    EXIT = "exit"
    DWELL = "dwell"    # stayed inside for > threshold


@dataclass
class GeofenceAlert:
    entity_id: str
    fence_id: int
    fence_name: str
    event: GeofenceEvent
    lat: float
    lon: float
    timestamp: datetime
    dwell_seconds: Optional[int] = None


class GeofenceEngine:
    """Real-time geofencing engine using PostGIS.

    Detects when tracked entities enter, exit, or dwell in
    geographic zones defined as polygons.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._alert_handlers: list[Callable] = []

    async def setup_schema(self):
        """Create geofencing tables and indexes."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                -- Geofence zones (polygons)
                CREATE TABLE IF NOT EXISTS geofences (
                    fence_id    SERIAL PRIMARY KEY,
                    name        VARCHAR(200) NOT NULL,
                    description TEXT,
                    fence_type  VARCHAR(50),  -- 'restricted', 'delivery', 'parking'
                    boundary    GEOGRAPHY(POLYGON, 4326) NOT NULL,
                    is_active   BOOLEAN DEFAULT TRUE,
                    metadata    JSONB DEFAULT '{}',
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );

                -- Entity current state (last known position + zone status)
                CREATE TABLE IF NOT EXISTS entity_state (
                    entity_id       VARCHAR(100) PRIMARY KEY,
                    entity_type     VARCHAR(50),  -- 'vehicle', 'person', 'asset'
                    current_lat     DOUBLE PRECISION,
                    current_lon     DOUBLE PRECISION,
                    current_location GEOGRAPHY(POINT, 4326),
                    speed_kmh       DOUBLE PRECISION,
                    heading         DOUBLE PRECISION,
                    -- Zones this entity is currently inside
                    current_fences  INTEGER[] DEFAULT '{}',
                    last_update     TIMESTAMPTZ DEFAULT NOW()
                );

                -- Location history (append-only log)
                CREATE TABLE IF NOT EXISTS location_history (
                    history_id  BIGSERIAL PRIMARY KEY,
                    entity_id   VARCHAR(100) NOT NULL,
                    location    GEOGRAPHY(POINT, 4326) NOT NULL,
                    speed_kmh   DOUBLE PRECISION,
                    heading     DOUBLE PRECISION,
                    recorded_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Geofence event log
                CREATE TABLE IF NOT EXISTS fence_events (
                    event_id    BIGSERIAL PRIMARY KEY,
                    entity_id   VARCHAR(100) NOT NULL,
                    fence_id    INTEGER REFERENCES geofences(fence_id),
                    event_type  VARCHAR(10) NOT NULL,  -- 'enter', 'exit', 'dwell'
                    location    GEOGRAPHY(POINT, 4326),
                    dwell_seconds INTEGER,
                    recorded_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_geofences_boundary
                    ON geofences USING GIST (boundary);
                CREATE INDEX IF NOT EXISTS idx_geofences_active
                    ON geofences USING GIST (boundary) WHERE is_active = true;
                CREATE INDEX IF NOT EXISTS idx_entity_state_location
                    ON entity_state USING GIST (current_location);
                CREATE INDEX IF NOT EXISTS idx_location_history_entity
                    ON location_history (entity_id, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fence_events_entity
                    ON fence_events (entity_id, recorded_at DESC);
            """)

    def on_alert(self, handler: Callable[[GeofenceAlert], None]):
        """Register alert handler."""
        self._alert_handlers.append(handler)

    async def create_fence(self, name: str, coordinates: list[tuple],
                           fence_type: str = "standard",
                           metadata: dict = None) -> int:
        """Create a geofence from a list of (lat, lon) coordinates."""
        # Close the polygon (first point = last point)
        if coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])

        # Build WKT polygon string
        points = ", ".join(f"{lon} {lat}" for lat, lon in coordinates)
        wkt = f"POLYGON(({points}))"

        async with self.pool.acquire() as conn:
            fence_id = await conn.fetchval("""
                INSERT INTO geofences (name, fence_type, boundary, metadata)
                VALUES ($1, $2, ST_GeogFromText($3), $4::JSONB)
                RETURNING fence_id
            """, name, fence_type, wkt, json.dumps(metadata or {}))

        logger.info(f"Created geofence '{name}' (id={fence_id})")
        return fence_id

    async def update_location(self, entity_id: str,
                              lat: float, lon: float,
                              speed_kmh: float = None,
                              heading: float = None,
                              entity_type: str = "vehicle"):
        """Process a new location update and check geofences."""
        now = datetime.utcnow()
        point_wkt = f"POINT({lon} {lat})"

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current state
                state = await conn.fetchrow("""
                    SELECT current_fences, last_update
                    FROM entity_state
                    WHERE entity_id = $1
                """, entity_id)

                old_fences = set(state["current_fences"]) if state else set()

                # 2. Find which active fences contain this point
                new_fence_rows = await conn.fetch("""
                    SELECT fence_id, name
                    FROM geofences
                    WHERE is_active = true
                      AND ST_Covers(boundary, ST_GeogFromText($1))
                """, point_wkt)

                new_fences = {r["fence_id"] for r in new_fence_rows}
                fence_names = {r["fence_id"]: r["name"] for r in new_fence_rows}

                # 3. Detect enter/exit events
                entered = new_fences - old_fences
                exited = old_fences - new_fences

                # 4. Log events
                for fence_id in entered:
                    await conn.execute("""
                        INSERT INTO fence_events
                            (entity_id, fence_id, event_type, location)
                        VALUES ($1, $2, 'enter', ST_GeogFromText($3))
                    """, entity_id, fence_id, point_wkt)

                    alert = GeofenceAlert(
                        entity_id=entity_id,
                        fence_id=fence_id,
                        fence_name=fence_names.get(fence_id, "unknown"),
                        event=GeofenceEvent.ENTER,
                        lat=lat, lon=lon, timestamp=now,
                    )
                    self._emit_alert(alert)

                for fence_id in exited:
                    # Calculate dwell time
                    enter_event = await conn.fetchrow("""
                        SELECT recorded_at
                        FROM fence_events
                        WHERE entity_id = $1 AND fence_id = $2
                          AND event_type = 'enter'
                        ORDER BY recorded_at DESC LIMIT 1
                    """, entity_id, fence_id)

                    dwell_secs = None
                    if enter_event:
                        dwell_secs = int(
                            (now - enter_event["recorded_at"]).total_seconds()
                        )

                    await conn.execute("""
                        INSERT INTO fence_events
                            (entity_id, fence_id, event_type, location,
                             dwell_seconds)
                        VALUES ($1, $2, 'exit', ST_GeogFromText($3), $4)
                    """, entity_id, fence_id, point_wkt, dwell_secs)

                    alert = GeofenceAlert(
                        entity_id=entity_id,
                        fence_id=fence_id,
                        fence_name="",
                        event=GeofenceEvent.EXIT,
                        lat=lat, lon=lon, timestamp=now,
                        dwell_seconds=dwell_secs,
                    )
                    self._emit_alert(alert)

                # 5. Update entity state
                await conn.execute("""
                    INSERT INTO entity_state
                        (entity_id, entity_type, current_lat, current_lon,
                         current_location, speed_kmh, heading,
                         current_fences, last_update)
                    VALUES ($1, $2, $3, $4, ST_GeogFromText($5),
                            $6, $7, $8, $9)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        current_lat = $3, current_lon = $4,
                        current_location = ST_GeogFromText($5),
                        speed_kmh = $6, heading = $7,
                        current_fences = $8, last_update = $9
                """, entity_id, entity_type, lat, lon, point_wkt,
                    speed_kmh, heading, list(new_fences), now)

                # 6. Append to history
                await conn.execute("""
                    INSERT INTO location_history
                        (entity_id, location, speed_kmh, heading)
                    VALUES ($1, ST_GeogFromText($2), $3, $4)
                """, entity_id, point_wkt, speed_kmh, heading)

    async def entities_in_fence(self, fence_id: int) -> list[dict]:
        """Find all entities currently inside a geofence."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    entity_id, entity_type,
                    current_lat, current_lon,
                    speed_kmh, heading, last_update
                FROM entity_state
                WHERE $1 = ANY(current_fences)
            """, fence_id)
            return [dict(r) for r in rows]

    def _emit_alert(self, alert: GeofenceAlert):
        """Send alert to all registered handlers."""
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")


# === Usage ===
async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/geodb")
    engine = GeofenceEngine(pool)
    await engine.setup_schema()

    # Register alert handler
    engine.on_alert(lambda a: logger.info(
        f"ALERT: {a.entity_id} {a.event.value} fence "
        f"'{a.fence_name}' at ({a.lat}, {a.lon})"
    ))

    # Create a restricted zone
    fence_id = await engine.create_fence(
        name="Warehouse A - Restricted",
        coordinates=[
            (40.7128, -74.0060),
            (40.7130, -74.0050),
            (40.7120, -74.0048),
            (40.7118, -74.0058),
        ],
        fence_type="restricted",
        metadata={"alert_level": "high", "notify": ["security@example.com"]},
    )

    # Simulate location updates
    await engine.update_location("truck-42", 40.7125, -74.0055)  # inside
    await engine.update_location("truck-42", 40.7140, -74.0070)  # outside (exit)
```

Key patterns:
1. **State-based detection** -- store `current_fences[]` per entity; compare old vs. new set on each update to detect enter/exit without scanning history
2. **ST_Covers for containment** -- `ST_Covers(boundary, point)` checks if polygon contains point; uses GIST spatial index for O(log N) lookup
3. **Dwell time tracking** -- on exit, query the most recent enter event to compute dwell duration; useful for parking, delivery, and compliance monitoring
4. **Partial index on active fences** -- `WHERE is_active = true` in the GIST index means deactivated fences have zero query overhead
5. **Transactional consistency** -- all state updates (entity_state, fence_events, location_history) happen in one transaction; no partial state on crash'''
    ),
    (
        "databases/geospatial-h3-tiling",
        "Show H3 hexagonal tiling for geospatial analytics: H3 indexing, resolution selection, hexagon aggregation, neighbor traversal, and visualization-ready output.",
        '''H3 hexagonal tiling system for geospatial analytics:

```python
import h3
import json
import asyncpg
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class H3Config:
    """H3 resolution configuration.

    Resolution | Hex edge length | Hex area
    0          | 1107.71 km      | 4,357,449 km2
    3          | 59.81 km        | 12,393 km2
    5          | 8.54 km         | 252.9 km2
    7          | 1.22 km         | 5.16 km2
    9          | 0.174 km        | 0.105 km2 (city block)
    10         | 0.066 km        | 0.015 km2 (building)
    12         | 0.009 km        | 307 m2 (room)
    """
    coarse_resolution: int = 5    # country/state level
    medium_resolution: int = 7    # city/district level
    fine_resolution: int = 9      # neighborhood/block level
    precision_resolution: int = 11  # building level


class H3SpatialAnalytics:
    """H3-based spatial analytics engine.

    H3 advantages over geohash:
    - Hexagons have uniform distance to all neighbors (no edge effects)
    - Hierarchical: each parent contains exactly 7 children
    - Consistent neighbor relationships (always 6 neighbors)
    - Area is nearly uniform across the globe
    """

    def __init__(self, pool: asyncpg.Pool, config: H3Config = None):
        self.pool = pool
        self.config = config or H3Config()

    async def setup_schema(self):
        """Create H3-indexed tables."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                -- Events with H3 indexes at multiple resolutions
                CREATE TABLE IF NOT EXISTS geo_events (
                    event_id    BIGSERIAL PRIMARY KEY,
                    event_type  VARCHAR(50),
                    lat         DOUBLE PRECISION NOT NULL,
                    lon         DOUBLE PRECISION NOT NULL,
                    h3_res5     VARCHAR(15) NOT NULL,  -- coarse
                    h3_res7     VARCHAR(15) NOT NULL,  -- medium
                    h3_res9     VARCHAR(15) NOT NULL,  -- fine
                    payload     JSONB DEFAULT '{}',
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );

                -- Pre-aggregated hexagon statistics
                CREATE TABLE IF NOT EXISTS h3_stats (
                    h3_index     VARCHAR(15) NOT NULL,
                    resolution   SMALLINT NOT NULL,
                    stat_date    DATE NOT NULL,
                    event_count  INTEGER DEFAULT 0,
                    unique_users INTEGER DEFAULT 0,
                    total_value  NUMERIC(12,2) DEFAULT 0,
                    PRIMARY KEY (h3_index, resolution, stat_date)
                );

                -- Indexes for H3-based queries
                CREATE INDEX IF NOT EXISTS idx_geo_events_h3_res7
                    ON geo_events(h3_res7);
                CREATE INDEX IF NOT EXISTS idx_geo_events_h3_res9
                    ON geo_events(h3_res9);
                CREATE INDEX IF NOT EXISTS idx_h3_stats_lookup
                    ON h3_stats(resolution, stat_date, h3_index);
            """)

    def lat_lon_to_h3(self, lat: float, lon: float,
                      resolution: int = None) -> dict[str, str]:
        """Convert lat/lon to H3 indexes at multiple resolutions."""
        res = resolution
        if res is not None:
            return {"h3_index": h3.latlng_to_cell(lat, lon, res)}

        return {
            "h3_res5": h3.latlng_to_cell(lat, lon, self.config.coarse_resolution),
            "h3_res7": h3.latlng_to_cell(lat, lon, self.config.medium_resolution),
            "h3_res9": h3.latlng_to_cell(lat, lon, self.config.fine_resolution),
        }

    async def insert_event(self, event_type: str, lat: float, lon: float,
                           payload: dict = None):
        """Insert event with pre-computed H3 indexes."""
        h3_indexes = self.lat_lon_to_h3(lat, lon)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO geo_events
                    (event_type, lat, lon, h3_res5, h3_res7, h3_res9, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7::JSONB)
            """, event_type, lat, lon,
                h3_indexes["h3_res5"],
                h3_indexes["h3_res7"],
                h3_indexes["h3_res9"],
                json.dumps(payload or {}))

    async def hexagon_aggregation(
        self, resolution: int = 7,
        event_type: str = None,
        start_date: str = None,
        end_date: str = None,
        bounding_box: tuple = None,
    ) -> list[dict]:
        """Aggregate events by H3 hexagon for heatmap visualization."""
        res_col = f"h3_res{resolution}"
        filters = ["TRUE"]
        params = []

        if event_type:
            params.append(event_type)
            filters.append(f"event_type = ${len(params)}")
        if start_date:
            params.append(start_date)
            filters.append(f"created_at >= ${len(params)}::DATE")
        if end_date:
            params.append(end_date)
            filters.append(f"created_at < ${len(params)}::DATE")
        if bounding_box:
            sw_lat, sw_lon, ne_lat, ne_lon = bounding_box
            params.extend([sw_lat, ne_lat, sw_lon, ne_lon])
            filters.append(
                f"lat BETWEEN ${len(params)-3} AND ${len(params)-2} "
                f"AND lon BETWEEN ${len(params)-1} AND ${len(params)}"
            )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT
                    {res_col} AS h3_index,
                    COUNT(*) AS event_count,
                    COUNT(DISTINCT payload->>'user_id') AS unique_users,
                    MIN(created_at) AS first_event,
                    MAX(created_at) AS last_event
                FROM geo_events
                WHERE {' AND '.join(filters)}
                GROUP BY {res_col}
                HAVING COUNT(*) > 0
                ORDER BY event_count DESC
            """, *params)

        # Add hexagon boundary coordinates for visualization
        results = []
        for row in rows:
            h3_idx = row["h3_index"]
            boundary = h3.cell_to_boundary(h3_idx)
            center = h3.cell_to_latlng(h3_idx)

            results.append({
                "h3_index": h3_idx,
                "event_count": row["event_count"],
                "unique_users": row["unique_users"],
                "center": {"lat": center[0], "lon": center[1]},
                "boundary": [
                    {"lat": lat, "lon": lon} for lat, lon in boundary
                ],
                "geojson_feature": {
                    "type": "Feature",
                    "properties": {
                        "h3": h3_idx,
                        "count": row["event_count"],
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[lon, lat] for lat, lon in boundary]
                            + [[boundary[0][1], boundary[0][0]]]
                        ],
                    },
                },
            })

        return results

    def get_neighbors(self, h3_index: str,
                      ring_size: int = 1) -> list[str]:
        """Get neighboring hexagons at distance K (k-ring)."""
        return list(h3.grid_disk(h3_index, ring_size))

    def get_hex_path(self, origin_h3: str,
                     dest_h3: str) -> list[str]:
        """Get hexagon path between two H3 cells."""
        return list(h3.grid_path_cells(origin_h3, dest_h3))

    async def hotspot_detection(
        self, resolution: int = 9,
        min_events: int = 50,
        time_window_hours: int = 24,
    ) -> list[dict]:
        """Detect spatial hotspots using H3 + neighbor analysis."""
        res_col = f"h3_res{resolution}"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT
                    {res_col} AS h3_index,
                    COUNT(*) AS event_count
                FROM geo_events
                WHERE created_at >= NOW() - INTERVAL '{time_window_hours} hours'
                GROUP BY {res_col}
                HAVING COUNT(*) >= $1
                ORDER BY event_count DESC
                LIMIT 1000
            """, min_events)

        # Enrich with neighbor analysis
        hex_counts = {r["h3_index"]: r["event_count"] for r in rows}
        hotspots = []

        for h3_idx, count in hex_counts.items():
            neighbors = self.get_neighbors(h3_idx, ring_size=1)
            neighbor_counts = [
                hex_counts.get(n, 0) for n in neighbors
                if n != h3_idx
            ]
            avg_neighbor = (
                sum(neighbor_counts) / len(neighbor_counts)
                if neighbor_counts else 0
            )

            # Hotspot: significantly more events than neighbors
            if count > avg_neighbor * 2:
                center = h3.cell_to_latlng(h3_idx)
                hotspots.append({
                    "h3_index": h3_idx,
                    "event_count": count,
                    "avg_neighbor_count": round(avg_neighbor, 1),
                    "hotspot_ratio": round(count / max(avg_neighbor, 1), 2),
                    "center": {"lat": center[0], "lon": center[1]},
                })

        return sorted(hotspots, key=lambda h: h["hotspot_ratio"],
                       reverse=True)

    def to_geojson_collection(
        self, hex_data: list[dict],
    ) -> dict:
        """Convert H3 results to GeoJSON FeatureCollection for mapping."""
        features = [
            item["geojson_feature"] for item in hex_data
            if "geojson_feature" in item
        ]
        return {
            "type": "FeatureCollection",
            "features": features,
        }


# === Usage ===
async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/geodb")
    h3a = H3SpatialAnalytics(pool)
    await h3a.setup_schema()

    # Insert events
    await h3a.insert_event("ride_request", 40.7128, -74.0060,
                           {"user_id": "u123", "value": 25.00})

    # Hexagon heatmap for visualization
    heatmap = await h3a.hexagon_aggregation(
        resolution=7,
        event_type="ride_request",
        start_date="2025-12-01",
        bounding_box=(40.5, -74.3, 40.9, -73.7),  # NYC bbox
    )

    # Export as GeoJSON for mapping
    geojson = h3a.to_geojson_collection(heatmap)
    with open("heatmap.geojson", "w") as f:
        json.dump(geojson, f)

    # Detect hotspots
    hotspots = await h3a.hotspot_detection(
        resolution=9, min_events=20, time_window_hours=4
    )
```

Key patterns:
1. **Multi-resolution indexing** -- store H3 at resolutions 5/7/9 simultaneously; use coarse for country-level, fine for block-level analytics; avoids recomputation
2. **Hexagon advantages** -- uniform area, uniform neighbor distance, exactly 6 neighbors; geohash rectangles have edge effects and 8 neighbors of varying distance
3. **Pre-aggregated stats** -- compute h3_stats table daily for instant dashboard rendering; raw events for ad-hoc queries
4. **Hotspot detection** -- compare hex event count to average of its 6 neighbors; ratio > 2x indicates a spatial hotspot worth investigating
5. **GeoJSON export** -- `cell_to_boundary()` returns hex vertices for rendering on any web map (Mapbox, Leaflet, deck.gl); hexagon heatmaps are visually cleaner than grid-based'''
    ),
]
