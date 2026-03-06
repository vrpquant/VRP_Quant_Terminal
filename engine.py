import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import time
import json
from datetime import datetime
import subprocess
import os

# ==========================================
# --- INSTITUTIONAL MATH & PRICING ENGINES ---
# ==========================================
class AlphaEngine:
    @staticmethod
    def apply_kalman_filter(prices, noise_estimate=1.0, measure_noise=1.0):
        n = len(prices)
        kalman_gains = np.zeros(n)
        estimates = np.zeros(n)
        current_estimate = prices.iloc[0]
        err_estimate = noise_estimate
        
        for i in range(n):
            kalman_gains[i] = err_estimate / (err_estimate + measure_noise)
            current_estimate = current_estimate + kalman_gains[i] * (prices.iloc[i] - current_estimate)
            err_estimate = (1 - kalman_gains[i]) * err_estimate
            estimates[i] = current_estimate
        return pd.Series(estimates, index=prices.index)

    @staticmethod
    def calculate_score(df):
        try:
            calc_df = df.copy().dropna()
            if len(calc_df) < 50: return 50
            calc_df['Kalman_Price'] = AlphaEngine.apply_kalman_filter(calc_df['Close'])
            returns = calc_df['Close'].pct_change()
            calc_df['GARCH_Proxy_Vol'] = returns.ewm(span=20).std() * np.sqrt(252) 
            calc_df['Band_Std'] = calc_df['GARCH_Proxy_Vol'] * calc_df['Kalman_Price'] / np.sqrt(252)
            calc_df['Upper_Band'] = calc_df['Kalman_Price'] + (2 * calc_df['Band_Std'])
            calc_df['Lower_Band'] = calc_df['Kalman_Price'] - (2 * calc_df['Band_Std'])
            calc_df['BBW'] = (calc_df['Upper_Band'] - calc_df['Lower_Band']) / calc_df['Kalman_Price']
            
            current_price = calc_df['Close'].iloc[-1]
            lower_band = calc_df['Lower_Band'].iloc[-1]
            upper_band = calc_df['Upper_Band'].iloc[-1]
            kalman_trend = calc_df['Kalman_Price'].iloc[-1] > calc_df['Kalman_Price'].iloc[-2]
            
            score = 50 
            if current_price < lower_band and kalman_trend: score += 35 
            elif current_price > upper_band: score -= 35
                
            bbw_z = (calc_df['BBW'].iloc[-1] - calc_df['BBW'].mean()) / (calc_df['BBW'].std() + 1e-9)
            score += max(-15, min(15, bbw_z * 10))
            return max(0, min(100, int(score)))
        except:
            return 50

class QuantLogic:
    @staticmethod
    def calculate_vol(df):
        return df['Close'].pct_change().std() * np.sqrt(252) * 100

    @staticmethod
    def get_atm_iv(ticker, current_price):
        try:
            stock = yf.Ticker(ticker)
            if stock.options:
                chain = stock.option_chain(stock.options[0])
                calls = chain.calls
                atm_idx = (calls['strike'] - current_price).abs().idxmin()
                return round(calls.loc[atm_idx, 'impliedVolatility'] * 100, 2)
            return None
        except: return None

    @staticmethod
    def calculate_vrp_edge(ticker, df):
        price = df['Close'].iloc[-1]
        hv = QuantLogic.calculate_vol(df)
        iv = QuantLogic.get_atm_iv(ticker, price)
        return round(iv - hv, 2) if iv else 0.0

    @staticmethod
    def calculate_sharpe(df, risk_free_rate=0.04):
        returns = df['Close'].pct_change().dropna()
        excess = returns.mean() * 252 - risk_free_rate
        vol = returns.std() * np.sqrt(252)
        return round(excess / vol, 2) if vol > 0 else 0.0

    @staticmethod
    def get_support_resistance(df):
        res = df['High'].rolling(50).max().iloc[-1]
        sup = df['Low'].rolling(50).min().iloc[-1]
        return sup, res

    @staticmethod
    def binomial_tree_american(S, K, T, r, sigma, option_type='call', N=50):
        if T <= 0 or sigma <= 0: return max(0, S - K) if option_type == 'call' else max(0, K - S)
        dt = T / N
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp(r * dt) - d) / (u - d)
        ST = np.array([S * (u ** j) * (d ** (N - j)) for j in range(N + 1)])
        C = np.maximum(0, ST - K) if option_type == 'call' else np.maximum(0, K - ST)
        for i in range(N - 1, -1, -1):
            ST = ST[:-1] / u
            C = np.exp(-r * dt) * (p * C[1:] + (1 - p) * C[:-1])
            C = np.maximum(C, ST - K) if option_type == 'call' else np.maximum(C, K - ST)
        return C[0]

class BacktestEngine:
    @staticmethod
    def run_quick_backtest(df, slippage_bps=5, commission_bps=2):
        try:
            bt_df = df.copy().dropna()
            bt_df['Kalman_Price'] = AlphaEngine.apply_kalman_filter(bt_df['Close'])
            returns = bt_df['Close'].pct_change()
            bt_df['Vol_Regime'] = returns.ewm(span=20).std() * np.sqrt(252)
            bt_df['Band_Std'] = bt_df['Vol_Regime'] * bt_df['Kalman_Price'] / np.sqrt(252)
            bt_df['Upper_Band'] = bt_df['Kalman_Price'] + (2 * bt_df['Band_Std'])
            bt_df['Lower_Band'] = bt_df['Kalman_Price'] - (2 * bt_df['Band_Std'])

            bt_df['Signal'] = 0
            bt_df.loc[bt_df['Close'] < bt_df['Lower_Band'], 'Signal'] = 1
            bt_df.loc[bt_df['Close'] > bt_df['Upper_Band'], 'Signal'] = -1
            
            bt_df['Target_Position'] = bt_df['Signal'].replace(0, np.nan).ffill().fillna(0)
            bt_df['Actual_Position'] = bt_df['Target_Position'].shift(1).fillna(0)
            bt_df['Net_Return'] = (bt_df['Actual_Position'] * returns.fillna(0)) - (bt_df['Actual_Position'].diff().abs().fillna(0) * ((slippage_bps + commission_bps) / 10000))
            
            win_rate = (bt_df['Net_Return'] > 0).mean() * 100
            cumulative = (1 + bt_df['Net_Return']).prod() - 1
            outperf = cumulative - ((1 + returns.fillna(0)).prod() - 1)
            peak = (1 + bt_df['Net_Return']).cumprod().cummax()
            max_dd = (((1 + bt_df['Net_Return']).cumprod() - peak) / peak).min() * 100
            
            wins, losses = bt_df[bt_df['Net_Return'] > 0]['Net_Return'], bt_df[bt_df['Net_Return'] < 0]['Net_Return']
            half_kelly = 0.0
            if len(wins) > 0 and len(losses) > 0:
                win_avg, loss_avg = wins.mean(), abs(losses.mean())
                if loss_avg > 0:
                    half_kelly = max(0.0, ((len(wins) / len(bt_df)) - ((1 - (len(wins) / len(bt_df))) / (win_avg / loss_avg))) / 2.0) * 100 
            return round(win_rate,1), round(cumulative*100,1), round(outperf*100,1), round(max_dd,1), round(half_kelly,1)
        except: return 0.0, 0.0, 0.0, 0.0, 0.0

class TradeArchitect:
    @staticmethod
    def generate_plan(price, score, vol, sup, res, half_kelly):
        plan = {}
        bias = "LONG (Bullish Trend)" if score >= 60 else "SHORT (Bearish Trend)" if score <= 40 else "NEUTRAL (Mean-Reverting)"
        sigma, r, T30 = max(0.01, vol / 100), 0.04, 30 / 365
        res, sup = max(res, price * 1.05), min(sup, price * 0.95)
        
        if "LONG" in bias:
            plan['name'], plan['legs'] = "Short Put Vertical", f"-P({sup:.0f}) / +P({sup*0.95:.0f})"
            credit = QuantLogic.binomial_tree_american(price, sup, T30, r, sigma, 'put') - QuantLogic.binomial_tree_american(price, sup*0.95, T30, r, sigma, 'put')
            plan['premium'], plan['pop'] = f"Credit ${max(0.01, credit):.2f}", 70
        elif "SHORT" in bias:
            plan['name'], plan['legs'] = "Short Call Vertical", f"-C({res:.0f}) / +C({res*1.05:.0f})"
            credit = QuantLogic.binomial_tree_american(price, res, T30, r, sigma, 'call') - QuantLogic.binomial_tree_american(price, res*1.05, T30, r, sigma, 'call')
            plan['premium'], plan['pop'] = f"Credit ${max(0.01, credit):.2f}", 70
        else:
            plan['name'], plan['legs'] = "Iron Condor", f"+P({sup*0.95:.0f})/-P({sup:.0f}) | -C({res:.0f})/+C({res*1.05:.0f})"
            plan['premium'], plan['pop'] = "Credit Calculated", 65
            
        plan['bias'] = bias
        return plan

class MonteCarloEngine:
    @staticmethod
    def simulate_paths(df, days=30, sims=1000):
        try:
            price = df['Close'].iloc[-1]
            returns = np.log(df['Close']/df['Close'].shift(1)).dropna()
            sigma, mu, dt = np.sqrt(np.average(returns**2, weights=np.power(0.94, np.arange(len(returns)-1,-1,-1))) * 252), returns.mean() * 252, 1/252
            paths = np.zeros((days+1, sims))
            paths[0] = price
            for t in range(1, days+1):
                paths[t] = paths[t-1] * np.exp((mu - 0.5*sigma**2)*dt + sigma*np.sqrt(dt)*np.random.normal(0,1,sims))
            return paths.mean(axis=1).tolist(), np.percentile(paths[-1], 5)
        except: return [df['Close'].iloc[-1]] * (days+1), df['Close'].iloc[-1] * 0.95

# ==========================================
# --- DECOUPLED DAEMON LOOP (THE CRR VAULT) ---
# ==========================================
TICKER_SETS = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "PLTR", "SOFI"]
STATE_FILE = "market_state.json"

def run_background_engine():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting HQTA Backend. Throttling yfinance calls...")
    
    while True:
        results = []
        for ticker in TICKER_SETS:
            try:
                print(f"Processing {ticker}...")
                df = yf.Ticker(ticker).history(period="2y")
                if len(df) > 50:
                    price = float(df['Close'].iloc[-1])
                    score = AlphaEngine.calculate_score(df)
                    vol = QuantLogic.calculate_vol(df)
                    vrp = QuantLogic.calculate_vrp_edge(ticker, df)
                    sup, res = QuantLogic.get_support_resistance(df)
                    sharpe = QuantLogic.calculate_sharpe(df)
                    win_rate, strat_ret, outperf, max_dd, kelly = BacktestEngine.run_quick_backtest(df)
                    plan = TradeArchitect.generate_plan(price, score, vol, sup, res, kelly)
                    mc_proj, var_95 = MonteCarloEngine.simulate_paths(df)
                    
                    results.append({
                        "Ticker": ticker, "Price": round(price, 2), "Alpha Score": score, "Trend": plan['bias'],
                        "VRP Edge": f"{vrp:+.1f}%", "Vol": f"{vol:.1f}%", "Kelly": f"{kelly}%",
                        "Strategy": plan['name'], "Legs": plan['legs'], "Premium": plan['premium'], "POP": plan['pop'],
                        "Support": round(sup, 2), "Resistance": round(res, 2), "Sharpe": sharpe, "VaR": round(var_95, 2),
                        "Win Rate": f"{win_rate}%", "Strat Ret": f"{strat_ret}%", "Outperf": f"{outperf}%", "Max DD": f"{max_dd}%",
                        "Chart_Dates": [d.strftime('%Y-%m-%d') for d in df.index[-100:]],
                        "Chart_Prices": df['Close'].iloc[-100:].tolist(),
                        "MC_Projection": mc_proj[1:]
                    })
                time.sleep(2.0) # Throttling to prevent IP bans
            except Exception as e:
                print(f"Error on {ticker}: {e}")
                time.sleep(5.0)
        
        # 1. Save locally
        with open(STATE_FILE, "w") as f:
            json.dump({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S EST'), "data": results}, f, indent=4)
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Saved. Pushing to GitHub CRR Vault...")
        
        # 2. Push to GitHub automatically
        try:
            subprocess.run(["git", "add", STATE_FILE], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Auto-sync CRR Vault: {datetime.now().strftime('%H:%M:%S')}"], check=True, capture_output=True)
            subprocess.run(["git", "push"], check=True, capture_output=True)
            print("🚀 Successfully uploaded to Live Terminal Vault!")
        except Exception as e:
            print("⚠️ GitHub Push Failed. (Is Git initialized and authenticated?)")

        print("⏳ Sleeping for 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    run_background_engine()