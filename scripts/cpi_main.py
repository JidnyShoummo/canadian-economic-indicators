import os
import time
import requests
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://www150.statcan.gc.ca/t1/wds/rest"
PRODUCT_ID = 18100004

WANTED_GEOGRAPHY = [
    "Canada", "Newfoundland and Labrador", "Prince Edward Island",
    "Nova Scotia", "New Brunswick", "Quebec", "Ontario",
    "Manitoba", "Saskatchewan", "Alberta", "British Columbia",
]

WANTED_CATEGORIES = [
    "All-items", "All-items excluding food and energy","Food", "Shelter",
    "Household operations, furnishings and equipment",
    "Clothing and footwear", "Transportation",
    "Health and personal care", "Recreation, education and reading",
    "Alcoholic beverages, tobacco products and recreational cannabis",
]


def chunks(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


# ---------- Step 1: Discover vector IDs ----------

def get_cube_metadata(product_id):
    resp = requests.post(f"{BASE_URL}/getCubeMetadata", json=[{"productId": product_id}], timeout=30)
    resp.raise_for_status()
    return resp.json()[0]["object"]


def find_dimension(metadata, name_contains):
    for dim in metadata["dimension"]:
        if name_contains.lower() in dim["dimensionNameEn"].lower():
            return dim
    raise ValueError(f"No dimension found matching '{name_contains}'")


def match_members(dimension, wanted_names):
    matched = {}
    for wanted in wanted_names:
        hit = next(
            (m for m in dimension["member"] if wanted.lower() in m["memberNameEn"].lower()),
            None,
        )
        if hit is None:
            print(f"  WARNING: no member matched for '{wanted}'")
            continue
        matched[wanted] = hit["memberId"]
    return matched


def build_coordinate(positions):
    slots = ["0"] * 10
    for pos, member_id in positions.items():
        slots[pos - 1] = str(member_id)
    return ".".join(slots)


def get_series_info_batch(product_id, coord_meta_pairs, max_retries=3):
    body = [{"productId": product_id, "coordinate": c} for c, _, _ in coord_meta_pairs]
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                f"{BASE_URL}/getSeriesInfoFromCubePidCoord", json=body, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Attempt {attempt} failed ({e}), retrying...")
            time.sleep(3)
    print("  Giving up on this batch.")
    return []


def discover_vectors():
    print("Discovering vector IDs...")
    metadata = get_cube_metadata(PRODUCT_ID)
    geo_dim = find_dimension(metadata, "Geography")
    cat_dim = find_dimension(metadata, "Product")

    geo_matches = match_members(geo_dim, WANTED_GEOGRAPHY)
    cat_matches = match_members(cat_dim, WANTED_CATEGORIES)

    all_combos = []
    for geo_name, geo_id in geo_matches.items():
        for cat_name, cat_id in cat_matches.items():
            coord = build_coordinate({
                geo_dim["dimensionPositionId"]: geo_id,
                cat_dim["dimensionPositionId"]: cat_id,
            })
            all_combos.append((coord, geo_name, cat_name))

    vectors = []
    for batch in chunks(all_combos, 20):
        results = get_series_info_batch(PRODUCT_ID, batch)

        # Match each result back to its request by the coordinate the API
        # echoes back -- NEVER assume response order matches request order.
        combo_by_coord = {coord: (geo_name, cat_name) for coord, geo_name, cat_name in batch}

        for result in results:
            if result.get("status") != "SUCCESS":
                continue
            obj = result["object"]
            returned_coord = obj.get("coordinate")
            if returned_coord not in combo_by_coord:
                print(f"  WARNING: got a coordinate back we didn't request: {returned_coord}")
                continue
            geo_name, cat_name = combo_by_coord[returned_coord]
            vectors.append({
                "vector_id": obj["vectorId"],
                "geography": geo_name,
                "category": cat_name,
            })
        time.sleep(1)

    print(f"  Found {len(vectors)} valid vectors.")
    return vectors


# ---------- Step 2: Fetch data for those vectors ----------

def fetch_data(vector_ids, latest_n=60, max_retries=3):
    body = [{"vectorId": v, "latestN": latest_n} for v in vector_ids]
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                f"{BASE_URL}/getDataFromVectorsAndLatestNPeriods", json=body, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Attempt {attempt} failed ({e}), retrying...")
            time.sleep(3)
    print("  Giving up on this batch.")
    return []


def flatten(api_results, lookup):
    rows = []
    for result in api_results:
        if result.get("status") != "SUCCESS":
            continue
        obj = result["object"]
        vector_id = obj["vectorId"]
        meta = lookup.get(vector_id, {})
        for point in obj.get("vectorDataPoint", []):
            rows.append({
                "vector_id": vector_id,
                "geography": meta.get("geography"),
                "category": meta.get("category"),
                "ref_date": point["refPer"],
                "value": point["value"],
            })
    return pd.DataFrame(rows)


def fetch_all_data(vectors):
    print("Fetching data values...")
    lookup = {v["vector_id"]: v for v in vectors}
    vector_ids = [v["vector_id"] for v in vectors]

    all_results = []
    for batch in chunks(vector_ids, 20):
        results = fetch_data(batch)
        all_results.extend(results)
        time.sleep(1)

    df = flatten(all_results, lookup)
    print(f"  Total rows fetched: {len(df)}")
    return df


# ---------- Step 3: Load to Supabase ----------

def load_to_supabase(df):
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    records = df.to_dict(orient="records")
    supabase.table("cpi_data").upsert(records, on_conflict="vector_id,ref_date").execute()
    print(f"Upserted {len(records)} rows to Supabase.")


# ---------- Run everything ----------

def run():
    try:
        vectors = discover_vectors()
        if not vectors:
            raise RuntimeError("No vectors discovered -- aborting.")

        df = fetch_all_data(vectors)
        if df.empty:
            raise RuntimeError("No data fetched -- aborting before touching Supabase.")

        load_to_supabase(df)
        print("Pipeline completed successfully.")
    except Exception as e:
        print(f"FAILED: {e}")
        raise


if __name__ == "__main__":
    run()