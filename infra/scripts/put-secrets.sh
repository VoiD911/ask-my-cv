#!/usr/bin/env bash
# Enregistre les secrets de production dans SSM (SecureString). À lancer soi-même.
set -euo pipefail
# Git Bash sous Windows réécrit les arguments commençant par / pour les exécutables natifs
# (comme aws.exe) ; sans effet ailleurs.
export MSYS_NO_PATHCONV=1
PREFIX=/ask-my-cv
REGION=${AWS_REGION:-ca-central-1}

put() {
  # La valeur passe par argv : sous Git Bash/Windows, file:///dev/stdin ne se résout pas de
  # façon fiable pour un exécutable natif comme aws.exe (ce n'est pas un binaire MSYS qui
  # bénéficie de l'émulation POSIX), donc on garde argv malgré le risque d'exposition dans
  # l'historique du shell ou la liste des processus.
  aws ssm put-parameter --region "$REGION" --name "$PREFIX/$1" --type SecureString \
    --value "$2" --overwrite >/dev/null
  echo "ok : $PREFIX/$1"
}

# On ne génère VISITOR_SALT que si le paramètre n'existe pas encore (ParameterNotFound).
# get-parameter sans --with-decryption, et sa sortie standard jetée : aucune valeur secrète
# ne peut être affichée.
if out=$(aws ssm get-parameter --region "$REGION" --name "$PREFIX/VISITOR_SALT" 2>&1 >/dev/null); then
  echo "VISITOR_SALT existe déjà : conservé (le changer réinitialise les quotas visiteurs)."
elif grep -q ParameterNotFound <<<"$out"; then
  put VISITOR_SALT "$(openssl rand -hex 32)"
else
  echo "$out" >&2
  exit 1
fi

read -rsp "Clé publique Langfuse (pk-lf-…) : " PK; echo
read -rsp "Clé secrète Langfuse (sk-lf-…) : " SK; echo
put LANGFUSE_PUBLIC_KEY "$PK"
put LANGFUSE_SECRET_KEY "$SK"
unset PK SK
