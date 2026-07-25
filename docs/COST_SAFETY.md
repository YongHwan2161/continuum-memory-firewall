# Cost safety

**Planning assumptions last reviewed:** 2026-07-25

This document is the authoritative source for spending assumptions and controls.
Provider prices, free tiers, hackathon credits, and eligibility can change. The
repository currently contains no written evidence of organizer-provided credits,
so the safe operating assumption is **no sponsored credit until the organizer or
provider confirms it in writing**.

## Hard constraints

- CockroachDB Cloud Basic only
- AWS on-demand and serverless services only
- no EKS
- no NAT Gateway
- no provisioned Bedrock throughput
- no paid multi-region demonstration
- no production customer data
- no unbounded model or embedding loops

## Budget controls

- create a dedicated development account or project where permitted
- set the smallest CockroachDB RU and storage limits
- set an AWS budget alarm before deploying
- cap Bedrock input, output, retries, and daily invocation counts in code
- keep CloudWatch log retention at 3–7 days
- store only bounded synthetic artifacts in S3
- remove or suspend resources after the judging period
- export schema and evidence before any free trial expires

## Planning target

The desired out-of-pocket cost is USD 0. If optional AWS work is approved without
promotional credit, use USD 30 as a project budget ceiling and stop before
crossing it. These are internal planning limits, not statements of current
provider pricing or guaranteed free-tier eligibility.

Before provisioning any managed service:

1. verify current terms on the official provider page;
2. record the account's actual credit and free-tier status;
3. set alerts and service-level limits before the first workload;
4. document teardown ownership and date.
