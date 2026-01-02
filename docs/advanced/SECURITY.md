# 🔒 Security Guide

This document outlines the security practices, policies, and configurations implemented in the Strava AI Boost system to ensure data protection, secure communication, and compliance with security best practices.

## Security Overview

Strava AI Boost implements a defense-in-depth security strategy with multiple layers of protection:

1. **Network Security** - HTTPS enforcement, local-only interface
2. **Identity and Access Management** - Least privilege IAM roles
3. **Data Protection** - Encryption at rest and in transit
4. **Application Security** - Input validation, secure coding practices
5. **Monitoring and Compliance** - Continuous security monitoring

## Data Protection

### Encryption at Rest

All data stored in AWS services is encrypted using AWS managed encryption:

#### DynamoDB Tables
```json
{
  "SSESpecification": {
    "SSEEnabled": true
  },
  "PointInTimeRecoverySpecification": {
    "PointInTimeRecoveryEnabled": true
  }
}
```

**Validated by Property 15**: All DynamoDB tables must have AWS managed encryption enabled.

#### SQS Queues
```json
{
  "KmsMasterKeyId": "alias/aws/sqs"
}
```

#### Secrets Manager
- Automatic encryption with AWS managed keys
- Automatic rotation capability (when supported by service)
- Access logging and monitoring

### Encryption in Transit

All data transmission uses TLS 1.2+ encryption:

#### API Gateway Configuration
```json
{
  "EndpointConfiguration": {
    "Types": ["REGIONAL"]
  },
  "SecurityPolicy": "TLS_1_2"
}
```

**Validated by Property 16**: All API endpoints must use HTTPS for secure communication.

#### Internal AWS Services
- Service-to-service communication uses AWS internal encryption
- Lambda to DynamoDB: Encrypted by default
- Lambda to SQS: KMS encryption
- Lambda to Secrets Manager: TLS encryption

#### Local Web Interface
```python
# HTTPS enforcement for local interface
app.config['FORCE_HTTPS'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
```

## Identity and Access Management

### IAM Security Principles

1. **Least Privilege**: Each role has minimal required permissions
2. **AWS Managed Policies**: Prefer AWS managed over custom policies
3. **Resource-Level Permissions**: Specific ARNs where possible
4. **Regular Review**: Periodic access review and cleanup

### Lambda Execution Roles

#### WebhookLambdaRole
```json
{
  "AssumeRolePolicyDocument": {
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  },
  "ManagedPolicyArns": [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ],
  "Policies": [{
    "PolicyName": "DynamoDBAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ],
        "Resource": [
          "arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-activities",
          "arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-rate-limits",
          "arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-activities/index/*"
        ]
      }]
    }
  }, {
    "PolicyName": "SQSAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "sqs:SendMessage"
        ],
        "Resource": [
          "arn:aws:sqs:eu-west-1:*:strava-ai-boost-activity-processing"
        ]
      }]
    }
  }, {
    "PolicyName": "SecretsManagerAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue"
        ],
        "Resource": [
          "arn:aws:secretsmanager:eu-west-1:*:secret:strava-ai-boost-oauth-tokens-*"
        ]
      }]
    }
  }]
}
```

#### ContentLambdaRole
```json
{
  "Policies": [{
    "PolicyName": "BedrockAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        "Resource": [
          "arn:aws:bedrock:eu-west-1::foundation-model/global.anthropic.claude-sonnet-4-5-20250929-v1:0"
        ]
      }]
    }
  }, {
    "PolicyName": "AgentCoreAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "bedrock-agentcore:InvokeAgent",
          "bedrock-agentcore:GetAgent",
          "bedrock-agentcore:ListAgents"
        ],
        "Resource": "*"
      }]
    }
  }]
}
```

### Step Functions Execution Role
```json
{
  "AssumeRolePolicyDocument": {
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "states.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  },
  "ManagedPolicyArns": [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaRole"
  ],
  "Policies": [{
    "PolicyName": "LambdaInvocation",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "lambda:InvokeFunction"
        ],
        "Resource": [
          "arn:aws:lambda:eu-west-1:*:function:StravaAIBoost-*"
        ]
      }]
    }
  }]
}
```

## Credential Management

### Secrets Manager Integration

#### OAuth Token Storage
```json
{
  "SecretName": "strava-ai-boost-oauth-tokens",
  "Description": "Strava OAuth access and refresh tokens",
  "SecretString": {
    "access_token": "encrypted_access_token",
    "refresh_token": "encrypted_refresh_token",
    "expires_at": "2025-12-22T10:00:00Z",
    "token_type": "Bearer",
    "scope": "read,activity:write"
  }
}
```

#### Campus Coach Credentials
```json
{
  "SecretName": "strava-ai-boost-campus-coach-credentials",
  "Description": "Campus Coach login credentials for AgentCore Browser Tool",
  "SecretString": {
    "username": "encrypted_username",
    "password": "encrypted_password",
    "login_url": "https://campus.coach/login",
    "session_cookies": {}
  }
}
```

### Secure Token Handling

```python
class SecureTokenManager:
    def __init__(self):
        self.secrets_client = boto3.client('secretsmanager')
    
    async def get_valid_token(self, secret_name: str) -> Dict[str, str]:
        """Retrieve and validate OAuth token with automatic refresh"""
        try:
            response = await self.secrets_client.get_secret_value(
                SecretId=secret_name
            )
            token_data = json.loads(response['SecretString'])
            
            # Check token expiration
            if datetime.now() >= datetime.fromisoformat(token_data['expires_at']):
                token_data = await self.refresh_token(token_data)
                await self.store_token(secret_name, token_data)
            
            return token_data
            
        except ClientError as e:
            logger.error(f"Failed to retrieve token: {e}")
            raise TokenRetrievalError(f"Token access failed: {e}")
    
    async def store_token(self, secret_name: str, token_data: Dict[str, str]) -> None:
        """Securely store token with encryption"""
        await self.secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(token_data)
        )
```

## Network Security

### API Gateway Security

#### HTTPS Enforcement
```python
# All API Gateway endpoints enforce HTTPS
{
  "RestApi": {
    "EndpointConfiguration": {
      "Types": ["REGIONAL"]
    },
    "Policy": {
      "Statement": [{
        "Effect": "Deny",
        "Principal": "*",
        "Action": "execute-api:Invoke",
        "Resource": "*",
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }]
    }
  }
}
```

#### Request Validation
```python
# Input validation for all API endpoints
{
  "RequestValidator": {
    "ValidateRequestBody": true,
    "ValidateRequestParameters": true
  },
  "RequestModels": {
    "application/json": "WebhookModel"
  }
}
```

### Local Interface Security

#### Network Binding
```python
# Local interface bound to localhost only
app.run(
    host='127.0.0.1',  # Localhost only
    port=8000,
    ssl_context='adhoc',  # HTTPS with self-signed cert
    debug=False  # Disable debug in production
)
```

#### Session Security
```python
app.config.update(
    SECRET_KEY=os.urandom(24),  # Random session key
    SESSION_COOKIE_SECURE=True,  # HTTPS only
    SESSION_COOKIE_HTTPONLY=True,  # No JavaScript access
    SESSION_COOKIE_SAMESITE='Strict',  # CSRF protection
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)  # Session timeout
)
```

## Application Security

### AI Security - Bedrock Guardrails (v1.16.0+)

**Purpose**: Protect AI agents against prompt injection, harmful content, and PII leakage

**Implementation**: Automatic via CDK SecurityStack

**Protection Layers**:
- 🛡️ **Prompt Injection**: HIGH strength blocking of instruction override attempts
- 🚫 **Harmful Content**: Filters violence, hate, sexual content, insults
- 📋 **Topic Boundaries**: Blocks politics, financial advice, medical advice
- 🔒 **PII Protection**: Blocks/anonymizes email, phone, address, credit cards
- 📝 **Custom Words**: Blocks injection phrases

**Deployment**: Fully automated
```bash
# Guardrails deployed automatically with infrastructure
./scripts/deploy.sh dev
```

**Configuration**: Automatic detection in agents
```python
# Both agents use guardrails automatically
model = BedrockModel(
    model_id="claude-sonnet-4-5",
    guardrail_id=os.getenv("GUARDRAIL_ID"),  # Auto-configured
    guardrail_version="1"
)
```

**Cost**: +$0.000375 per activity (+2%)

**Reference**: See `docs/advanced/BEDROCK-GUARDRAILS.md`

### Input Validation

#### Pydantic Models
```python
from pydantic import BaseModel, validator
from typing import Literal

class WebhookPayload(BaseModel):
    """Strava webhook payload validation"""
    object_type: Literal['activity']
    object_id: int
    aspect_type: Literal['create', 'update', 'delete']
    owner_id: int
    subscription_id: int
    event_time: int
    
    @validator('object_id', 'owner_id', 'subscription_id')
    def validate_positive_integers(cls, v):
        if v <= 0:
            raise ValueError('IDs must be positive integers')
        return v
    
    @validator('event_time')
    def validate_event_time(cls, v):
        # Validate timestamp is reasonable (not too old or future)
        now = int(time.time())
        if v < now - 86400 or v > now + 3600:  # 24h past, 1h future
            raise ValueError('Invalid event timestamp')
        return v

class ActivityData(BaseModel):
    """Activity data validation"""
    id: str
    name: str
    description: Optional[str] = None
    type: Literal['Run', 'Ride', 'Swim', 'Workout']
    distance: float
    moving_time: int
    
    @validator('distance')
    def validate_distance(cls, v):
        if v < 0 or v > 1000000:  # 0 to 1000km reasonable range
            raise ValueError('Invalid distance value')
        return v
    
    @validator('moving_time')
    def validate_time(cls, v):
        if v < 0 or v > 86400:  # 0 to 24 hours
            raise ValueError('Invalid moving time')
        return v
```

#### SQL Injection Prevention
```python
# Using DynamoDB (NoSQL) eliminates SQL injection risks
# All queries use parameterized operations

dynamodb_table.put_item(
    Item={
        'activity_id': activity_id,  # Parameterized
        'data': sanitized_data       # Validated input
    }
)
```

### Error Handling

#### Secure Error Messages
```python
class SecureErrorHandler:
    def handle_error(self, error: Exception, context: str) -> Dict[str, str]:
        """Return safe error messages without sensitive information"""
        
        # Log full error details securely
        logger.error(f"Error in {context}: {str(error)}", extra={
            'context': context,
            'error_type': type(error).__name__,
            'user_id': self.get_current_user_id()
        })
        
        # Return sanitized error to user
        if isinstance(error, ValidationError):
            return {"error": "Invalid input data", "code": "VALIDATION_ERROR"}
        elif isinstance(error, RateLimitError):
            return {"error": "Rate limit exceeded", "code": "RATE_LIMIT"}
        else:
            return {"error": "Internal server error", "code": "INTERNAL_ERROR"}
```

## Security Monitoring

### CloudWatch Security Metrics

#### Failed Authentication Attempts
```python
# Monitor failed OAuth attempts
cloudwatch.put_metric_data(
    Namespace='StravaAIBoost/Security',
    MetricData=[{
        'MetricName': 'FailedAuthAttempts',
        'Value': 1,
        'Unit': 'Count',
        'Dimensions': [
            {'Name': 'Source', 'Value': 'OAuth'},
            {'Name': 'Reason', 'Value': 'InvalidToken'}
        ]
    }]
)
```

#### Suspicious Activity Detection
```python
# Monitor unusual API usage patterns
cloudwatch.put_metric_data(
    Namespace='StravaAIBoost/Security',
    MetricData=[{
        'MetricName': 'UnusualActivity',
        'Value': 1,
        'Unit': 'Count',
        'Dimensions': [
            {'Name': 'Type', 'Value': 'HighFrequencyRequests'},
            {'Name': 'UserID', 'Value': user_id}
        ]
    }]
)
```

### Security Alarms

#### High Error Rate Alarm
```json
{
  "AlarmName": "StravaAIBoost-HighErrorRate",
  "AlarmDescription": "High error rate indicating potential security issues",
  "MetricName": "Errors",
  "Namespace": "AWS/Lambda",
  "Statistic": "Sum",
  "Period": 300,
  "EvaluationPeriods": 2,
  "Threshold": 10,
  "ComparisonOperator": "GreaterThanThreshold",
  "AlarmActions": [
    "arn:aws:sns:eu-west-1:*:security-alerts"
  ]
}
```

#### Failed Authentication Alarm
```json
{
  "AlarmName": "StravaAIBoost-FailedAuth",
  "AlarmDescription": "Multiple failed authentication attempts",
  "MetricName": "FailedAuthAttempts",
  "Namespace": "StravaAIBoost/Security",
  "Statistic": "Sum",
  "Period": 300,
  "EvaluationPeriods": 1,
  "Threshold": 5,
  "ComparisonOperator": "GreaterThanThreshold"
}
```

## Compliance and Auditing

### Security Properties Validation

The system implements property-based testing to validate security requirements:

#### Property 15: Data Encryption at Rest
```python
@given(table_name=st.text(min_size=1, max_size=50))
def test_property_15_data_encryption_at_rest(self, table_name):
    """Validate all DynamoDB tables have encryption enabled"""
    template = assertions.Template.from_stack(self.core_stack)
    
    # Verify encryption is enabled
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {
            "SSEEnabled": True
        }
    })
```

#### Property 16: Secure HTTPS Communication
```python
@given(api_endpoint=st.text(min_size=1, max_size=100))
def test_property_16_secure_communication_https(self, api_endpoint):
    """Validate all API endpoints use HTTPS"""
    template = assertions.Template.from_stack(self.webhook_stack)
    
    # Verify HTTPS configuration
    template.has_resource_properties("AWS::ApiGateway::RestApi", {
        "EndpointConfiguration": {
            "Types": ["REGIONAL"]
        }
    })
```

### Audit Logging

#### CloudTrail Integration
```json
{
  "CloudTrail": {
    "IncludeGlobalServiceEvents": true,
    "IsLogging": true,
    "EnableLogFileValidation": true,
    "EventSelectors": [{
      "ReadWriteType": "All",
      "IncludeManagementEvents": true,
      "DataResources": [{
        "Type": "AWS::DynamoDB::Table",
        "Values": ["arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-*"]
      }, {
        "Type": "AWS::SecretsManager::Secret",
        "Values": ["arn:aws:secretsmanager:eu-west-1:*:secret:strava-ai-boost-*"]
      }]
    }]
  }
}
```

#### Application Audit Logs
```python
class AuditLogger:
    def log_security_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Log security-relevant events for audit trail"""
        audit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': self.get_current_user_id(),
            'source_ip': self.get_source_ip(),
            'details': details
        }
        
        # Log to CloudWatch with structured format
        logger.info("SECURITY_AUDIT", extra=audit_entry)
        
        # Store in DynamoDB for long-term retention
        self.audit_table.put_item(Item=audit_entry)
```

## Security Best Practices

### Development Security

1. **Secure Coding Practices**
   - Input validation for all user inputs
   - Output encoding to prevent XSS
   - Parameterized queries (DynamoDB operations)
   - Error handling without information disclosure

2. **Dependency Management**
   - Regular dependency updates
   - Vulnerability scanning with `pip audit`
   - Minimal dependency principle
   - Separate development and runtime dependencies

3. **Secret Management**
   - No hardcoded secrets in code
   - Environment variables for non-sensitive config
   - Secrets Manager for sensitive data
   - Regular secret rotation

### Deployment Security

1. **Infrastructure as Code**
   - All infrastructure defined in CDK
   - Version controlled security configurations
   - Automated security testing
   - Immutable infrastructure deployments

2. **Access Control**
   - Least privilege IAM roles
   - Resource-level permissions
   - Regular access reviews
   - Automated permission validation

3. **Monitoring and Alerting**
   - Real-time security monitoring
   - Automated incident response
   - Security metrics and dashboards
   - Regular security assessments

### Operational Security

1. **Incident Response**
   - Defined incident response procedures
   - Automated alerting and escalation
   - Security event correlation
   - Post-incident analysis and improvement

2. **Backup and Recovery**
   - Point-in-time recovery for DynamoDB
   - Encrypted backups
   - Regular recovery testing
   - Cross-region backup strategy

3. **Compliance Monitoring**
   - Continuous compliance validation
   - Automated security assessments
   - Regular penetration testing
   - Security audit trail maintenance

## Security Checklist

### Pre-Deployment Security Validation

- [ ] All DynamoDB tables have encryption enabled
- [ ] All API endpoints enforce HTTPS
- [ ] IAM roles follow least privilege principle
- [ ] Secrets are stored in Secrets Manager
- [ ] Input validation is implemented
- [ ] Error handling doesn't leak sensitive information
- [ ] Security monitoring is configured
- [ ] Property-based security tests pass

### Post-Deployment Security Verification

- [ ] CloudTrail logging is active
- [ ] Security alarms are configured
- [ ] Access logs are being collected
- [ ] Vulnerability scanning is scheduled
- [ ] Incident response procedures are documented
- [ ] Security metrics are being monitored
- [ ] Regular security reviews are scheduled

---