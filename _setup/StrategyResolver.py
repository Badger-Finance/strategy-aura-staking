from brownie import interface

from helpers.StrategyCoreResolver import StrategyCoreResolver
from rich.console import Console
from _setup.config import WANT

console = Console()


class StrategyResolver(StrategyCoreResolver):
    def get_strategy_destinations(self):
        """
        Track balances for all strategy implementations
        (Strategy Must Implement)
        """
        strategy = self.manager.strategy
        sett = self.manager.sett
        return {
            "baseRewardPool": strategy.baseRewardPool(),
            "bAuraBal": strategy.BAURABAL(),
            "graviAura": strategy.GRAVIAURA(),
            "badgerTree": sett.badgerTree(),
        }

    def add_balances_snap(self, calls, entities):
        super().add_balances_snap(calls, entities)
        strategy = self.manager.strategy

        aura = interface.IERC20(strategy.AURA())
        auraBal = interface.IERC20(strategy.AURABAL())  # want

        bAuraBal = interface.IERC20(strategy.BAURABAL())
        graviAura = interface.IERC20(strategy.GRAVIAURA())

        calls = self.add_entity_balances_for_tokens(calls, "aura", aura, entities)
        calls = self.add_entity_balances_for_tokens(calls, "auraBal", auraBal, entities)
        calls = self.add_entity_balances_for_tokens(
            calls, "bAuraBal", bAuraBal, entities
        )
        calls = self.add_entity_balances_for_tokens(
            calls, "graviAura", graviAura, entities
        )

        return calls

    def confirm_harvest(self, before, after, tx):
        console.print("=== Compare Harvest ===")
        self.manager.printCompare(before, after)
        self.confirm_harvest_state(before, after, tx)

        super().confirm_harvest(before, after, tx)

        assert len(tx.events["Harvested"]) == 1
        event = tx.events["Harvested"][0]

        assert event["token"] == WANT
        assert event["amount"] == 0

        assert len(tx.events["TreeDistribution"]) == 2

        emitted = {
            "bAuraBal": self.manager.strategy.BAURABAL(),
            "graviAura": self.manager.strategy.GRAVIAURA(),
        }

        for i, key in enumerate(emitted):
            event = tx.events["TreeDistribution"][i]

            assert after.balances(key, "badgerTree") > before.balances(
                key, "badgerTree"
            )

            if before.get("sett.performanceFeeGovernance") > 0:
                assert after.balances(key, "treasury") > before.balances(
                    key, "treasury"
                )

            if before.get("sett.performanceFeeStrategist") > 0:
                assert after.balances(key, "strategist") > before.balances(
                    key, "strategist"
                )

            assert event["token"] == emitted[key]
            assert event["amount"] == after.balances(
                key, "badgerTree"
            ) - before.balances(key, "badgerTree")
