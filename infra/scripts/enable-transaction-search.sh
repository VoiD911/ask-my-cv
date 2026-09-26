#!/usr/bin/env bash
# Active Transaction Search (X-Ray → CloudWatch Logs) : une fois par compte.
# La politique de ressource CloudWatch Logs est créée par Terraform (infra/prod).
set -euo pipefail
REGION=${AWS_REGION:-ca-central-1}
aws xray update-trace-segment-destination --region "$REGION" --destination CloudWatchLogs
aws xray update-indexing-rule --region "$REGION" --name Default \
  --rule '{"Probabilistic": {"DesiredSamplingPercentage": 1}}'
aws xray get-trace-segment-destination --region "$REGION"
