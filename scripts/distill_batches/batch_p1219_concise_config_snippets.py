"""
Concise answer training pairs - Quick config/snippet answers
Teaches the model that short, direct answers are often best.
"""

pairs = [
    {
        "instruction": r'''Give me a basic .gitignore for a Python project.''',
        "output": r'''__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
venv/
.env
*.log'''
    },
    {
        "instruction": r'''Give me a minimal Dockerfile for a Python app.''',
        "output": r'''FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]'''
    },
    {
        "instruction": r'''<think>
GitHub Actions for Python tests. Keep it minimal but functional -- needs checkout, setup-python, install, pytest.
</think>

Give me a basic GitHub Actions workflow to run Python tests.''',
        "output": r'''name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest'''
    },
    {
        "instruction": r'''What does a typical .env file look like for a web app?''',
        "output": r'''DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
REDIS_URL=redis://localhost:6379
SECRET_KEY=change-me-in-production
DEBUG=true
PORT=8000
ALLOWED_HOSTS=localhost,127.0.0.1
LOG_LEVEL=info
API_KEY=your-api-key-here'''
    },
    {
        "instruction": r'''Give me a basic tsconfig.json.''',
        "output": r'''{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true,
    "esModuleInterop": true,
    "outDir": "dist",
    "rootDir": "src",
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"],
  "exclude": ["node_modules"]
}'''
    },
]
