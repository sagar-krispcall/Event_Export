import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime

# --- PAGE SETUP ---
st.set_page_config(page_title="Mixpanel Event Exporter", layout="wide")
st.title("📊 Mixpanel Event Exporter")

# --- STATIC EVENT LIST ---
STATIC_EVENTS = [
    "New Payment Made",
    "Guest Payment",
    "Refund Granted",
    "Outbound Calls",
    "Inbound Calls",
    "Outbound SMS",
    "Inbound SMS",
    "Agent Added",
    "Business Domain Subscription",
    "Phone Number Purchased",
    "Phone Number Renewed",
    "Phone Number Assigned",
    "[Auto] Page View",
    "New User Sign-up"
]

# --- USER INPUTS ---
events_selected = st.multiselect(
    "Select Event(s) to export:", STATIC_EVENTS, default=["New Payment Made"]
)

col1, col2 = st.columns(2)
with col1:
    from_date = st.date_input("📅 From Date", datetime(2025, 8, 1))
with col2:
    to_date = st.date_input("📅 To Date", datetime(2025, 8, 31))

st.markdown("### 🔍 Optional Filter (Mixpanel where expression)")
where_expression = st.text_input(
    'Enter Mixpanel "where" expression (e.g., properties["Plan"]=="Pro")'
)

file_name_input = st.text_input("💾 Output CSV filename:", "mixpanel_export")
run = st.button("🚀 Run Export")

# --- GET API KEY & PROJECT ID SECURELY ---
try:
    API_KEY = st.secrets["MIXPANEL_API_KEY"]
    PROJECT_ID = st.secrets["MIXPANEL_PROJECT_ID"]
except Exception:
    st.error(
        "API key or Project ID not found in st.secrets. "
        "Create .streamlit/secrets.toml with MIXPANEL_API_KEY and MIXPANEL_PROJECT_ID"
    )
    st.stop()

# --- RUN EXPORT LOGIC ---
if run:
    if not events_selected:
        st.warning("⚠️ Please select at least one event.")
    else:
        filename = file_name_input.strip()
        if not filename.lower().endswith(".csv"):
            filename += ".csv"

        event_array_json = json.dumps(events_selected)
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")

        url = (
            f"https://data-eu.mixpanel.com/api/2.0/export?project_id={PROJECT_ID}"
            f"&from_date={from_date_str}&to_date={to_date_str}&event={event_array_json}"
        )

        if where_expression.strip():
            url += f"&where={where_expression}"

        headers = {
            "accept": "text/plain",
            "authorization": f"Basic {API_KEY}",
        }

        with st.spinner("⏳ Fetching data from Mixpanel..."):
            try:
                response = requests.get(url, headers=headers)
            except Exception as e:
                st.error(f"Error connecting to Mixpanel: {e}")
                st.stop()

        if response.status_code == 200:
            with st.spinner("Processing data..."):
                try:
                    data_json = [json.loads(line) for line in response.text.strip().split("\n")]
                    df = pd.DataFrame(data_json)

                    if "properties" in df.columns:
                        prop_df = pd.json_normalize(df["properties"])
                        df = pd.concat([df.drop(columns=["properties"]), prop_df], axis=1)

                    if "$insert_id" in df.columns:
                        df = df.drop_duplicates(subset="$insert_id").sort_values("$insert_id")

                    st.success(f"✅ Data fetched! Total rows: {len(df)}")

                    # --- STORE dataframe in session state for column filter ---
                    st.session_state["event_df"] = df

                except Exception as e:
                    st.error(f"❌ Error processing data: {e}")
                    st.stop()
        else:
            st.error(f"❌ Error fetching data. Status code: {response.status_code}")
            st.stop()

# --- COLUMN FILTER AND DOWNLOAD ---
if "event_df" in st.session_state:
    df = st.session_state["event_df"]

    st.markdown("### 🧩 Optional Column Filter")
    selected_cols = st.multiselect(
        "Select columns to export (leave empty to export all):",
        options=df.columns.tolist()
    )

    if selected_cols:
        export_df = df[selected_cols]
    else:
        export_df = df

    export_df = export_df.reset_index(drop=True)
    st.dataframe(export_df)

    csv_data = export_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv_data, file_name_input.strip()+".csv", "text/csv")
