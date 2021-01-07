from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Common")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Algorithm.Framework")

from System import *
from QuantConnect import *
from QuantConnect.Algorithm import *
from QuantConnect.Algorithm.Framework import *
from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightType, InsightDirection

import numpy as np

class LongShortMovingAverageCrossoverAlphaCreationModel(AlphaModel):
    
    '''
    * Refer to the research notebook for a visual explanation of this alpha logic
    Description:
        This Alpha model creates InsightDirection.Up to go Long when a Short Moving Average crosses above a Long Moving Average,
        and InsightDirection.Down to go Short when it crosses below
    Details:
        The important things to understand here are:
            - We can retrieve historical data by calling algorith.History(symbol, bar_count, resolution)
            - We can easily orginise the code in Python with a class to store calculations for indicators for each symbol
            - We can use InsightDirection.Up/InsightDirection.Down to go Long/Short
    '''

    def __init__(self, shortPeriodSMA = 50, longPeriodSMA = 200, resolution = Resolution.Daily, allowPlots = False):
        
        self.shortPeriodSMA = shortPeriodSMA # period for short moving average
        self.longPeriodSMA = longPeriodSMA # period for long moving average
        self.resolution = resolution # resolution for historical data
        self.allowPlots = allowPlots # boolean to allow plots or not
        
        self.securities = [] # list to store securities to consider
        self.calculations = {} # store calculations
        
        self.insightExpiry = Time.Multiply(Extensions.ToTimeSpan(resolution), 0.25) # insight duration
        
    def Update(self, algorithm, data):
        
        # get the symbols for which we have already calculate indicators to simply add last data point to update them
        # we separate this from new symbols to avoid calling full history for all securities every time
        currentSymbols = [x.Symbol for x in self.securities if x.Symbol in self.calculations.keys()]
        if len(currentSymbols) > 0:
            historyCurrentSymbols = algorithm.History(currentSymbols, 1, self.resolution)
        
        # get the new symbols for which we need to warm up indicators from scratch
        newSymbols = [x.Symbol for x in self.securities if x.Symbol not in self.calculations.keys()]
        if len(newSymbols) > 0:
            historyNewSymbols = algorithm.History(newSymbols, self.longPeriodSMA + 1, self.resolution)
        
        # now loop through securities to create/update indicators
        for security in self.securities:
            if security.Symbol in newSymbols:
                self.calculations[security.Symbol] = SymbolData(security.Symbol, self.shortPeriodSMA, self.longPeriodSMA)
                history = historyNewSymbols
            else:
                history = historyCurrentSymbols
            try:
                self.calculations[security.Symbol].UpdateIndicators(history)
            except Exception as e:
                algorithm.Log('removing from calculations due to ' + str(e))
                self.calculations.pop(security.Symbol, None)
                continue
        
        ### generate insights ------------------------------------------------------------------------------------------------------
        
        insights = [] # list to store the new insights to be created
        
        # loop through active securities and generate insights
        for symbol, symbolData in self.calculations.items():
            # check if there's new data for the security or we're already invested
            # if there's no new data but we're invested, we keep updating the insight since we don't really need to place orders
            if data.ContainsKey(symbol) or algorithm.Portfolio[symbol].Invested:
                # if short sma just crossed above long sma, we go long with an InsightDirection.Up
                if symbolData.crossAbove:
                    insightDirection = InsightDirection.Up
                    
                    if self.allowPlots:
                        algorithm.Plot('Moving Average Crossover ' + str(symbol.Value), 'Buy', float(symbolData.currentShortSMA))
                
                # if short sma just crossed below long sma, we go short with an InsightDirection.Down
                elif symbolData.crossBelow:
                    insightDirection = InsightDirection.Down
                    
                    if self.allowPlots:
                        algorithm.Plot('Moving Average Crossover ' + str(symbol.Value), 'Sell Short', float(symbolData.currentShortSMA))
                
                # if no cross happened but we are currently Long, update the InsightDirection.Up to stay Long for another bar
                elif algorithm.Portfolio[symbol].IsLong:
                    insightDirection = InsightDirection.Up
                    
                # if no cross happened but we are currently Short, update the InsightDirection.Down to stay Short for another bar
                elif algorithm.Portfolio[symbol].IsShort:
                    insightDirection = InsightDirection.Down
                    
                # if no cross has happened and we are not invested, emit an InsightDirection.Flat to stay in cash for another bar
                else:
                    insightDirection = InsightDirection.Flat
                
                # append the insights list with the prediction for each symbol
                insights.append(Insight.Price(symbol, self.insightExpiry, insightDirection))
                
                # update the charts
                if self.allowPlots and symbolData.closePrices.IsReady:
                    algorithm.Plot('Moving Average Crossover ' + str(symbol.Value), 'Short SMA', float(symbolData.currentShortSMA))
                    algorithm.Plot('Moving Average Crossover ' + str(symbol.Value), 'Long SMA', float(symbolData.currentLongSMA))
                    
            else:
                algorithm.Log('excluding this security due to missing data: ' + str(symbol.Value))
            
        return insights
        
    def OnSecuritiesChanged(self, algorithm, changes):
        
        '''
        Description:
            Event fired each time the we add/remove securities from the data feed
        Args:
            algorithm: The algorithm instance that experienced the change in securities
            changes: The security additions and removals from the algorithm
        '''
        
        # add new securities
        for added in changes.AddedSecurities:
            self.securities.append(added)

        # remove securities
        for removed in changes.RemovedSecurities:
            if removed in self.securities:
                self.securities.remove(removed)
                self.calculations.pop(removed.Symbol, None)

# this class is coming from the research nothebook (check its logic there)
class SymbolData:
    
    '''
    make all the calculations needed for each symbol including
    all the indicators and whether the ticker meets the criteria
    '''
    
    def __init__(self, symbol, shortPeriodSMA, longPeriodSMA):
        self.Symbol = symbol
        self.shortPeriod = shortPeriodSMA
        self.longPeriod = longPeriodSMA
        self.closePrices = RollingWindow[float](longPeriodSMA + 1)
    
    # method to update the rolling window
    def UpdateIndicators(self, history):
        if str(self.Symbol) in history.index:
            for index, row in history.loc[str(self.Symbol)].iterrows():
                if 'close' in row:
                    self.closePrices.Add(row['close'])
                else:
                    raise Exception('missing some close prices for: ' + str(self.Symbol.Value))
        else:
            raise Exception('symbol not in history index: ' + str(self.Symbol.Value))
    
    # convert the rolling window to list for easier manipulation
    @property
    def listClosePrices(self):
        if self.closePrices.IsReady:
            return [float(x) for x in self.closePrices]
        else:
            return [0]
    
    # update short and long current SMA
    @property
    def currentShortSMA(self):
        return np.mean(self.listClosePrices[:self.shortPeriod])
    @property
    def currentLongSMA(self):
        return np.mean(self.listClosePrices[:self.longPeriod])
    
    # update short and long before SMA (the SMA from the previous trading bar)
    @property
    def beforeShortSMA(self):
        return np.mean(self.listClosePrices[1:][:self.shortPeriod])
    @property
    def beforeLongSMA(self):
        return np.mean(self.listClosePrices[1:][:self.longPeriod])
    
    # update boolean for cross above/below of moving averages
    @property
    def crossAbove(self):
        return (self.currentShortSMA > self.currentLongSMA) and (self.beforeShortSMA < self.beforeLongSMA)
    @property
    def crossBelow(self):
        return (self.currentShortSMA < self.currentLongSMA) and (self.beforeShortSMA > self.beforeLongSMA)