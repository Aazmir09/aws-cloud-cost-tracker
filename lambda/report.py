import os
import boto3
from datetime import date, timedelta
from decimal import Decimal

# Cost Explorer uses the US East (N. Virginia) endpoint.
ce = boto3.client("ce", region_name="us-east-1")

# SNS and S3 are in the Mumbai region.
sns = boto3.client("sns", region_name="ap-south-1")
s3 = boto3.client("s3", region_name="ap-south-1")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
REPORT_BUCKET = os.environ["REPORT_BUCKET"]


def lambda_handler(event, context):
    # Cost Explorer's End date is exclusive.
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": start_date.isoformat(),
            "End": end_date.isoformat(),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[
            {"Type": "DIMENSION", "Key": "SERVICE"}
        ],
    )

    service_totals = {}
    total_cost = Decimal("0")

    for day in response["ResultsByTime"]:
        for group in day["Groups"]:
            service = group["Keys"][0]
            amount = Decimal(
                group["Metrics"]["UnblendedCost"]["Amount"]
            )

            service_totals[service] = (
                service_totals.get(service, Decimal("0")) + amount
            )
            total_cost += amount

    lines = [
        "AWS CLOUD COST REPORT",
        f"Period: {start_date} to {end_date} (end date exclusive)",
        f"Total cost: ${total_cost:.2f} USD",
        "",
        "COST BY SERVICE:",
    ]

    for service, amount in sorted(
        service_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        lines.append(f"{service}: ${amount:.2f} USD")

    if not service_totals:
        lines.append("No cost data was returned for this period.")

    message = "\n".join(lines)

    # Save the report in S3.
    report_key = (
        f"reports/weekly-cost-report-{end_date.isoformat()}.txt"
    )

    s3.put_object(
        Bucket=REPORT_BUCKET,
        Key=report_key,
        Body=message.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )

    # Email the report through SNS.
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="Your Weekly AWS Cost Report",
        Message=message,
    )

    return {
        "statusCode": 200,
        "message": "Weekly cost report sent and saved to S3",
        "total_cost_usd": str(total_cost),
        "services_reported": len(service_totals),
        "report_bucket": REPORT_BUCKET,
        "report_key": report_key,
    }