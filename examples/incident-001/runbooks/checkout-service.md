# Runbook: checkout-service

## Service overview

Handles cart checkout and payment orchestration. Owned by the payments team.
Dashboards: `checkout-overview` (Grafana). Pager: `checkout-oncall`.

## Alerts

| Alert | Meaning | First response |
|---|---|---|
| CheckoutHighErrorRate | 5xx rate above 5% for 5m | Check recent deploys, then downstream payment gateway status |

## Common failure modes

- Payment gateway timeouts: check gateway status page, enable retry queue.
- Bad deploy: roll back via `spinnaker rollback checkout-service`.

## Escalation

Page `payments-lead` if error rate stays above 5% for more than 30 minutes.
