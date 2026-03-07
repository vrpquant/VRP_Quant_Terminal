import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import numpy as np

# ==========================================
# --- GITHUB CRR VAULT CONNECTION ---
# ==========================================
# ⚠️ PASTE YOUR RAW GITHUB LINK INSIDE THESE QUOTES:
GITHUB_VAULT_URL = "https://raw.githubusercontent.com/vrpquant/VRP_Quant_Terminal/main/market_state.json"

@st.cache_data(ttl=60)
def load_vault_data():
    try:
        response = requests.get(GITHUB_VAULT_URL)
        if response.status_code == 200: return response.json()
        return None
    except: return None

# ==========================================
# --- INSTITUTIONAL UI THEME INJECTION ---
# ==========================================
st.set_page_config(page_title="VRP Quant | V22.2 Cloud", layout="wide", page_icon="🏦", initial_sidebar_state="expanded")

def inject_institutional_css():
    st.markdown("""
    <style>
        /* Main Backgrounds */
        .stApp { background-color: #0B0F19; color: #F8FAFC; }
        [data-testid="stSidebar"] { background-color: #0F172A; border-right: 1px solid #1E293B; }
        
        /* Metric Cards */
        div[data-testid="metric-container"] {
            background-color: #1E293B; border: 1px solid #334155;
            padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        div[data-testid="metric-container"] label { color: #94A3B8 !important; font-weight: 600 !important; letter-spacing: 0.5px; }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #38BDF8 !important; font-size: 1.8rem !important; font-weight: 700 !important; }
        
        /* The Awesome Spot / Apex Box */
        .apex-box {
            background-color: #082F49; border-left: 5px solid #38BDF8;
            border-radius: 5px; padding: 20px; margin-top: 15px; margin-bottom: 25px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .hqta-red { background-color: #450a0a; border-left: 5px solid #f87171; border-radius: 5px; padding: 20px; margin-top: 15px; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);}
        .hqta-green { background-color: #082F49; border-left: 5px solid #38BDF8; border-radius: 5px; padding: 20px; margin-top: 15px; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);}
        
        .apex-title { color: #BAE6FD; font-size: 1.4em; font-weight: 800; margin-bottom: 10px; }
        .apex-action { font-size: 1.2em; font-weight: 700; margin-bottom: 10px; }
        .apex-logic { color: #94A3B8; font-size: 1em; font-style: italic; }
        
        /* Headers and Dividers */
        h1, h2, h3 { color: #F1F5F9 !important; font-weight: 700 !important; }
        hr { border-color: #334155 !important; }
    </style>
    """, unsafe_allow_html=True)

inject_institutional_css()

try: USERS = st.secrets["credentials"]
except Exception as e:
    st.error("⚠️ SYSTEM LOCKED: Security vault not connected. Please configure [credentials] in Streamlit Secrets.")
    st.stop()

def check_login():
    if "authenticated" not in st.session_state: st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.markdown("<br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        
        with c2:
            st.markdown("""
            <div style='background-color: #1E293B; padding: 30px; border-radius: 10px; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);'>
                <h2 style='text-align: center; color: #F8FAFC;'>🔒 VRP Quant Terminal</h2>
                <p style='text-align: center; color: #94A3B8; font-size: 14px;'>Institutional-Grade Options Architecture & Volatility Risk Premium Scans</p>
                <hr style='border-color: #334155;'>
            </div>
            """, unsafe_allow_html=True)
            
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            
            if st.button("Log In", use_container_width=True):
                if user in USERS and USERS[user]["password"] == pwd:
                    st.session_state.authenticated, st.session_state.tier = True, USERS[user]["tier"]
                    st.rerun()
                else: 
                    st.error("Invalid Credentials.")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 👑 Founding Member Cohort (V22.2)")
            
            b1, b2 = st.columns(2)
            with b1:
                st.info("**ANALYST TIER**\n* Retail Price: ~~$299/mo~~\n* Founding Member: **$149/mo**")
                # ⚠️ PASTE YOUR ANALYST PAYPAL LINK HERE
                st.link_button("💳 Subscribe via PayPal", "https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-0CB63794C10515154NGMNDNA", use_container_width=True)
            with b2:
                st.success("**GOD MODE TIER**\n* Unlock 10k-path MC & CRR Binomial Pricing.\n* Founding Member: **$499/mo**")
                # ⚠️ PASTE YOUR GOD MODE PAYPAL LINK HERE
                st.link_button("💳 Subscribe via PayPal", "https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-723423746M676015CNGMNFGI", use_container_width=True)

        return False
    return True

# ==========================================
# --- MAIN APP EXECUTION ---
# ==========================================
if check_login():
    tier = st.session_state.tier
    vault_state = load_vault_data()
    
    with st.sidebar:
        st.markdown("# 🏦 VRP Quant V22.2")
        if tier == "GOD_MODE": st.success("🔓 GOD MODE ACTIVE")
        else: st.warning("🔒 ANALYST TIER")
        st.markdown("---")
        mode = st.radio("Module", ["🚀 Market Scanner", "🔬 Deep Dive Analysis"])
        st.markdown("---")
        
        if vault_state:
            macro = vault_state.get('macro', {})
            st.metric("VIX (Volatility Index)", f"{macro.get('vix', 'N/A')}")
            st.metric("TNX (10-Yr Yield)", f"{macro.get('tnx', 'N/A')}%")
            st.caption(f"📡 Vault Last Synced:\n{vault_state.get('last_updated', 'Unknown')}")
        else: st.error("📡 Vault Connection Severed")
            
        st.markdown("---")
        if st.button("Log Out"):
            st.session_state.authenticated = False
            st.rerun()

    if not vault_state: st.stop()
    df_scan = pd.DataFrame(vault_state["data"])

    # --- MODULE 1: MARKET SCANNER ---
    if mode == "🚀 Market Scanner":
        st.title("🚀 Institutional Market Scanner")
        
        if tier != "GOD_MODE":
            st.error("🔒 ACCESS DENIED: Market Scanner is locked for Analyst Tier. Please upgrade to God Mode.")
        else:
            st.caption("⏱️ **Data Snapshot:** Displaying latest compiled quantitative run from the cloud.")
            display_cols = ["Ticker", "Price", "Alpha Score", "Trend", "VRP Edge", "Vol", "Strategy", "Kelly"]
            styled_df = df_scan[display_cols].style.set_properties(**{
                'background-color': '#1E293B', 'color': '#F8FAFC', 'border-color': '#334155'
            })
            st.dataframe(styled_df, use_container_width=True, height=600)

    # --- MODULE 2: DEEP DIVE ANALYSIS ---
    elif mode == "🔬 Deep Dive Analysis":
        st.title("🔬 Deep Dive & Trade Architect")
        
        ticker = st.selectbox("Asset Ticker", df_scan['Ticker'].tolist())
        stats = df_scan[df_scan['Ticker'] == ticker].iloc[0]
        
        # Hybrid Plan Logic (Recreated for lightweight speed)
        vrp_num = float(stats['VRP Edge'].replace('%', ''))
        score = stats['Alpha Score']
        sup, res = stats['Support'], stats['Resistance']
        
        if score >= 60:
            if vrp_num > 0:
                h_name, h_action, h_logic = "The Institutional Buy-Write (Yield Harvest)", f"Buy 100 Shares @ Market AND Sell 1 Call Option @ ${res:.2f} Strike.", "Trend is strong, but options are expensive. We buy the stock and sell overpriced calls to institutions to lower our risk."
            else:
                h_name, h_action, h_logic = "The Bulletproof Bull (Protected Upside)", f"Buy 100 Shares @ Market AND Buy 1 Put Option @ ${sup:.2f} Strike.", "Trend is strong and options are cheap. We ride the stock up, but buy cheap insurance at Support to make this mathematically low-stress."
        elif score <= 40:
            if vrp_num > 0:
                h_name, h_action, h_logic = "The Warren Buffett Entry (Discount Acquisition)", f"Hold Cash AND Sell 1 Cash-Secured Put @ ${sup:.2f} Strike.", "Momentum is weak and fear is high. Do not buy the stock yet. Sell puts to get paid upfront while waiting to buy it at the Support floor."
            else:
                h_name, h_action, h_logic = "The Smart-Money Short (Risk-Defined Bear)", f"Do NOT Buy Stock. Buy 1 Put Option Vertical Spread targeting ${sup:.2f}.", "Momentum is broken and options are cheap. We use low-risk put options to profit from the drop without shorting shares."
        else:
            h_name, h_action, h_logic = "The Floor-to-Ceiling Swing (Mean Reversion)", f"Place Limit Buy Order for Shares @ ${sup:.2f} AND Set Sell Target @ ${res:.2f}.", "Stock is trapped in a channel. We refuse to buy at current prices. We set traps at the floor and sell at the ceiling."

        st.markdown(f"""
        <div class="apex-box">
            <div class="apex-title">🏆 THE AWESOME SPOT: {h_name}</div>
            <div class="apex-action" style="color: #38BDF8;">TRADE ARCHITECTURE: {h_action}</div>
            <div class="apex-logic">Institutional Logic: {h_logic}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 📊 Market Variables")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Price", f"${stats['Price']:.2f}")
        m2.metric("Alpha Score", f"{stats['Alpha Score']}/100")
        m3.metric("Trend", stats['Trend'])
        m4.metric("Volatility", f"{stats['Vol']}")
        m5.metric("Orthogonalization", stats.get('Ortho', 'N/A'))

        m6, m7, m8, m9, m10 = st.columns(5)
        m6.metric("VRP Edge", stats['VRP Edge'])
        m7.metric("Sharpe Ratio", f"{stats.get('Sharpe', 'N/A')}")
        m8.metric("Support (Floor)", f"${stats['Support']:.2f}")
        m9.metric("Resistance (Ceiling)", f"${stats['Resistance']:.2f}")
        m10.metric("95% VaR (Variance)", f"${stats.get('VaR', 'N/A')}" if tier == "GOD_MODE" else "🔒 God Mode")

        st.markdown("---")
        st.markdown("### ⚙️ Strategy Backtest Validation (2-Year)")
        b1, b2, b3, b4, b5 = st.columns(5)
        b1.metric("Historical Win Rate", f"{stats['Win Rate']}")
        b2.metric("Net Strategy Return", f"{stats['Strat Ret']}")
        b3.metric("Alpha Generated", f"{stats['Outperf']}")
        b4.metric("Markdown % (Max DD)", f"{stats['Max DD']}", delta_color="inverse")
        b5.metric("Kelly Fraction (Half)", f"{stats['Kelly']}", delta_color="normal")

        # Dynamic HQTA Allocation Box
        kelly_val = float(stats['Kelly'].replace('%', ''))
        if kelly_val > 0:
            st.markdown(f"""
            <div class="hqta-green">
                <div class="apex-title">⚡ HQTA Allocation Directive</div>
                <div class="apex-action" style="color: #38BDF8;">ACTION: ALLOCATE CAPITAL / EDGE DETECTED</div>
                <div class="apex-logic">Optimal Half-Kelly Sizing: <strong>{stats['Kelly']}</strong> of total portfolio equity.<br><em>Calculated using EWMA GARCH-proxied variance.</em></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="hqta-red">
                <div class="apex-title">⚡ HQTA Allocation Directive</div>
                <div class="apex-action" style="color: #f87171;">ACTION: FLATTEN POSITION / NO EDGE</div>
                <div class="apex-logic">Optimal Half-Kelly Sizing: <strong>0.00%</strong> of total portfolio equity.<br><em>Mathematical risk outweighs potential alpha.</em></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 🎯 Advanced Options Architecture (For Pros)")
        st.info(f"**STRATEGY:** {stats['Strategy']} (Pricing: 50-Step CRR Binomial) | **LEGS:** {stats['Legs']}")
        
        s1, s2, s3 = st.columns(3)
        s1.metric("Est. Execution Target", stats['Premium'])
        s2.metric("Prob. of Profit (POP)", f"{stats['POP']}%")
        s3.metric("Ideal DTE", "30 Days")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Institutional Chart Generation
        if 'Chart_Dates' in stats and 'Chart_Prices' in stats:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=stats['Chart_Dates'], y=stats['Chart_Prices'], name='History', line=dict(color='#F1F5F9', width=2)))
            
            if 'MC_Projection' in stats:
                future_dates = pd.date_range(start=stats['Chart_Dates'][-1], periods=30, freq='B')
                fig.add_trace(go.Scatter(x=future_dates, y=stats['MC_Projection'], name='Mean Projection', line=dict(dash='dash', color='#38BDF8', width=2)))
            
            fig.add_hline(y=stats['Support'], line_dash="dot", line_color="#4ADE80", annotation_text="Support", annotation_position="bottom right", annotation_font_color="#4ADE80")
            fig.add_hline(y=stats['Resistance'], line_dash="dot", line_color="#F87171", annotation_text="Resistance", annotation_position="top right", annotation_font_color="#F87171")
            
            fig.update_layout(
                template="plotly_dark", 
                height=500, 
                title=f"Institutional Chart (History + 30-Day Projection | 10000 Simulations)",
                paper_bgcolor='#0B0F19', 
                plot_bgcolor='#0F172A',
                font=dict(color='#F8FAFC'),
                margin=dict(l=20, r=20, t=50, b=20),
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )
            st.plotly_chart(fig, use_container_width=True)

st.markdown("<br><br><br>", unsafe_allow_html=True)
st.markdown("""
<div style="font-size: 0.85em; color: #94A3B8; line-height: 1.6; text-align: justify; padding: 15px; border-left: 4px solid #F59E0B; background-color: #1E293B; border-radius: 4px; margin-bottom: 20px;">
    <b style="color: #F8FAFC;">SEC RULE 206(4)-1 COMPLIANCE NOTICE:</b> VRP Quant and its associated V22.2 Terminal operate strictly as a financial data and analytics publisher. We are not a registered investment advisor, broker-dealer, or financial planner. All quantitative metrics, Alpha Scores, Volatility Risk Premium (VRP) edges, probabilities of Profit (POP), and mathematically derived Support/Resistance levels provided by this platform are for informational and educational purposes only. Past performance does not guarantee future results.<br><br>
    <div style="text-align: center; font-size: 0.9em; color: #64748B;">
        &copy; 2026 vrpquant.com. All Rights Reserved.
    </div>
</div>
""", unsafe_allow_html=True)
