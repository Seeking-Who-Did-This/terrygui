# Simple Terraform project for testing

variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region"
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "enable_monitoring" {
  type    = bool
  default = false
}

variable "api_key" {
  type      = string
  sensitive = true
  description = "API key for external service"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID. Leave null to use default VPC."
  default     = null
}

resource "null_resource" "example" {
  triggers = {
    region = var.region
  }
}

output "instance_type" {
  value = var.instance_type
}
