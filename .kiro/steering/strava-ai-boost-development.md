---
inclusion: fileMatch
fileMatchPattern: 'strava-ai-boost/**'
---

# Strava AI Boost Development Guidelines

## 🎯 Project Overview

**Strava AI Boost** is a simplified, modular serverless application that automatically enhances Strava activity titles and descriptions using AI. This project is a radical simplification of the existing strava-ai-coach project, focusing on core functionality while maintaining modularity.

## 🛠️ Technology Stack (MANDATORY)

### Core Technologies
- **Language**: Python 3.13 (ONLY Python, no TypeScript/JavaScript)
- **Infrastructure**: AWS CDK with Python constructs
- **AI Framework**: Strands Agents for agent orchestration
- **Memory System**: AgentCore Memory for persistent personalization
- **Browser Automation**: AgentCore Browser Tool for Campus Coach scraping
- **Local Interface**: Python Flask/FastAPI with AWS Cloudscape components

### AWS Services
- **Compute**: AWS Lambda (Python 3.12 runtime)
- **Storage**: DynamoDB, S3 (if needed)
- **Messaging**: SQS with Dead Letter Queues
- **Orchestration**: Step Functions
- **AI/ML**: Amazon Bedrock (Claude Sonnet 4.5)
- **Security**: Secrets Manager, IAM
- **API**: API Gateway
- **Monitoring**: CloudWatch, X-Ray

## 📚 Documentation-First Development (CRITICAL)

### ALWAYS Use MCP Tools Before Coding

**RULE**: Never write code without consulting the official documentation first using available MCP tools.

#### 1. AWS Documentation MCP Server
```bash
# Search AWS documentation before implementing any AWS service
mcp_awslabsaws_documentation_mcp_server_search_documentation
mcp_awslabsaws_documentation_mcp_server_read_documentation
```

**Use Cases**:
- CDK construct documentation
- Lambda best practices
- DynamoDB table design
- Step Functions workflow patterns
- API Gateway configuration

#### 2. Strands Agents Documentation MCP Server
```bash
# Search Strands documentation before implementing agents
mcp_strands_search_docs
mcp_strands_fetch_doc
```

**Use Cases**:
- Agent creation patterns
- Bedrock model integration
- Multi-agent workflows
- Error handling in agents

#### 3. AgentCore Documentation MCP Server
```bash
# Search AgentCore documentation before implementing AgentCore features
mcp_awslabsamazon_bedrock_agentcore_mcp_server_search_agentcore_
mcp_awslabsamazon_bedrock_agentcore_mcp_server_fetch_agentcore_d
```

**Use Cases**:
- AgentCore Memory setup
- Browser Tool agent creation
- CLI deployment commands
- Runtime management

#### 4. CDK MCP Server
```bash
# Get CDK guidance and construct examples
mcp_awslabscdk_mcp_server_CDKGeneralGuidance
mcp_awslabscdk_mcp_server_SearchGenAICDKConstructs
```

**Use Cases**:
- CDK best practices
- Construct patterns
- GenAI integrations
- Security configurations

## 🏗️ Development Workflow (MANDATORY)

### Step 1: Research First
1. **Search documentation** using MCP tools for the specific technology/service
2. **Read official examples** and best practices
3. **Understand the patterns** before writing any code
4. **Check existing strava-ai-coach code** for similar implementations

### Step 2: Implementation
1. **Follow documented patterns** exactly
2. **Use official examples** as templates
3. **Implement incrementally** with testing at each step
4. **Document decisions** and rationale

### Step 3: Validation
1. **Test against documentation examples**
2. **Verify with official patterns**
3. **Check for anti-patterns**
4. **Validate security best practices**

## 🚫 Anti-Patterns to Avoid

### Never Do This:
- ❌ Write CDK code without checking AWS CDK documentation
- ❌ Create agents without consulting Strands/AgentCore docs
- ❌ Implement AWS services without reading official patterns
- ❌ Use deprecated or experimental APIs without checking alternatives
- ❌ Copy code from random internet sources
- ❌ Guess API parameters or configuration options

### Always Do This:
- ✅ Search MCP documentation first
- ✅ Use official examples as templates
- ✅ Follow documented best practices
- ✅ Validate against official patterns
- ✅ Check security guidelines
- ✅ Test with documented examples

## 🔧 AgentCore Integration Guidelines

### Deployment Strategy
- **Use AgentCore CLI** for agent deployment (not experimental CDK L2)
- **Create shell scripts** for automated deployment
- **Follow CLI documentation** exactly for commands
- **Use official AgentCore patterns** for agent structure

### AgentCore CLI Commands (Reference)
```bash
# Always check documentation first
agentcore configure --region eu-west-1
agentcore memory create --name <memory-name>
agentcore agent deploy --name <agent-name> --runtime <runtime>
agentcore invoke <agent-name> --input <input-data>
```

### Memory Integration
- **Use AgentCore Memory** for persistent personalization
- **Follow memory patterns** from official documentation
- **Store user preferences** and style learning
- **Implement memory cleanup** for data management

## 🐍 Python Development Standards

### Code Quality
- **Use type hints** everywhere (from typing import ...)
- **Use Pydantic models** for data validation
- **Follow PEP 8** style guidelines
- **Use async/await** for I/O operations
- **Handle exceptions** properly with try/except

### Dependencies Management
- **Use requirements.txt** for Lambda layers
- **Pin versions** for reproducible builds
- **Separate dev/prod** dependencies
- **Use virtual environments** for development

### Testing Strategy
- **Unit tests** with pytest
- **Property-based tests** with Hypothesis (100+ iterations)
- **Integration tests** for AWS services
- **Mock external services** appropriately

## 📋 CDK Development Patterns

### Stack Organization
```python
# Follow this structure exactly
strava-ai-boost/
├── app.py                              # CDK app entry point
├── stacks/
│   ├── core_infrastructure_stack.py    # DynamoDB, IAM
│   ├── api_gateway_stack.py           # API Gateway
│   ├── webhook_processing_stack.py    # Webhooks, SQS
│   ├── content_generation_stack.py    # Step Functions
│   └── monitoring_stack.py            # CloudWatch
├── lambda_functions/                   # Lambda code
├── src/agents/                        # Agent implementations
└── scripts/                           # AgentCore CLI scripts
```

### CDK Best Practices
- **Use L2 constructs** when available and stable
- **Follow least privilege** for IAM roles
- **Enable encryption** by default
- **Use environment variables** for configuration
- **Tag all resources** appropriately

## 🔍 Documentation Research Workflow

### Before Implementing Any Feature:

1. **Search Strands docs** if implementing agents:
   ```bash
   mcp_strands_search_docs("agent creation bedrock")
   ```

2. **Search AWS docs** for AWS services:
   ```bash
   mcp_awslabsaws_documentation_mcp_server_search_documentation("lambda python bedrock")
   ```

3. **Search AgentCore docs** for AgentCore features:
   ```bash
   mcp_awslabsamazon_bedrock_agentcore_mcp_server_search_agentcore_("memory integration")
   ```

4. **Get CDK guidance** for infrastructure:
   ```bash
   mcp_awslabscdk_mcp_server_CDKGeneralGuidance()
   ```

### Documentation Priority Order:
1. **Official AWS documentation** (highest priority)
2. **Strands Agents documentation**
3. **AgentCore documentation**
4. **CDK documentation and examples**
5. **Existing strava-ai-coach patterns** (for reference only)

## 🚨 Critical Requirements

### Security
- **Never hardcode credentials** - use Secrets Manager
- **Use IAM roles** with least privilege
- **Enable encryption** at rest and in transit
- **Validate all inputs** with Pydantic models
- **Follow AWS security best practices**

### Performance
- **Optimize Lambda cold starts** - use provisioned concurrency if needed
- **Implement proper caching** - DynamoDB, in-memory
- **Use async operations** for I/O bound tasks
- **Monitor performance** with CloudWatch metrics

### Reliability
- **Implement retry logic** with exponential backoff
- **Use Dead Letter Queues** for failed messages
- **Handle rate limits** properly (Strava API: 100/15min, 1000/day)
- **Graceful degradation** when modules fail

## 📖 Reference Documentation

### Essential Reading Before Coding:
1. **AWS CDK Python Documentation** - CDK constructs and patterns
2. **Strands Agents Documentation** - Agent creation and orchestration
3. **AgentCore Documentation** - Memory and Browser Tool integration
4. **AWS Lambda Python Documentation** - Runtime and best practices
5. **Amazon Bedrock Documentation** - Model integration patterns

### Code Examples Sources:
1. **Official AWS samples** (GitHub: aws-samples)
2. **Strands framework examples**
3. **AgentCore example agents**
4. **strava-ai-coach project** (for reference patterns only)

## 🎯 Success Criteria

### Code Quality Checklist:
- [ ] All code follows documented patterns from MCP tools
- [ ] No hardcoded values or credentials
- [ ] Proper error handling and logging
- [ ] Type hints and Pydantic models used
- [ ] Tests written and passing
- [ ] Security best practices followed
- [ ] Performance optimized
- [ ] Documentation updated

### Implementation Validation:
- [ ] Matches official documentation examples
- [ ] Follows AWS Well-Architected principles
- [ ] Uses stable APIs (no experimental features)
- [ ] Implements proper monitoring and observability
- [ ] Handles edge cases and failures gracefully

---

**REMEMBER**: This is a documentation-driven project. Always research first, implement second, validate third. Use the MCP tools extensively to avoid hallucinations and ensure code quality.