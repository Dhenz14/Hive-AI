"""Django — models, views, ORM queries, REST framework, and production patterns."""

PAIRS = [
    (
        "python/django-models",
        "Show Django model patterns: field types, relationships, managers, querysets, signals, and model methods.",
        """Django model patterns for production:

```python
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models import Q, F, Count, Sum, Avg, Window
from django.db.models.functions import Rank
from uuid import uuid4

# --- Base model with common fields ---

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class SoftDeleteModel(TimeStampedModel):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # Include deleted

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    class Meta:
        abstract = True


# --- User model ---

class User(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "is_active"]),
        ]

    def __str__(self):
        return self.email


# --- Product with custom manager ---

class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, stock__gt=0)

    def by_category(self, category):
        return self.filter(category=category)

    def expensive(self, min_price=100):
        return self.filter(price__gte=min_price)

    def with_review_stats(self):
        return self.annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews"),
        )

class Product(TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    category = models.ForeignKey(
        "Category", on_delete=models.PROTECT, related_name="products",
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    tags = models.ManyToManyField("Tag", blank=True, related_name="products")

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "is_active", "price"]),
            models.Index(fields=["slug"]),
        ]

    @property
    def is_in_stock(self):
        return self.stock > 0

    def reduce_stock(self, quantity):
        if self.stock < quantity:
            raise ValueError(f"Insufficient stock: {self.stock} < {quantity}")
        Product.objects.filter(pk=self.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )
        self.refresh_from_db(fields=["stock"])


# --- Order with items ---

class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    def confirm(self):
        if self.status != self.Status.PENDING:
            raise ValueError(f"Cannot confirm order in {self.status} state")
        self.status = self.Status.CONFIRMED
        self.save(update_fields=["status", "updated_at"])

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.price * self.quantity


# --- Advanced queries ---

# Top customers by spending
top_customers = (
    User.objects
    .annotate(
        total_spent=Sum("orders__items__price"),
        order_count=Count("orders", distinct=True),
    )
    .filter(total_spent__gt=0)
    .order_by("-total_spent")[:10]
)

# Products with ranking by category
ranked = Product.objects.annotate(
    category_rank=Window(
        expression=Rank(),
        partition_by=F("category"),
        order_by=F("price").desc(),
    )
)

# Complex filter with Q objects
results = Product.objects.filter(
    Q(name__icontains="laptop") | Q(description__icontains="laptop"),
    is_active=True,
    price__range=(500, 2000),
).select_related("category").prefetch_related("tags")
```

Patterns:
1. **Abstract base models** — timestamps, soft delete reused across models
2. **Custom managers/querysets** — chainable, reusable query filters
3. **`F()` expressions** — atomic updates without race conditions
4. **`select_related`/`prefetch_related`** — prevent N+1 queries
5. **TextChoices** — type-safe status enums with labels"""
    ),
    (
        "python/django-rest-framework",
        "Show Django REST Framework patterns: serializers, viewsets, permissions, filtering, and pagination.",
        """Django REST Framework production patterns:

```python
from rest_framework import serializers, viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import CursorPagination
from django_filters import rest_framework as django_filters
from django.db.models import Prefetch

# --- Serializers ---

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "price",
            "category", "category_name", "stock", "is_active",
            "avg_rating", "review_count", "created_at",
        ]
        read_only_fields = ["slug", "created_at"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be positive")
        return value

class OrderCreateSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=serializers.DictField(), min_length=1
    )
    notes = serializers.CharField(required=False, default="")

    def validate_items(self, items):
        for item in items:
            if "product_id" not in item or "quantity" not in item:
                raise serializers.ValidationError(
                    "Each item needs product_id and quantity"
                )
            if item["quantity"] < 1:
                raise serializers.ValidationError("Quantity must be >= 1")
        return items

    def create(self, validated_data):
        user = self.context["request"].user
        items_data = validated_data.pop("items")

        order = Order.objects.create(user=user, **validated_data)
        for item in items_data:
            product = Product.objects.get(pk=item["product_id"])
            OrderItem.objects.create(
                order=order, product=product,
                quantity=item["quantity"], price=product.price,
            )
            product.reduce_stock(item["quantity"])
        return order

class OrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "notes", "items", "total", "created_at"]

    def get_items(self, obj):
        return [
            {
                "product": item.product.name,
                "quantity": item.quantity,
                "price": str(item.price),
                "subtotal": str(item.subtotal),
            }
            for item in obj.items.select_related("product").all()
        ]


# --- Filters ---

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    category = django_filters.CharFilter(field_name="category__slug")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = ["is_active", "category"]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__gt=0)
        return queryset.filter(stock=0)


# --- Pagination ---

class ProductCursorPagination(CursorPagination):
    page_size = 20
    ordering = "-created_at"
    cursor_query_param = "cursor"


# --- Permissions ---

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


# --- ViewSets ---

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = ProductCursorPagination
    filterset_class = ProductFilter
    filter_backends = [
        django_filters.DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "name"]

    def get_queryset(self):
        return (
            Product.objects
            .active()
            .with_review_stats()
            .select_related("category")
            .prefetch_related("tags")
        )

    @action(detail=True, methods=["post"])
    def add_review(self, request, pk=None):
        product = self.get_object()
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product, user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return (
            Order.objects
            .filter(user=self.request.user)
            .prefetch_related(
                Prefetch("items", queryset=OrderItem.objects.select_related("product"))
            )
        )

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status not in ["pending", "confirmed"]:
            return Response(
                {"error": "Cannot cancel order in this state"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "cancelled"
        order.save(update_fields=["status"])
        return Response(OrderSerializer(order).data)
```

DRF patterns:
1. **Custom querysets** — chain filters in `get_queryset` with select/prefetch
2. **Separate create/read serializers** — different fields for input vs output
3. **`@action`** — custom endpoints on viewsets
4. **Cursor pagination** — efficient for infinite scroll (no offset counting)
5. **FilterSet** — declarative filtering with django-filter"""
    ),
]
