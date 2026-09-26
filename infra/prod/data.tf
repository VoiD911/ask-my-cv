# Index vectoriel : non géré par hashicorp/aws 6.66, d'où awscc.
# Aucune propriété de l'index n'est modifiable : un changement recrée la table (réingestion).
resource "awscc_dynamodb_table" "chunks" {
  table_name   = "ask-my-cv-chunks"
  billing_mode = "PAY_PER_REQUEST"
  attribute_definitions = [
    { attribute_name = "id", attribute_type = "S" },
  ]
  # Le schéma awscc représente cette propriété CloudFormation (polymorphe) comme une chaîne JSON.
  key_schema = jsonencode([
    { AttributeName = "id", KeyType = "HASH" },
  ])
  vector_indexes = [{
    index_name        = "embedding-index"
    dimensions        = 1024
    distance_function = "DOT_PRODUCT" # vecteurs Titan normalisés ; COSINE inverserait top_score
    vector_attribute  = { attribute_name = "embedding" }
    projection = {
      projection_type    = "INCLUDE"
      non_key_attributes = ["section", "text"] # lus par DynamoVectorStore.search
    }
  }]
  tags = [
    { key = "project", value = "ask-my-cv" },
    { key = "managed-by", value = "terraform" },
    { key = "stack", value = "prod" },
  ]
}

resource "aws_dynamodb_table" "ledger" {
  name         = "ask-my-cv-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
