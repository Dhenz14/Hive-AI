"""Flask — application factory, blueprints, extensions, and production patterns."""

PAIRS = [
    (
        "python/flask-patterns",
        "Show Flask application patterns: application factory, blueprints, extensions, error handling, and configuration.",
        '''Flask production application patterns:

```python
# --- Application Factory ---

# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)

def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)

    # Load config
    config_map = {
        "development": "app.config.DevelopmentConfig",
        "testing": "app.config.TestingConfig",
        "production": "app.config.ProductionConfig",
    }
    app.config.from_object(config_map[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    limiter.init_app(app)

    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.users import users_bp
    from app.api.products import products_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(products_bp, url_prefix="/api/products")

    # Register error handlers
    register_error_handlers(app)

    # Register CLI commands
    register_cli_commands(app)

    return app


# --- Config ---

# app/config.py
import os

class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///dev.db"
    )

class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,
        "pool_recycle": 300,
    }

class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# --- Blueprint ---

# app/api/users.py
from flask import Blueprint, request, jsonify, abort
from app.models import User
from app.schemas import UserSchema, UserCreateSchema
from app.auth import login_required, admin_required

users_bp = Blueprint("users", __name__)

@users_bp.route("/", methods=["GET"])
@login_required
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = User.query.filter_by(is_active=True).paginate(
        page=page, per_page=min(per_page, 100), error_out=False,
    )

    return jsonify({
        "items": UserSchema(many=True).dump(pagination.items),
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })

@users_bp.route("/", methods=["POST"])
@admin_required
def create_user():
    schema = UserCreateSchema()
    data = schema.load(request.get_json())

    if User.query.filter_by(email=data["email"]).first():
        abort(409, "Email already registered")

    user = User(**data)
    db.session.add(user)
    db.session.commit()

    return jsonify(UserSchema().dump(user)), 201

@users_bp.route("/<uuid:user_id>", methods=["GET"])
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(UserSchema().dump(user))

@users_bp.route("/<uuid:user_id>", methods=["PUT"])
@login_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = UserSchema(partial=True).load(request.get_json())
    for key, value in data.items():
        setattr(user, key, value)
    db.session.commit()
    return jsonify(UserSchema().dump(user))


# --- Error handlers ---

def register_error_handlers(app: Flask):
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad Request", "message": str(error)}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not Found", "message": str(error)}), 404

    @app.errorhandler(422)
    def validation_error(error):
        return jsonify({"error": "Validation Error",
                        "details": error.description}), 422

    @app.errorhandler(429)
    def rate_limited(error):
        return jsonify({"error": "Rate Limited",
                        "message": "Too many requests"}), 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({"error": "Internal Server Error"}), 500


# --- Auth decorator ---

# app/auth.py
from functools import wraps
from flask import request, g, abort

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            abort(401, "Authentication required")
        try:
            payload = verify_jwt(token)
            g.current_user = User.query.get(payload["sub"])
            if not g.current_user:
                abort(401, "User not found")
        except Exception:
            abort(401, "Invalid token")
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if "admin" not in g.current_user.roles:
            abort(403, "Admin access required")
        return f(*args, **kwargs)
    return decorated


# --- CLI commands ---

def register_cli_commands(app: Flask):
    @app.cli.command("seed")
    def seed_db():
        """Seed database with sample data."""
        ...

    @app.cli.command("create-admin")
    def create_admin():
        """Create admin user."""
        ...
```

Flask patterns:
1. **Application factory** — `create_app()` for testability and multiple configs
2. **Blueprints** — modular route organization by feature
3. **Extension pattern** — init extensions globally, bind to app in factory
4. **`g` object** — request-scoped globals (current user)
5. **CLI commands** — `@app.cli.command` for admin tasks'''
    ),
]
"""
