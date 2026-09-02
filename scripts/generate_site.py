import os
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def fetch_cpi_yoy():
    response = (
        supabase.table("cpi_yoy_change")
        .select("*")
        .eq("geography", "Canada")
        .eq("category", "All-items")
        .order("ref_date", desc=True)
        .limit(24)
        .execute()
    )
    df = pd.DataFrame(response.data)
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    df = df.sort_values("ref_date")  # oldest to newest, for a left-to-right chart
    return df


def build_chart(df):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["ref_date"],
        y=df["yoy_percent_change"],
        mode="lines+markers",
        name="CPI YoY % change",
        line=dict(color="#1f77b4", width=2),
        hovertemplate=(
            "<b>%{x|%b %Y}</b><br>"
            "Inflation rate: %{y:.2f}%"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        title="Canada — CPI Inflation Rate (Year-over-Year), Last 24 Months",
        xaxis_title="Month",
        yaxis_title="% change vs. same month last year",
        hovermode="x unified",
        template="plotly_white",
    )

    return fig


def build_page_html(fig):
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Canadian Economic Pulse</title>
  <style>
    body {{
      font-family: -apple-system, Arial, sans-serif;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 20px;
    }}
    h1 {{ font-size: 1.8em; }}
  </style>
</head>
<body>
  <h1>Canadian Economic Pulse</h1>
  {chart_html}
</body>
</html>"""
    return page


def main():
    df = fetch_cpi_yoy()
    print(f"Fetched {len(df)} rows.")

    fig = build_chart(df)
    html = build_page_html(fig)

    os.makedirs("site", exist_ok=True)
    with open("site/index.html", "w") as f:
        f.write(html)

    print("Saved site/index.html")


if __name__ == "__main__":
    main()