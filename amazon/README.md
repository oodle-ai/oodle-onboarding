# Amazon agent demos

Three independent Python order-support demos, with agent and tool traces
sent directly to Oodle over OTLP/HTTP.

| Demo | Where the agent runs | Model |
|---|---|---|
| [bedrock](./bedrock) | Locally, as a one-shot CLI | Amazon Bedrock Converse |
| [bedrock-agentcore](./bedrock-agentcore) | Locally or in Amazon Bedrock AgentCore Runtime | Amazon Bedrock Converse |
| [bedrock-managed-agents](./bedrock-managed-agents) | AWS-managed Agents for Amazon Bedrock, with local return-control tools | Model calls managed by AWS |

All use fictional orders stored in DynamoDB, a return policy in SSM Parameter
Store, and documentation search through the AWS-managed Knowledge MCP server.
The agent tools are read-only. They show successful model/tool
round trips and an intentional tool failure. Each folder has its own environment,
dependencies, tests, and run instructions; none imports from another demo.

These examples cover agent traces: prompts, answers, model calls, token usage,
tool calls, latency, and errors. They do not configure CloudWatch ingestion or
infrastructure metrics. The first two use native Strands spans. The managed-agent
demo provisions **Agents for Amazon Bedrock** and converts its `enableTrace`
stream into OTel model spans alongside local tool spans.

Each demo provides `make tools-deploy`, `make tools-check`, and
`make tools-destroy`. The tool check makes real AWS/MCP calls without a model and
emits a clearly labeled diagnostic trace. AgentCore also has `make invoke-tools`
to perform that check inside its deployed Runtime. No EKS or ECS is required.
