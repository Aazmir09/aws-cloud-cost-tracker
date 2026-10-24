
# Allow EventBridge Scheduler to invoke our Lambda function.
resource "aws_iam_role" "scheduler_invoke_lambda" {
  name = "cloud-cost-tracker-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

# Restrict the scheduler to invoking our reporting function.
resource "aws_iam_role_policy" "scheduler_lambda_permission" {
  name = "invoke-cost-report-lambda"
  role = aws_iam_role.scheduler_invoke_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:InvokeFunction"
      ]
      Resource = aws_lambda_function.cost_report.arn
    }]
  })
}

# Run the report every Monday at 8 AM Pakistan time.
resource "aws_scheduler_schedule" "weekly_cost_report" {
  name        = "cloud-cost-tracker-weekly-schedule"
  description = "Generate and email a weekly AWS cost report"

  schedule_expression          = "cron(0 8 ? * MON *)"
  schedule_expression_timezone = "Asia/Karachi"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.cost_report.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn
  }

  depends_on = [
    aws_iam_role_policy.scheduler_lambda_permission
  ]
}
