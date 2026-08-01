# Cost safety

**Planning assumptions last reviewed:** 2026-07-31

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
- AWS on-demand services only; one `t3.micro` host is the bounded exception
  required for fixed SQL egress
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
- reserve Lambda concurrency at 1 only when the account quota can retain AWS's
  minimum unreserved pool; omit the reservation at the new-account quota of 10,
  and keep 256 MiB memory with a 30-second timeout;
- avoid a VPC/NAT path by calling Managed MCP over HTTPS;
- cap Bedrock input, output, retries, and daily invocation counts in code
- keep CloudWatch log retention at 3–7 days
- store only bounded synthetic artifacts in S3
- remove or suspend resources after the judging period
- export schema and evidence before any free trial expires

## Planning target

The desired out-of-pocket cost is USD 0. The initial infrastructure default is a
USD 10 account-level monthly AWS alert budget. The template accepts USD 1–30, and
USD 30 remains the absolute project planning ceiling if optional paid AWS work
is explicitly approved. These alerts are internal planning controls, not
guaranteed free-tier eligibility or automatic shutdown.

## Live controls observed on 2026-08-01

- the USD 10 Budget stack is `CREATE_COMPLETE`, with forecast-at-80% and
  actual-at-100% notifications;
- the private package bucket blocks public access, uses AES256 server-side
  encryption, and expires `lambda/` objects after seven days;
- the Lambda has no public URL, retains logs for seven days, and can read only
  the one Managed MCP secret;
- the authenticated MCP host is one `t3.micro` with one Elastic IP, no SSH,
  IMDSv2 required, and an instance role limited to one runtime secret and one
  S3 artifact object;
- before the increase, the recurring USD 5 budget reported USD 2.043 actual and
  USD 2.053 forecast; the current alert ceiling is USD 10. Budget data can lag
  new EC2 and public-IPv4 usage, so these values are historical evidence of the
  alert state, not a final monthly cost;
- no NAT Gateway, VPC, API Gateway, EKS, or provisioned model service was
  deployed;
- the Secrets Manager key does not yet rotate automatically, so teardown or
  rotation remains a cost and security gate after judging.

The EC2 instance and public IPv4 address accrue time-based charges while left
running. Stop or delete the authenticated-MCP stack after judging; releasing
the stack also releases its Elastic IP. The alert does not enforce a hard stop.

Before provisioning any managed service:

1. verify current terms on the official provider page;
2. record the account's actual credit and free-tier status;
3. set alerts and service-level limits before the first workload;
4. document teardown ownership and date.

The operational sequence and teardown commands are owned by
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).
