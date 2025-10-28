import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
from io import BytesIO

# --- PAGE SETUP ---
st.set_page_config(page_title="Mixpanel Event Exporter", layout="wide")
st.title("📊 Mixpanel Event Exporter")

st.caption("Export Mixpanel event data with optional filters, date range, and column selection.")

# --- STATIC EVENT LIST ---
STATIC_EVENTS = [
    "New Payment Made", "Guest Payment", "Refund Granted", "Outbound Calls",
    "Inbound Calls", "Outbound SMS", "Inbound SMS", "Agent Added",
    "Business Domain Subscription", "Phone Number Purchased", "Phone Number Renewed",
    "Phone Number Assigned", "[Auto] Page View", "New User Sign-up"
]

# --- USER INPUTS ---
st.markdown("### 🎯 Event Selection")

event_search = st.text_input("Search events:", "")
filtered_events = [e for e in STATIC_EVENTS if event_search.lower() in e.lower()]

events_selected = st.multiselect(
    "Select Event(s) to export:",
    filtered_events,
    default=["New Payment Made"]
)

col1, col2, col3 = st.columns(3)
with col1:
    from_date = st.date_input("📅 From Date", datetime(2025, 8, 1))
with col2:
    to_date = st.date_input("📅 To Date", datetime(2025, 8, 31))
with col3:
    region = st.selectbox("🌍 Mixpanel Region", ["EU", "US"], index=0)

st.markdown("### 🔍 Optional Filter")
where_expression = st.text_input(
    'Enter Mixpanel "where" expression (e.g., properties["Plan"]=="Pro")',
    placeholder='properties["Plan"]=="Pro"'
)

file_name_input = st.text_input("💾 Output Filename (without extension):", "mixpanel_export")
run = st.button("🚀 Run Export")

# --- SECURE CREDENTIALS ---
try:
    API_KEY = st.secrets["MIXPANEL_API_KEY"]
    PROJECT_ID = st.secrets["MIXPANEL_PROJECT_ID"]
except Exception:
    st.error("""
    🔑 Missing credentials!
    Please create `.streamlit/secrets.toml` with:
    ```
    MIXPANEL_API_KEY = "your_api_key"
    MIXPANEL_PROJECT_ID = "your_project_id"
    ```
    """)
    st.stop()


# --- FETCH DATA FUNCTION ---
def fetch_mixpanel_events(events, start_date, end_date, where=None, region="EU"):
    """Fetch Mixpanel event data via Export API."""
    region_prefix = "data-eu" if region == "EU" else "data"
    base_url = f"https://{region_prefix}.mixpanel.com/api/2.0/export"
    event_json = json.dumps(events)

    params = {
        "project_id": PROJECT_ID,
        "from_date": start_date,
        "to_date": end_date,
        "event": event_json,
    }
    if where:
        params["where"] = where

    headers = {
        "accept": "text/plain",
        "authorization": f"Basic {API_KEY}",
    }

    response = requests.get(base_url, headers=headers, params=params, timeout=300)

    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code} - {response.text[:500]}")

    # Each line = JSON event
    lines = response.text.strip().split("\n")
    if not lines or lines == [""]:
        raise Exception("No data returned from Mixpanel for the given criteria.")

    data_json = [json.loads(line) for line in lines]
    df = pd.DataFrame(data_json)

    # Flatten event properties
    if "properties" in df.columns:
        prop_df = pd.json_normalize(df["properties"])
        df = pd.concat([df.drop(columns=["properties"]), prop_df], axis=1)

    # Drop duplicates if event id exists
    if "$insert_id" in df.columns:
        df = df.drop_duplicates(subset="$insert_id").sort_values("$insert_id")

    return df


# --- MAIN LOGIC ---
if run:
    if not events_selected:
        st.warning("⚠️ Please select at least one event.")
    else:
        from_str = from_date.strftime("%Y-%m-%d")
        to_str = to_date.strftime("%Y-%m-%d")

        st.info(f"Fetching events from **{from_str}** to **{to_str}**...")

        try:
            with st.spinner("⏳ Fetching data from Mixpanel..."):
                df = fetch_mixpanel_events(
                    events=events_selected,
                    start_date=from_str,
                    end_date=to_str,
                    where=where_expression.strip() or None,
                    region=region
                )
            st.success(f"✅ Data fetched successfully! {len(df)} rows retrieved.")
            st.session_state["event_df"] = df

        except Exception as e:
            st.error(f"❌ {e}")
            st.stop()


# --- COLUMN FILTER + DOWNLOAD ---
if "event_df" in st.session_state:
    df = st.session_state["event_df"]

    st.markdown("### 🧩 Optional Column Selection")
    selected_cols = st.multiselect(
        "Select columns to include in export (leave empty for all):",
        options=df.columns.tolist(),
        default=[]
    )

    export_df = df[selected_cols] if selected_cols else df
    st.dataframe(export_df.head(20), use_container_width=True)

    # --- Downloads ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    base_name = file_name_input.strip() or "mixpanel_export"
    csv_filename = f"{base_name}_{timestamp}.csv"
    json_filename = f"{base_name}_{timestamp}.json"

    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    json_bytes = json.dumps(export_df.to_dict(orient="records"), indent=2, ensure_ascii=False).encode("utf-8")

    st.download_button("⬇️ Download CSV", csv_bytes, csv_filename, "text/csv")
    st.download_button("⬇️ Download JSON", json_bytes, json_filename, "application/json")

