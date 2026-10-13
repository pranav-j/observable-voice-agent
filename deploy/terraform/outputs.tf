output "url" {
  value = "https://${local.site_host}"
}

output "site_host" {
  value = local.site_host
}

output "instance_id" {
  value = aws_instance.demo.id
}

output "registry" {
  value = local.registry
}
