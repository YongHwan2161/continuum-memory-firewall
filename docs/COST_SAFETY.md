# Cost safety

**Planning assumptions last reviewed:** 2026-07-25

This document is the authoritative source for spending assumptions and controls.
Provider prices, free tiers, hackathon credits, and eligibility can change. The
repository currently contains no written evidence of organizer-provided credits,
so the safe operating assumption is **no sponsored credit until the organizer or
provider confirms it in writing**.

## Current provider facts

As reviewed against official provider documentation on 2026-07-25:

- a CockroachDB organization without billing information can create one Basic
  cluster;
- Basic includes 50 million request units and 10 GiB storage per organization
  each month before configured paid usage;
- published Basic usage prices are USD 0.20 per million request units and USD
  0.50 per GiB-month storage;
- qualifying pay-as-you-go Basic organizations may receive a USD 15 monthly
  free-resource benefit, and a first eligible organization may receive trial
  credit. These benefits are account-specific and must be confirmed in the
  participant's console;
- Basic is hosted by Cockroach Labs on AWS or GCP. It does not consume the
  participant's AWS account;
- no AWS promotional credit or hackathon reimbursement has been evidenced for
  this repository.

Sources:
[Basic creation](https://www.cockroachlabs.com/docs/cockroachcloud/create-a-basic-cluster),
[Basic planning and pricing](https://www.cockroachlabs.com/docs/cockroachcloud/plan-your-cluster-basic),
and [CockroachDB Cloud trial](https://www.cockroachlabs.com/docs/cockroachcloud/free-trial/).

## Hard constraints

- CockroachDB Cloud Basic only
- AWS on-demand and serverless services only
- no EKS
- no NAT Gateway
- no provisioned Bedrock throughput
- no paid multi-region demonstration
- no production customer data
- no unbounded model or embedding loops
- no public Lambda Function URL or API Gateway for the Managed MCP evidence worker
- no CockroachDB SQL `0.0.0.0/0` network after initial cluster review

## Budget controls

- create a dedicated development account or project where permitted;
- start CockroachDB Basic at a zero spend limit and raise it only after measured
  free usage proves insufficient;
- deploy the independent AWS Budget stack before the package bucket, secret,
  and Lambda; make the workload preflight fail unless that exact budget exists;
- alert at 80% forecast and 100% actual monthly budget;
- remember that AWS Budget alerts do not stop resources;
- reserve Lambda concurrency at 1, use 256 MiB memory and a 30-second timeout;
- avoid a VPC/NAT path by calling Managed MCP over HTTPS;
- cap Bedrock input, output, retries, and daily invocation counts in code
- keep CloudWatch log retention at 3–7 days
- store only bounded synthetic artifacts in S3
- remove or suspend resources after the judging period
- export schema and evidence before any free trial expires

## Planning target

The desired out-of-pocket cost is USD 0. The initial infrastructure default is a
USD 5 account-level monthly AWS alert budget. The template accepts USD 1–30, and
USD 30 remains the absolute project planning ceiling if optional paid AWS work
is explicitly approved. These alerts are internal planning controls, not
guaranteed free-tier eligibility or automatic shutdown.

Before provisioning any managed service:

1. verify current terms on the official provider page;
2. record the account's actual credit and free-tier status;
3. set alerts and service-level limits before the first workload;
4. document teardown ownership and date.

The operational sequence and teardown commands are owned by
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).
