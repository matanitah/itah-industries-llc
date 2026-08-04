variable "aws_region" {
  type        = string
  description = "AWS region for the control plane"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Environment name"
  default     = "prod"
}

variable "project_name" {
  type        = string
  description = "Name prefix for resources"
  default     = "itah"
}

variable "spark_origin_base_url" {
  type        = string
  description = "Cloudflare Tunnel origin base URL that reaches spark-gateway (e.g. https://spark-origin.example.com)"
  default     = "https://spark-origin.example.com"
}

variable "edge_shared_token" {
  type        = string
  description = "Shared secret sent as X-Itah-Edge-Token from API Gateway to Spark"
  sensitive   = true
  default     = ""
}

variable "portal_shared_token" {
  type        = string
  description = "Shared secret for website BFF → API Gateway (X-Itah-Portal-Token). Never expose to browsers."
  sensitive   = true
  default     = ""
}
