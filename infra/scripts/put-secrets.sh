#!/usr/bin/env bash
# Enregistre les secrets de production dans SSM (SecureString). À lancer soi-même.
set -euo pipefail
PREFIX=/ask-my-cv
REGION=${AWS_REGION:-ca-central-1}

put() {
  aws ssm put-parameter --region "$REGION" --name "$PREFIX/$1" --type SecureString \
    --value "$2" --overwrite >/dev/null
  echo "ok : $PREFIX/$1"
}

if aws ssm get-parameter --region "$REGION" --name "$PREFIX/VISITOR_SALT" >/dev/null 2>&1; then
  echo "VISITOR_SALT existe déjà : conservé (le changer réinitialise les quotas visiteurs)."
else
  put VISITOR_SALT "$(openssl rand -hex 32)"
fi

read -rsp "Clé publique Langfuse (pk-lf-…) : " PK; echo
read -rsp "Clé secrète Langfuse (sk-lf-…) : " SK; echo
put LANGFUSE_PUBLIC_KEY "$PK"
put LANGFUSE_SECRET_KEY "$SK"
unset PK SK
