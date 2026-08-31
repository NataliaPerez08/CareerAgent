"""Review current AWS costs via Cost Explorer and optionally email a report.

Usage:
    python scripts/aws_costs.py
    python scripts/aws_costs.py --days 7 --budget 50
    python scripts/aws_costs.py --json
    python scripts/aws_costs.py --email

Email settings are read from the .env file (see .env.example):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _client():
    session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"))
    return session.client("ce", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _today() -> datetime:
    return datetime.now(UTC)


def _dates(days: int) -> tuple[str, str]:
    end = _today().date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def month_to_date_cost(client) -> dict:
    start, end = _dates(_today().day)
    response = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    results = response.get("ResultsByTime", [])
    if not results:
        return {"total": 0.0, "currency": "USD"}
    total = float(results[0]["Total"]["UnblendedCost"]["Amount"])
    currency = results[0]["Total"]["UnblendedCost"]["Unit"]
    return {"total": total, "currency": currency}


def forecast_for_month(client) -> dict:
    start = _today().date().isoformat()
    end = (_today().date() + timedelta(days=1)).isoformat()
    response = client.get_cost_forecast(
        TimePeriod={"Start": start, "End": end},
        Metric="UNBLENDED_COST",
        Granularity="MONTHLY",
    )
    total = float(response["Total"]["Amount"])
    unit = response["Total"]["Unit"]
    return {"total": total, "currency": unit}


def daily_costs(client, days: int) -> list[dict]:
    start, end = _dates(days)
    response = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    return [
        {
            "date": result["TimePeriod"]["Start"],
            "amount": float(result["Total"]["UnblendedCost"]["Amount"]),
            "currency": result["Total"]["UnblendedCost"]["Unit"],
        }
        for result in response.get("ResultsByTime", [])
    ]


def costs_by_service(client, days: int) -> list[dict]:
    start, end = _dates(days)
    response = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    rows = []
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            rows.append(
                {
                    "service": group["Keys"][0],
                    "amount": float(group["Metrics"]["UnblendedCost"]["Amount"]),
                    "currency": group["Metrics"]["UnblendedCost"]["Unit"],
                }
            )
    return sorted(rows, key=lambda row: row["amount"], reverse=True)


def build_report(args) -> dict:
    client = _client()
    report = {
        "month_to_date": month_to_date_cost(client),
        "forecast": forecast_for_month(client),
        "daily": daily_costs(client, args.days),
        "by_service": costs_by_service(client, args.days),
    }
    return report


def format_report(report: dict, budget: float | None) -> str:
    mtd = report["month_to_date"]
    forecast = report["forecast"]
    currency = mtd["currency"]

    lines = [
        "AWS Cost Report",
        "===============",
        f"Month-to-date: {mtd['total']:.2f} {currency}",
        f"Month forecast: {forecast['total']:.2f} {currency}",
    ]

    if budget is not None:
        over = mtd["total"] > budget
        lines.append(f"Budget limit: {budget:.2f} {currency} -> {'OVER BUDGET' if over else 'OK'}")

    lines.append("\nCost by service:")
    for row in report["by_service"]:
        lines.append(f"  {row['service']:<40} {row['amount']:.2f} {row['currency']}")

    lines.append("\nDaily spend:")
    for row in report["daily"]:
        lines.append(f"  {row['date']}  {row['amount']:.2f} {row['currency']}")

    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    to = os.getenv("EMAIL_TO")

    if not (user and password and to):
        raise RuntimeError(
            "Missing email settings. Set SMTP_USER, SMTP_PASSWORD and EMAIL_TO in .env."
        )

    message = EmailMessage()
    message["From"] = user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review current AWS costs.")
    parser.add_argument("--days", type=int, default=7, help="Days of daily spend to show.")
    parser.add_argument(
        "--budget", type=float, default=None, help="Alert if month-to-date exceeds this."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--email", action="store_true", help="Email the report.")
    args = parser.parse_args()

    report = build_report(args)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = format_report(report, args.budget)
        print(text)
        if args.email:
            over_budget = args.budget is not None and report["month_to_date"]["total"] > args.budget
            subject = "AWS Cost Report" + (" - OVER BUDGET" if over_budget else "")
            send_email(subject, text)
            print("\nEmail sent.")

    if args.budget is not None and report["month_to_date"]["total"] > args.budget:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
