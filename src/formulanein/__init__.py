__version__ = "0.1.0"

from collections import namedtuple
from dataclasses import dataclass
from typing import Dict, List
import json
import jinja2
import requests
import pprint
import sys

POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
CACHE_FILE_TEMPLATE = "/tmp/formulanein_{}.json"
HTML_FILE_TEMPLATE = "/tmp/{}.html"

@dataclass
class Standing:
    name: str
    constructorId: str
    constructor: str
    points: int = 0
    wins: int = 0
    podiums: int = 0


def collect_season(season: int, reload_cache: bool = False) -> List:
    if reload_cache:
        # Force update from ergast
        return update_cache_from_ergast(season)
    else:
        # Try to use local cache, update from ergast if required
        try: 
            return load_season_from_cache(season)
        except:
            return update_cache_from_ergast(season)


def update_cache_from_ergast(season: int) -> List:
    # Attempt to query ergast for race results, race-by-race
    races = []
    while len(races) < 30:  # Don't enumerate forever, just in case
        url = "https://ergast.com/api/f1/{}/{}/results.json".format(
            season, len(races) + 1
        )
        response = requests.get(url, params={"limit": 50})
        if response.status_code != 200:
            raise RuntimeError("Unable to query ergast, error code {}".format(response.status_code))
        result = response.json()
        if not result["MRData"]["RaceTable"]["Races"]:
            break
        races.append(result["MRData"]["RaceTable"]["Races"][0])
    # Save races to local cache
    cache_filename = CACHE_FILE_TEMPLATE.format(season)
    with open(cache_filename, "w") as cache_fh:
        json.dump(races, cache_fh)
    return races

def load_season_from_cache(season: int) -> List:
    # Load season race data from the local cache
    cache_filename = CACHE_FILE_TEMPLATE.format(season)
    races = []
    try:
        with open(cache_filename, "r") as cache_fh:
            races = json.load(cache_fh)
    except:
        # Cache not found, bail out
        raise RuntimeError("Unable to load races from cache")
    return races


def simulate_season(
    season: int, ignore_drivers: list = [], ignore_constructors: list = [], reload_cache: bool = False
) -> List:
    races = collect_season(season, reload_cache=reload_cache)
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
                    constructorId=result["Constructor"]["constructorId"],
                )
            driver_standings[driverId].points += result["points"]
            driver_standings[driverId].wins += result.get("win", 0)
            driver_standings[driverId].podiums += result.get("podium", 0)
            # Add constructor standing
            constructor = result["Constructor"]["name"]
            if not constructor in constructor_standings:
                constructor_standings[constructor] = Standing(
                    name=constructor, constructor=constructor, constructorId=result["Constructor"]["constructorId"]
                )
            constructor_standings[constructor].points += result["points"]
    # Sort standings by point totals
    sorted_driver_standings = sorted(
        driver_standings.values(), key=lambda x: x.points, reverse=True
    )
    sorted_constructor_standings = sorted(
        constructor_standings.values(), key=lambda x: x.points, reverse=True
    )
    return (
        sorted_driver_standings, 
        sorted_constructor_standings
    )


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
    for standing in driver_standings:
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
    for standing in constructor_standings:
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

def generate_html(races: List) -> None:
    template_env = jinja2.Environment(loader=jinja2.PackageLoader("formulanein", "templates"))
    template = template_env.get_template("season.html")
    season = races[0]["season"]
    (driver_standings, constructor_standings) = aggregate_standings(races)
    output = template.render(season=season, races=races, driver_standings=driver_standings, constructor_standings=constructor_standings)
    with open(HTML_FILE_TEMPLATE.format(season), "w") as html_fh:
        html_fh.write(output)
    

def main():
    races = simulate_season(2019, ignore_constructors=["mercedes"])
    # res = simulate_race(2020, 4, ignore_constructors="red_bull")
    generate_html(races)


if __name__ == "__main__":
    main()
