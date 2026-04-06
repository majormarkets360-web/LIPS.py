import requests
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="LP Monitor", layout="wide", page_icon="📊")

st.title("🪙 Real-Time Liquidity Pool Monitor")
st.markdown("**Search any token pair (e.g. WETH USDC) → live pools across DEXes + price impact simulator**")

# ====================== SIDEBAR ======================
with st.sidebar:
    st.header("🔎 Pair Selection")
    query = st.text_input("Search tokens (e.g. WETH USDC)", value="WETH USDC")
   
    chain_options = ["All", "ethereum", "base", "arbitrum", "solana", "bsc", "polygon"]
    selected_chains = st.multiselect("Filter chains", chain_options[1:], default=["ethereum"])
   
    st.divider()
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_sec = st.slider("Refresh interval", 10, 60, 15)
   
    st.info("💡 Data from DexScreener public API (no key needed)")

# ====================== SESSION STATE ======================
if "pool_history" not in st.session_state:
    st.session_state.pool_history = {}   # pairAddress → list of (timestamp, price, liquidity_usd)

# ====================== FETCH DATA ======================
def fetch_pairs(search_query: str):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={search_query.replace(' ', '%20')}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("pairs", [])
    except Exception as e:
        st.error(f"API error: {e}")
        return []

# Initial fetch / refresh
if st.button("🔄 Refresh Now", type="primary") or "raw_pairs" not in st.session_state:
    with st.spinner("Fetching live pool data..."):
        raw_pairs = fetch_pairs(query)
        st.session_state.raw_pairs = raw_pairs
        st.session_state.last_update = datetime.now().strftime("%H:%M:%S")

# Filter by chain
filtered_pairs = st.session_state.get("raw_pairs", [])
if selected_chains and "All" not in selected_chains:
    filtered_pairs = [p for p in filtered_pairs if p.get("chainId") in selected_chains]

if not filtered_pairs:
    st.warning("No pools found. Try another pair like SOL USDC or ETH USDT.")
    st.stop()

# ====================== DATAFRAME ======================
data_rows = []
for p in filtered_pairs:
    liq = p.get("liquidity", {})
    vol = p.get("volume", {})
    data_rows.append({
        "Chain": p.get("chainId", "N/A").upper(),
        "DEX": p.get("dexId", "unknown").title(),
        "Pair": f"{p.get('baseToken', {}).get('symbol', '?')}/{p.get('quoteToken', {}).get('symbol', '?')}",
        "Price USD": float(p.get("priceUsd") or 0),
        "Liquidity USD": float(liq.get("usd") or 0),
        "Base Liquidity": float(liq.get("base") or 0),
        "Quote Liquidity": float(liq.get("quote") or 0),
        "24h Volume": float(vol.get("h24") or 0),
        "Pair Address": p.get("pairAddress"),
        "URL": p.get("url")
    })

df = pd.DataFrame(data_rows)

# ====================== TABS ======================
tab1, tab2, tab3, tab4 = st.tabs(["📋 All Pools", "📊 Charts by DEX", "📈 Live History", "💱 Price Impact Simulator"])

with tab1:
    st.dataframe(
        df.sort_values("Liquidity USD", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("DexScreener")}
    )
    st.caption(f"Last updated: {st.session_state.get('last_update', '—')} • {len(df)} pools")

with tab2:
    st.subheader("Liquidity & Volume by Exchange")
    colA, colB = st.columns(2)
   
    with colA:
        # One chart per DEX (bar of individual pools)
        grouped = defaultdict(list)
        for _, row in df.iterrows():
            grouped[row["DEX"]].append(row)
       
        for dex_name, pools in grouped.items():
            if len(pools) > 1 or True:  # always show
                df_dex = pd.DataFrame(pools)
                fig = px.bar(
                    df_dex,
                    x="Pair Address",
                    y="Liquidity USD",
                    title=f"{dex_name} Pools — WETH/USDC (or selected pair)",
                    labels={"Pair Address": "Pool"},
                    color="Liquidity USD",
                    color_continuous_scale="blues"
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{dex_name}")
   
    with colB:
        # Aggregated comparison across DEXes
        agg = df.groupby("DEX").agg({
            "Liquidity USD": "sum",
            "24h Volume": "sum"
        }).reset_index()
        fig_agg_liq = px.bar(agg, x="DEX", y="Liquidity USD", title="Total Liquidity per DEX")
        st.plotly_chart(fig_agg_liq, use_container_width=True)
        fig_agg_vol = px.bar(agg, x="DEX", y="24h Volume", title="24h Volume per DEX")
        st.plotly_chart(fig_agg_vol, use_container_width=True)

with tab3:
    st.subheader("Track selected pools live (price & liquidity over refreshes)")
    pool_options = df["Pair Address"].unique()
    selected_addresses = st.multiselect(
        "Choose pools to track",
        options=pool_options,
        format_func=lambda x: df[df["Pair Address"] == x]["Pair"].iloc[0] if not df[df["Pair Address"] == x].empty else x
    )
   
    # Update history on every refresh
    for addr in selected_addresses:
        row = df[df["Pair Address"] == addr].iloc[0]
        if addr not in st.session_state.pool_history:
            st.session_state.pool_history[addr] = []
        st.session_state.pool_history[addr].append((
            datetime.now(),
            row["Price USD"],
            row["Liquidity USD"]
        ))
        if len(st.session_state.pool_history[addr]) > 30:
            st.session_state.pool_history[addr] = st.session_state.pool_history[addr][-30:]
   
    if selected_addresses:
        for addr in selected_addresses:
            hist = st.session_state.pool_history.get(addr, [])
            if len(hist) >= 2:
                times, prices, liqs = zip(*hist)
                hist_df = pd.DataFrame({"Price (USD)": prices, "Liquidity (USD)": liqs}, index=times)
                st.line_chart(hist_df, use_container_width=True)
                st.caption(f"Pool: {df[df['Pair Address']==addr]['Pair'].iloc[0]} on {df[df['Pair Address']==addr]['DEX'].iloc[0]}")

with tab4:
    st.subheader("💱 Price Impact Simulator (Constant-Product AMM)")
    if len(df) > 0:
        selected_idx = st.selectbox(
            "Select pool",
            range(len(df)),
            format_func=lambda i: f"{df.iloc[i]['DEX']} — {df.iloc[i]['Pair']} (${df.iloc[i]['Liquidity USD']:,.0f} liquidity)"
        )
        row = df.iloc[selected_idx]
       
        base_sym = row["Pair"].split("/")[0]
        quote_sym = row["Pair"].split("/")[1]
       
        direction = st.radio("Direction", [f"{base_sym} → {quote_sym}", f"{quote_sym} → {base_sym}"])
        amount_in = st.number_input("Amount to swap", value=1000.0, min_value=0.01, step=10.0)
        fee_rate = st.slider("DEX fee (%)", 0.0, 1.0, 0.3) / 100.0
       
        # Use reserves from the pool
        if direction.startswith(base_sym):
            reserve_in = row["Base Liquidity"]
            reserve_out = row["Quote Liquidity"]
            token_in = base_sym
            token_out = quote_sym
        else:
            reserve_in = row["Quote Liquidity"]
            reserve_out = row["Base Liquidity"]
            token_in = quote_sym
            token_out = base_sym
       
        if reserve_in > 0 and reserve_out > 0:
            amount_in_fee = amount_in * (1 - fee_rate)
            k = reserve_in * reserve_out
            new_reserve_in = reserve_in + amount_in_fee
            new_reserve_out = k / new_reserve_in
            amount_out = reserve_out - new_reserve_out
           
            spot_price = reserve_out / reserve_in
            execution_price = amount_out / amount_in
            price_impact_pct = (execution_price - spot_price) / spot_price * 100
           
            st.success(f"**You would receive ≈ {amount_out:,.4f} {token_out}**")
            st.metric("Price Impact", f"{price_impact_pct:.2f}%")
            st.info(f"Spot price: 1 {token_in} = {spot_price:,.4f} {token_out}\n"
                    f"Effective price after impact: 1 {token_in} = {execution_price:,.4f} {token_out}")
        else:
            st.warning("Insufficient liquidity data for simulation.")
    else:
        st.info("No pools available for simulation.")

# ====================== AUTO REFRESH ======================
st.caption(f"✅ Real-time data • Next refresh in {refresh_sec} seconds")
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
</code></pre>

    <div class="note">
        <strong>Features included:</strong>
        <ul>
            <li>Live DexScreener data for any token pair</li>
            <li>Separate interactive bar charts for every DEX (one chart per exchange as requested)</li>
            <li>Full comparison charts across exchanges</li>
            <li>Live price/liquidity history tracking (updates on every refresh)</li>
            <li>Accurate price-impact simulator using real pool reserves (constant-product formula)</li>
            <li>Auto-refresh + manual button</li>
            <li>Works on Ethereum, Base, Arbitrum, Solana, etc.</li>
        </ul>
        Push to GitHub → deploy instantly on Streamlit Cloud. No backend needed!
    </div>
   
    <p>Enjoy your live DEX liquidity dashboard! 🚀 If you need any tweaks (more chains, V3 tick math, etc.), just let me know.</p>
</body>
</html> 
