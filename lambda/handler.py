import json
import logging
import os
import socket
import time
from datetime import datetime

import boto3
import pytz
import requests
from fake_useragent import UserAgent
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger()
logger.setLevel("INFO")
socket.setdefaulttimeout(15)

region_name = "us-east-1"
sns_client = boto3.client("sns", region_name=region_name)
s3_client = boto3.client("s3", region_name=region_name)

TOPIC_ARN = os.environ["TOPIC_ARN"]
BUCKET_NAME = os.environ["BUCKET_NAME"]
CONFIG_FILENAME = os.environ["CONFIG_FILENAME"]


def gsheet_service(user_info):
    return build(
        "sheets",
        "v4",
        credentials=Credentials.from_authorized_user_info(
            user_info, ["https://www.googleapis.com/auth/spreadsheets"]
        ),
    )


def gsheet_write(values, service, gsheet_config):
    for i in range(1, 4):
        try:
            # Call the Sheets API
            sheet = service.spreadsheets()
            result = (
                sheet.values()
                .get(
                    spreadsheetId=gsheet_config["id"],
                    range=f"{gsheet_config['tab']}!A2:F",
                )
                .execute()
            )
            row_number = len(result.get("values", [])) + 1
            service.spreadsheets().values().append(
                spreadsheetId=gsheet_config["id"],
                range=f"{gsheet_config['tab']}!A{row_number}:F",
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
            break
        except Exception:
            logger.exception("Unable to write to GSheet (try %s)", i)
            time.sleep(30 * i)


def check_seats(trip, gsheets_service, gsheet_config):
    run_datetime = (
        datetime.now(pytz.timezone("US/Eastern"))
        .replace(tzinfo=None)
        .isoformat(sep=" ", timespec="seconds")
    )
    try:
        headers = {
            "user-agent": str(UserAgent().chrome),
            "authority": "www.delta.com",
            "accept": "*/*",
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
            "referer": "https://www.delta.com/seat/RetrieveSeatMapAction",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
        }
        r = requests.post(trip["url"], headers=headers, data=trip["data"])

        if r.status_code != 200:
            logger.error("Unable to get seats!\n\n%s", r.text)
            return

        ism_response = r.json()["retrieveISMResponse"]
        values = []
        for cabin in ism_response["seatMapDO"]["seatCabins"]:
            prices = []
            cabin_type = cabin["cabinType"]
            if cabin_type not in ["COACH"]:
                for row in cabin["seatRows"]:
                    for column in row["seatColumns"]:
                        for offer in column["seatOffer"]:
                            seat_price = float(offer["amount"])
                            if seat_price > 0:
                                prices.append(seat_price)
            if len(prices) > 0:
                min_price = int(min(prices))
                values.append(
                    [
                        run_datetime,
                        cabin_type,
                        min_price,
                        int(max(prices)),
                        int(sum(prices) / len(prices)),
                        trip["name"],
                        f"{trip['name']} - {cabin_type}",
                    ]
                )

                # Send alert
                if (
                        cabin_type in trip["alerts"]
                        and min_price <= trip["alerts"][cabin_type]
                ):
                    subject = f"Delta Bot - {cabin_type} for ${min_price} ({trip['name']})"
                    logger.info("Sending alert with subject '%s'", subject)

                    # Publish to SNS
                    sns_client.publish(
                        TopicArn=TOPIC_ARN, Message="Buy it!", Subject=subject
                    )

        if len(values):
            logger.info("Writing to Google Sheets")
            gsheet_write(
                values,
                gsheets_service,
                gsheet_config,
            )
    except Exception:
        logger.exception(f"Exception while checking seat")


def main(event, context):
    s3_object = s3_client.get_object(Bucket=BUCKET_NAME, Key=CONFIG_FILENAME)
    config = json.loads(s3_object["Body"].read().decode("utf-8"))

    gsheets_service = gsheet_service(config["google"])
    for idx, trip in enumerate(config["trips"]):
        logger.info("Checking trip %s : %s", idx, trip["url"])
        check_seats(trip, gsheets_service, config["gsheet"])
