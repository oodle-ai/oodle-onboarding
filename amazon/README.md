# Amazon agent demos

Three independent Python order-support demos, with agent and tool traces
sent directly to Oodle over OTLP/HTTP.

| Demo | Where the agent runs | Model |
|---|---|---|
| [bedrock](./bedrock) | Locally, as a one-shot CLI | Amazon Bedrock Converse |
| [bedrock-agentcore](./bedrock-agentcore) | Locally or in Amazon Bedrock AgentCore Runtime | Amazon Bedrock Converse |
| [bedrock-managed-agents](./bedrock-managed-agents) | AWS-managed Agents for Amazon Bedrock, with local return-control tools | Model calls managed by AWS |

All use fictional orders and read-only tools. They show successful model/tool
round trips and an intentional tool failure. Each folder has its own environment,
dependencies, tests, and run instructions; none imports from another demo.

These examples cover agent traces: prompts, answers, model calls, token usage,
tool calls, latency, and errors. They do not configure CloudWatch ingestion or
infrastructure metrics. The first two use native Strands spans. The managed-agent
demo provisions **Agents for Amazon Bedrock** and converts its `enableTrace`
stream into OTel model spans alongside local tool spans.
