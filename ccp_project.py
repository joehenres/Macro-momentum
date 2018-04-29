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
def optimization(print_date, start_date, end_date, freq,
        X_macro, Y_assets, target_vol, periods, granularity, method, thresholds,
        reduce_indic, reduce_coeff, dynamic_weighting=False, rescale_vol=True, nb_indic=4):
    
    # dates at which we optimize the portfolio    
    optimization_dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    
    # output of the function = dataframe of the returns of the strategy
    # columns are the weights of each asset, plus the return for the corresponding period
    strategy_returns = pd.DataFrame(index=optimization_dates, columns=[Y_assets.columns.tolist() + ["Return"]], dtype=np.float64)
    
    # OUTSIDE LOOP ON THE OPTIMIZATION DATES
    for date in optimization_dates:
        # displays the date to show where we are in the optimization
        if print_date == True:
            print date
        
        # date t-1, on which we do the optimization
        date_shifted = pd.DatetimeIndex(start=date, end=date, freq=freq).shift(n=-1, freq=freq)[0]
        
        # optimal weights for each macro indicator will be stored in this np.array
        optimal_weights = np.zeros((len(X_macro.columns), len(Y_assets.columns)))
        
        # rolling target vol
        if target_vol == 'rolling':
            vol_constraint = data_slice(Y_assets, date_shifted, periods).std().mean() * np.sqrt(annualization_factor(freq))
        else:
            vol_constraint = target_vol
        
        
        if method != 'quantile':
            granularity = 2
        else:
            assert granularity >=1, 'Invalid granularity (%i)' % granularity
        
            
        # INSIDE LOOP ON THE INDICATORS => we do the optimization for each indicator, store the results, and then aggregate the portfolio.
        for i, indicator in enumerate(X_macro.columns.tolist()):
        
            # signal & corresponding boundaries for the ptf optimization
            si = signal_intensity(X_macro[indicator], macro_data[indicator], date, method, granularity, thresholds)
            sd = signal_directions(asset_classes.columns[:-1], indicator) # exclude RFR when calling this function
            bnds = signal_boundaries(si, sd, granularity)
            
            # the optimization is very sensitive to the initial weights
            init_weights = list(0.5 * si * sd) + [0.0]
            
            # optimization and storage of the optimal weights
            optimal_weights[i] = portfolio_optimize(init_weights, vol_constraint, bnds, Y_assets, date_shifted, freq, periods)
            
            # reduces if it's a Business Cycle indicator (Business Cycle = 0.5 * Growth + 0.5 * Inflation)
            if reduce_indic != False:
                assert type(reduce_indic) == list, 'indicators to reduce are not in the form of a list'
                if indicator in reduce_indic:
                    optimal_weights[i] *= reduce_coeff
            
            # shows the performance of the portfolio optimized with respect to the indicator
            # print(portfolio_stats(optimal_weights[i], data_slice(Y_assets, date, periods), freq))
        
        # aggregate the 4 strategies
        if dynamic_weighting == False:
            scaled_weights = optimal_weights.sum(axis=0) / np.float64(nb_indic) # normal weighting
        else:
            pass # TO IMPLEMENT
        
        if rescale_vol == True:
            # in-sample volatility of the strategy    
            strategy_volatility = portfolio_stats(scaled_weights, data_slice(Y_assets, date_shifted, periods), freq)[1]
            
            # we scale the portfolio such that the in-sample volatility is equal to target
            scaled_weights = scaled_weights[:-1] * vol_constraint / strategy_volatility
            scaled_weights = np.array(scaled_weights.tolist() + [1.0 - scaled_weights.sum()])
        
        # weights of the strategy
        strategy_returns.loc[date] = scaled_weights.tolist() + [(scaled_weights * Y_assets.loc[date]).sum()]
        
    # returns the dataframe of the weights + returns of the strategy
    return strategy_returns



def period_name(period):
    """Returns a string in the form '1980 - 1989'."""
    year_start = period[0][:4]
    year_end = period[1][:4]
    return year_start + " - " + year_end

def period_names_list(periods):
    """Returns a list using function period_name."""
    return [period_name(period) for period in periods]

#%%

#==============================================================================
# PARAMETRIZATION OF THE OPTIMIZATION
#==============================================================================

# we try the optimization decade by decade
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
strategy_results = []

# optimization parameters
target_vol = [0.1, 0.09, 0.08, 0.07] # scale the portfolio to get a volatility of 10% in sample


params = {
    'print_date': True,
    'start_date': start_date,
    'end_date': end_date,
    'freq': "M",
    'X_macro': X_macro,
    'Y_assets': Y_assets,
    'target_vol': 'rolling', # target_vol[i]
    'periods': 120, # 10Y => need for a large sample to compute robust volatility from monthly returns
    'granularity': 2,
    'method': "quantile", #zscore_robust
    'thresholds': [-1.2, 1.2],
    'reduce_indic': ["Growth","Inflation"],
    'reduce_coeff': 0.5,
    'dynamic_weighting': False,
    'rescale_vol': False,
    'nb_indic': 4
    }

#%%

#==============================================================================
# OPTIMIZATION
#==============================================================================

#params['X_macro'] = X_macro[['Monetary Policy', 'Risk Sentiment', 'Inflation']]
#params['reduce_indic'] = False

for i, period in enumerate(optimization_periods):
    params['start_date'], params['end_date'] = period
    
    # to change parameters for different optimization periods:
    # params['target_vol'] = target_vol[i]
    
    strategy_results.append(optimization(**params))

   
#%%

def histogram_analysis(optimization_periods, strategy_results, Y_assets, indicator='Sharpe Ratio'):

    # histograms for analysis
    my_df = strategy_analysis(optimization_periods, strategy_results, Y_assets)
    
    my_df.sort_index(axis=1).loc(axis=1)[:, 'Sharpe Ratio'].plot.bar(figsize=(12,6))
    plt.show()

histogram_analysis(optimization_periods, strategy_results, Y_assets, indicator='Sharpe Ratio')

#%%

# testing each indicator performance separately

mydict = {}
params['print_date'] = False
params['reduce_indic'] = False
params['nb_indic'] = 1

params['granularity'] = 4

for i, indicator in enumerate(X_macro.columns.tolist()):
    print(indicator)
    strategy_results = []
    
    params['X_macro'] = pd.DataFrame(X_macro[indicator])
    
    for j, period in enumerate(optimization_periods):
        params['start_date'], params['end_date'] = period
        
        strategy_results.append(optimization(**params))
    

    mydict[indicator] = strategy_results

    histogram_analysis(optimization_periods, strategy_results, Y_assets, indicator='Sharpe Ratio')


#%%
    

# prints the portfolio composition over time
for i in range(4):
    period = period_name(optimization_periods[i])
    strategy_results[i].drop(["Return"], axis=1).plot.bar(stacked=True, figsize=(12,6))
    plt.title("Portfolio composition for the period " + period)
    plt.legend()
    plt.show()  
    



#%%

# compare to a static rebalancing
naive_strategy = strategy_results

for i, period in enumerate(optimization_periods):
    start_date, end_date = period
    
    item = naive_strategy[i]
    
    weight_eq = 0.4
    weight_fi = 1 - weight_eq
    
    item.Equities = weight_eq
    item.Bonds = weight_fi
    item.RFR = 0.0
    item.Return = Y_assets.Equities * weight_eq + Y_assets.Bonds * weight_fi


naive_strategy_df = strategy_analysis(optimization_periods, naive_strategy, Y_assets)

print(naive_strategy_df.sort_index(axis=1).loc(axis=1)[:, 'Sharpe Ratio'].loc["Strategy"])
print(my_df.sort_index(axis=1).loc(axis=1)[:, 'Sharpe Ratio'].loc["Strategy"])

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











