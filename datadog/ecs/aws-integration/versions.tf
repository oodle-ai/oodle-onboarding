terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.85.0"
    }
    datadog = {
      source  = "DataDog/datadog"
      version = "~> 3.50"
    }
  }
}
