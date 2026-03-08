import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import pytz
import json
import time
import os
import subprocess

# ==========================================
# --- GLOBAL INSTITUTIONAL UNIVERSE ---
# ==========================================
TICKERS = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "PLTR", "ORCL", "BTC-USD",]

# ==========================================
# --- ADVANCED INSTITUTIONAL MATH ENGINE ---
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

class BacktestEngine:
    @staticmethod
    def run_quick_backtest(df, slippage_bps=5, commission_bps=2):
        try:
            bt_df = df.copy().dropna()
            if len(bt_df) < 50:
                return 0.0, 0.0, 0.0, 0.0, 0.0
                
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
            bt_df['Underlying_Return'] = returns.fillna(0)
            bt_df['Gross_Return'] = bt_df['Actual_Position'] * bt_df['Underlying_Return']
            
            turnover = bt_df['Actual_Position'].diff().abs().fillna(0)
            total_cost = (slippage_bps + commission_bps) / 10000
            
            bt_df['Net_Return'] = bt_df['Gross_Return'] - (turnover * total_cost * (1 + (bt_df['Vol_Regime'] > 0.35).astype(int)))
            
            win_rate = (bt_df['Net_Return'] > 0).mean() * 100
            cumulative = (1 + bt_df['Net_Return']).prod() - 1
            buy_hold = (1 + bt_df['Underlying_Return']).prod() - 1
            outperf = cumulative - buy_hold
            
            peak = (1 + bt_df['Net_Return']).cumprod().cummax()
            max_dd = (((1 + bt_df['Net_Return']).cumprod() - peak) / peak).min() * 100
            
            wins = bt_df[bt_df['Net_Return'] > 0]['Net_Return']
            losses = bt_df[bt_df['Net_Return'] < 0]['Net_Return']
            
            half_kelly = 0.0
            if len(wins) > 0 and len(losses) > 0:
                win_avg = wins.mean()
                loss_avg = abs(losses.mean())
                win_prob = len(wins) / (len(wins) + len(losses))
                
                if loss_avg > 0:
                    kelly_fraction = win_prob - ((1 - win_prob) / (win_avg / loss_avg))
                    half_kelly = max(0.0, kelly_fraction / 2.0) * 100 
                    
            return round(win_rate,1), round(cumulative*100,1), round(outperf*100,1), round(max_dd,1), round(half_kelly,1)
        except:
            return 0.0, 0.0, 0.0, 0.0, 0.0

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
        except:
            return None

    @staticmethod
    def calculate_vrp_edge(ticker, df):
        # Calculate Historical Volatility
        hv20 = df['Close'].pct_change().tail(20).std() * np.sqrt(252) * 100
        hv60 = df['Close'].pct_change().tail(60).std() * np.sqrt(252) * 100
        hv = df['Close'].pct_change().std() * np.sqrt(252) * 100
        
        # Try to get True Implied Vol (IV)
        price = df['Close'].iloc[-1]
        iv = QuantLogic.get_atm_iv(ticker, price)
        
        # FIX: If market is closed/weekend and IV fails, fallback to HV20 - HV60
        if iv is None or iv == 0:
            return round(hv20 - hv60, 2)
        return round(iv - hv, 2)

    @staticmethod
    def detect_reversal(df):
        try:
            if len(df) < 201: return "Insufficient Data"
            sma50 = df['Close'].rolling(50).mean()
            sma200 = df['Close'].rolling(200).mean()
            if sma50.iloc[-2] < sma200.iloc[-2] and sma50.iloc[-1] >= sma200.iloc[-1]: return "Golden Cross (Bull)"
            elif sma50.iloc[-2] > sma200.iloc[-2] and sma50.iloc[-1] <= sma200.iloc[-1]: return "Death Cross (Bear)"
            return "No Active Reversal"
        except:
            return "No Active Reversal"

    @staticmethod
    def calculate_sharpe(df, risk_free_rate=0.04):
        returns = df['Close'].pct_change().dropna()
        excess = returns.mean() * 252 - risk_free_rate
        vol = returns.std() * np.sqrt(252)
        return round(excess / vol, 2) if vol > 0 else 0

    @staticmethod
    def get_support_resistance(df):
        res = df['High'].rolling(50).max().iloc[-1]
        sup = df['Low'].rolling(50).min().iloc[-1]
        return sup, res
        
    @staticmethod
    def calculate_var(df, confidence=0.95):
        try:
            price = df['Close'].iloc[-1]
            daily_returns = df['Close'].pct_change().dropna()
            var_pct = np.percentile(daily_returns, (1 - confidence) * 100)
            return round(price * (1 + var_pct), 2)
        except:
            return df['Close'].iloc[-1] * 0.95

    # 🚀 THE 50-STEP AMERICAN BINOMIAL TREE PRICER
    @staticmethod
    def american_binomial_pricer(S, K, T, r, sigma, option_type='call', steps=50):
        if T <= 0 or sigma <= 0:
            return max(0, S - K) if option_type == 'call' else max(0, K - S)
        
        dt = T / steps
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp(r * dt) - d) / (u - d)
        
        # Initialize asset prices at maturity
        asset_prices = np.zeros(steps + 1)
        for i in range(steps + 1):
            asset_prices[i] = S * (u ** (steps - i)) * (d ** i)
            
        # Initialize option values at maturity
        option_values = np.zeros(steps + 1)
        for i in range(steps + 1):
            if option_type == 'call': option_values[i] = max(0, asset_prices[i] - K)
            else: option_values[i] = max(0, K - asset_prices[i])
                
        # Step back through the tree
        for j in range(steps - 1, -1, -1):
            for i in range(j + 1):
                asset_prices[i] = asset_prices[i] / u 
                c_val = np.exp(-r * dt) * (p * option_values[i] + (1 - p) * option_values[i + 1])
                
                if option_type == 'call': i_val = max(0, asset_prices[i] - K)
                else: i_val = max(0, K - asset_prices[i])
                
                # American Options can be exercised early
                option_values[i] = max(i_val, c_val)
                
        return option_values[0]

class TradeArchitect:
    @staticmethod
    def prob_itm(S, K, T, r, sigma, option_type='call'):
        if T <= 0 or sigma <= 0: return 0.0
        d2 = (np.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        return norm.cdf(d2) if option_type == 'call' else norm.cdf(-d2)

    @staticmethod
    def generate_plan(ticker, price, score, vol, sup, res, half_kelly):
        plan = {}
        bias = "LONG (Bullish Trend)" if score >= 60 else "SHORT (Bearish Trend)" if score <= 40 else "NEUTRAL (Mean-Reverting)"
        vol_regime = "HIGH" if vol > 35 else "LOW"
        sigma = max(0.01, vol / 100)
        r = 0.04
        T30 = 30 / 365
        
        if res <= price: res = price * 1.05
        if sup >= price: sup = price * 0.95
        lower_wing = sup * 0.95
        upper_wing = res * 1.05
        
        if "LONG" in bias:
            if vol_regime == "LOW":
                plan['name'] = "Long Call Vertical"
                plan['legs'] = f"+C({price:.0f}) / -C({res:.0f})"
                debit = QuantLogic.american_binomial_pricer(price, price, T30, r, sigma, 'call') - QuantLogic.american_binomial_pricer(price, res, T30, r, sigma, 'call')
                plan['premium'] = f"Debit ${max(0.01, debit):.2f}"
                plan['pop'] = int(TradeArchitect.prob_itm(price, price + debit, T30, r, sigma, 'call') * 100)
            else:
                plan['name'] = "Short Put Vertical"
                plan['legs'] = f"-P({sup:.0f}) / +P({lower_wing:.0f})"
                credit = QuantLogic.american_binomial_pricer(price, sup, T30, r, sigma, 'put') - QuantLogic.american_binomial_pricer(price, lower_wing, T30, r, sigma, 'put')
                plan['premium'] = f"Credit ${max(0.01, credit):.2f}"
                plan['pop'] = int((1 - TradeArchitect.prob_itm(price, sup, T30, r, sigma, 'put')) * 100)
        elif "SHORT" in bias:
            if vol_regime == "LOW":
                plan['name'] = "Long Put Vertical"
                plan['legs'] = f"+P({price:.0f}) / -P({sup:.0f})"
                debit = QuantLogic.american_binomial_pricer(price, price, T30, r, sigma, 'put') - QuantLogic.american_binomial_pricer(price, sup, T30, r, sigma, 'put')
                plan['premium'] = f"Debit ${max(0.01, debit):.2f}"
                plan['pop'] = int(TradeArchitect.prob_itm(price, price - debit, T30, r, sigma, 'put') * 100)
            else:
                plan['name'] = "Short Call Vertical"
                plan['legs'] = f"-C({res:.0f}) / +C({upper_wing:.0f})"
                credit = QuantLogic.american_binomial_pricer(price, res, T30, r, sigma, 'call') - QuantLogic.american_binomial_pricer(price, upper_wing, T30, r, sigma, 'call')
                plan['premium'] = f"Credit ${max(0.01, credit):.2f}"
                plan['pop'] = int((1 - TradeArchitect.prob_itm(price, res, T30, r, sigma, 'call')) * 100)
        else:
            plan['name'] = "Iron Condor"
            plan['legs'] = f"+P({lower_wing:.0f}) / -P({sup:.0f}) | -C({res:.0f}) / +C({upper_wing:.0f})"
            put_credit = QuantLogic.american_binomial_pricer(price, sup, T30, r, sigma, 'put') - QuantLogic.american_binomial_pricer(price, lower_wing, T30, r, sigma, 'put')
            call_credit = QuantLogic.american_binomial_pricer(price, res, T30, r, sigma, 'call') - QuantLogic.american_binomial_pricer(price, upper_wing, T30, r, sigma, 'call')
            plan['premium'] = f"Credit ${max(0.01, put_credit + call_credit):.2f}"
            plan['pop'] = 65
            
        plan['kelly_size'] = f"{int(max(0, min(50, half_kelly)))}%"
        plan['dte'] = "30 Days"
        plan['bias'] = bias
        return plan

class MonteCarloEngine:
    @staticmethod
    def generate_mean_projection(df, days=30, sims=10000):
        try:
            price = df['Close'].iloc[-1]
            returns = np.log(df['Close']/df['Close'].shift(1)).dropna()
            lambda_ = 0.94
            ewma_var = np.average(returns**2, weights=np.power(lambda_, np.arange(len(returns)-1,-1,-1)))
            sigma = np.sqrt(ewma_var * 252)
            mu = returns.mean() * 252
            dt = 1/252
            
            z = np.random.normal(0,1,(days,sims))
            jumps = np.random.poisson(0.8*dt,(days,sims)) * np.random.normal(-0.015, 0.08, (days,sims))
            
            paths = np.zeros((days+1, sims))
            paths[0] = price
            for t in range(1, days+1):
                paths[t] = paths[t-1] * np.exp((mu - 0.5*sigma**2)*dt + sigma*np.sqrt(dt)*z[t-1] + jumps[t-1])
            
            # For the lightweight cloud, we only need to export the MEAN path of all 10,000 simulations
            mean_path = paths.mean(axis=1)
            return mean_path.tolist()
        except:
            return [df['Close'].iloc[-1]] * (days + 1)

# ==========================================
# --- MAIN EXECUTION & JSON COMPILATION ---
# ==========================================
def compile_market_state():
    est_tz = pytz.timezone('US/Eastern')
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting V22.2 GOD MODE Backend. 10k MC Paths Active...")
    
    results = []
    for ticker in TICKERS:
        print(f"Deep Processing {ticker} (Binomial + 10k Monte Carlo)...")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="2y")
            
            if len(df) > 50:
                price = df['Close'].iloc[-1]
                score = AlphaEngine.calculate_score(df)
                vol = QuantLogic.calculate_vol(df)
                vrp = QuantLogic.calculate_vrp_edge(ticker, df)
                reversal = QuantLogic.detect_reversal(df)
                sup, res = QuantLogic.get_support_resistance(df)
                sharpe = QuantLogic.calculate_sharpe(df)
                var_95 = QuantLogic.calculate_var(df)
                win_rate, strat_ret, outperf, max_dd, kelly = BacktestEngine.run_quick_backtest(df)
                
                # 50-Step Binomial Trade Architecture
                plan = TradeArchitect.generate_plan(ticker, price, score, vol, sup, res, kelly)
                
                # 10,000 Path Monte Carlo Mean Projection
                mc_mean_path = MonteCarloEngine.generate_mean_projection(df, days=30, sims=10000)
                
                # Charting Dates & Prices for Frontend Payload
                hist_dates = df.index[-100:].strftime('%Y-%m-%d').tolist()
                hist_prices = df['Close'].tail(100).tolist()
                
                # HQTA Directive Formatting
                action = "Buy 100 Shares" if score >= 60 else "Do NOT Buy Stock" if score <= 40 else "Place Limit Buy Order"

                results.append({
                    "Ticker": ticker, 
                    "Price": round(price, 2), 
                    "Alpha Score": score, 
                    "Trend": plan['bias'],
                    "Reversal": reversal, 
                    "VRP Edge": f"{vrp:+.1f}%", 
                    "Vol": f"{vol:.1f}%", 
                    "Support": round(sup, 2), 
                    "Resistance": round(res, 2), 
                    "HQTA Apex Action": action,
                    "Strategy": plan['name'], 
                    "Kelly": f"{kelly}%",
                    "Sharpe": round(sharpe, 2),
                    "VaR": round(var_95, 2),
                    "Win Rate": f"{win_rate}%",
                    "Strat Ret": f"{strat_ret:+.1f}%",
                    "Outperf": f"{outperf:+.1f}%",
                    "Max DD": f"{max_dd}%",
                    "Premium": plan['premium'],
                    "POP": plan['pop'],
                    "Legs": plan['legs'],
                    "Chart_Dates": hist_dates,
                    "Chart_Prices": hist_prices,
                    "MC_Projection": mc_mean_path
                })
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    # Create Final Vault Payload
    vault_data = {
        "last_updated": datetime.now(est_tz).strftime("%Y-%m-%d %H:%M:%S EST"),
        "macro": {"vix": "14.5", "tnx": "4.2"}, # Placeholder for macro data
        "data": sorted(results, key=lambda x: x['Alpha Score'], reverse=True)
    }

    # Save locally to E: Drive
    with open("market_state.json", "w") as f:
        json.dump(vault_data, f, indent=4)
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Saved. Pushing to GitHub CRR Vault...")

    # Attempt Auto-Push to GitHub
    try:
        subprocess.run(["git", "add", "market_state.json"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Auto-update Binomial Vault"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("✅ Successfully pushed to GitHub!")
    except Exception as e:
        print("⚠️ GitHub Push Failed. (Awaiting Manual Upload)")
        print("You can manually drag market_state.json into your GitHub repo.")

if __name__ == "__main__":
    compile_market_state()
