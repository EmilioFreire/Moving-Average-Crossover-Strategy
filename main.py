### PRODUCT INFORMATION --------------------------------------------------------------------------------
# Copyright InnoQuantivity.com, granted to the public domain.
# Use entirely at your own risk.
# This algorithm contains open source code from other sources and no claim is being made to such code.
# Do not remove this copyright notice.
### ----------------------------------------------------------------------------------------------------

from LongShortMovingAverageCrossoverAlphaCreation import LongShortMovingAverageCrossoverAlphaCreationModel
from CustomEqualWeightingPortfolioConstruction import CustomEqualWeightingPortfolioConstructionModel
from ImmediateExecutionWithLogs import ImmediateExecutionWithLogsModel

from System.Drawing import Color

class LongOnlyMovingAverageCrossoverFrameworkAlgorithm(QCAlgorithmFramework):
    
    '''
    Trading Logic:
        - This algorithm is a long-short market timing strategy that buys when a Short Moving Average crosses above a Long Moving Average
            and sells short when it crosses below
        - This is a simple technique commonly used to time the market, and can be combined with other strategies to reduce drawdown and improve Sharpe Ratio
    Modules:
        Universe: Manual input of tickers
        Alpha: Creation of Up/Down Insights based on Moving Average Crossover
            - Up Insights when Short Moving Average crosses above Long Moving Average (to go Long)
            - Down Insights when Long Moving Average crosses below Short Moving Average (to go Short)
        Portfolio: Equal Weighting (allocate equal amounts of portfolio % to each security)
            - If some of the tickers did not exist at the start date, it will start processing them when they first appeared in the market
            - To rebalance the portfolio periodically to ensure equal weighting, change the rebalancingParam below
        Execution: Immediate Execution with Market Orders
        Risk: Null
    '''

    def Initialize(self):
        
        ### user-defined inputs --------------------------------------------------------------
        
        # set timeframe for backtest and starting cash
        self.SetStartDate(1998, 1, 1)   # set start date
        #self.SetEndDate(2019, 1, 1)    # set end date
        self.SetCash(100000)            # set strategy cash
        
        # set data resolution (Resolution.Daily, Resolution.Hour, Resolution.Minute)
        resolution = Resolution.Daily
        
        # add tickers to the list
        tickers = ['SPY']
        
        # select the periods for the moving averages
        shortPeriodSMA = 50
        longPeriodSMA = 200
        
        # rebalancing period (to enable rebalancing enter an integer for number of days, e.g. 1, 7, 30, 365)
        rebalancingParam = False
        
        ### -----------------------------------------------------------------------------------
        
        # set the brokerage model for slippage and fees
        self.SetBrokerageModel(AlphaStreamsBrokerageModel())
        
        # set requested data resolution and disable fill forward data
        self.UniverseSettings.Resolution = resolution
        self.UniverseSettings.FillForward = False
        
        # initialize the moving average crossover plots for all tickers
        # we only plot if we have less than 5 tickers to avoid creating too many charts
        if len(tickers) < 5:
            allowPlots = True
            for ticker in tickers:
                smaPlot = Chart('Moving Average Crossover ' + str(ticker))
                smaPlot.AddSeries(Series('Short SMA', SeriesType.Line, '$', Color.Blue))
                smaPlot.AddSeries(Series('Long SMA', SeriesType.Line, '$', Color.Black))
                smaPlot.AddSeries(Series('Buy',  SeriesType.Scatter, '$', Color.Green, ScatterMarkerSymbol.Triangle))
                smaPlot.AddSeries(Series('Sell Short',  SeriesType.Scatter, '$', Color.Red, ScatterMarkerSymbol.Triangle))
                self.AddChart(smaPlot)
        else:
            allowPlots = False
        
        symbols = []
        # loop through the list and create symbols for the universe
        for i in range(len(tickers)):
            symbols.append(Symbol.Create(tickers[i], SecurityType.Equity, Market.USA))
        
        # select modules
        self.SetUniverseSelection(ManualUniverseSelectionModel(symbols))
        self.SetAlpha(LongShortMovingAverageCrossoverAlphaCreationModel(shortPeriodSMA = shortPeriodSMA,
                                                                        longPeriodSMA = longPeriodSMA,
                                                                        resolution = resolution,
                                                                        allowPlots = allowPlots))
        self.SetPortfolioConstruction(CustomEqualWeightingPortfolioConstructionModel(rebalancingParam = rebalancingParam))
        self.SetExecution(ImmediateExecutionWithLogsModel())
        self.SetRiskManagement(NullRiskManagementModel())