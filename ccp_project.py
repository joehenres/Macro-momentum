import datetime as dt
import scipy.optimize as sco
import scipy.stats as scs
import statsmodels.regression.linear_model as sm

import pandas as pd
import pandas.tseries.offsets as pdtso

import numpy as np

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
%matplotlib inline

################################
# our modules

# import sys
# sys.path.insert(0, path)

# from ccp_functions import *



#%%

#==============================================================================
# PORTFOLIO OPTIMIZATION
#==============================================================================

# optimization of the portfolio between start_date and end_date, at a frequency "freq"
# the signals used are X_macro and Y_assets (all the data available at the same frequency). Ex:
#       Y_assets = data_returns(asset_classes, first_date, last_date, freq, 1)
#       X_macro = data_lagged(macro_data, first_date, last_date, freq, 1)
# target vol is the volatility used for portfolio optimization
# periods is the number of historical returns used for portfolio optimization (ie. estimating historical vol and returns)
# returns a dataframe over the period [start_date, end_date], with the weights of the portfolio and its returns
def optimization(start_date, end_date, freq, X_macro, Y_assets, target_vol, periods):

    # dates at which we optimize the portfolio    
    optimization_dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    
    # output of the function = dataframe of the returns of the strategy
    # columns are the weights of each asset, plus the return for the corresponding period
    strategy_returns = pd.DataFrame(index=optimization_dates, columns=[Y_assets.columns.tolist() + ["Return"]], dtype=np.float64)
    
    # OUTSIDE LOOP ON THE OPTIMIZATION DATES
    for date in optimization_dates:
        # displays the date to show where we are in the optimization
        print date
        
        # date t-1, on which we do the optimization
        date_shifted = pd.DatetimeIndex(start=date, end=date, freq=freq).shift(n=-1, freq=freq)[0]
        
        # optimal weights for each macro indicator will be stored in this np.array
        optimal_weights = np.zeros((len(X_macro.columns), len(Y_assets.columns)))
        
        # INSIDE LOOP ON THE INDICATORS => we do the optimization for each indicator, store the results, and then aggregate the portfolio.
        for i, indicator in enumerate(X_macro.columns.tolist()):
        
            # signal & corresponding boundaries for the ptf optimization
            si = signal_intensity(X_macro[indicator], macro_data[indicator], date)
            sd = signal_directions(asset_classes.columns[:-1], indicator) # exclude RFR when calling this function
            bnds = signal_boundaries(si, sd)
            
            # the optimization is very sensitive to the initial weights
            init_weights = list(0.5 * si * sd) + [0.0]
            
            # optimization and storage of the optimal weights
            optimal_weights[i] = portfolio_optimize(init_weights, target_vol, bnds, Y_assets, date_shifted, freq, periods)
            
            # reduces if it's a Business Cycle indicator (Business Cycle = 0.5 * Growth + 0.5 * Inflation)
            if indicator in ["Growth","Inflation"]:
                optimal_weights[i] *= 0.5
            
            # shows the performance of the portfolio optimized with respect to the indicator
            # print(portfolio_stats(optimal_weights[i], data_slice(Y_assets, date, periods), freq))
        
        # aggregate the 4 strategies
        aggregated_weights = optimal_weights.sum(axis=0) / 4.0
        
        # in-sample volatility of the strategy    
        strategy_volatility = portfolio_stats(aggregated_weights, data_slice(Y_assets, date_shifted, periods), freq)[1]
        
        # we scale the portfolio such that the in-sample volatility is 10%
        scaled_weights = aggregated_weights[:-1] * target_vol / strategy_volatility
        scaled_weights = np.array(scaled_weights.tolist() + [1.0 - scaled_weights.sum()])
        
        # weights of the strategy
        strategy_returns.loc[date] = scaled_weights.tolist() + [(scaled_weights * Y_assets.loc[date]).sum()]
        
    # returns the dataframe of the weights + returns of the strategy
    return strategy_returns


#%%

#==============================================================================
# DIFFERENT OPTIMIZATION PERIODS (DECADE BY DECADE)
#==============================================================================

# we try the optimization decade by decade
freq = "M"
optimization_periods = [
        ("1980 01 01", "1989 12 31"),
        ("1990 01 01", "1999 12 31"), 
        ("2000 01 01", "2009 12 31"),
        ("2010 01 01", "2017 12 31")
    ]

# data treated for portfolio optimization
Y_assets = data_returns(asset_classes, first_date, last_date, freq, 1)
X_macro = data_lagged(macro_data, first_date, last_date, freq, 1)

# here we will store the results for each decade
strategy_results = {}

# optimization parameters
target_vol = 0.1 # scale the portfolio to get a volatility of 10% in sample
periods_trailing = 120 # 10Y => need for a large sample to compute robust volatility from monthly returns


for period in optimization_periods:
    start_date, end_date = period
    
    strategy_results[period_name(period)] = \
        optimization(start_date, end_date, freq,
                     X_macro, Y_assets, target_vol, periods_trailing)

#%%

def period_name(period):
    """Returns a string in the form '1980 - 1989'."""
    year_start = period[0][:4]
    year_end = period[1][:4]
    return year_start + " - " + year_end

def period_names_list(periods):
    """Returns a list using function period_name."""
    return [period_name(period) for period in periods]
    


#%%
    

# prints the portfolio composition over time
for i in range(4):
    strategy_results[i].drop(["Return"], axis=1).plot.bar(stacked=True, figsize=(12,6))
    plt.title("Portfolio composition for the period " + period_name(optimization_periods[i]))
    plt.legend()
    plt.show()



#%%

#==============================================================================
# RETURNS ANALYSIS
#==============================================================================

# Sharpe Ratio (the argument dataframe must have a RFR). Typically:
#       period_returns.columns = [["Equities", "Bonds", "RFR", "Strategy"]]
def sharpe_ratio(period_returns):
    results = pd.Series(index=period_returns.columns, dtype=np.float64)
    
    for asset in period_returns:
        results[asset] = np.sqrt(12.0) * (period_returns[asset] - period_returns["RFR"]).mean() / period_returns[asset].std()
        
    return results

def max_drawdown(returns):
    """Computes the max drawdown over an array of returns."""
    
    # computes prices from returns
    prices = (1.0 + returns).cumprod()
    
    # end of the period
    dd_end = np.argmax(np.maximum.accumulate(prices) - prices)
    
    # start of period
    dd_start = np.argmax(prices[:dd_end])
    
    # returns max_drawdown in percentage
    return (prices[dd_start] - prices[dd_end]) / prices[dd_start]


# computes the max drawdown over the period
def max_drawdown_period(period_returns):
    results = pd.Series(index=period_returns.columns, dtype=np.float64)
    
    for asset in period_returns:
        results[asset] = max_drawdown(period_returns[asset])
    
    return results

# returns a dataframe with basic statistics on the portfolio for the given period
def returns_analysis(strategy_returns, Y_assets):
    
    # returns for the period (optimization_dates)
    period_returns = Y_assets.copy()
    period_returns = period_returns.reindex(index=strategy_returns.index)
    period_returns["Strategy"] = strategy_returns.copy()
    
    # statistics for the period
    period_statistics = pd.DataFrame(index=period_returns.columns)
    
    # return, vol, correlation, sharpe ratio
    period_statistics["Returns"] = (period_returns.mean() * 12 * 100)
    period_statistics["Volatility"] = (np.sqrt(period_returns.var() * 12) * 100)
    period_statistics["Correlation"] = period_returns.corr()["Strategy"]
    period_statistics["Sharpe Ratio"] = sharpe_ratio(period_returns)
    period_statistics["Drawdown"] = max_drawdown_period(period_returns)
    # CAN ADD OTHER STATISTICS, IN THIS CASE MUST MODIFY "names_indicators" IN THE FUNCTION "strategy_analysis" BELOW
    
    return period_statistics


def strategy_analysis(periods, strategy_results, Y_assets):
    """Returns a MultiIndex DataFrame with statistics of the strategy
    for different optimization periods.
    
    periods -- list of tuples
    strategy_results -- list of DataFrames from function 'optimization'
    Y_assets -- DataFrame from function 'data_returns'
    """
    
    names_indicators = ["Returns",
                        "Volatility",
                        "Correlation",
                        "Sharpe Ratio",
                        "Drawdown"]
    
    names_periods = period_names_list(periods)
    
    names_columns = pd.MultiIndex.from_product([names_periods, names_indicators], names=['Periods', 'Indicators'])
    names_index = [Y_assets.columns.tolist() + ["Strategy"]]
    my_df = pd.DataFrame(index=names_index, columns=names_columns)
    
    
    for i, period_results in enumerate(strategy_results):
        my_df[names_periods[i]] = returns_analysis(period_results["Return"], Y_assets)
        
    return my_df
    # HOW TO USE THIS DATAFRAME
    # my_df.sort_index(axis=1).loc(axis=1)[:, 'Volatility']
    
    


#%%

# histograms for analysis
my_df = strategy_analysis(optimization_periods, strategy_results, Y_assets)

my_df.sort_index(axis=1).loc(axis=1)[:, 'Drawdown'].plot.bar(figsize=(12,6))
plt.show()
#%%

x = np.array([0.05, 0.04, -0.025, -0.014, 0.01, -0.015, 0.02, 0.03, 0.02])
max_drawdown(x)

#%%

"""

to do
- improve signal decision process (ratios, distance from mean with IQ / std...)
- improve boundaries / optimization
- improve portfolio aggregation
- improve ptf analytics
- add asset classes
- construct inflation forecasts
- interpretation of the ptf




- tester signaux actuels + ajouter des signaux (cohérence dans le temps)
- ajouter asset classes plus granulaires
- améliorer le process de signal / portfolio optimization + aggregation
- améliorer les portfolio analytics








"""











