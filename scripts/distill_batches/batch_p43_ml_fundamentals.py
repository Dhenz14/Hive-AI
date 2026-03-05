"""ML fundamentals — scikit-learn, feature engineering, model evaluation, and pipelines."""

PAIRS = [
    (
        "ml/sklearn-pipelines",
        "Show scikit-learn pipeline patterns: preprocessing, feature engineering, model selection, cross-validation, and hyperparameter tuning.",
        '''Scikit-learn production ML pipeline:

```python
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import (
    StandardScaler, OneHotEncoder, OrdinalEncoder,
    FunctionTransformer, PolynomialFeatures,
)
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.model_selection import (
    cross_val_score, StratifiedKFold, GridSearchCV,
    RandomizedSearchCV, learning_curve,
)
from sklearn.ensemble import (
    RandomForestClassifier, GradientBoostingClassifier,
    VotingClassifier, StackingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, precision_recall_curve,
    make_scorer,
)
from sklearn.base import BaseEstimator, TransformerMixin
import joblib

# --- Custom transformer ---

class DateFeatureExtractor(BaseEstimator, TransformerMixin):
    """Extract features from datetime columns."""
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        df = X.copy()
        for col in df.select_dtypes(include=["datetime64"]).columns:
            df[f"{col}_year"] = df[col].dt.year
            df[f"{col}_month"] = df[col].dt.month
            df[f"{col}_dayofweek"] = df[col].dt.dayofweek
            df[f"{col}_hour"] = df[col].dt.hour
            df[f"{col}_is_weekend"] = df[col].dt.dayofweek >= 5
            df = df.drop(columns=[col])
        return df

class OutlierClipper(BaseEstimator, TransformerMixin):
    """Clip outliers to IQR bounds."""
    def __init__(self, factor=1.5):
        self.factor = factor

    def fit(self, X, y=None):
        Q1 = np.percentile(X, 25, axis=0)
        Q3 = np.percentile(X, 75, axis=0)
        IQR = Q3 - Q1
        self.lower_ = Q1 - self.factor * IQR
        self.upper_ = Q3 + self.factor * IQR
        return self

    def transform(self, X):
        return np.clip(X, self.lower_, self.upper_)


# --- Column transformer (different preprocessing per column type) ---

numeric_features = ["age", "income", "credit_score", "balance"]
categorical_features = ["employment", "education", "marital_status"]
ordinal_features = ["risk_level"]  # low < medium < high

preprocessor = ColumnTransformer(
    transformers=[
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("outlier", OutlierClipper()),
            ("scaler", StandardScaler()),
        ]), numeric_features),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical_features),
        ("ord", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OrdinalEncoder(categories=[["low", "medium", "high"]])),
        ]), ordinal_features),
    ],
    remainder="drop",
)


# --- Full pipeline ---

pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("feature_selection", SelectKBest(mutual_info_classif, k=20)),
    ("classifier", GradientBoostingClassifier(random_state=42)),
])


# --- Cross-validation ---

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="roc_auc")
print(f"ROC-AUC: {scores.mean():.3f} (+/- {scores.std():.3f})")


# --- Hyperparameter tuning ---

param_grid = {
    "feature_selection__k": [10, 20, 30],
    "classifier__n_estimators": [100, 200, 500],
    "classifier__max_depth": [3, 5, 7],
    "classifier__learning_rate": [0.01, 0.1, 0.2],
    "classifier__min_samples_leaf": [5, 10, 20],
}

search = RandomizedSearchCV(
    pipeline, param_grid, n_iter=50,
    scoring="roc_auc", cv=cv, n_jobs=-1,
    random_state=42, verbose=1,
)
search.fit(X_train, y_train)

print(f"Best score: {search.best_score_:.3f}")
print(f"Best params: {search.best_params_}")


# --- Model evaluation ---

y_pred = search.predict(X_test)
y_proba = search.predict_proba(X_test)[:, 1]

print(classification_report(y_test, y_pred))
print(f"ROC-AUC: {roc_auc_score(y_test, y_proba):.3f}")

# --- Save/load model ---

joblib.dump(search.best_estimator_, "model_v1.joblib")
model = joblib.load("model_v1.joblib")
predictions = model.predict(new_data)
```

Pipeline patterns:
1. **ColumnTransformer** — different preprocessing per feature type
2. **Custom transformers** — extend `BaseEstimator` + `TransformerMixin`
3. **Feature selection** — `SelectKBest` inside pipeline prevents data leakage
4. **RandomizedSearchCV** — faster than GridSearch for large param spaces
5. **Stratified CV** — maintain class balance across folds'''
    ),
    (
        "ml/nlp-basics",
        "Show NLP patterns in Python: text preprocessing, TF-IDF, word embeddings, sentiment analysis, and text classification.",
        '''NLP patterns from preprocessing to classification:

```python
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from typing import Callable

# --- Text preprocessing ---

def clean_text(text: str) -> str:
    """Standard text cleaning pipeline."""
    text = text.lower()
    text = re.sub(r"https?://\\S+|www\\.\\S+", "", text)  # Remove URLs
    text = re.sub(r"<.*?>", "", text)                       # Remove HTML
    text = re.sub(r"[^a-zA-Z\\s]", "", text)               # Keep only letters
    text = re.sub(r"\\s+", " ", text).strip()               # Normalize whitespace
    return text

def tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer with stopword removal."""
    STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be",
                 "been", "being", "have", "has", "had", "do", "does",
                 "did", "will", "would", "could", "should", "may",
                 "might", "shall", "can", "to", "of", "in", "for",
                 "on", "with", "at", "by", "from", "as", "into",
                 "through", "during", "before", "after", "and", "but",
                 "or", "not", "no", "this", "that", "it", "its"}
    words = text.lower().split()
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# --- TF-IDF text classification ---

text_classifier = Pipeline([
    ("tfidf", TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),      # Unigrams and bigrams
        min_df=5,                 # Minimum document frequency
        max_df=0.95,              # Remove very common terms
        sublinear_tf=True,        # Apply log normalization
        preprocessor=clean_text,
        tokenizer=tokenize,
    )),
    ("classifier", LogisticRegression(
        C=1.0, max_iter=1000, class_weight="balanced",
    )),
])

# Train
text_classifier.fit(train_texts, train_labels)

# Predict
predictions = text_classifier.predict(test_texts)
probabilities = text_classifier.predict_proba(test_texts)
print(classification_report(test_labels, predictions))


# --- Feature importance (most informative words) ---

def top_features_per_class(pipeline, class_names, n=10):
    """Show most important features per class."""
    tfidf = pipeline.named_steps["tfidf"]
    clf = pipeline.named_steps["classifier"]
    feature_names = tfidf.get_feature_names_out()

    for i, class_name in enumerate(class_names):
        if clf.coef_.ndim == 1:
            coef = clf.coef_
        else:
            coef = clf.coef_[i]

        top_indices = coef.argsort()[-n:][::-1]
        top_features = [(feature_names[j], coef[j]) for j in top_indices]
        print(f"\\n{class_name}:")
        for feat, score in top_features:
            print(f"  {feat}: {score:.3f}")


# --- Simple sentiment with lexicon ---

POSITIVE_WORDS = {"good", "great", "excellent", "amazing", "love",
                  "best", "wonderful", "fantastic", "awesome", "happy"}
NEGATIVE_WORDS = {"bad", "terrible", "awful", "horrible", "hate",
                  "worst", "poor", "disappointing", "sad", "angry"}

def lexicon_sentiment(text: str) -> dict:
    """Simple lexicon-based sentiment analysis."""
    words = set(text.lower().split())
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return {"sentiment": "neutral", "score": 0.0}
    score = (pos - neg) / total
    sentiment = "positive" if score > 0 else "negative" if score < 0 else "neutral"
    return {"sentiment": sentiment, "score": score}


# --- Text similarity with TF-IDF ---

def find_similar(query: str, documents: list[str],
                 top_k: int = 5) -> list[tuple[int, float]]:
    """Find most similar documents using cosine similarity."""
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(documents + [query])
    query_vec = tfidf_matrix[-1]
    doc_vecs = tfidf_matrix[:-1]

    similarities = cosine_similarity(query_vec, doc_vecs).flatten()
    top_indices = similarities.argsort()[-top_k:][::-1]
    return [(int(i), float(similarities[i])) for i in top_indices]
```

NLP pipeline:
1. **Clean** — lowercase, remove URLs/HTML/special chars
2. **Tokenize** — split into words, remove stopwords
3. **Vectorize** — TF-IDF with n-grams for ML, embeddings for DL
4. **Classify** — LogisticRegression for baseline, transformers for SOTA
5. **Evaluate** — precision, recall, F1 per class'''
    ),
    (
        "ml/model-evaluation",
        "Show ML model evaluation patterns: metrics selection, cross-validation, learning curves, calibration, and fairness metrics.",
        '''ML model evaluation beyond accuracy:

```python
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score,
    confusion_matrix, classification_report,
    mean_squared_error, mean_absolute_error, r2_score,
    log_loss, brier_score_loss,
)
from sklearn.model_selection import learning_curve, cross_validate
from sklearn.calibration import calibration_curve, CalibratedClassifierCV

# --- Classification metrics ---

def evaluate_classifier(y_true, y_pred, y_proba=None) -> dict:
    """Comprehensive classification evaluation."""
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average="weighted"),
        "recall": recall_score(y_true, y_pred, average="weighted"),
        "f1": f1_score(y_true, y_pred, average="weighted"),
    }

    if y_proba is not None:
        if y_proba.ndim == 2:
            # Multi-class
            metrics["roc_auc"] = roc_auc_score(
                y_true, y_proba, multi_class="ovr", average="weighted"
            )
            metrics["log_loss"] = log_loss(y_true, y_proba)
        else:
            # Binary
            metrics["roc_auc"] = roc_auc_score(y_true, y_proba)
            metrics["avg_precision"] = average_precision_score(y_true, y_proba)
            metrics["brier_score"] = brier_score_loss(y_true, y_proba)

    return metrics


# --- Confusion matrix analysis ---

def analyze_confusion_matrix(y_true, y_pred, labels=None):
    """Detailed confusion matrix analysis."""
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    n_classes = cm.shape[0]

    # Per-class metrics
    results = []
    for i in range(n_classes):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        tn = cm.sum() - tp - fp - fn

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        results.append({
            "class": labels[i] if labels else i,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
        })

    return results


# --- Learning curve (detect over/underfitting) ---

def plot_learning_curve_data(estimator, X, y, cv=5):
    """Generate learning curve data."""
    train_sizes, train_scores, val_scores = learning_curve(
        estimator, X, y,
        train_sizes=np.linspace(0.1, 1.0, 10),
        cv=cv,
        scoring="roc_auc",
        n_jobs=-1,
    )

    return {
        "train_sizes": train_sizes.tolist(),
        "train_mean": train_scores.mean(axis=1).tolist(),
        "train_std": train_scores.std(axis=1).tolist(),
        "val_mean": val_scores.mean(axis=1).tolist(),
        "val_std": val_scores.std(axis=1).tolist(),
    }
    # If train >> val: overfitting (need regularization/more data)
    # If train ≈ val but both low: underfitting (need more features/complex model)


# --- Metric selection guide ---

METRIC_GUIDE = {
    "balanced_classes": {
        "primary": "accuracy",
        "additional": ["f1_macro", "roc_auc"],
    },
    "imbalanced_classes": {
        "primary": "f1_weighted or average_precision",
        "additional": ["recall (if false negatives costly)", "precision (if false positives costly)"],
        "avoid": "accuracy (misleading with class imbalance)",
    },
    "ranking": {
        "primary": "roc_auc",
        "additional": ["average_precision", "ndcg"],
    },
    "regression": {
        "primary": "rmse (interpretable units)",
        "additional": ["mae (robust to outliers)", "r2 (explained variance)"],
    },
    "calibration": {
        "primary": "brier_score",
        "additional": ["calibration_curve", "log_loss"],
    },
}
```

Evaluation strategy:
1. **Holdout** — train/val/test split (quick iteration)
2. **Cross-validation** — k-fold for reliable estimates
3. **Stratified** — maintain class distribution in splits
4. **Learning curves** — diagnose over/underfitting
5. **Calibration** — check if predicted probabilities are trustworthy
6. **Metric selection** — match metric to business objective'''
    ),
]
