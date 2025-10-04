"""
Streamlit Web App for Uber Driver Advisor
Run with: streamlit run app.py
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from engine import UberDriverAdvisor

# Page config
st.set_page_config(
    page_title="Uber Driver Advisor",
    page_icon="🚗",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {s
        font-size: 3rem;
        color: #000000;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .recommendation-box {
        padding: 2rem;
        border-radius: 10px;
        margin: 2rem 0;
        font-size: 1.2rem;
        font-weight: bold;
    }
    .rec-break {
        background-color: #ff4b4b;
        color: white;
    }
    .rec-move {
        background-color: #00cc00;
        color: white;
    }
    .rec-stay {
        background-color: #ffa500;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Load data (cache for performance)
@st.cache_data
def load_data():
    """Load all data once and cache it."""
    path = "/Users/chahid/projects/uber-copilot/data/data_sets.xlsx"
    
    with st.spinner("Loading data..."):
        ride_trips = pd.read_excel(path, sheet_name='rides_trips')
        eats_orders = pd.read_excel(path, sheet_name='eats_orders')
        heatmap = pd.read_excel(path, sheet_name='heatmap')
        surge_by_hour = pd.read_excel(path, sheet_name='surge_by_hour')
    
    return ride_trips, eats_orders, heatmap, surge_by_hour

@st.cache_resource
def get_advisor(_ride_trips, _eats_orders, _heatmap, _surge_by_hour):
    """Initialize advisor once and cache it."""
    return UberDriverAdvisor(_ride_trips, _eats_orders, _heatmap, _surge_by_hour)

def get_driver_list(ride_trips, eats_orders):
    """Get list of all drivers with stats."""
    all_drivers = list(set(ride_trips['driver_id'].unique()) | 
                      set(eats_orders['courier_id'].unique()))
    
    driver_stats = []
    for driver_id in all_drivers:
        driver_rides = ride_trips[ride_trips['driver_id'] == driver_id]
        driver_eats = eats_orders[eats_orders['courier_id'] == driver_id]
        
        if not driver_rides.empty:
            total_trips = len(driver_rides)
            last_active = pd.to_datetime(driver_rides['start_time']).max()
        elif not driver_eats.empty:
            total_trips = len(driver_eats)
            last_active = pd.to_datetime(driver_eats['start_time']).max()
        else:
            continue
        
        driver_stats.append({
            'driver_id': driver_id,
            'total_trips': total_trips,
            'last_active': last_active
        })
    
    return sorted(driver_stats, key=lambda x: x['last_active'], reverse=True)

def format_fatigue_badge(fatigue):
    """Return colored badge for fatigue level."""
    if fatigue < 0.3:
        return "Fresh"
    elif fatigue < 0.5:
        return "Moderate"
    elif fatigue < 0.7:
        return "Tired"
    elif fatigue < 0.85:
        return "Very Tired"
    else:
        return "Exhausted"

# Main app
def main():
    # Header
    st.markdown('<h1 class="main-header">🚗 Uber Driver Advisor</h1>', unsafe_allow_html=True)
    st.markdown("### Get intelligent recommendations on where to drive next")
    
    # Load data
    try:
        ride_trips, eats_orders, heatmap, surge_by_hour = load_data()
        advisor = get_advisor(ride_trips, eats_orders, heatmap, surge_by_hour)
        st.success(f"Data loaded: {len(ride_trips)} rides, {len(eats_orders)} deliveries")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.stop()
    
    # Sidebar - Driver Selection
    st.sidebar.header("🔍 Select Driver")
    
    driver_list = get_driver_list(ride_trips, eats_orders)
    
    # Driver selection dropdown
    driver_options = [f"{d['driver_id']} ({d['total_trips']} trips)" for d in driver_list[:50]]
    selected_driver_str = st.sidebar.selectbox("Choose a driver:", driver_options, index=0)
    selected_driver_id = selected_driver_str.split(' ')[0]
    
    # Get driver's available dates
    driver_rides = ride_trips[ride_trips['driver_id'] == selected_driver_id]
    driver_eats = eats_orders[eats_orders['courier_id'] == selected_driver_id]
    
    if not driver_rides.empty:
        driver_times = pd.to_datetime(driver_rides['start_time'])
    elif not driver_eats.empty:
        driver_times = pd.to_datetime(driver_eats['start_time'])
    else:
        st.error("No data for selected driver")
        st.stop()
    
    min_date = driver_times.min().date()
    max_date = driver_times.max().date()
    
    # Time selection
    st.sidebar.header("Select Time")
    
    use_latest = st.sidebar.checkbox("Use latest available time", value=True)
    
    if use_latest:
        selected_datetime = driver_times.max()
        st.sidebar.info(f"Using: {selected_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        selected_date = st.sidebar.date_input(
            "Date:",
            value=max_date,
            min_value=min_date,
            max_value=max_date
        )
        
        selected_time = st.sidebar.time_input(
            "Time:",
            value=datetime.now().time()
        )
        
        selected_datetime = datetime.combine(selected_date, selected_time)
    
    # Get Recommendation Button
    if st.sidebar.button("Get Recommendation", type="primary", use_container_width=True):
        st.session_state['show_recommendation'] = True
    
    # Show recommendation if button clicked
    if st.session_state.get('show_recommendation', False):
        with st.spinner("Analyzing..."):
            result = advisor.recommend_action(
                selected_driver_id, 
                selected_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                verbose=False
            )
        
        if 'error' in result:
            st.error(f"{result['error']}")
            st.stop()
        
        # Display Results
        st.markdown("---")
        st.header("Driver Status")
        
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Hours Worked", f"{result['total_hours']:.1f} hrs")
        
        with col2:
            st.metric("Jobs Completed", result['total_jobs'])
        
        with col3:
            st.metric("Fatigue Level", f"{result['fatigue']:.0%}")
            st.markdown(format_fatigue_badge(result['fatigue']))
        
        with col4:
            st.metric("Current Location", result['current_hex'])
        
        # Current location info
        st.markdown("---")
        st.subheader("Current Location")
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Base EPH", f"€{result['current_eph']:.2f}/hr")
        
        with col2:
            st.metric("Effective EPH", f"€{result['current_effective_eph']:.2f}/hr", 
                     help="Adjusted for fatigue")
        
        # Recommendation
        st.markdown("---")
        st.header("💡 Recommendation")
        
        # Color based on action
        if result['action'] == 'break':
            rec_class = "rec-break"
            icon = "🛑"
        elif result['action'] == 'move':
            rec_class = "rec-move"
            icon = "🚀"
        else:
            rec_class = "rec-stay"
            icon = "⏸️"
        
        st.markdown(
            f'<div class="recommendation-box {rec_class}">{icon} {result["recommendation"]}</div>',
            unsafe_allow_html=True
        )
        
        # Best hotspot details (if moving)
        if result['action'] == 'move':
            st.markdown("---")
            st.subheader("🎯 Best Hotspot Details")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Location", result['best_hex'])
            
            with col2:
                st.metric("Distance", f"{result['best_distance_km']} km")
            
            with col3:
                st.metric("Travel Time", f"~{result['best_travel_time_mins']:.0f} min")
            
            with col4:
                st.metric("Expected EPH", f"€{result['best_effective_eph']:.2f}/hr",
                         delta=f"+{result['best_effective_eph'] - result['current_effective_eph']:.2f}")
        
        # Additional insights
        if result['action'] == 'stay' and result.get('reason') == 'no_hotspots':
            st.info("ℹ️ No better locations found within 30 minutes drive. Current location is optimal.")
        
        elif result['action'] == 'stay' and result.get('reason') == 'insufficient_improvement':
            st.info(f"ℹ️ Best alternative only improves earnings by {(result['improvement_ratio'] - 1) * 100:.0f}%. "
                   f"Travel time not worth it (need ≥25% improvement).")

if __name__ == "__main__":
    main()