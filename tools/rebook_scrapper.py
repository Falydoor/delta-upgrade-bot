import asyncio
import json
import logging
from datetime import date

import aiohttp
import polars as pl
from fake_useragent import UserAgent

SEAT_TYPES = {
    "Main": "Main",
    "Economy": "Main",
    "Refundable Main": "Main",
    "Comfort+": "Comfort+",
    "Refundable Delta Comfort+": "Comfort+",
    "Premium Select": "Premium Select",
    "Premium Economy": "Premium Select",
    "Premium Comfort": "Premium Select",
    "Delta One": "Delta One",
    "First": "Delta One",
    "Delta One Suites": "Delta One",
    "Business": "Delta One",
    "La Premiere": "Delta One",
}
PRICES = []

logging.basicConfig(level=logging.INFO, format="%(message)s")


def extract_prices(offers_sets, day):
    for offers_set in offers_sets:
        for offer in offers_set["offers"]:
            for item in offer["offerItems"]:
                for pricing in item["offerItemPricing"]:
                    if "repriceQuoteAmt" in pricing:
                        amount = pricing["repriceQuoteAmt"]["additionalCollectionAmt"]
                        if "currencyEquivalentPrice" in amount:
                            item = item["retailItems"][0]
                            seat_type = item["retailItemMetaData"]["fareInformation"][0][
                                "brandByFlightLegs"
                            ][0]["brandName"].replace("&#174;", "")
                            PRICES.append(
                                {
                                    "date": day.isoformat(),
                                    "type": SEAT_TYPES.get(seat_type, f"{seat_type} (NOT_FOUND)"),
                                    "price": amount["currencyEquivalentPrice"]["roundedNumericPart"],
                                    "stop": len(item["flightSegmentIds"]) - 1,
                                }
                            )


async def get_day(session, day):
    headers = {
        "user-agent": str(UserAgent().chrome),
        "authority": "www.delta.com",
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7,es;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": 'Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "origin": "https://www.delta.com",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "content-type": "application/json; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
    }
    data = {
        "offersCriteria": {
            "resultsPageNum": 1,
            "resultsPerRequestNum": 20,
            "recordLocatorId": "",
            "pricingCriteria": {"priceableIn": ["CURRENCY"], "waiveChangeFee": False},
            "flightRequestCriteria": {
                "sortableOptionId": "customScore",
                "bundleOffer": False,
                "calendarSearch": False,
                "currentTripIndexId": "1",
                "selectedOfferId": "",
                "searchOriginDestination": [
                    {
                        "departureLocalTs": day.isoformat(),
                        "tripId": "1",
                        "origins": [{"airportCode": "JFK"}],
                        "destinations": [{"airportCode": "CDG"}],
                    }
                ],
            },
        },
        "isSearch": True,
    }
    for _ in range(5):
        try:
            async with session.post(
                    "https://www.delta.com/ngcOffer/offer/search",
                    headers=headers,
                    data=json.dumps(data),
            ) as response:
                response = await response.json()
                extract_prices(response["offersSets"], day)
                logging.info(f"Try N°{_ + 1} for {day} done")
                break
        except TimeoutError:
            logging.exception(f"Try N°{_ + 1} failed for {day}")


async def get_prices(days):
    post_tasks = []
    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=7)
    ) as session:
        for day in days:
            post_tasks.append(get_day(session, day))
        await asyncio.gather(*post_tasks)
    df = pl.DataFrame(PRICES)
    df = df.unique().sort("date", "type", "price", "stop")
    df.write_csv("prices.csv")


def save_prices(start_date, end_date):
    days = pl.date_range(start_date, end_date, "1d", eager=True)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(get_prices(days))
    finally:
        loop.close()


def get_min():
    df_prices = pl.read_csv("prices.csv")
    df = df_prices.group_by("type", "stop").agg(pl.col("price").min())
    df = df.join(df_prices, on=["type", "stop", "price"])
    with pl.Config(tbl_rows=-1, fmt_table_cell_list_len=-1, fmt_str_lengths=500):
        logging.info(
            df.unique()
            .sort("date")
            .group_by("price", "type", "stop")
            .agg(pl.col("date"))
            .sort("type", "price", "stop")
        )


if __name__ == '__main__':
    save_prices(date(year=2024, month=12, day=1), date(year=2024, month=12, day=1))
    get_min()
