# The demo: one EC2 instance running everything in docker compose, plus the registry it
# pulls from. See docs/adr/0009-deployment.md for why one box, and what would change it.

terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
  # Every resource carries these, so it's clear in the console what belongs to this project.
  default_tags {
    tags = {
      project    = "voice-order-agent"
      repo       = "observable-voice-agent"
      managed-by = "terraform"
    }
  }
}

data "aws_caller_identity" "me" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

locals {
  registry  = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  site_host = "${replace(aws_eip.demo.public_ip, ".", "-")}.sslip.io"
}

# --- images ------------------------------------------------------------------------------

resource "aws_ecr_repository" "image" {
  for_each             = toset(["voice-order-agent/app", "voice-order-agent/web"])
  name                 = each.key
  image_tag_mutability = "IMMUTABLE" # a tag always means the same build
  force_delete         = true        # so `make deploy-destroy` really removes everything
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = { Name = each.key }
}

resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each   = aws_ecr_repository.image
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 10 builds"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# --- the instance's permissions: Session Manager, pulling images, reading its secrets ------

resource "aws_iam_role" "demo" {
  name = "voice-order-agent-demo"
  tags = { Name = "voice-order-agent-demo" }
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])
  role       = aws_iam_role.demo.name
  policy_arn = each.key
}

resource "aws_iam_role_policy" "read_secrets" {
  name = "voice-order-agent-read-parameters"
  role = aws_iam_role.demo.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.me.account_id}:parameter/voice-order-agent/*"
    }]
  })
}

resource "aws_iam_instance_profile" "demo" {
  name = "voice-order-agent-demo"
  role = aws_iam_role.demo.name
  tags = { Name = "voice-order-agent-demo" }
}

# --- network: HTTPS and WebRTC in, no SSH (use Session Manager) ----------------------------

resource "aws_security_group" "demo" {
  name        = "voice-order-agent-demo"
  description = "voice-order-agent demo: HTTPS and WebRTC"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP, for the certificate challenge and the redirect to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS: the web app, the API and LiveKit signalling"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "WebRTC over TCP, when UDP is blocked"
    from_port   = 7881
    to_port     = 7881
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "WebRTC media"
    from_port   = 7882
    to_port     = 7882
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "voice-order-agent-demo" }
}

# --- the box ------------------------------------------------------------------------------

resource "aws_eip" "demo" {
  domain = "vpc"
  tags   = { Name = "voice-order-agent-demo" }
}

resource "aws_instance" "demo" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.demo.name
  vpc_security_group_ids = [aws_security_group.demo.id]

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
    tags        = { Name = "voice-order-agent-demo-root" }
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  # First boot only: install Docker and Compose, write the deploy files, start the service.
  # Later releases push the files over SSM (deploy/release.sh), so changes here don't
  # replace the instance.
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    compose_b64 = filebase64("${path.module}/../compose.yaml")
    livekit_b64 = filebase64("${path.module}/../livekit.yaml")
    run_b64     = filebase64("${path.module}/../run.sh")
    registry    = local.registry
    site_host   = local.site_host
    region      = var.region
  })

  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = { Name = "voice-order-agent-demo" }
}

resource "aws_eip_association" "demo" {
  instance_id   = aws_instance.demo.id
  allocation_id = aws_eip.demo.id
}

# --- a spending alarm, if an address is given ---------------------------------------------

resource "aws_budgets_budget" "monthly" {
  count        = var.alert_email == "" ? 0 : 1
  name         = "voice-order-agent-demo"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  tags         = { Name = "voice-order-agent-demo" }
  cost_filter {
    name   = "TagKeyValue"
    values = ["user:project$voice-order-agent"]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
