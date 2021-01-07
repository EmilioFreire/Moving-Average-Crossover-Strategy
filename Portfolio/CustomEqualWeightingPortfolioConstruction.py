from clr import AddReference
AddReference("QuantConnect.Common")
AddReference("QuantConnect.Algorithm.Framework")

from QuantConnect import Resolution, Extensions
from QuantConnect.Algorithm.Framework.Alphas import *
from QuantConnect.Algorithm.Framework.Portfolio import *
from itertools import groupby
from datetime import datetime, timedelta
from pytz import utc
UTCMIN = datetime.min.replace(tzinfo=utc)

class CustomEqualWeightingPortfolioConstructionModel(PortfolioConstructionModel):
    
    '''
    Description:
        Provide a custom implementation of IPortfolioConstructionModel that gives equal weighting to all active securities
    Details:
        - The target percent holdings of each security is 1/N where N is the number of securities with active Up/Down insights
        - For InsightDirection.Up, long targets are returned
        - For InsightDirection.Down, short targets are returned
        - For InsightDirection.Flat, closing position targets are returned
    '''

    def __init__(self, rebalancingParam = False):
        
        '''
        Description:
            Initialize a new instance of CustomEqualWeightingPortfolioConstructionModel
        Args:
            rebalancingParam: Integer indicating the number of days for rebalancing (default set to False, no rebalance)
                - Independent of this parameter, the portfolio will be rebalanced when a security is added/removed/changed direction
        '''
        
        self.insightCollection = InsightCollection()
        self.removedSymbols = []
        self.nextExpiryTime = UTCMIN
        self.rebalancingTime = UTCMIN
        
        # if the rebalancing parameter is not False but a positive integer
        # convert rebalancingParam to timedelta and create rebalancingFunc
        if rebalancingParam > 0:
            self.rebalancing = True
            rebalancingParam = timedelta(days = rebalancingParam)
            self.rebalancingFunc = lambda dt: dt + rebalancingParam
        else:
            self.rebalancing = rebalancingParam

    def CreateTargets(self, algorithm, insights):

        '''
        Description:
            Create portfolio targets from the specified insights
        Args:
            algorithm: The algorithm instance
            insights: The insights to create portfolio targets from
        Returns:
            An enumerable of portfolio targets to be sent to the execution model
        '''

        targets = []
        
        # check if we have new insights coming from the alpha model or if some existing insights have expired
        # or if we have removed symbols from the universe
        if (len(insights) == 0 and algorithm.UtcTime <= self.nextExpiryTime and self.removedSymbols is None):
            return targets
        
        # here we get the new insights and add them to our insight collection
        for insight in insights:
            self.insightCollection.Add(insight)
            
        # create flatten target for each security that was removed from the universe
        if self.removedSymbols is not None:
            universeDeselectionTargets = [ PortfolioTarget(symbol, 0) for symbol in self.removedSymbols ]
            targets.extend(universeDeselectionTargets)
            self.removedSymbols = None

        # get insight that haven't expired of each symbol that is still in the universe
        activeInsights = self.insightCollection.GetActiveInsights(algorithm.UtcTime)

        # get the last generated active insight for each symbol
        lastActiveInsights = []
        for symbol, g in groupby(activeInsights, lambda x: x.Symbol):
            lastActiveInsights.append(sorted(g, key = lambda x: x.GeneratedTimeUtc)[-1])

        errorSymbols = {}
        # check if we actually want to create new targets for the securities (check function ShouldCreateTargets for details)
        if self.ShouldCreateTargets(algorithm, lastActiveInsights):
            # determine target percent for the given insights (check function DetermineTargetPercent for details)
            percents = self.DetermineTargetPercent(lastActiveInsights)
            for insight in lastActiveInsights:
                target = PortfolioTarget.Percent(algorithm, insight.Symbol, percents[insight])
                if not target is None:
                    targets.append(target)
                else:
                    errorSymbols[insight.Symbol] = insight.Symbol
                    
            # update rebalancing time
            if self.rebalancing:
                self.rebalancingTime = self.rebalancingFunc(algorithm.UtcTime)

        # get expired insights and create flatten targets for each symbol
        expiredInsights = self.insightCollection.RemoveExpiredInsights(algorithm.UtcTime)

        expiredTargets = []
        for symbol, f in groupby(expiredInsights, lambda x: x.Symbol):
            if not self.insightCollection.HasActiveInsights(symbol, algorithm.UtcTime) and not symbol in errorSymbols:
                expiredTargets.append(PortfolioTarget(symbol, 0))
                continue

        targets.extend(expiredTargets)
        
        # here we update the next expiry date in the insight collection
        self.nextExpiryTime = self.insightCollection.GetNextExpiryTime()
        if self.nextExpiryTime is None:
            self.nextExpiryTime = UTCMIN

        return targets

    def ShouldCreateTargets(self, algorithm, lastActiveInsights):
        
        '''
        Description:
            Determine whether we should rebalance the portfolio to keep equal weighting when:
                - It is time to rebalance regardless
                - We want to include some new security in the portfolio
                - We want to modify the direction of some existing security
        Args:
            lastActiveInsights: The last active insights to check
        '''
        
        # it is time to rebalance
        if self.rebalancing and algorithm.UtcTime >= self.rebalancingTime:
            return True
        
        for insight in lastActiveInsights:
            # if there is an insight for a new security that's not invested, then rebalance
            if not algorithm.Portfolio[insight.Symbol].Invested and insight.Direction != InsightDirection.Flat:
                return True
            # if there is an insight to close a long position, then rebalance
            elif algorithm.Portfolio[insight.Symbol].IsLong and insight.Direction != InsightDirection.Up:
                return True
            # if there is an insight to close a short position, then rebalance
            elif algorithm.Portfolio[insight.Symbol].IsShort and insight.Direction != InsightDirection.Down:
                return True
            else:
                continue
            
        return False
        
    def DetermineTargetPercent(self, lastActiveInsights):
        
        '''
        Description:
            Determine the target percent from each insight
        Args:
            lastActiveInsights: The active insights to generate a target from
        '''
            
        result = {}

        # give equal weighting to each security
        count = sum(x.Direction != InsightDirection.Flat for x in lastActiveInsights)
        percent = 0 if count == 0 else 1.0 / count
        
        for insight in lastActiveInsights:
            result[insight] = insight.Direction * percent
            
        return result
        
    def OnSecuritiesChanged(self, algorithm, changes):
        
        '''
        Description:
            Event fired each time the we add/remove securities from the data feed
        Args:
            algorithm: The algorithm instance that experienced the change in securities
            changes: The security additions and removals from the algorithm
        '''

        # get removed symbol and invalidate them in the insight collection
        self.removedSymbols = [x.Symbol for x in changes.RemovedSecurities]
        self.insightCollection.Clear(self.removedSymbols)