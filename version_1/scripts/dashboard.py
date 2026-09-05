import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st


# ============================================================
# 1. PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "strava_dashboard.db"


st.set_page_config(
    page_title="Strava Running Dashboard",
    page_icon="🏃",
    layout="wide",
)


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def format_pace(decimal_pace):
    """
    Convert decimal minutes/km into mm:ss/km.

    Example:
        5.5 -> 5:30
    """
    if pd.isna(decimal_pace) or decimal_pace <= 0 or np.isinf(decimal_pace):
        return "--:--"

    mins = int(decimal_pace)
    secs = int(round((decimal_pace - mins) * 60))

    if secs >= 60:
        mins += 1
        secs = 0

    return f"{mins}:{secs:02d}"


def format_duration(seconds):
    """Convert seconds into HH:MM:SS."""
    if pd.isna(seconds):
        return "00:00:00"

    seconds = int(max(0, seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"

    return f"{minutes}m {secs:02d}s"

def format_split_time(seconds):
    """Format a kilometer split as mm:ss."""

    if pd.isna(seconds):
        return "--:--"

    seconds = int(round(seconds))

    minutes = seconds // 60
    secs = seconds % 60

    return f"{minutes}:{secs:02d}"

def safe_mean(series):
    values = pd.to_numeric(series, errors="coerce").dropna()

    if len(values) == 0:
        return np.nan

    return values.mean()


def safe_max(series):
    values = pd.to_numeric(series, errors="coerce").dropna()

    if len(values) == 0:
        return np.nan

    return values.max()


def safe_min(series):
    values = pd.to_numeric(series, errors="coerce").dropna()

    if len(values) == 0:
        return np.nan

    return values.min()


# ============================================================
# 3. DATABASE FUNCTIONS
# ============================================================

@st.cache_data
def get_activity_list(db_path):
    """
    Load only activity-level information.

    We do NOT load all trackpoints here.
    """

    if not db_path.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            activity_id,
            MIN(time) AS start_time,
            MAX(time) AS end_time,
            MAX(distance) AS distance
        FROM trackpoints
        GROUP BY activity_id
        ORDER BY start_time DESC
    """

    activities = pd.read_sql_query(query, conn)

    conn.close()

    if activities.empty:
        return activities

    activities["start_time"] = pd.to_datetime(
        activities["start_time"],
        errors="coerce"
    )

    activities["end_time"] = pd.to_datetime(
        activities["end_time"],
        errors="coerce"
    )

    activities["distance_km"] = activities["distance"] / 1000

    return activities


@st.cache_data
def load_activity(db_path, activity_id):
    """
    Load ONLY the selected activity.
    """

    if not db_path.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            activity_id,
            time,
            latitude,
            longitude,
            altitude,
            distance,
            heart_rate,
            speed
        FROM trackpoints
        WHERE activity_id = ?
        ORDER BY time ASC
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(str(activity_id),)
    )

    conn.close()

    if df.empty:
        return df

    df["time"] = pd.to_datetime(
        df["time"],
        errors="coerce"
    )

    numeric_columns = [
        "latitude",
        "longitude",
        "altitude",
        "distance",
        "heart_rate",
        "speed",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    return df


# ============================================================
# 4. DERIVED METRICS
# ============================================================

def calculate_metrics(df):

    df = df.copy()

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    df["time_diff_sec"] = (
        df["time"]
        .diff()
        .dt.total_seconds()
    )

    df["time_diff_sec"] = (
        df["time_diff_sec"]
        .clip(lower=0)
    )

    df["time_diff_sec"] = (
        df["time_diff_sec"]
        .fillna(0)
    )

    total_duration = df["time_diff_sec"].sum()

    # --------------------------------------------------------
    # Distance
    # --------------------------------------------------------

    if df["distance"].notna().any():

        total_distance_m = df["distance"].max()

    else:

        total_distance_m = 0

    total_distance_km = total_distance_m / 1000

    # --------------------------------------------------------
    # Elevation
    # --------------------------------------------------------

    df["alt_diff"] = df["altitude"].diff()

    elevation_gain = (
        df.loc[
            df["alt_diff"] > 0,
            "alt_diff"
        ]
        .sum()
    )

    elevation_loss = (
        df.loc[
            df["alt_diff"] < 0,
            "alt_diff"
        ]
        .sum()
        * -1
    )

    # --------------------------------------------------------
    # Pace
    # --------------------------------------------------------

    df["pace_min_km"] = np.where(
        df["speed"] > 0,
        (1000 / df["speed"]) / 60,
        np.nan
    )

    # Remove unrealistic values

    df.loc[
        (df["pace_min_km"] < 2) |
        (df["pace_min_km"] > 20),
        "pace_min_km"
    ] = np.nan

    # --------------------------------------------------------
    # Speed conversion
    # --------------------------------------------------------

    df["speed_kmh"] = df["speed"] * 3.6

    # --------------------------------------------------------
    # Calculated speed from distance/time
    # --------------------------------------------------------

    df["distance_diff"] = df["distance"].diff()

    df["calculated_speed"] = np.where(
        df["time_diff_sec"] > 0,
        df["distance_diff"] / df["time_diff_sec"],
        np.nan
    )

    # --------------------------------------------------------
    # Grade
    # --------------------------------------------------------

    horizontal_distance = df["distance_diff"]

    df["grade_percent"] = np.where(
        horizontal_distance > 0,
        (
            df["alt_diff"]
            / horizontal_distance
            * 100
        ),
        np.nan
    )

    # Remove impossible grade spikes

    df.loc[
        (df["grade_percent"] < -30) |
        (df["grade_percent"] > 30),
        "grade_percent"
    ] = np.nan

    # --------------------------------------------------------
    # Rolling metrics
    # --------------------------------------------------------

    df["pace_smooth"] = (
        df["pace_min_km"]
        .rolling(
            window=10,
            min_periods=3
        )
        .mean()
    )

    df["hr_smooth"] = (
        df["heart_rate"]
        .rolling(
            window=10,
            min_periods=3
        )
        .mean()
    )

    # --------------------------------------------------------
    # Pace-HR efficiency
    #
    # Higher = more speed per unit HR
    # --------------------------------------------------------

    df["hr_efficiency"] = np.where(
        df["heart_rate"] > 0,
        df["speed"] / df["heart_rate"],
        np.nan
    )

    # --------------------------------------------------------
    # Moving time
    #
    # We consider a point "moving" when:
    #
    # speed > 0.5 m/s
    # and
    # gap <= 10 seconds
    # --------------------------------------------------------

    moving_mask = (
        (df["speed"] > 0.5) &
        (df["time_diff_sec"] <= 10)
    )

    moving_time = df.loc[
        moving_mask,
        "time_diff_sec"
    ].sum()

    return {
        "df": df,
        "total_duration": total_duration,
        "moving_time": moving_time,
        "distance_km": total_distance_km,
        "elevation_gain": elevation_gain,
        "elevation_loss": elevation_loss,
        "avg_hr": safe_mean(df["heart_rate"]),
        "max_hr": safe_max(df["heart_rate"]),
        "min_hr": safe_min(df["heart_rate"]),
        "avg_speed": safe_mean(
            df.loc[df["speed"] > 0, "speed_kmh"]
        ),
        "max_speed": safe_max(df["speed_kmh"]),
    }


# ============================================================
# 5. EXACT KILOMETER SPLITS
# ============================================================

def calculate_splits(df):
    """
    Calculate kilometer splits from cumulative TCX distance.

    Uses only:
        time
        distance
        heart_rate
        altitude
    """

    data = df[
        [
            "time",
            "distance",
            "heart_rate",
            "altitude"
        ]
    ].copy()

    # --------------------------------------------------------
    # Clean data
    # --------------------------------------------------------

    data["time"] = pd.to_datetime(
        data["time"],
        errors="coerce"
    )

    data["distance"] = pd.to_numeric(
        data["distance"],
        errors="coerce"
    )

    data["heart_rate"] = pd.to_numeric(
        data["heart_rate"],
        errors="coerce"
    )

    data["altitude"] = pd.to_numeric(
        data["altitude"],
        errors="coerce"
    )

    data = data.dropna(
        subset=["time", "distance"]
    )

    if len(data) < 2:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Sort by time
    # --------------------------------------------------------

    data = data.sort_values(
        "time"
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Remove duplicate distance values
    # --------------------------------------------------------

    data = data.drop_duplicates(
        subset=["distance"],
        keep="first"
    )

    # Sort by distance for interpolation
    data = data.sort_values(
        "distance"
    ).reset_index(drop=True)

    if len(data) < 2:
        return pd.DataFrame()

    max_distance = data["distance"].max()

    # Need at least 1 km
    if pd.isna(max_distance) or max_distance < 1000:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Elapsed time from activity start
    # --------------------------------------------------------

    start_time = data["time"].iloc[0]

    data["elapsed_sec"] = (
        data["time"] - start_time
    ).dt.total_seconds()

    # --------------------------------------------------------
    # Kilometer boundaries
    #
    # Example:
    # 0
    # 1000
    # 2000
    # 3000
    # ...
    # final distance
    # --------------------------------------------------------

    boundaries = np.arange(
        0,
        max_distance,
        1000
    )

    if boundaries[-1] < max_distance:
        boundaries = np.append(
            boundaries,
            max_distance
        )

    # --------------------------------------------------------
    # Interpolate time at each distance boundary
    # --------------------------------------------------------

    boundary_time = np.interp(
        boundaries,
        data["distance"].to_numpy(),
        data["elapsed_sec"].to_numpy()
    )

    # --------------------------------------------------------
    # Interpolate heart rate
    # --------------------------------------------------------

    hr_data = data.dropna(
        subset=["heart_rate"]
    )

    if len(hr_data) >= 2:

        boundary_hr = np.interp(
            boundaries,
            hr_data["distance"].to_numpy(),
            hr_data["heart_rate"].to_numpy()
        )

    else:

        boundary_hr = np.full(
            len(boundaries),
            np.nan
        )

    # --------------------------------------------------------
    # Interpolate altitude
    # --------------------------------------------------------

    altitude_data = data.dropna(
        subset=["altitude"]
    )

    if len(altitude_data) >= 2:

        boundary_altitude = np.interp(
            boundaries,
            altitude_data["distance"].to_numpy(),
            altitude_data["altitude"].to_numpy()
        )

    else:

        boundary_altitude = np.full(
            len(boundaries),
            np.nan
        )

    # --------------------------------------------------------
    # Generate splits
    # --------------------------------------------------------

    rows = []

    for i in range(len(boundaries) - 1):

        start_distance = boundaries[i]
        end_distance = boundaries[i + 1]

        distance_m = (
            end_distance
            - start_distance
        )

        if distance_m <= 0:
            continue

        # Split duration
        split_time_sec = (
            boundary_time[i + 1]
            - boundary_time[i]
        )

        if split_time_sec <= 0:
            continue

        # Distance in km
        distance_km = distance_m / 1000

        # Pace in min/km
        pace_min_km = (
            split_time_sec / 60
        ) / distance_km

        # Average HR
        if (
            not np.isnan(boundary_hr[i])
            and
            not np.isnan(boundary_hr[i + 1])
        ):

            avg_hr = (
                boundary_hr[i]
                +
                boundary_hr[i + 1]
            ) / 2

        else:

            avg_hr = np.nan

        # Elevation gain
        if (
            not np.isnan(boundary_altitude[i])
            and
            not np.isnan(boundary_altitude[i + 1])
        ):

            elevation_change = (
                boundary_altitude[i + 1]
                -
                boundary_altitude[i]
            )

            elevation_gain = max(
                0,
                elevation_change
            )

        else:

            elevation_gain = np.nan

        rows.append(
            {
                "Kilometer": i + 1,
                "Distance_km": distance_km,
                "Time_sec": split_time_sec,
                "Pace_min_km": pace_min_km,
                "Avg_HR": avg_hr,
                "Elevation_Gain": elevation_gain,
            }
        )

    return pd.DataFrame(rows)

# ============================================================
# 6. HEART-RATE DRIFT
# ============================================================

def calculate_hr_drift(df):

    valid = df[
        (df["speed"] > 0) &
        (df["heart_rate"] > 0)
    ].copy()

    if len(valid) < 20:
        return np.nan, np.nan, np.nan

    midpoint = (
        valid["distance"].min()
        +
        (
            valid["distance"].max()
            - valid["distance"].min()
        )
        / 2
    )

    first_half = valid[
        valid["distance"] <= midpoint
    ]

    second_half = valid[
        valid["distance"] > midpoint
    ]

    if (
        first_half.empty
        or second_half.empty
    ):
        return np.nan, np.nan, np.nan

    first_efficiency = (
        first_half["speed"].mean()
        /
        first_half["heart_rate"].mean()
    )

    second_efficiency = (
        second_half["speed"].mean()
        /
        second_half["heart_rate"].mean()
    )

    drift = (
        (
            second_efficiency
            -
            first_efficiency
        )
        /
        first_efficiency
    ) * 100

    return (
        drift,
        first_efficiency,
        second_efficiency
    )


# ============================================================
# 7. DATA QUALITY
# ============================================================

def calculate_quality(df):

    total = len(df)

    if total == 0:
        return {}

    missing = {}

    columns_to_check = [
        "time",
        "latitude",
        "longitude",
        "altitude",
        "distance",
        "heart_rate",
        "speed",
    ]

    for column in columns_to_check:

        missing[column] = (
            df[column]
            .isna()
            .sum()
        )

    time_diffs = (
        df["time"]
        .diff()
        .dt.total_seconds()
        .dropna()
    )

    if len(time_diffs) > 0:

        median_interval = time_diffs.median()
        max_gap = time_diffs.max()

    else:

        median_interval = np.nan
        max_gap = np.nan

    # Speed anomaly

    calculated = df[
        (df["speed"] > 0) &
        (df["calculated_speed"] > 0)
    ].copy()

    if not calculated.empty:

        speed_ratio = (
            calculated["speed"]
            /
            calculated["calculated_speed"]
        )

        speed_anomalies = (
            (
                speed_ratio < 0.5
            )
            |
            (
                speed_ratio > 2
            )
        ).sum()

    else:

        speed_anomalies = 0

    # GPS completeness

    gps_missing = (
        df["latitude"].isna()
        |
        df["longitude"].isna()
    ).sum()

    return {
        "total_points": total,
        "missing": missing,
        "median_interval": median_interval,
        "max_gap": max_gap,
        "gps_missing": gps_missing,
        "speed_anomalies": speed_anomalies,
    }


# ============================================================
# 8. COLOR FUNCTIONS
# ============================================================

def value_to_color(
    value,
    minimum,
    maximum
):

    if pd.isna(value):
        return [128, 128, 128, 180]

    if maximum == minimum:
        ratio = 0.5
    else:
        ratio = (
            value - minimum
        ) / (
            maximum - minimum
        )

    ratio = np.clip(
        ratio,
        0,
        1
    )

    # Green → Yellow → Red
    if ratio < 0.5:

        local = ratio * 2

        r = int(255 * local)
        g = 255

    else:

        local = (
            ratio - 0.5
        ) * 2

        r = 255
        g = int(
            255 * (1 - local)
        )

    return [
        r,
        g,
        50,
        220
    ]


# ============================================================
# 9. APPLICATION HEADER
# ============================================================

st.title("🏃 Strava Running Dashboard")

st.caption(
    "Analysis based exclusively on TCX-derived fundamental data."
)


# ============================================================
# 10. DATABASE CHECK
# ============================================================

if not DB_PATH.exists():

    st.error(
        f"Database not found:\n\n{DB_PATH}"
    )

    st.stop()


# ============================================================
# 11. LOAD ACTIVITY LIST
# ============================================================

activities = get_activity_list(DB_PATH)

if activities.empty:

    st.warning(
        "No activities found in the database."
    )

    st.stop()


# ============================================================
# 12. SIDEBAR — YEAR / MONTH / ACTIVITY SELECTION
# ============================================================

st.sidebar.header("Activity Selection")

# ------------------------------------------------------------
# Make sure start_time is datetime
# ------------------------------------------------------------

activities["start_time"] = pd.to_datetime(
    activities["start_time"]
)

# ------------------------------------------------------------
# Create Year and Month columns
# ------------------------------------------------------------

activities["year"] = (
    activities["start_time"]
    .dt.year
)

activities["month"] = (
    activities["start_time"]
    .dt.month
)

activities["month_name"] = (
    activities["start_time"]
    .dt.strftime("%B")
)

# ------------------------------------------------------------
# YEAR SELECTION
# ------------------------------------------------------------

years = sorted(
    activities["year"].unique(),
    reverse=True
)

selected_year = st.sidebar.selectbox(
    "Year",
    years
)

# ------------------------------------------------------------
# Filter activities by selected year
# ------------------------------------------------------------

year_activities = activities[
    activities["year"] == selected_year
].copy()

# ------------------------------------------------------------
# MONTH SELECTION
# ------------------------------------------------------------

months = (
    year_activities[
        ["month", "month_name"]
    ]
    .drop_duplicates()
    .sort_values(
        "month",
        ascending=False
    )
)

month_options = [
    (row["month"], row["month_name"])
    for _, row in months.iterrows()
]

selected_month = st.sidebar.selectbox(
    "Month",
    month_options,
    format_func=lambda x: x[1]
)[0]

# ------------------------------------------------------------
# Filter activities by selected month
# ------------------------------------------------------------

month_activities = year_activities[
    year_activities["month"] == selected_month
].copy()

# Sort newest → oldest
month_activities = (
    month_activities
    .sort_values(
        "start_time",
        ascending=False
    )
    .reset_index(drop=True)
)

# ------------------------------------------------------------
# Create activity display name
# ------------------------------------------------------------

# Convert UTC → UTC+8 (Malaysia / Asia/Kuala_Lumpur)
month_activities["start_time"] = (
    pd.to_datetime(month_activities["start_time"], utc=True)
    .dt.tz_convert("Asia/Kuala_Lumpur")
)

month_activities["display"] = (
    month_activities["start_time"].dt.strftime(
        "%d %B %Y, %H:%M:%S")
    +
    " | "
    +
    month_activities["distance_km"]
    .round(2)
    .astype(str)
    +
    " km"
)

# ------------------------------------------------------------
# ACTIVITY SELECTION
# ------------------------------------------------------------

selected_index = st.sidebar.selectbox(
    "Activity",
    range(len(month_activities)),
    format_func=lambda i:
        month_activities.iloc[i]["display"]
)

selected_activity = (
    month_activities.iloc[
        selected_index
    ]["activity_id"]
)


# ============================================================
# 13. LOAD SELECTED ACTIVITY
# ============================================================

activity_df = load_activity(
    DB_PATH,
    selected_activity
)

if activity_df.empty:

    st.error(
        "Selected activity contains no trackpoints."
    )

    st.stop()


analysis = calculate_metrics(
    activity_df
)

activity_df = analysis["df"]

splits = calculate_splits(
    activity_df
)

drift, first_efficiency, second_efficiency = (
    calculate_hr_drift(activity_df)
)

quality = calculate_quality(
    activity_df
)


# ============================================================
# 14. ACTIVITY HEADER
# ============================================================

start_time = activity_df["time"].min()
start_time = (pd.to_datetime(start_time, utc=True)
    .tz_convert("Asia/Kuala_Lumpur")
) 

st.subheader(
    f"Activity: {selected_activity}"
)

st.caption(
    start_time.strftime(
        "%d %B %Y, %H:%M:%S"
    )
)


# ============================================================
# 15. TOP KPI ROW
# ============================================================

distance_km = analysis["distance_km"]
duration = analysis["total_duration"]
moving_time = analysis["moving_time"]

if distance_km > 0:

    overall_pace = (
        duration / 60
    ) / distance_km

else:

    overall_pace = np.nan


k1, k2, k3, k4, k5 = st.columns(5)

k1.metric(
    "Distance",
    f"{distance_km:.2f} km"
)

k2.metric(
    "Duration",
    format_duration(duration)
)

k3.metric(
    "Avg Pace",
    f"{format_pace(overall_pace)} /km"
)

k4.metric(
    "Avg HR",
    (
        f"{analysis['avg_hr']:.0f} bpm"
        if not pd.isna(analysis["avg_hr"])
        else "--"
    )
)

k5.metric(
    "Elevation Gain",
    f"{analysis['elevation_gain']:.0f} m"
)


# ============================================================
# 16. SECONDARY KPI ROW
# ============================================================

st.markdown("### Activity Details")

k1, k2, k3, k4, k5 = st.columns(5)

k1.metric(
    "Moving Time",
    format_duration(moving_time)
)

k2.metric(
    "Max HR",
    (
        f"{analysis['max_hr']:.0f} bpm"
        if not pd.isna(analysis["max_hr"])
        else "--"
    )
)

k3.metric(
    "Min HR",
    (
        f"{analysis['min_hr']:.0f} bpm"
        if not pd.isna(analysis["min_hr"])
        else "--"
    )
)

k4.metric(
    "Avg Speed",
    (
        f"{analysis['avg_speed']:.2f} km/h"
        if not pd.isna(analysis["avg_speed"])
        else "--"
    )
)

k5.metric(
    "Max Speed",
    (
        f"{analysis['max_speed']:.2f} km/h"
        if not pd.isna(analysis["max_speed"])
        else "--"
    )
)


st.divider()


# ============================================================
# 17. TABS
# ============================================================

tab_overview, tab_running, tab_splits, tab_route, tab_quality = st.tabs(
    [
        "Overview",
        "Running Analysis",
        "Kilometer Splits",
        "Route & Elevation",
        "Data Quality",
    ]
)


# ============================================================
# TAB 1 — OVERVIEW
# ============================================================

with tab_overview:

    st.subheader("Activity Overview")

    col1, col2 = st.columns(
        [2, 1]
    )

    with col1:

        chart_data = activity_df[
            [
                "distance",
                "heart_rate",
                "pace_min_km",
                "altitude"
            ]
        ].dropna(
            subset=["distance"]
        ).copy()

        chart_data["Distance (km)"] = (
            chart_data["distance"]
            / 1000
        )

        fig = go.Figure()

        # HR

        hr_data = chart_data.dropna(
            subset=["heart_rate"]
        )

        fig.add_trace(
            go.Scatter(
                x=hr_data["Distance (km)"],
                y=hr_data["heart_rate"],
                name="Heart Rate",
                mode="lines",
                yaxis="y1",
            )
        )

        # Pace

        pace_data = chart_data.dropna(
            subset=["pace_min_km"]
        )

        fig.add_trace(
            go.Scatter(
                x=pace_data["Distance (km)"],
                y=pace_data["pace_min_km"],
                name="Pace",
                mode="lines",
                yaxis="y2",
            )
        )

        fig.update_layout(
            height=450,
            xaxis_title="Distance (km)",
            yaxis=dict(
                title="Heart Rate (bpm)"
            ),
            yaxis2=dict(
                title="Pace (min/km)",
                overlaying="y",
                side="right",
                autorange="reversed",
            ),
            margin=dict(
                l=20,
                r=20,
                t=40,
                b=20,
            ),
            legend=dict(
                orientation="h"
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with col2:

        st.markdown("### Performance Indicators")

        if not pd.isna(drift):

            st.metric(
                "HR Drift",
                f"{drift:+.2f}%"
            )

            if abs(drift) < 3:

                st.caption(
                    "Low cardiovascular drift"
                )

            elif abs(drift) < 5:

                st.caption(
                    "Moderate cardiovascular drift"
                )

            else:

                st.caption(
                    "High cardiovascular drift"
                )

        else:

            st.metric(
                "HR Drift",
                "N/A"
            )

        st.metric(
            "Elevation Loss",
            f"{analysis['elevation_loss']:.0f} m"
        )

        st.metric(
            "Trackpoints",
            f"{quality['total_points']:,}"
        )


# ============================================================
# TAB 2 — RUNNING ANALYSIS
# ============================================================

with tab_running:

    st.subheader("Pace Analysis")

    chart_data = activity_df.copy()

    chart_data["Distance (km)"] = (
        chart_data["distance"] / 1000
    )

    pace_data = chart_data.dropna(
        subset=[
            "Distance (km)",
            "pace_min_km"
        ]
    )

    fig_pace = go.Figure()

    fig_pace.add_trace(
        go.Scatter(
            x=pace_data["Distance (km)"],
            y=pace_data["pace_min_km"],
            name="Raw Pace",
            mode="lines",
            opacity=0.35,
            line=dict(color = "#FF4B4B")
        )
    )

    smooth_data = pace_data.dropna(
        subset=["pace_smooth"]
    )

    fig_pace.add_trace(
        go.Scatter(
            x=smooth_data["Distance (km)"],
            y=smooth_data["pace_smooth"],
            name="Smoothed Pace",
            mode="lines",
            line=dict(width=3,
                      color = "#1f77b4")
        )
    )

    fig_pace.update_layout(
        height=450,
        xaxis_title="Distance (km)",
        yaxis_title="Pace (min/km)",
        yaxis_autorange="reversed",
        margin=dict(
            l=20,
            r=20,
            t=30,
            b=20,
        ),
    )

    st.plotly_chart(
        fig_pace,
        use_container_width=True
    )

    # --------------------------------------------------------
    # HR
    # --------------------------------------------------------

    st.subheader("Heart Rate Analysis")

    hr_data = chart_data.dropna(
        subset=[
            "Distance (km)",
            "heart_rate"
        ]
    )

    fig_hr = go.Figure()

    fig_hr.add_trace(
        go.Scatter(
            x=hr_data["Distance (km)"],
            y=hr_data["heart_rate"],
            name="Heart Rate",
            mode="lines",
            line=dict(color = "#FF4B4B")
        )
    )

    hr_smooth = chart_data.dropna(
        subset=[
            "Distance (km)",
            "hr_smooth"
        ]
    )

    fig_hr.add_trace(
        go.Scatter(
            x=hr_smooth["Distance (km)"],
            y=hr_smooth["hr_smooth"],
            name="Smoothed HR",
            mode="lines",
            line=dict(width=3, color = "#4bff7b"),
        )
    )

    fig_hr.update_layout(
        height=400,
        xaxis_title="Distance (km)",
        yaxis_title="Heart Rate (bpm)",
        margin=dict(
            l=20,
            r=20,
            t=30,
            b=20,
        ),
    )

    st.plotly_chart(
        fig_hr,
        use_container_width=True
    )

    # --------------------------------------------------------
    # Pace vs HR
    # --------------------------------------------------------

    st.subheader("Pace vs Heart Rate")

    relationship = activity_df[
        [
            "pace_min_km",
            "heart_rate",
            "distance"
        ]
    ].dropna()

    relationship = relationship[
        relationship["pace_min_km"].between(
            2,
            15
        )
    ]

    relationship["Distance (km)"] = (
        relationship["distance"] / 1000
    )

    fig_relationship = px.scatter(
        relationship,
        x="heart_rate",
        y="pace_min_km",
        color="Distance (km)",
        hover_data=[
            "Distance (km)"
        ],
    )

    fig_relationship.update_layout(
        height=450,
        xaxis_title="Heart Rate (bpm)",
        yaxis_title="Pace (min/km)",
    )

    fig_relationship.update_yaxes(
        autorange="reversed"
    )

    st.plotly_chart(
        fig_relationship,
        use_container_width=True
    )

    # --------------------------------------------------------
    # Efficiency
    # --------------------------------------------------------

    st.subheader("Pace / Heart Rate Efficiency")

    efficiency = activity_df[
        [
            "distance",
            "hr_efficiency"
        ]
    ].dropna()

    efficiency["Distance (km)"] = (
        efficiency["distance"] / 1000
    )

    fig_efficiency = px.line(
        efficiency,
        x="Distance (km)",
        y="hr_efficiency",
    )

    fig_efficiency.update_layout(
        height=350,
        xaxis_title="Distance (km)",
        yaxis_title="Speed / HR",
        margin=dict(
            l=20,
            r=20,
            t=30,
            b=20,
        ),
    )

    st.plotly_chart(
        fig_efficiency,
        use_container_width=True
    )


# ============================================================
# TAB 3 — SPLITS
# ============================================================

with tab_splits:

    st.subheader("Kilometer Splits")

    if splits.empty:

        st.info(
            "Not enough distance data for kilometer splits."
        )

    else:

        display_splits = splits.copy()

        # ----------------------------------------------------
        # Format values for display
        # ----------------------------------------------------

        display_splits["Time"] = (
            display_splits["Time_sec"]
            .apply(format_split_time)
        )

        display_splits["Pace"] = (
            display_splits["Pace_min_km"]
            .apply(format_pace)
        )

        display_splits["Avg HR"] = (
            display_splits["Avg_HR"]
            .round(0)
        )

        display_splits["Elevation Gain"] = (
            display_splits["Elevation_Gain"]
            .round(1)
        )

        # ----------------------------------------------------
        # Display table
        # ----------------------------------------------------

        display_splits = display_splits[
            [
                "Kilometer",
                "Time",
                "Pace",
                "Avg HR",
                "Elevation Gain",
            ]
        ]

        st.dataframe(
            display_splits,
            use_container_width=True,
            hide_index=True,
        )

        # ----------------------------------------------------
        # Split Pace Chart
        # ----------------------------------------------------

        st.subheader("Split Pace")

        fig_split = go.Figure()

        fig_split.add_trace(
            go.Bar(
                x=splits["Kilometer"],
                y=splits["Pace_min_km"],
                name="Pace",
            )
        )

        fig_split.update_layout(
            height=400,
            xaxis_title="Kilometer",
            yaxis_title="Pace (min/km)",
        )

        st.plotly_chart(
            fig_split,
            use_container_width=True
        )

        # ----------------------------------------------------
        # Split HR Chart
        # ----------------------------------------------------

        st.subheader("Split Heart Rate")

        fig_split_hr = px.line(
            splits,
            x="Kilometer",
            y="Avg_HR",
            markers=True,
        )

        fig_split_hr.update_layout(
            height=350,
            xaxis_title="Kilometer",
            yaxis_title="Average HR (bpm)",
        )

        st.plotly_chart(
            fig_split_hr,
            use_container_width=True
        )


# ============================================================
# TAB 4 — ROUTE & ELEVATION
# ============================================================

with tab_route:

    st.subheader("GPS Route")

    map_data = activity_df.dropna(
        subset=[
            "latitude",
            "longitude"
        ]
    ).copy()

    if map_data.empty:

        st.warning(
            "No GPS coordinates available."
        )

    else:

        # ----------------------------------------------------
        # Color selector
        # ----------------------------------------------------

        color_variable = st.selectbox(
            "Route point color",
            [
                "Heart Rate",
                "Pace",
                "Speed",
                "Elevation",
            ]
        )

        if color_variable == "Heart Rate":

            map_data["map_value"] = (
                map_data["heart_rate"]
            )

            tooltip_name = "Heart Rate"

        elif color_variable == "Pace":

            map_data["map_value"] = (
                map_data["pace_min_km"]
            )

            tooltip_name = "Pace"

        elif color_variable == "Speed":

            map_data["map_value"] = (
                map_data["speed_kmh"]
            )

            tooltip_name = "Speed"

        else:

            map_data["map_value"] = (
                map_data["altitude"]
            )

            tooltip_name = "Elevation"

        valid_values = map_data[
            "map_value"
        ].dropna()

        if valid_values.empty:

            minimum = 0
            maximum = 1

        else:

            minimum = valid_values.min()
            maximum = valid_values.max()

        map_data["color"] = map_data[
            "map_value"
        ].apply(
            lambda x:
                value_to_color(
                    x,
                    minimum,
                    maximum
                )
        )

        # ----------------------------------------------------
        # View
        # ----------------------------------------------------

        view_state = pdk.ViewState(
            latitude=map_data[
                "latitude"
            ].mean(),

            longitude=map_data[
                "longitude"
            ].mean(),

            zoom=13,
            pitch=0,
        )

        # ----------------------------------------------------
        # Route line
        # ----------------------------------------------------

        route_data = [
            [
                row["longitude"],
                row["latitude"]
            ]
            for _, row in map_data.iterrows()
        ]

        route_layer = pdk.Layer(
            "PathLayer",
            data=[
                {
                    "path": route_data
                }
            ],
            get_path="path",
            get_color=[
                255,
                255,
                255,
                180
            ],
            width_min_pixels=3,
        )

        # ----------------------------------------------------
        # Trackpoint layer
        # ----------------------------------------------------

        point_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position=[
                "longitude",
                "latitude"
            ],
            get_fill_color="color",
            get_radius=6,
            pickable=True,
        )

        deck = pdk.Deck(
            initial_view_state=view_state,
            layers=[
                route_layer,
                point_layer
            ],
            tooltip={
                "html":
                    f"<b>{tooltip_name}</b>: "
                    "{map_value}<br/>"
                    "<b>HR</b>: {heart_rate}<br/>"
                    "<b>Speed</b>: {speed_kmh} km/h<br/>"
                    "<b>Altitude</b>: {altitude} m"
            },
        )

        st.pydeck_chart(
            deck,
            use_container_width=True
        )

    # --------------------------------------------------------
    # Elevation
    # --------------------------------------------------------

    st.subheader("Elevation Profile")

    elevation_data = activity_df.dropna(
        subset=[
            "distance",
            "altitude"
        ]
    ).copy()

    elevation_data[
        "Distance (km)"
    ] = (
        elevation_data["distance"]
        / 1000
    )

    fig_elevation = px.area(
        elevation_data,
        x="Distance (km)",
        y="altitude",
    )

    fig_elevation.update_layout(
        height=400,
        xaxis_title="Distance (km)",
        yaxis_title="Elevation (m)",
    )

    st.plotly_chart(
        fig_elevation,
        use_container_width=True
    )

    # --------------------------------------------------------
    # Grade
    # --------------------------------------------------------

    st.subheader("Grade")

    grade_data = activity_df.dropna(
        subset=[
            "distance",
            "grade_percent"
        ]
    ).copy()

    grade_data[
        "Distance (km)"
    ] = (
        grade_data["distance"]
        / 1000
    )

    fig_grade = px.line(
        grade_data,
        x="Distance (km)",
        y="grade_percent",
    )

    fig_grade.add_hline(
        y=0,
        line_width=1
    )

    fig_grade.update_layout(
        height=350,
        xaxis_title="Distance (km)",
        yaxis_title="Grade (%)",
    )

    st.plotly_chart(
        fig_grade,
        use_container_width=True
    )


# TAB 5 — DATA QUALITY
# ============================================================

with tab_quality:

    st.subheader("Data Quality")

    total_points = quality[
        "total_points"
    ]

    q1, q2, q3, q4 = st.columns(4)

    q1.metric(
        "Trackpoints",
        f"{total_points:,}"
    )

    q2.metric(
        "Median Sampling",
        (
            f"{quality['median_interval']:.2f} s"
            if not pd.isna(
                quality["median_interval"]
            )
            else "--"
        )
    )

    q3.metric(
        "Maximum Time Gap",
        (
            f"{quality['max_gap']:.1f} s"
            if not pd.isna(
                quality["max_gap"]
            )
            else "--"
        )
    )

    q4.metric(
        "Speed Anomalies",
        f"{quality['speed_anomalies']:,}"
    )

    st.divider()

    st.subheader("Missing Data")

    missing_rows = []

    for column, count in quality[
        "missing"
    ].items():

        percentage = (
            count / total_points
        ) * 100

        missing_rows.append(
            {
                "Field": column,
                "Missing": count,
                "Missing (%)": percentage,
            }
        )

    missing_df = pd.DataFrame(
        missing_rows
    )

    missing_df[
        "Missing (%)"
    ] = missing_df[
        "Missing (%)"
    ].round(2)

    st.dataframe(
        missing_df,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Sampling Interval")

    sampling = (
        activity_df["time"]
        .diff()
        .dt.total_seconds()
        .dropna()
    )

    if not sampling.empty:

        fig_sampling = px.histogram(
            sampling,
            x=sampling,
            nbins=30,
        )

        fig_sampling.update_layout(
            xaxis_title="Time Between Trackpoints (seconds)",
            yaxis_title="Number of Trackpoints",
            height=350,
        )

        st.plotly_chart(
            fig_sampling,
            use_container_width=True
        )

    st.divider()

    st.subheader("Raw Data Preview")

    display_df = activity_df.copy()

    display_df["time"] = (
        pd.to_datetime(
            display_df["time"],
            utc=True
        )
        .dt.tz_convert("Asia/Kuala_Lumpur")
    )

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
    )