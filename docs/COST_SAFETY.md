# Cost safety

The hackathon provides links to standard free tiers. It does not currently
promise participant-specific AWS or CockroachDB credits. The entrant is
responsible for usage beyond free-tier limits.

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

## Target

The target out-of-pocket cost for new eligible accounts is USD 0. For an
existing AWS account without promotional credit, the working ceiling is USD 30.
This is a planning target, not a promise of provider pricing.
