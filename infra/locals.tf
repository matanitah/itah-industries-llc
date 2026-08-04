locals {
  name_prefix = "${var.project_name}-${var.environment}"

  tables = {
    customers      = "${var.project_name}-customers"
    api_keys       = "${var.project_name}-api-keys"
    entitlements   = "${var.project_name}-entitlements"
    spark_status   = "${var.project_name}-spark-status"
    portal_users   = "${var.project_name}-portal-users"
    portal_invites = "${var.project_name}-portal-invites"
  }
}
