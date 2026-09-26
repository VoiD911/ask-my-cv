#!/usr/bin/env bash
# Active Transaction Search (X-Ray → CloudWatch Logs) : une fois par compte.
# La politique de ressource CloudWatch Logs est créée par Terraform (infra/prod).
set -euo pipefail
# Git Bash sous Windows réécrit les arguments commençant par / pour les exécutables natifs
# (comme aws.exe) ; sans effet ailleurs.
export MSYS_NO_PATHCONV=1
REGION=${AWS_REGION:-ca-central-1}
aws xray update-trace-segment-destination --region "$REGION" --destination CloudWatchLogs
aws xray update-indexing-rule --region "$REGION" --name Default \
  --rule '{"Probabilistic": {"DesiredSamplingPercentage": 1}}'
aws xray get-trace-segment-destination --region "$REGION"

# Le groupe de logs des spans X-Ray n'existe qu'à l'arrivée des premiers spans : tolérer son
# absence et laisser l'opérateur relancer ce script plus tard pour fixer sa rétention.
if out=$(aws logs put-retention-policy --region "$REGION" --log-group-name aws/spans \
  --retention-in-days 14 2>&1); then
  echo "rétention (14 jours) définie sur le groupe de logs aws/spans"
elif grep -q ResourceNotFoundException <<<"$out"; then
  echo "groupe de logs aws/spans introuvable pour l'instant : relancer ce script plus tard pour fixer sa rétention."
else
  echo "$out" >&2
  exit 1
fi
