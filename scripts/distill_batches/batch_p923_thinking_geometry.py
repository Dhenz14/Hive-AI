PAIRS = [
    ("thinking/algorithms", r'''Implement the Convex Hull algorithm using Graham Scan: given a set of 2D points, find the smallest convex polygon that contains all the points.''', r'''<think>
The convex hull is the smallest convex polygon enclosing all points. Graham Scan computes it in O(n log n).

Algorithm:
1. Find the point with the lowest y-coordinate (leftmost if tie). This is the anchor point p0.
2. Sort all other points by polar angle with respect to p0.
3. Process points in sorted order, maintaining a stack of hull points:
   - For each point, check if adding it makes a left turn or right turn with the last two points on the stack
   - If right turn (or collinear), pop the last point from the stack
   - Push the new point

The "turn" check uses the cross product:
cross(O, A, B) = (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x)
- Positive: left turn (counter-clockwise)
- Negative: right turn (clockwise)
- Zero: collinear

We keep only left turns to maintain convexity.

Implementation details:
- When sorting by angle, use atan2 or compare cross products (cross product comparison avoids floating point)
- Handle collinear points: for same angle, sort by distance from anchor
- Need at least 3 non-collinear points for a proper hull

Edge cases:
- All points collinear (hull is a line segment)
- Duplicate points
- Fewer than 3 points
- Multiple points at same angle from anchor

Time: O(n log n) dominated by sorting.
Space: O(n) for the hull stack.
</think>

**Convex Hull -- Graham Scan**

```python
import math


def cross(o, a, b):
    """Cross product of vectors OA and OB. Positive = counter-clockwise."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def dist_sq(a, b):
    """Squared distance between two points."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def graham_scan(points):
    """
    Compute convex hull using Graham Scan.

    Args:
        points: list of (x, y) tuples
    Returns:
        list of hull points in counter-clockwise order
    """
    points = list(set(points))  # remove duplicates
    n = len(points)

    if n <= 2:
        return points[:]

    # Step 1: Find anchor (lowest y, then leftmost x)
    anchor = min(points, key=lambda p: (p[1], p[0]))

    # Step 2: Sort by polar angle relative to anchor
    def angle_key(p):
        if p == anchor:
            return (-math.inf, 0)
        angle = math.atan2(p[1] - anchor[1], p[0] - anchor[0])
        dist = dist_sq(anchor, p)
        return (angle, dist)

    points.sort(key=angle_key)

    # Step 3: Build hull using stack
    stack = []
    for p in points:
        while len(stack) >= 2 and cross(stack[-2], stack[-1], p) <= 0:
            stack.pop()
        stack.append(p)

    return stack


def convex_hull_andrew(points):
    """Alternative: Andrew's monotone chain algorithm."""
    points = sorted(set(points))
    if len(points) <= 2:
        return points[:]

    # Build lower hull
    lower = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    # Build upper hull
    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    # Remove last point of each half (duplicated at junction)
    return lower[:-1] + upper[:-1]


# Example
points = [(0, 3), (1, 1), (2, 2), (4, 4), (0, 0), (1, 2),
          (3, 1), (3, 3)]

hull1 = graham_scan(points)
hull2 = convex_hull_andrew(points)

print(f"Points: {points}")
print(f"Graham Scan hull: {hull1}")
print(f"Andrew's hull:    {hull2}")
print(f"Hull size: {len(hull1)} points")

# Compute hull area using shoelace formula
def polygon_area(hull):
    n = len(hull)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += hull[i][0] * hull[j][1]
        area -= hull[j][0] * hull[i][1]
    return abs(area) / 2

area = polygon_area(hull1)
print(f"Hull area: {area}")

# Verify all points inside hull
def point_in_convex_hull(p, hull):
    n = len(hull)
    for i in range(n):
        j = (i + 1) % n
        if cross(hull[i], hull[j], p) < 0:
            return False
    return True

all_inside = all(point_in_convex_hull(p, hull1) for p in points)
print(f"All points inside hull: {all_inside}")
```

**Complexity:**
- Graham Scan: O(n log n) for sorting + O(n) for stack processing
- Andrew's Monotone Chain: O(n log n) same complexity, often simpler to implement
- Space: O(n) for hull storage'''),

    ("thinking/algorithms", r'''Implement line segment intersection detection: given two line segments in 2D, determine if they intersect. Handle all edge cases including collinear and overlapping segments.''', r'''<think>
Line segment intersection is a fundamental computational geometry problem. Two segments intersect if they share at least one point.

Approach using cross products (orientation test):
For segments AB and CD:
1. Compute orientations:
   - d1 = orientation(A, B, C)
   - d2 = orientation(A, B, D)
   - d3 = orientation(C, D, A)
   - d4 = orientation(C, D, B)

2. General case: segments intersect if:
   - d1 and d2 have different signs (C and D are on opposite sides of line AB)
   AND
   - d3 and d4 have different signs (A and B are on opposite sides of line CD)

3. Special cases (collinear): If any orientation is 0, a point lies on the line containing the other segment. Check if it lies within the segment.

The orientation function uses the cross product:
orientation(P, Q, R) = sign of (Q-P) x (R-P)
- Positive: counterclockwise (left turn)
- Negative: clockwise (right turn)
- Zero: collinear

For collinear cases, we need to check if the segments overlap using "on segment" tests.

Edge cases:
- Parallel segments (may be collinear and overlapping)
- One segment is a single point (degenerate)
- Segments share exactly one endpoint
- T-junction (one endpoint on the other segment)
- Completely overlapping segments

I will also implement finding the actual intersection point when it exists.
</think>

**Line Segment Intersection Detection**

```python
def orientation(p, q, r):
    """
    Orientation of triplet (p, q, r).
    Returns:
        > 0: counterclockwise
        < 0: clockwise
        = 0: collinear
    """
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def on_segment(p, q, r):
    """Check if point q lies on segment pr (assuming collinear)."""
    return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and
            min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))


def segments_intersect(a, b, c, d):
    """
    Check if segment AB intersects segment CD.

    Args:
        a, b: endpoints of first segment
        c, d: endpoints of second segment
    Returns:
        True if segments intersect
    """
    d1 = orientation(a, b, c)
    d2 = orientation(a, b, d)
    d3 = orientation(c, d, a)
    d4 = orientation(c, d, b)

    # General case: segments straddle each other
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True

    # Special cases: collinear points
    if d1 == 0 and on_segment(a, c, b):
        return True
    if d2 == 0 and on_segment(a, d, b):
        return True
    if d3 == 0 and on_segment(c, a, d):
        return True
    if d4 == 0 and on_segment(c, b, d):
        return True

    return False


def intersection_point(a, b, c, d):
    """
    Find intersection point of segments AB and CD.
    Returns (x, y) or None if no single intersection point.
    """
    denom = ((a[0]-b[0])*(c[1]-d[1]) - (a[1]-b[1])*(c[0]-d[0]))

    if abs(denom) < 1e-10:
        return None  # parallel or collinear

    t_num = (a[0]-c[0])*(c[1]-d[1]) - (a[1]-c[1])*(c[0]-d[0])
    t = t_num / denom

    x = a[0] + t * (b[0] - a[0])
    y = a[1] + t * (b[1] - a[1])

    return (x, y)


# Test cases
tests = [
    # (seg1_start, seg1_end, seg2_start, seg2_end, expected)
    ((0,0), (4,4), (0,4), (4,0), True,   "X cross"),
    ((0,0), (2,2), (3,3), (5,5), False,  "parallel"),
    ((0,0), (2,2), (1,1), (3,3), True,   "collinear overlap"),
    ((0,0), (1,1), (2,2), (3,3), False,  "collinear no overlap"),
    ((0,0), (2,0), (1,0), (1,2), True,   "T-junction"),
    ((0,0), (1,0), (1,0), (1,1), True,   "shared endpoint"),
    ((0,0), (1,0), (2,0), (2,1), False,  "no intersection"),
]

print("Segment Intersection Tests:")
for a, b, c, d, expected, desc in tests:
    result = segments_intersect(a, b, c, d)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] {desc}: {a}-{b} x {c}-{d} = {result}")

    if result and not (orientation(a, b, c) == 0 and
                       orientation(a, b, d) == 0):
        pt = intersection_point(a, b, c, d)
        if pt:
            print(f"         intersection at ({pt[0]:.2f}, {pt[1]:.2f})")
```

**Orientation Test (Cross Product):**
```
orientation(P, Q, R) = (Q-P) x (R-P)
  > 0: R is to the left of PQ (counterclockwise)
  < 0: R is to the right of PQ (clockwise)
  = 0: P, Q, R are collinear
```

**Complexity:**
- Intersection test: O(1)
- For n segments, all-pairs: O(n^2), or O(n log n) with sweep line (Bentley-Ottmann)'''),

    ("thinking/algorithms", r'''Implement the Closest Pair of Points algorithm: given n points in 2D, find the pair with the smallest Euclidean distance. Use the divide-and-conquer approach for O(n log n) time.''', r'''<think>
The closest pair problem has a classic O(n log n) divide-and-conquer solution.

Algorithm:
1. Sort points by x-coordinate
2. Divide into left and right halves
3. Recursively find closest pair in each half: d_left, d_right
4. Let delta = min(d_left, d_right)
5. Key step: Check for closer pairs that cross the dividing line
   - Consider only points within delta distance of the dividing line (the "strip")
   - Sort strip points by y-coordinate
   - For each point in the strip, only compare with the next 7 points (at most) in y-sorted order

Why only 7 comparisons? Within a delta x 2*delta rectangle, at most 8 points can exist with pairwise distance >= delta (by packing argument). So each point needs to check at most 7 neighbors.

This gives the recurrence T(n) = 2T(n/2) + O(n log n) if we sort the strip each time, giving O(n log^2 n). But with the optimization of maintaining a y-sorted order across recursive calls (merge step), we get T(n) = 2T(n/2) + O(n) = O(n log n).

For simplicity, I will implement the O(n log^2 n) version first, then note the optimization.

Edge cases:
- Fewer than 3 points (check all pairs directly)
- All points on the same line
- Multiple points at the same location (distance 0)
- Large number of points in the strip (bounded by the 7-neighbor property)
</think>

**Closest Pair of Points -- Divide and Conquer**

```python
import math


def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def closest_pair_brute(points):
    """Brute force for small inputs."""
    n = len(points)
    min_dist = float('inf')
    best = (None, None)
    for i in range(n):
        for j in range(i+1, n):
            d = distance(points[i], points[j])
            if d < min_dist:
                min_dist = d
                best = (points[i], points[j])
    return min_dist, best


def closest_pair(points):
    """
    Find closest pair of points in O(n log^2 n).

    Args:
        points: list of (x, y) tuples
    Returns:
        (min_distance, (point1, point2))
    """
    points = sorted(points, key=lambda p: p[0])
    return _closest_rec(points)


def _closest_rec(pts):
    n = len(pts)
    if n <= 3:
        return closest_pair_brute(pts)

    mid = n // 2
    mid_x = pts[mid][0]

    left_result = _closest_rec(pts[:mid])
    right_result = _closest_rec(pts[mid:])

    if left_result[0] < right_result[0]:
        delta, best = left_result
    else:
        delta, best = right_result

    # Build strip of points within delta of dividing line
    strip = [p for p in pts if abs(p[0] - mid_x) < delta]
    strip.sort(key=lambda p: p[1])

    # Check strip pairs (at most 7 comparisons per point)
    for i in range(len(strip)):
        j = i + 1
        while j < len(strip) and (strip[j][1] - strip[i][1]) < delta:
            d = distance(strip[i], strip[j])
            if d < delta:
                delta = d
                best = (strip[i], strip[j])
            j += 1

    return delta, best


# Example
import random
random.seed(42)
points = [(random.uniform(0, 100), random.uniform(0, 100))
          for _ in range(20)]

dist_dc, pair_dc = closest_pair(points)
dist_bf, pair_bf = closest_pair_brute(points)

print(f"Number of points: {len(points)}")
print(f"Divide & Conquer: dist={dist_dc:.6f}")
print(f"  Pair: ({pair_dc[0][0]:.2f},{pair_dc[0][1]:.2f}) - "
      f"({pair_dc[1][0]:.2f},{pair_dc[1][1]:.2f})")
print(f"Brute Force:      dist={dist_bf:.6f}")
print(f"  Match: {abs(dist_dc - dist_bf) < 1e-9}")

# Stress test
for trial in range(100):
    pts = [(random.uniform(-1000, 1000), random.uniform(-1000, 1000))
           for _ in range(random.randint(2, 50))]
    d1, _ = closest_pair(pts)
    d2, _ = closest_pair_brute(pts)
    if abs(d1 - d2) > 1e-6:
        print(f"MISMATCH at trial {trial}: dc={d1}, bf={d2}")
        break
else:
    print("\nAll 100 stress tests passed!")
```

**Key Insight -- Strip Analysis:**
- Only points within delta of the dividing line can form a closer cross-pair
- Within the strip, each point needs to compare with at most 7 neighbors in y-order
- This is proven by a packing argument: in a delta x 2*delta box, at most 8 points can have pairwise distance >= delta

**Complexity:**
- Time: O(n log^2 n) as implemented (strip sort each level)
- Optimized: O(n log n) by merging y-sorted lists during recursion
- Space: O(n)'''),

    ("thinking/algorithms", r'''Implement the point-in-polygon test: given a polygon (as a list of vertices) and a query point, determine if the point lies inside, outside, or on the boundary of the polygon. Handle both convex and concave polygons.''', r'''<think>
The ray casting algorithm (also called the crossing number algorithm) is the standard approach for point-in-polygon testing. It works for any simple polygon (convex or concave, with or without holes).

Algorithm:
1. Cast a ray from the query point in any direction (typically horizontal, to the right)
2. Count how many times the ray crosses the polygon boundary
3. If the count is odd, the point is inside. If even, outside.

Why it works: As we move from inside to outside the polygon, we must cross the boundary. Each boundary crossing toggles inside/outside status. Starting from "outside" (infinitely far along the ray), an odd number of crossings means we are inside.

Edge cases (the tricky part):
- Ray passes through a vertex: need careful handling
- Ray is collinear with an edge
- Point is exactly on an edge
- Very close to boundary (floating point)

Standard handling for vertex cases:
- Count an edge crossing only if one endpoint is strictly above the ray and the other is at or below. This avoids double-counting at vertices.

For checking if the point is ON the boundary:
- For each edge, check if the point lies on the segment (using cross product + bounding box).

I will also implement the winding number algorithm as an alternative, which is more robust for some cases.

The winding number counts how many times the polygon winds around the point. Non-zero winding number means inside.

Time: O(n) where n is the number of vertices.
</think>

**Point-in-Polygon -- Ray Casting and Winding Number**

```python
def cross_2d(o, a, b):
    """Cross product of OA x OB."""
    return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])


def point_on_segment(p, a, b):
    """Check if point p lies on segment AB."""
    # Check collinearity
    if abs(cross_2d(a, b, p)) > 1e-10:
        return False
    # Check bounding box
    return (min(a[0],b[0]) <= p[0] <= max(a[0],b[0]) and
            min(a[1],b[1]) <= p[1] <= max(a[1],b[1]))


def point_in_polygon_ray(point, polygon):
    """
    Ray casting algorithm for point-in-polygon.

    Args:
        point: (x, y) query point
        polygon: list of (x, y) vertices in order
    Returns:
        1 if inside, -1 if on boundary, 0 if outside
    """
    n = len(polygon)
    px, py = point

    # Check boundary first
    for i in range(n):
        j = (i + 1) % n
        if point_on_segment(point, polygon[i], polygon[j]):
            return -1  # on boundary

    # Ray casting: horizontal ray to the right
    crossings = 0
    for i in range(n):
        j = (i + 1) % n
        yi, yj = polygon[i][1], polygon[j][1]
        xi, xj = polygon[i][0], polygon[j][0]

        # Check if edge crosses the horizontal ray
        if (yi <= py < yj) or (yj <= py < yi):
            # Compute x-coordinate of intersection
            t = (py - yi) / (yj - yi)
            x_intersect = xi + t * (xj - xi)
            if px < x_intersect:
                crossings += 1

    return 1 if crossings % 2 == 1 else 0


def point_in_polygon_winding(point, polygon):
    """
    Winding number algorithm for point-in-polygon.

    Returns: 1 if inside, -1 if boundary, 0 if outside
    """
    n = len(polygon)

    # Check boundary
    for i in range(n):
        j = (i + 1) % n
        if point_on_segment(point, polygon[i], polygon[j]):
            return -1

    winding = 0
    px, py = point

    for i in range(n):
        j = (i + 1) % n
        yi, yj = polygon[i][1], polygon[j][1]

        if yi <= py:
            if yj > py:
                # Upward crossing
                if cross_2d(polygon[i], polygon[j], point) > 0:
                    winding += 1
        else:
            if yj <= py:
                # Downward crossing
                if cross_2d(polygon[i], polygon[j], point) < 0:
                    winding -= 1

    return 1 if winding != 0 else 0


# Test with various polygons
# Square
square = [(0,0), (4,0), (4,4), (0,4)]

# L-shaped (concave)
l_shape = [(0,0), (4,0), (4,2), (2,2), (2,4), (0,4)]

tests = [
    (square, (2, 2), 1, "center of square"),
    (square, (5, 2), 0, "outside square"),
    (square, (2, 0), -1, "on edge of square"),
    (square, (0, 0), -1, "on vertex of square"),
    (l_shape, (1, 1), 1, "inside L"),
    (l_shape, (3, 3), 0, "outside L (concave region)"),
    (l_shape, (3, 1), 1, "inside L (right part)"),
]

print("Point-in-Polygon Tests:")
for poly, point, expected, desc in tests:
    r1 = point_in_polygon_ray(point, poly)
    r2 = point_in_polygon_winding(point, poly)
    labels = {1: "inside", 0: "outside", -1: "boundary"}
    status = "PASS" if r1 == expected else "FAIL"
    print(f"  [{status}] {desc}: ray={labels[r1]}, "
          f"winding={labels[r2]}")
```

**Ray Casting vs Winding Number:**
- Ray casting: simpler, counts boundary crossings
- Winding number: more robust for self-intersecting polygons
- Both are O(n) per query

**Complexity:**
- Time: O(n) per query, where n = number of polygon edges
- Space: O(1) extra
- For many queries: preprocess with triangulation for O(log n) per query'''),

    ("thinking/algorithms", r'''Describe the Voronoi diagram and implement a simple algorithm to compute the Voronoi diagram for a set of 2D points. Show how to query the nearest site for any point.''', r'''<think>
A Voronoi diagram partitions the plane into regions (cells), one per input point (site). Each cell contains all points closer to its site than to any other site.

Properties:
- Each Voronoi cell is a convex polygon (possibly unbounded)
- Voronoi edges are equidistant from exactly two sites
- Voronoi vertices are equidistant from exactly three (or more) sites
- The dual of the Voronoi diagram is the Delaunay triangulation

Algorithms:
1. Fortune's sweep line: O(n log n) -- the standard efficient algorithm
2. Incremental insertion: O(n^2) average
3. Divide and conquer: O(n log n)
4. Brute force (for each pixel, find nearest site): O(n * pixels)

Fortune's algorithm is complex to implement correctly. For educational purposes, I will implement:
1. A brute-force approach for visualization
2. The nearest-site query (which is the practical use of Voronoi)
3. Construction using scipy (if available) or a simplified approach

For the nearest-site query without the full Voronoi diagram, a KD-tree gives O(log n) per query after O(n log n) preprocessing.

I will implement:
- Brute-force Voronoi cell computation (bounded to a rectangle)
- KD-tree for nearest neighbor queries
- Show the connection to Delaunay triangulation
</think>

**Voronoi Diagram -- Concepts and Nearest-Site Queries**

```python
import math
from collections import defaultdict


def nearest_site_brute(query, sites):
    """Find the nearest site to a query point. O(n) per query."""
    best_dist = float('inf')
    best_idx = -1
    for i, s in enumerate(sites):
        d = math.sqrt((query[0]-s[0])**2 + (query[1]-s[1])**2)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx, best_dist


class KDNode:
    def __init__(self, point, idx, left=None, right=None, axis=0):
        self.point = point
        self.idx = idx
        self.left = left
        self.right = right
        self.axis = axis


class KDTree:
    """KD-Tree for efficient nearest neighbor queries."""

    def __init__(self, points):
        indexed = list(enumerate(points))
        self.root = self._build(indexed, 0)

    def _build(self, points, depth):
        if not points:
            return None
        axis = depth % 2
        points.sort(key=lambda p: p[1][axis])
        mid = len(points) // 2
        idx, point = points[mid]
        return KDNode(
            point=point, idx=idx,
            left=self._build(points[:mid], depth + 1),
            right=self._build(points[mid+1:], depth + 1),
            axis=axis
        )

    def nearest(self, query):
        """Find nearest point to query. Returns (index, distance)."""
        self.best_dist = float('inf')
        self.best_idx = -1
        self._search(self.root, query)
        return self.best_idx, self.best_dist

    def _search(self, node, query):
        if node is None:
            return

        d = math.sqrt(sum((q-p)**2 for q, p in zip(query, node.point)))
        if d < self.best_dist:
            self.best_dist = d
            self.best_idx = node.idx

        axis = node.axis
        diff = query[axis] - node.point[axis]

        # Search the side containing the query point first
        if diff <= 0:
            first, second = node.left, node.right
        else:
            first, second = node.right, node.left

        self._search(first, query)

        # Check if we need to search the other side
        if abs(diff) < self.best_dist:
            self._search(second, query)


def compute_voronoi_grid(sites, bounds, resolution=50):
    """
    Compute Voronoi diagram by assigning each grid cell to nearest site.

    Args:
        sites: list of (x, y) points
        bounds: (x_min, y_min, x_max, y_max)
        resolution: grid cells per axis
    Returns:
        2D grid of site indices
    """
    x_min, y_min, x_max, y_max = bounds
    kd = KDTree(sites)
    grid = []

    for row in range(resolution):
        y = y_min + (y_max - y_min) * row / resolution
        row_data = []
        for col in range(resolution):
            x = x_min + (x_max - x_min) * col / resolution
            idx, _ = kd.nearest((x, y))
            row_data.append(idx)
        grid.append(row_data)

    return grid


# Example
sites = [(1, 1), (5, 1), (3, 5), (7, 4), (2, 7)]

print("Voronoi Sites:")
for i, s in enumerate(sites):
    print(f"  Site {i}: {s}")

# Build KD-Tree
kd = KDTree(sites)

# Query some points
queries = [(0, 0), (3, 3), (6, 2), (4, 6)]
print("\nNearest site queries:")
for q in queries:
    idx_kd, dist_kd = kd.nearest(q)
    idx_bf, dist_bf = nearest_site_brute(q, sites)
    match = idx_kd == idx_bf
    print(f"  Query {q}: nearest=Site {idx_kd} "
          f"(dist={dist_kd:.2f}) match={match}")

# ASCII visualization of Voronoi diagram
grid = compute_voronoi_grid(sites, (0, 0, 8, 8), resolution=20)
symbols = "0123456789ABCDEF"
print("\nVoronoi diagram (ASCII):")
for row in reversed(grid):
    print("  " + "".join(symbols[c] for c in row))

print("\nKD-Tree Properties:")
print(f"  Construction: O(n log n)")
print(f"  Nearest query: O(log n) average")
print(f"  Voronoi = partition where each cell has all points")
print(f"  closest to one particular site")
```

**Voronoi Diagram Properties:**
- Each cell is a convex polygon (possibly unbounded)
- Dual graph = Delaunay triangulation
- Voronoi edges are perpendicular bisectors of Delaunay edges
- Applications: nearest facility, spatial partitioning, mesh generation

**Complexity:**
- Fortune's algorithm: O(n log n) construction
- KD-tree: O(n log n) build, O(log n) nearest-neighbor query
- Brute force nearest: O(n) per query
- Grid-based visualization: O(resolution^2 * log n)'''),
]
