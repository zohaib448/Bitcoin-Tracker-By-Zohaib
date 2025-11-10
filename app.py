import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import time
from datetime import datetime, timedelta
import os
from typing import Optional, Dict, Any

# Page configuration
st.set_page_config(
    page_title="Zohaib's Bitcoin Tracker",
    page_icon="₿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

class BitcoinDashboard:
    def _init_(self):
        self.cache_file = "bitnodes_cache.json"
        self.data_file = "network_data.json"
        self.max_data_points = 1008  # 7 days of 10-minute intervals
        self.cache_duration = 600  # 10 minutes in seconds
        self.sample_size = 1000
        
    def get_cached_data(self, key: str) -> Optional[Dict]:
        """Retrieve cached data with expiration check"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                
                if key in cache:
                    cached_time = datetime.fromisoformat(cache[key]['timestamp'])
                    if (datetime.now() - cached_time).total_seconds() < self.cache_duration:
                        return cache[key]['data']
        except Exception:
            pass
        return None
    
    def set_cached_data(self, key: str, data: Dict):
        """Store data in cache with timestamp"""
        try:
            cache = {}
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
            
            cache[key] = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f)
        except Exception:
            pass
    
    def make_api_request_with_retry(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Make API request with exponential backoff retry logic"""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff: 2, 4, 8 seconds
        
        return None
    
    def get_bitcoin_price(self) -> Optional[float]:
        """Get BTC price with fallback APIs"""
        apis = [
            ("Binance", "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"),
            ("CoinGecko", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"),
            ("Coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot")
        ]
        
        for name, url in apis:
            data = self.make_api_request_with_retry(url)
            if data:
                try:
                    if name == "Binance":
                        return float(data['price'])
                    elif name == "CoinGecko":
                        return float(data['bitcoin']['usd'])
                    elif name == "Coinbase":
                        return float(data['data']['amount'])
                except (KeyError, TypeError):
                    continue
        
        return None
    
    def get_bitnodes_data(self) -> Optional[Dict]:
        """Get Bitnodes data with caching"""
        # Check cache first
        cached_data = self.get_cached_data('bitnodes')
        if cached_data:
            return cached_data
        
        # Fetch fresh data
        url = "https://bitnodes.io/api/v1/snapshots/latest/"
        data = self.make_api_request_with_retry(url)
        
        if data:
            self.set_cached_data('bitnodes', data)
        
        return data
    
    def calculate_tor_percentage(self, nodes: Dict) -> float:
        """Calculate percentage of Tor nodes"""
        if not nodes:
            return 0.0
        
        # Sample nodes for performance
        sampled_nodes = dict(list(nodes.items())[:self.sample_size])
        
        tor_count = 0
        total_count = len(sampled_nodes)
        
        for node_data in sampled_nodes.values():
            if isinstance(node_data, list) and len(node_data) >= 2:
                user_agent = str(node_data[1]).lower()
                if 'tor' in user_agent or 'onion' in user_agent:
                    tor_count += 1
        
        return (tor_count / total_count) * 100 if total_count > 0 else 0.0
    
    def load_historical_data(self) -> list:
        """Load historical network data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def save_historical_data(self, data: list):
        """Save historical network data with retention limit"""
        try:
            # Keep only the last max_data_points
            if len(data) > self.max_data_points:
                data = data[-self.max_data_points:]
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    
    def calculate_tor_trend(self, current_tor: float, previous_tor: float) -> float:
        """Calculate Tor trend percentage"""
        if previous_tor == 0:
            return 0.0
        return ((current_tor - previous_tor) / previous_tor) * 100
    
    def get_tor_market_bias(self, tor_trend: float) -> tuple:
        """Determine market bias based on Tor trend"""
        if tor_trend > 1.0:  # Significant increase
            return "SELL BIAS", "🔴", "red"
        elif tor_trend < -1.0:  # Significant decrease
            return "BUY BIAS", "🟢", "green"
        else:
            return "NEUTRAL", "🟡", "yellow"
    
    def calculate_network_signal(self, current_data: Dict, previous_data: Dict) -> float:
        """Calculate network trend signal"""
        if not previous_data:
            return 0.0
        
        current_total = current_data.get('total_nodes', 0)
        previous_total = previous_data.get('total_nodes', 0)
        current_active = current_data.get('active_nodes', 0)
        
        if previous_total == 0 or current_total == 0:
            return 0.0
        
        node_growth = (current_total - previous_total) / previous_total
        active_ratio = current_active / current_total
        
        return active_ratio * node_growth
    
    def get_network_signal(self, signal_value: float) -> tuple:
        """Determine network trading signal"""
        if signal_value > 0.01:
            return "BUY", "🟢", "green"
        elif signal_value < -0.01:
            return "SELL", "🔴", "red"
        else:
            return "SIDEWAYS", "🟡", "yellow"
    
    def create_tor_chart(self, historical_data: list) -> go.Figure:
        """Create Tor percentage trend chart"""
        if len(historical_data) < 2:
            fig = go.Figure()
            fig.update_layout(
                title="Tor Percentage Trend (24 Hours)",
                xaxis_title="Time",
                yaxis_title="Tor Percentage (%)",
                height=300
            )
            return fig
        
        # Get last 24 hours of data
        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_data = []
        
        for point in historical_data[-144:]:  # Last 144 data points (24 hours)
            try:
                point_time = datetime.fromisoformat(point['timestamp'])
                if point_time >= cutoff_time:
                    recent_data.append(point)
            except Exception:
                continue
        
        if not recent_data:
            recent_data = historical_data[-24:]  # Fallback to last 24 points
        
        timestamps = [point.get('timestamp', '') for point in recent_data]
        tor_percentages = [point.get('tor_percentage', 0) for point in recent_data]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=tor_percentages,
            mode='lines+markers',
            name='Tor %',
            line=dict(color='#FF4B4B', width=3),
            marker=dict(size=4)
        ))
        
        fig.update_layout(
            title="Tor Percentage Trend (24 Hours)",
            xaxis_title="Time",
            yaxis_title="Tor Percentage (%)",
            height=300,
            showlegend=False,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        return fig
    
    def run_dashboard(self):
        """Main dashboard execution"""
        
        # Custom CSS for mobile optimization
        st.markdown("""
        <style>
        .main > div {
            padding: 1rem;
        }
        .stAlert {
            padding: 0.5rem;
        }
        .metric-card {
            background-color: #f0f2f6;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 0.5rem 0;
        }
        @media (max-width: 768px) {
            .main > div {
                padding: 0.5rem;
            }
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Header with branding
        st.markdown("<h1 style='text-align: center;'>₿ Zohaib's Bitcoin Tracker</h1>", unsafe_allow_html=True)
        
        # Real-time BTC Price
        st.markdown("### Live Bitcoin Price")
        btc_price = self.get_bitcoin_price()
        
        if btc_price:
            st.markdown(f"""
            <div style='text-align: center; padding: 1rem; background-color: #f0f2f6; border-radius: 0.5rem;'>
                <h2 style='margin: 0; color: #f7931a;'>${btc_price:,.2f}</h2>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("Unable to fetch BTC price")
        
        st.markdown("---")
        
        # Bitnodes Data Analysis
        st.markdown("### Network Analysis")
        
        bitnodes_data = self.get_bitnodes_data()
        historical_data = self.load_historical_data()
        
        if not bitnodes_data:
            st.error("Unable to fetch Bitnodes data. Please try again later.")
            return
        
        # Calculate current metrics
        nodes = bitnodes_data.get('nodes', {})
        total_nodes = len(nodes)
        current_tor_percentage = self.calculate_tor_percentage(nodes)
        
        current_snapshot = {
            'timestamp': datetime.now().isoformat(),
            'total_nodes': total_nodes,
            'active_nodes': total_nodes,  # Bitnodes provides active snapshots
            'tor_percentage': current_tor_percentage
        }
        
        # Get previous data for comparisons
        previous_data = None
        if historical_data:
            previous_data = historical_data[-1]
        
        # Tor Trend Analysis
        st.markdown("#### Tor Privacy Trend Analysis")
        
        if previous_data:
            previous_tor = previous_data.get('tor_percentage', 0)
            tor_trend = self.calculate_tor_trend(current_tor_percentage, previous_tor)
            market_bias, bias_icon, bias_color = self.get_tor_market_bias(tor_trend)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Previous Tor %", f"{previous_tor:.1f}%")
            with col2:
                st.metric("Current Tor %", f"{current_tor_percentage:.1f}%")
            
            st.markdown(f"""
            <div style='padding: 1rem; background-color: {bias_color}20; border-radius: 0.5rem; border-left: 4px solid {bias_color};'>
                <h4 style='margin: 0;'>Tor Trend: {tor_trend:+.1f}%</h4>
                <p style='margin: 0.5rem 0 0 0;'>→ Market Bias: {market_bias} {bias_icon}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Collecting initial data... Please refresh in 10 minutes for trend analysis.")
        
        # Network Trend Signal
        st.markdown("#### Network Trend Signal")
        
        network_signal_value = self.calculate_network_signal(current_snapshot, previous_data) if previous_data else 0.0
        network_signal, signal_icon, signal_color = self.get_network_signal(network_signal_value)
        
        st.markdown(f"""
        <div style='padding: 1rem; background-color: {signal_color}20; border-radius: 0.5rem; border-left: 4px solid {signal_color};'>
            <h4 style='margin: 0;'>Network Signal: {network_signal_value:+.4f}</h4>
            <p style='margin: 0.5rem 0 0 0;'>→ Trading Signal: {network_signal} {signal_icon}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Update historical data
        historical_data.append(current_snapshot)
        self.save_historical_data(historical_data)
        
        # Tor Trend Chart
        st.markdown("#### Tor Privacy Metrics")
        tor_chart = self.create_tor_chart(historical_data)
        st.plotly_chart(tor_chart, use_container_width=True)
        
        # Network Statistics
        st.markdown("#### Network Statistics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Nodes", f"{total_nodes:,}")
        with col2:
            st.metric("Tor Nodes", f"{current_tor_percentage:.1f}%")
        with col3:
            st.metric("Data Points", len(historical_data))
        
        # Last update time
        st.markdown(f"""
        <div style='text-align: center; margin-top: 2rem; color: #666; font-size: 0.8rem;'>
            Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
        """, unsafe_allow_html=True)

if _name_ == "_main_":
    main()
