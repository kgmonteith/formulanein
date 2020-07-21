__version__ = "0.1.0"

from collections import namedtuple
from dataclasses import dataclass
from typing import Dict, List
import requests
import pprint

POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]


@dataclass
class Standing:
    name: str
    constructor: str
    points: int = 0
    wins: int = 0
    podiums: int = 0


def collect_season(season: int) -> List:
    # Query results for a season, race by race (to avoid pagination)
    races = []
    while len(races) < 50:  # Don't enumerate forever, just in case
        url = "https://ergast.com/api/f1/{}/{}/results.json".format(
            season, len(races) + 1
        )
        result = requests.get(url, params={"limit": 50}).json()
        if not result["MRData"]["RaceTable"]["Races"]:
            break
        races.append(result["MRData"]["RaceTable"]["Races"][0])
    return races


def simulate_season(
    season: int, ignore_drivers: list = [], ignore_constructors: list = []
) -> List:
    races = collect_season(season)
    for race in races:
        race = simulate_race(
            race, ignore_drivers=ignore_drivers, ignore_constructors=ignore_constructors
        )
    return races


def simulate_race(
    race: Dict, ignore_drivers: list = [], ignore_constructors: list = [],
) -> Dict:
    # Recreate the results as though provided drivers/constructors did not exist
    simulated_results = []
    position = 1
    overall_fastest_lap_position = 0
    overall_fastest_lap_rank = 100
    for result in race["Results"]:
        if (
            not result["Constructor"]["constructorId"] in ignore_constructors
            and not result["Driver"]["driverId"] in ignore_drivers
        ):
            # Finished/DNF must be inferred from 'status' value
            finished = (
                True
                if result["status"].lower() == "finished"
                or "lap" in result["status"].lower()
                else False
            )
            # Points are only awarded if driver finished
            result["points"] = (
                POINTS[position - 1] if position < len(POINTS) + 1 and finished else 0
            )
            # Update position
            result["position"] = position
            result["positionText"] = position
            if position == 1:
                # Count wins
                result["win"] = 1
            elif position <= 3:
                # Count podiums
                result["podium"] = 1
            # Check for fastest lap
            try:
                driver_fastest_lap_rank = int(result["FastestLap"]["rank"])
                if driver_fastest_lap_rank < overall_fastest_lap_rank:
                    overall_fastest_lap_rank = driver_fastest_lap_rank
                    overall_fastest_lap_position = position
            except KeyError:
                # Driver did not complete a lap :(
                pass
            simulated_results.append(result)
            position += 1
    # Award fastest lap point if in top ten
    if simulated_results[overall_fastest_lap_position - 1]["points"]:
        simulated_results[overall_fastest_lap_position - 1]["points"] += 1
    race["Results"] = simulated_results
    return race


def aggregate_standings(races: List) -> Dict:
    # Total points per driver for a given list of races
    # There is definitely a simpler way to do this but my brain is gone
    driver_standings = {}
    constructor_standings = {}
    for race in races:
        for result in race["Results"]:
            # Add driver standing
            driverId = result["Driver"]["driverId"]
            if not driverId in driver_standings:
                driver_standings[driverId] = Standing(
                    name=result["Driver"]["familyName"],
                    constructor=result["Constructor"]["name"],
                )
            driver_standings[driverId].points += result["points"]
            driver_standings[driverId].wins += result.get("win", 0)
            driver_standings[driverId].podiums += result.get("podium", 0)
            # Add constructor standing
            constructor = result["Constructor"]["name"]
            if not constructor in constructor_standings:
                constructor_standings[constructor] = Standing(
                    name=constructor, constructor=constructor
                )
            constructor_standings[constructor].points += result["points"]
    return (driver_standings, constructor_standings)


def print_season(races: List) -> None:
    season = races[0]["season"]
    (driver_standings, constructor_standings) = aggregate_standings(races)
    print_driver_standings(driver_standings, season)
    print()
    print_constructor_standings(constructor_standings, season)
    print()
    for race in races:
        print_race(race)
        print()


def print_driver_standings(driver_standings: Dict, season: int) -> None:
    title = "{} driver standings".format(season)
    print(title)
    print("=" * len(title))
    template = "{:<20} {:<20} {:<8} {:<7} {:<8}"
    print(template.format("Driver", "Team", "Points", "Wins", "Podiums"))
    for standing in sorted(
        driver_standings.values(), key=lambda x: x.points, reverse=True
    ):
        print(
            template.format(
                standing.name,
                standing.constructor,
                standing.points,
                standing.wins if standing.wins > 0 else "",
                standing.podiums if standing.podiums > 0 else "",
            )
        )


def print_constructor_standings(constructor_standings: Dict, season: int) -> None:
    title = "{} constructor standings".format(season)
    print(title)
    print("=" * len(title))
    template = "{:<20} {:<8}"
    print(template.format("Team", "Points"))
    for standing in sorted(
        constructor_standings.values(), key=lambda x: x.points, reverse=True
    ):
        print(template.format(standing.constructor, standing.points))


def print_race(race: Dict) -> None:
    title = "{} {}".format(race["season"], race["raceName"])
    print(title)
    print("-" * len(title))
    template = "{:<4} {:<20} {:<20} {:<3}"
    print(template.format("Pos.", "Driver", "Team", "Points"))
    for result in race["Results"]:
        print(
            template.format(
                result["position"],
                result["Driver"]["familyName"],
                result["Constructor"]["name"],
                result["points"],
            )
        )


def entrypoint():
    races = simulate_season(2020, ignore_constructors=["mercedes"])
    # res = simulate_race(2020, 4, ignore_constructors="red_bull")
    print_season(races)


if __name__ == "__main__":
    entrypoint()
