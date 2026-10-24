# Allow AWS Lambda to assume this execution role.
resource "aws_iam_role" "cost_report_lambda" {
  name = "cloud-cost-tracker-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

# Grant permissions needed by the report.
resource "aws_iam_role_policy" "cost_report_permissions" {
  name = "cloud-cost-tracker-report-permissions"
  role = aws_iam_role.cost_report_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.cost_alerts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.cost_reports.arn}/*"
      }
    ]
  })
}

# Package the Python code into a ZIP file.
data "archive_file" "cost_report" {
  type        = "zip"
  source_file = "${path.module}/../lambda/report.py"
  output_path = "${path.module}/../lambda/cost_report.zip"
}

# Create the Lambda function.
resource "aws_lambda_function" "cost_report" {
  function_name = "cloud-cost-tracker-weekly-report"
  role          = aws_iam_role.cost_report_lambda.arn

  runtime = "python3.12"
  handler = "report.lambda_handler"

  filename         = data.archive_file.cost_report.output_path
  source_code_hash = data.archive_file.cost_report.output_base64sha256

  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.cost_alerts.arn
      REPORT_BUCKET = aws_s3_bucket.cost_reports.id
    }
  }

  depends_on = [
    aws_iam_role_policy.cost_report_permissions
  ]
}                      