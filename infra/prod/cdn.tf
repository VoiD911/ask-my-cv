# Pour une requête POST, le client doit envoyer x-amz-content-sha256 = SHA-256 hexadécimal
# du corps (l'OAC Lambda refuse les payloads non signés). Le site (plan 1e) et
# infra/scripts/smoke_prod.py s'en chargent.
resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "ask-my-cv-api"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "strip_api" {
  name    = "ask-my-cv-strip-api"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/strip-api.js")
}

resource "aws_cloudfront_function" "site_index" {
  name    = "ask-my-cv-site-index"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/site-index.js")
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# Tous les en-têtes du visiteur sauf Host, plus les en-têtes CloudFront (dont CloudFront-Viewer-Address).
data "aws_cloudfront_origin_request_policy" "all_but_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# En-têtes de sécurité standard (HSTS, X-Content-Type-Options, etc.).
data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

# En-têtes de sécurité du site : ceux de Managed-SecurityHeadersPolicy plus la CSP.
resource "aws_cloudfront_response_headers_policy" "site" {
  name    = "ask-my-cv-site"
  comment = "En-tetes de securite et CSP du site statique"

  security_headers_config {
    content_security_policy {
      content_security_policy = var.site_csp
      override                = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = false # sous-domaine d'un domaine personnel : ne pas imposer HSTS aux voisins
      preload                    = false
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    xss_protection {
      protection = true
      mode_block = true
      override   = true
    }
  }
}

locals {
  api_domain = trimsuffix(trimprefix(aws_lambda_function_url.api.function_url, "https://"), "/")
}

resource "aws_cloudfront_distribution" "site" {
  enabled         = true
  comment         = "ask-my-cv"
  price_class     = "PriceClass_100"
  http_version    = "http2and3"
  is_ipv6_enabled = true

  aliases             = [var.site_domain]
  default_root_object = "index.html"

  origin {
    origin_id                = "api"
    domain_name              = local.api_domain
    origin_access_control_id = aws_cloudfront_origin_access_control.api.id
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60 # délai LLM global 25 s + étapes précédentes
      origin_keepalive_timeout = 5
    }
  }

  origin {
    origin_id                = "site"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  # Site statique : GET/HEAD seulement, donc redirect-to-https sans risque de perdre un corps.
  default_cache_behavior {
    target_origin_id           = "site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
    compress                   = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.site_index.arn
    }
  }

  # API : https-only (pas redirect-to-https) : une redirection 301 sur un POST transformerait
  # la requête en GET et perdrait le corps. CloudFront transmet l'URI complète (/api/...) :
  # strip-api retire le préfixe avant l'origine Lambda.
  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = "api"
    viewer_protocol_policy     = "https-only"
    allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_but_host.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    compress                   = false # pas de compression d'un flux SSE

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.strip_api.arn
    }
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn # certificat validé
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# L'OAC exige les deux permissions (URL de fonction créée après octobre 2025).
resource "aws_lambda_permission" "cloudfront_url" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.site.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke" {
  statement_id             = "AllowCloudFrontInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.site.arn
  invoked_via_function_url = true
}
