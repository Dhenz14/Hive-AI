"""Data visualization — matplotlib, seaborn, and plotting patterns."""

PAIRS = [
    (
        "python/matplotlib-patterns",
        "Show matplotlib and seaborn patterns: chart types, styling, subplots, annotations, and publication-quality figures.",
        """Data visualization patterns with matplotlib and seaborn:

```python
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import numpy as np
import pandas as pd

# --- Global styling ---

plt.style.use("seaborn-v0_8-whitegrid")
sns.set_palette("husl")

COLORS = {
    "primary": "#3b82f6",
    "secondary": "#8b5cf6",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
}

# --- Bar chart with annotations ---

def plot_category_comparison(df: pd.DataFrame, x: str, y: str,
                              title: str = ""):
    fig, ax = plt.subplots(figsize=(10, 6))

    bars = ax.bar(df[x], df[y], color=COLORS["primary"], alpha=0.8)

    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2, height + 0.5,
            f"{height:,.0f}",
            ha="center", va="bottom", fontsize=10,
        )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel(x.replace("_", " ").title())
    ax.set_ylabel(y.replace("_", " ").title())
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    return fig


# --- Time series with multiple lines ---

def plot_time_series(df: pd.DataFrame, date_col: str,
                     value_cols: list[str], title: str = ""):
    fig, ax = plt.subplots(figsize=(12, 6))

    for i, col in enumerate(value_cols):
        ax.plot(df[date_col], df[col], label=col.replace("_", " ").title(),
                linewidth=2, alpha=0.8)
        # Add confidence band
        # ax.fill_between(df[date_col], df[col] * 0.95, df[col] * 1.05, alpha=0.1)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", frameon=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    return fig


# --- Distribution plots ---

def plot_distributions(df: pd.DataFrame, columns: list[str], title: str = ""):
    n_cols = len(columns)
    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5))
    if n_cols == 1:
        axes = [axes]

    for ax, col in zip(axes, columns):
        sns.histplot(df[col], kde=True, ax=ax, color=COLORS["primary"], alpha=0.6)
        ax.axvline(df[col].mean(), color=COLORS["danger"], linestyle="--",
                   label=f"Mean: {df[col].mean():.1f}")
        ax.axvline(df[col].median(), color=COLORS["success"], linestyle="--",
                   label=f"Median: {df[col].median():.1f}")
        ax.set_title(col.replace("_", " ").title())
        ax.legend(fontsize=9)

    fig.suptitle(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig


# --- Correlation heatmap ---

def plot_correlation(df: pd.DataFrame, columns: list[str] = None):
    if columns:
        corr = df[columns].corr()
    else:
        corr = df.select_dtypes(include=[np.number]).corr()

    fig, ax = plt.subplots(figsize=(10, 8))
    mask = np.triu(np.ones_like(corr, dtype=bool))  # Upper triangle mask

    sns.heatmap(
        corr, mask=mask, annot=True, fmt=".2f",
        cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        square=True, linewidths=0.5, ax=ax,
    )
    ax.set_title("Feature Correlations", fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig


# --- Multi-panel dashboard ---

def create_dashboard(df: pd.DataFrame):
    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    # Panel 1: Revenue over time
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.plot(df["date"], df["revenue"], color=COLORS["primary"], linewidth=2)
    ax1.fill_between(df["date"], df["revenue"], alpha=0.1, color=COLORS["primary"])
    ax1.set_title("Revenue Trend")

    # Panel 2: Category breakdown (pie)
    ax2 = fig.add_subplot(gs[0, 2])
    category_data = df.groupby("category")["revenue"].sum()
    ax2.pie(category_data, labels=category_data.index, autopct="%1.1f%%",
            startangle=90)
    ax2.set_title("Revenue by Category")

    # Panel 3: Top products (horizontal bar)
    ax3 = fig.add_subplot(gs[1, 0])
    top_products = df.groupby("product")["revenue"].sum().nlargest(10)
    ax3.barh(top_products.index, top_products.values, color=COLORS["secondary"])
    ax3.set_title("Top 10 Products")

    # Panel 4: Distribution
    ax4 = fig.add_subplot(gs[1, 1])
    sns.boxplot(data=df, x="category", y="amount", ax=ax4, palette="Set2")
    ax4.set_title("Amount Distribution")
    ax4.tick_params(axis="x", rotation=45)

    # Panel 5: Scatter with regression
    ax5 = fig.add_subplot(gs[1, 2])
    sns.regplot(data=df, x="price", y="quantity", ax=ax5,
                scatter_kws={"alpha": 0.5}, color=COLORS["primary"])
    ax5.set_title("Price vs Quantity")

    fig.suptitle("Sales Dashboard", fontsize=16, fontweight="bold", y=1.02)
    return fig


# --- Save for different uses ---

def save_figure(fig, name: str, formats: list[str] = None):
    formats = formats or ["png", "svg"]
    for fmt in formats:
        fig.savefig(
            f"figures/{name}.{fmt}",
            dpi=300 if fmt == "png" else None,
            bbox_inches="tight",
            facecolor="white",
            edgecolor="none",
        )
    plt.close(fig)
```

Visualization rules:
1. **Right chart type** — bar (comparison), line (trend), scatter (relationship)
2. **Remove clutter** — hide top/right spines, minimize gridlines
3. **Annotate values** — add labels on bars, highlight key points
4. **Color with purpose** — consistent palette, use color to encode meaning
5. **Figure size** — match output medium (slides: wide, reports: narrow)"""
    ),
]
