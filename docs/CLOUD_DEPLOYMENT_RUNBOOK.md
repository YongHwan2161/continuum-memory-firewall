# CockroachDB Cloud Basic and AWS deployment runbook

This document is the single source of truth for preparing, deploying, proving,
and removing the managed-cloud competition slice. Current verified state belongs
in [PROJECT_STATUS.md](PROJECT_STATUS.md); changing price assumptions and hard
cost limits belong in [COST_SAFETY.md](COST_SAFETY.md).

The repository automates only operations that are repeatable and safe to encode.
Account creation, legal acceptance, payment or credit confirmation, MFA, and
copying a newly issued API key are participant-owned actions.

## What is ready now

| Item | Repository support | Still requires the participant |
|---|---|---|
| CockroachDB Basic plan | dry-by-default `ccloud` preflight and provisioning script | create/login to the account, confirm actual free/trial entitlement, approve cluster creation |
| CockroachDB network | architecture does not require Lambda-to-SQL access | remove broad SQL networks and add only the operator's temporary IP |
| Managed MCP identity | Lambda reads one secret ARN and accepts read-only tools only | create the CockroachDB service account/API key and copy it once |
| AWS identity | read-only preflight verifies STS, S3, Secrets Manager, Budgets, and CloudFormation | secure the AWS root user, configure MFA/SSO, and choose the deployment account |
| AWS budget | a separate, first-deployed CloudFormation stack creates forecast-at-80% and actual-at-100% email alerts | supply the billing-owner email and understand that alerts do not stop spend |
| AWS worker | tested Lambda package, minimum IAM, concurrency 1, 30-second timeout, 7-day logs | create a private package bucket and secret, then approve deployment |
| Public exposure | no Function URL or API Gateway is created | keep direct invocation restricted to authorized AWS principals |
| Live evidence | deterministic smoke-test commands are documented | run them against the participant's accounts and retain non-secret output |

No CockroachDB or AWS resource has been created merely by merging these files.

## Deployed architecture

```text
authorized AWS operator
    -> direct Lambda Invoke
       -> 16 KiB input bound
       -> hard-coded read-only MCP tool allowlist
       -> Secrets Manager GetSecretValue for one ARN
       -> HTTPS https://cockroachlabs.cloud/mcp
          + Authorization: Bearer <service-account API key>
          + mcp-cluster-id: <dedicated cluster ID>
       -> at most 256 KiB sanitized result

CloudFormation
    +-> account-level monthly AWS Budget alerts
    +-> Lambda reserved concurrency = 1
    +-> CloudWatch Logs retention = 7 days
    +-> no VPC, NAT Gateway, Function URL, or API Gateway
```

Lambda does not connect to the CockroachDB SQL port. A non-VPC Lambda has no
stable outbound IP, while adding a VPC/NAT Gateway would violate the project's
cost rules. Managed MCP over HTTPS avoids both the broad SQL allowlist and NAT
cost. SQL access is needed only from a temporary operator workstation for
versioned migrations and application verification.

The Managed MCP service has write-capable tools. The worker rejects every tool
outside the explicit set in `src/continuum/aws_mcp_worker.py` before it reads the
secret. The function is an internal evidence worker, not an application
authorization boundary and not a public query API. Use only a dedicated cluster
containing synthetic hackathon data.

## Phase 0 — local checks

From a fresh clone:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
make test
make cloud-package
```

Expected outcomes:

- all unit tests pass, including the write-tool and endpoint-exfiltration
  negative tests;
- `infra/aws/template.json` is valid JSON;
- the Lambda zip passes `unzip -t`;
- no cloud resource is created.

## Phase 1 — participant-only account safety

### CockroachDB Cloud

1. Sign in or create the participant-owned CockroachDB Cloud organization.
2. Enable MFA for the identity provider or account used to sign in.
3. Open the billing/credits view and record a screenshot showing the
   organization-specific trial credit, Basic free allowance, payment status, and
   expiry date. Do not infer eligibility from a public pricing page.
4. Do not add a payment method merely to make automation proceed. Stop and
   decide explicitly if the console requires billing for the selected limit.
5. Use a dedicated synthetic-data cluster. Do not reuse a production
   organization or database.

CockroachDB hosts Basic clusters in its own cloud account. Selecting AWS as the
cluster provider does not require giving CockroachDB this project's AWS
credentials.

### AWS

1. Choose a dedicated hackathon AWS account if available. An account-level
   budget cannot isolate this project from unrelated account spend.
2. Secure the root user with MFA and do not create root access keys.
3. Prefer IAM Identity Center/SSO for the human deployer:

   ```bash
   aws configure sso --profile continuum-hackathon
   aws sso login --profile continuum-hackathon
   export AWS_PROFILE=continuum-hackathon
   export AWS_REGION=ap-southeast-1
   aws sts get-caller-identity
   ```

4. Confirm that the returned account ID is the intended billing account.
5. The deployer needs temporary permission to manage CloudFormation, Lambda,
   IAM roles, CloudWatch Logs, Budgets, the deployment S3 object, and the one
   Secrets Manager secret. Reduce or remove this deployment access after the
   stack is stable.

Do not create a long-lived AWS access key for this workflow. The repository and
`.env.cloud` must never contain AWS session credentials.

### Create the AWS budget before project resources

Copy the ignored non-secret environment file and fill only the AWS profile,
region, budget email, amount, and budget name first:

```bash
cp .env.cloud.example .env.cloud
chmod 600 .env.cloud
set -a
source .env.cloud
set +a
./scripts/deploy_aws_budget.sh --apply
```

This independent stack contains only `AWS::Budgets::Budget`, so it can be
created before the deployment bucket, secret, or Lambda. The later AWS preflight
fails unless this named budget already exists. Confirm that the billing-owner
email is correct and that both forecast and actual notifications appear in AWS
Budgets before continuing.

## Phase 2 — create CockroachDB Basic

Install the current `ccloud` CLI from the official instructions, then:

```bash
ccloud auth login
./scripts/cockroach_preflight.sh
./scripts/provision_cockroach_basic.sh
```

The final command is a dry run. It pins:

- plan: Basic;
- provider: AWS;
- region: `ap-southeast-1` (Singapore);
- cluster name: `continuum-ai`;
- initial spend limit: `0`.

Before approving, inspect the installed CLI:

```bash
ccloud cluster create basic --help
./scripts/provision_cockroach_basic.sh --apply
```

The apply script aborts if the installed CLI no longer advertises
`--spend-limit`. In that case, use the Cloud Console:

1. Create cluster.
2. Select **Basic**, **AWS**, and **Singapore (`ap-southeast-1`)**.
3. Set the lowest no-charge usage/spend configuration displayed by the current
   console.
4. Review the price estimate before clicking Create.

This fail-closed check is intentional: the Cloud API has evolved its Basic usage
limit fields, so an old unattended command must not silently create paid
capacity.

After creation:

1. Record the cluster ID and organization ID in the private deployment record.
2. If the SQL network list contains `0.0.0.0/0`, remove it immediately.
3. Add only the current workstation's public `/32` address while applying the
   migrations. Remove it after the SQL smoke test.
4. Create a dedicated SQL application user and download the CockroachDB CA
   certificate. Use `sslmode=verify-full`; never commit its URL or password.
5. Use the packaged, checksummed migrations documented in
   [MIGRATIONS.md](MIGRATIONS.md). Do not reconstruct or paste a bootstrap
   schema in the SQL console.

Apply migrations and run the cleanup-by-default live smoke test:

```bash
python -m pip install -e ".[cockroach]"
read -rsp 'CockroachDB SQL URL: ' CONTINUUM_DATABASE_URL
printf '\n'
export CONTINUUM_DATABASE_URL
make migrate
./scripts/smoke_live_database.sh --apply
unset CONTINUUM_DATABASE_URL
```

The URL must include the CA path and `sslmode=verify-full`. Use synthetic data
only. The smoke test applies or validates migrations, exercises promotion,
vector indexing, scoped retrieval, fetch, and retrieval audit, then deletes only
the randomly generated rows.

An existing database made from the final P2 bootstrap schema is not silently
trusted. A normal migration run refuses it. After inspecting it and confirming
that no schema job is active, follow the validated `--adopt-existing` procedure
in [MIGRATIONS.md](MIGRATIONS.md). Never adopt an older or partial schema.

## Phase 3 — create the Managed MCP service account

This is participant-only because CockroachDB shows the new API key once.

1. In CockroachDB Cloud, open access management for the dedicated organization.
2. Create a service account named `continuum-aws-mcp`.
3. Assign the minimum Managed MCP role supported for the target cluster. Current
   Managed MCP documentation requires Cluster Operator or Cluster Admin; choose
   Cluster Operator unless a tested tool requires more.
4. Restrict the identity to the dedicated hackathon cluster where the console
   supports resource scoping.
5. Create one API key and copy it into a password manager temporarily.
6. Do not paste it into an issue, PR, shell history, `.env` file, browser code,
   or CloudFormation parameter.

The Lambda IAM role controls who can fetch the AWS secret; the worker tool
allowlist controls which Managed MCP tool names can be called. These controls do
not provide row-level tenant authorization inside an arbitrary `select_query`.
That is why this worker must remain private and the cluster must contain only
synthetic project data.

## Phase 4 — prepare AWS storage, secret, and variables

Choose a globally unique, private bucket name and create it:

```bash
export AWS_PROFILE=continuum-hackathon
export AWS_REGION=ap-southeast-1
export CONTINUUM_DEPLOY_BUCKET='replace-with-a-unique-private-name'

aws s3api create-bucket \
  --bucket "$CONTINUUM_DEPLOY_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration "LocationConstraint=$AWS_REGION"
aws s3api put-public-access-block \
  --bucket "$CONTINUUM_DEPLOY_BUCKET" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
aws s3api put-bucket-encryption \
  --bucket "$CONTINUUM_DEPLOY_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Create the secret without placing the API key in a command-line argument:

```bash
read -rsp 'CockroachDB service-account API key: ' COCKROACH_MCP_API_KEY
printf '\n'
printf '%s' "$COCKROACH_MCP_API_KEY" |
  aws secretsmanager create-secret \
    --name continuum/cockroach-managed-mcp \
    --description 'CockroachDB Cloud Managed MCP key for Continuum' \
    --secret-string file:///dev/stdin
unset COCKROACH_MCP_API_KEY
```

Record only the returned secret ARN. If the secret already exists, use
`put-secret-value` with the same standard-input pattern and then redeploy or wait
up to five minutes for a warm Lambda container's cache to expire.

Update the existing `.env.cloud` with the real bucket, cluster ID, and secret
ARN. Keep the already deployed budget name, billing-owner email, and USD 1–30
monthly alert ceiling aligned with the budget stack. Then reload it:

```bash
set -a
source .env.cloud
set +a
./scripts/aws_preflight.sh
```

The preflight reads secret metadata only; it never calls `GetSecretValue`. It
also verifies the active AWS account, bucket access, the exact named Budget, and
CloudFormation template validity.

## Phase 5 — deploy and verify AWS

Review the exact files first:

- `infra/aws/template.json`
- `infra/aws/requirements-lambda.txt`
- `scripts/build_lambda_package.sh`
- `scripts/deploy_aws.sh`

Then explicitly apply:

```bash
./scripts/deploy_aws.sh --apply
```

The separate budget stack must already exist before this command passes
preflight, but AWS Budgets is an alerting mechanism rather than a hard service
shutdown. Reserved concurrency, short timeout, small memory, no VPC/NAT, and the
absence of a public endpoint are the actual workload-side cost bounds.

Obtain the function name and invoke a metadata-only tool:

```bash
function_name="$(
  aws cloudformation describe-stacks \
    --stack-name continuum-hackathon \
    --query 'Stacks[0].Outputs[?OutputKey==`FunctionName`].OutputValue' \
    --output text
)"
aws lambda invoke \
  --function-name "$function_name" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool":"list_databases","arguments":{}}' \
  /tmp/continuum-mcp-response.json
python -m json.tool /tmp/continuum-mcp-response.json
```

Expected response: `ok: true`, tool `list_databases`, a Managed MCP result, and
an AWS request ID. Do not publish table contents or query output until checked
for sensitive data.

Prove the negative boundary:

```bash
aws lambda invoke \
  --function-name "$function_name" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool":"insert_rows","arguments":{}}' \
  /tmp/continuum-mcp-denied.json
python -m json.tool /tmp/continuum-mcp-denied.json
```

Expected response: `ok: false` with `INVALID_REQUEST`. This request is rejected
before Secrets Manager or Managed MCP is accessed.

## Phase 6 — evidence to retain

Save only non-secret evidence:

- CockroachDB console screenshot showing Basic, AWS Singapore, usage/spend limit,
  and cluster status;
- a redacted `ccloud cluster list` result;
- migration JSON showing the applied or current version, plus a redacted
  ordered query of `continuum_schema_migrations`;
- the passing synthetic SQL smoke-test JSON against the live disposable
  cluster (retain identifiers only if reviewer evidence is required);
- CloudFormation stack outputs;
- Lambda positive metadata invocation and write-tool denial result;
- AWS Budget name and both alert thresholds;
- CloudWatch log group retention and Lambda reserved concurrency;
- GitHub Actions run for the exact deployed commit.

Never capture the SQL URL, API key, secret value, AWS cookies, or access tokens.
Update [PROJECT_STATUS.md](PROJECT_STATUS.md) only after this evidence exists.

## Phase 7 — teardown

Before teardown, export non-secret schema/query-plan evidence and confirm the
judging window has ended.

```bash
aws cloudformation delete-stack --stack-name continuum-hackathon
aws cloudformation wait stack-delete-complete \
  --stack-name continuum-hackathon
aws s3 rm \
  "s3://$CONTINUUM_DEPLOY_BUCKET/lambda/continuum-managed-mcp-worker.zip"
aws secretsmanager delete-secret \
  --secret-id "$CONTINUUM_COCKROACH_MCP_SECRET_ARN" \
  --recovery-window-in-days 7
```

After confirming the bucket has no required evidence, delete the empty package
bucket. In CockroachDB Cloud, revoke the service-account key first, delete the
disposable cluster, and confirm billing/usage has stopped. Secret deletion is
recoverable during the selected seven-day window; cluster deletion may not be.
Keep the budget through all teardown checks, then remove it last:

```bash
aws cloudformation delete-stack \
  --stack-name continuum-hackathon-budget
```

## Official references

- [Create a Basic cluster](https://www.cockroachlabs.com/docs/cockroachcloud/create-a-basic-cluster)
- [Plan a Basic cluster](https://www.cockroachlabs.com/docs/cockroachcloud/plan-your-cluster-basic)
- [`ccloud` getting started](https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started)
- [`ccloud` reference](https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-reference)
- [CockroachDB Cloud Managed MCP](https://www.cockroachlabs.com/docs/cockroachcloud/connect-to-the-cockroachdb-cloud-mcp-server)
- [CockroachDB network authorization](https://www.cockroachlabs.com/docs/cockroachcloud/network-authorization)
- [CockroachDB online schema changes](https://www.cockroachlabs.com/docs/stable/online-schema-changes)
- [AWS Budgets CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-budgets-budget.html)
- [Retrieve Secrets Manager values in Python](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets-python-sdk.html)
- [AWS Lambda Python packages](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
