PAIRS = [
    ("thinking/algorithms", r'''Implement the Convex Hull algorithm using Graham Scan: given a set of 2D points, find the smallest convex polygon that contains all the points.''', r'''<think>
The convex hull is the smallest convex polygon enclosing all points. My first thought was a gift-wrapping (Jarvis march) approach: start at the leftmost point and repeatedly find the next hull point by checking all candidates. But that is O(n * h) where h is the number of hull points, which can be O(n^2) in the worst case when many points are on the hull.

Graham Scan is better at O(n log n). The algorithm sorts points by polar angle relative to an anchor (the lowest point), then processes them in order while maintaining a stack. The key invariant: the stack always forms a valid convex hull of the points processed so far. When a new point causes a right turn (clockwise) with the last two stack points, the middle point cannot be on the hull, so we pop it.

Hmm, how do I detect left vs. right turns? The cross product cross(O, A, B) = (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x). Positive means counter-clockwise (left turn), negative means clockwise (right turn), zero means collinear. I keep only left turns, popping on right turns and collinear cases. Wait -- should I keep or discard collinear points? If I use cross <= 0 as the pop condition, I discard collinear points, giving the minimal hull. If I used cross < 0 instead, I would keep collinear points on the hull boundary. The problem asks for the polygon, so discarding collinear points (using <=) is standard.

One subtlety I initially overlooked: when sorting by polar angle, if two points have the same angle relative to the anchor, I need a tiebreaker. I sort by distance from the anchor, so the closer point comes first. Actually, I considered sorting by distance in reverse (farther first), but that would cause problems: the closer point would be processed after the farther one and potentially pop it. Sorting closer points first ensures they get popped in favor of the farther collinear point, which is the correct hull vertex.

I will also implement Andrew's monotone chain as an alternative -- it sorts by coordinates instead of polar angle, which avoids the atan2 floating-point issues entirely. It builds the lower and upper hulls separately and concatenates them.

Time: O(n log n) dominated by sorting. Space: O(n) for the hull stack.
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
Two line segments intersect if they share at least one point. My first thought was to compute the intersection of the two infinite lines and check if it falls within both segments. But wait -- this approach fails when the lines are parallel or collinear, requiring special cases that are easy to get wrong with floating-point arithmetic.

The orientation-based approach is more robust. For segments AB and CD, I compute four orientations:
- d1 = orientation(A, B, C) and d2 = orientation(A, B, D): are C and D on opposite sides of line AB?
- d3 = orientation(C, D, A) and d4 = orientation(C, D, B): are A and B on opposite sides of line CD?

If d1 and d2 have different signs AND d3 and d4 have different signs, the segments properly cross each other. This handles the general case cleanly with no floating point at all (since orientation is just a cross product, which is exact for integer coordinates).

Hmm, but what about the degenerate cases? If any orientation is zero, a point lies exactly on the line containing the other segment. I initially thought I could just check d1*d2 < 0 && d3*d4 < 0, but that misses cases like T-junctions (one endpoint touching the other segment) and collinear overlapping segments. For the collinear cases, I need an "on segment" test that checks both collinearity (cross product == 0) and bounding box containment.

One edge case that tripped me up: two collinear segments that share exactly one endpoint, like (0,0)-(1,0) and (1,0)-(2,0). Here d1 = d2 = d3 = d4 = 0 (all collinear), and the on_segment test correctly identifies that (1,0) lies on both segments. So the segments do intersect -- at a single point.

I should also implement finding the actual intersection point for non-degenerate crossings. This uses the parametric form of the lines and solves for the parameter t. Since the collinear/parallel case has denom = 0, I return None in that case because there is no unique intersection point.

The orientation test runs in O(1) time, making this very efficient for individual segment pair tests. For n segments, the Bentley-Ottmann sweep line algorithm finds all intersections in O((n + k) log n) where k is the number of intersections.
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
The brute force checks all O(n^2) pairs. Could I use spatial hashing or a grid to speed this up? Hmm, a grid with cell size delta would work if I knew delta in advance, but delta is exactly what I am trying to find. Divide and conquer avoids this chicken-and-egg problem.

The algorithm sorts points by x, splits into halves, recursively finds the closest pair in each half, then checks for closer "split" pairs crossing the dividing line. The split-pair check is the subtle part. I only need to consider points within delta of the dividing line (the "strip"). But even the strip could contain O(n) points in the worst case, so naively checking all strip pairs would still be O(n^2).

The key insight -- which I found counterintuitive at first -- is that each strip point only needs to compare with at most 7 neighbors when sorted by y-coordinate. Why? Consider a delta x 2*delta rectangle centered on the dividing line. On each side, within a delta x delta square, at most 4 points can have pairwise distance >= delta (by a circle-packing argument). So the rectangle contains at most 8 points total, meaning each point has at most 7 potential closer neighbors.

Wait, I need to be more precise. The rectangle has width 2*delta (delta on each side of the dividing line) and height delta (the y-range we check above each point). Actually, the proof considers that within a delta x delta square, we can place at most 4 points with pairwise distance >= delta (one at each corner). Two such squares side by side give at most 8 points total, hence 7 neighbors to check per point.

This gives recurrence T(n) = 2T(n/2) + O(n log n) because I sort the strip by y at each level. That solves to O(n log^2 n). I considered the optimization of merging y-sorted lists during recursion (like merge sort) to avoid re-sorting, which would bring it down to O(n log n). But the simpler O(n log^2 n) version is clear enough for educational purposes.

For base cases, when n <= 3, I just check all pairs directly since the overhead of recursion would dominate.
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
Point-in-polygon testing for arbitrary (possibly concave) polygons. My first thought was to triangulate the polygon and test each triangle, but triangulation is complex and overkill for this. The ray casting algorithm is much simpler.

The idea: cast a horizontal ray to the right from the query point and count how many polygon edges it crosses. Odd crossings means inside, even means outside. This works because each boundary crossing toggles the inside/outside state, and the ray starts from "outside" at infinity.

But the edge cases are where things get tricky. What if the ray passes exactly through a vertex? I could get a double-count (the ray "crosses" two edges that share that vertex). The standard fix is to count an edge crossing only when one endpoint is strictly above the ray level and the other is at or below. This way, a vertex at the ray level is counted for exactly one of its two edges. Hmm, I initially thought I should use strict inequality on both sides, but actually using strict-above on one side and non-strict on the other is the key -- it handles vertices consistently without double-counting.

Wait, there is another case: the ray could be collinear with an entire edge. If the point is on that edge, we should report "boundary." If it is not on the edge but the ray grazes it, the even/odd count might be wrong. Actually, if I check for boundary points first (before the crossing count), I can handle this cleanly -- report "boundary" immediately and skip the ray casting entirely for those points.

I considered the winding number algorithm as an alternative. It counts how many times the polygon wraps around the point. For simple (non-self-intersecting) polygons, winding number != 0 is equivalent to odd crossings. But for self-intersecting polygons, they can disagree -- the winding number correctly handles the "even-odd" vs "nonzero" fill rules. Since the problem says "simple polygon," both methods give the same result, but I will implement both for comparison.

Time: O(n) per query where n is the number of edges. For many queries against the same polygon, preprocessing with triangulation could give O(log n) per query.
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
A Voronoi diagram partitions the plane into regions where each region contains all points closest to a particular site. My first instinct is to implement Fortune's sweep line algorithm, but that is notoriously complex to code correctly -- it involves a beach line of parabolic arcs and a priority queue of circle events. For an educational implementation, I should prioritize clarity.

Could I compute the diagram by intersecting half-planes? Each Voronoi cell is the intersection of n-1 half-planes (one for each other site, defined by the perpendicular bisector). But computing the intersection of n-1 half-planes is O(n log n) per cell, giving O(n^2 log n) total. That is worse than Fortune's O(n log n) but simpler to understand.

Actually, for practical purposes, the most common use of Voronoi diagrams is nearest-site queries -- finding which site is closest to a given point. I do not need the explicit diagram edges for that. A KD-tree gives O(log n) per query after O(n log n) construction, which is much simpler to implement than the full Voronoi construction.

Hmm, but the problem asks me to "compute" the Voronoi diagram. Let me compromise: I will implement a brute-force grid-based visualization (assign each grid cell to its nearest site) and a KD-tree for efficient queries. The grid approach is O(resolution^2 * n) with brute force, but using the KD-tree it becomes O(resolution^2 * log n).

One property worth noting: the Voronoi diagram is the dual of the Delaunay triangulation. Voronoi edges are perpendicular bisectors of Delaunay edges, and Voronoi vertices are circumcenters of Delaunay triangles. Therefore computing one gives you the other. I considered implementing Delaunay triangulation first and deriving the Voronoi from it, but that is actually more complex than the direct approach for visualization purposes.

For the KD-tree, the key optimization is: when searching for the nearest neighbor, I first explore the subtree containing the query point, then only explore the other subtree if the splitting plane is closer than the current best distance. This pruning is what makes average-case queries O(log n).
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
