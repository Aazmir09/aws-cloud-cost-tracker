import json
from datetime import date, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

# AWS Cost Explorer client with timeouts and limited retries
ce = boto3.client(
    "ce",
    region_name="us-east-1",
    config=Config(
        connect_timeout=5,
        read_timeout=15,
        retries={
            "max_attempts": 1,
            "mode": "standard",
        },
    ),
)


class DashboardHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Handle CORS preflight requests from browsers."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        # Health check endpoint for root path
        if self.path == "/":
            self.send_json(200, {
                "status": "ok",
                "message": "Cloud Cost Tracker API is active. Request /api/costs for data."
            })
            return

        # Suppress favicon requests
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if self.path != "/api/costs":
            self.send_json(404, {
                "error": "Endpoint not found",
                "hint": "Open /api/costs",
            })
            return

        # Cost Explorer's End date is exclusive.
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        print(
            f"Request received: {start_date} to {end_date}",
            flush=True,
        )
        print("Calling AWS Cost Explorer...", flush=True)

        try:
            result = ce.get_cost_and_usage(
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

            print("AWS Cost Explorer responded.", flush=True)

            services = {}
            daily = []
            total = Decimal("0")
            estimated = False

            for period in result.get("ResultsByTime", []):
                day_total = Decimal("0")
                estimated = estimated or period.get("Estimated", False)

                for group in period.get("Groups", []):
                    name = group["Keys"][0]
                    amount = Decimal(
                        group["Metrics"]["UnblendedCost"]["Amount"]
                    )

                    services[name] = (
                        services.get(name, Decimal("0")) + amount
                    )
                    day_total += amount

                # Sum all services for this date.
                daily.append({
                    "date": period["TimePeriod"]["Start"],
                    "cost": float(day_total),
                })

            total = sum(services.values(), Decimal("0"))

            response = {
                "currency": "USD",
                "start_date": start_date.isoformat(),
                "end_date_exclusive": end_date.isoformat(),
                "estimated": estimated,
                "total": float(total),
                "services": [
                    {
                        "name": name,
                        "cost": float(amount),
                    }
                    for name, amount in sorted(
                        services.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                ],
                "daily": daily,
            }

            self.send_json(200, response)

        except ClientError as exc:
            error = exc.response.get("Error", {})
            print(
                f"AWS API error: {error.get('Code')}: "
                f"{error.get('Message')}",
                flush=True,
            )
            self.send_json(502, {
                "error": "AWS Cost Explorer request failed",
                "code": error.get("Code", "Unknown"),
                "details": error.get("Message", "Unknown AWS error"),
            })

        except BotoCoreError as exc:
            print(f"AWS connection/configuration error: {exc}", flush=True)
            self.send_json(502, {
                "error": "Could not communicate with AWS",
                "details": str(exc),
            })

        except Exception as exc:
            print(f"Unexpected backend error: {exc}", flush=True)
            self.send_json(500, {
                "error": "Unexpected backend error",
                "details": str(exc),
            })

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        ("0.0.0.0", 8001),
        DashboardHandler,
    )

    print(
        "Cost API running at http://0.0.0.0:8001/api/costs",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Cost API...", flush=True)
    finally:
        server.server_close()