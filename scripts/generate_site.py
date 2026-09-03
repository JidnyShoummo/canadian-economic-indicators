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
        .order("ref_date", desc=True)
        .limit(12)
        .execute()
    )
    df = pd.DataFrame(response.data)
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    df = df.sort_values("ref_date")  # oldest to newest, left to right on the chart
    return df


def build_cpi_chart(df):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["ref_date"],
        y=df["all_items_yoy"],
        mode="lines+markers",
        name="All-items (Headline)",
        line=dict(color="#1f77b4", width=2.5),
        marker=dict(size=6),
        hovertemplate="<b>%{x|%b %Y}</b><br>All-items: %{y:.2f}%<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["ref_date"],
        y=df["core_yoy"],
        mode="lines+markers",
        name="Excl. Food and Energy (Core)",
        line=dict(color="#d62728", width=2.5, dash="dot"),
        marker=dict(size=6),
        hovertemplate="<b>%{x|%b %Y}</b><br>Core: %{y:.2f}%<extra></extra>",
    ))

    # Bank of Canada's 2% inflation target, for visual reference
    fig.add_hline(
        y=2.0,
        line_dash="dash",
        line_color="gray",
        line_width=1,
        annotation_text="Bank of Canada 2% target",
        annotation_position="bottom right",
        annotation_font_size=11,
        annotation_font_color="gray",
    )

    fig.update_layout(
        title=dict(
            text="Canada CPI — Year-over-Year Inflation (Last 12 Months)",
            font=dict(size=20),
        ),
        xaxis_title=None,
        yaxis_title="% change vs. same month last year",
        hovermode="x unified",
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5,
        ),
        margin=dict(t=60, b=80, l=60, r=30),
        height=520,
    )
    

    fig.update_yaxes(ticksuffix="%")

    return fig


# ---------- Page assembly ----------
# Each new indicator gets its own fetch_*() + build_*_chart() pair, added
# to the `chart_htmls` list in main(). This keeps every chart independent --
# a bug in one doesn't affect the others -- and scales cleanly as more
# charts (GDP, employment, retail sales, etc.) get added over time.

def build_page_html(chart_htmls):
    charts_block = "\n".join(
        f'<div class="chart-container">{html}</div>' for html in chart_htmls
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Canadian Economic Pulse</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      max-width: 900px;
      margin: 50px auto;
      padding: 0 24px;
      color: #222;
      background: #fafafa;
    }}
    h1 {{
      font-size: 2em;
      margin-bottom: 4px;
    }}
    .subtitle {{
      color: #666;
      font-size: 0.95em;
      margin-bottom: 32px;
    }}
    .chart-container {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      padding: 16px;
      margin-bottom: 24px;
    }}
  </style>
</head>
<body>
  <h1>Canadian Economic Pulse</h1>
  <div class="subtitle">Updated daily from Statistics Canada and the Bank of Canada</div>
  {charts_block}
</body>
</html>"""
    return page


def main():
    chart_htmls = []

    # --- CPI (headline + core inflation) ---
    cpi_df = fetch_cpi_yoy()
    print(f"CPI: fetched {len(cpi_df)} rows.")
    cpi_fig = build_cpi_chart(cpi_df)
    # include_plotlyjs="cdn" loads Plotly from cdn.plot.ly, which is fine
    # for GitHub Pages (no script-host restriction there).
    chart_htmls.append(cpi_fig.to_html(full_html=False, include_plotlyjs="cdn"))

    # --- Future charts go here, same pattern ---
    # gdp_df = fetch_gdp_data()
    # chart_htmls.append(build_gdp_chart(gdp_df).to_html(full_html=False, include_plotlyjs=False))

    html = build_page_html(chart_htmls)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w") as f:
        f.write(html)

    print("Saved site/index.html")


if __name__ == "__main__":
    main()