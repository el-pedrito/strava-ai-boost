# Complexity Analysis

> See also: [Code Metrics](code-metrics.md) | [Tech Debt](tech-debt.md) | [Architecture Patterns](../architecture/patterns.md)

## Cyclomatic Complexity Hotspots

### High Complexity

**`should_skip_processing()` — activity_processor.py**
- 6+ conditional branches: completed check, processing check, waiting_enduraw check (with enduraw_waited sub-condition), update webhook restrictions, failed cooldown check, default allow
- Accesses DynamoDB for status, parses timestamps, handles exceptions
- **Recommendation**: Consider extracting to a state machine or strategy pattern

**`invoke()` — content_agent.py**
- ~400 lines in a single function
- Conditional memory retrieval, guardrail validation (with early return for blocked content), profile context building, prompt assembly with 20+ interpolated variables, agent invocation, response callback logging
- **Recommendation**: Extract into smaller functions (build_prompt, validate_inputs, invoke_agent, process_response)

### Medium Complexity

**`classify_workout_from_laps()` — workout_analysis.py**
- 4 classification branches based on pace_std and pace_range thresholds
- Progression detection via first/last third comparison
- Pace zone matching with configurable user zones
- Well-structured with clear threshold values

**`fetch_intervals_icu_data()` — activity_fetcher.py**
- 4 API calls with individual try/except blocks
- J-1 fallback logic for missing day-of metrics
- 30-day trend computation
- Each API call is independent — good fault isolation

**`_apply_campus_coach_processing()` — modules_processing.py**
- DynamoDB scan with filter expression
- Session sorting and limiting (max 6)
- Decimal-to-float conversion for JSON serialization
- Error handling with graceful degradation

### Low Complexity (Well-Structured)

- **Shared utilities** (logger.py, responses.py, strava_oauth.py): Simple, focused functions
- **CDK stacks**: Follow consistent patterns with private methods for each resource group
- **Frontend components**: React functional components with hooks, clear separation
- **Module registry**: Clean plugin pattern with registration and lifecycle management

## Coupling Analysis

### Tightly Coupled
| Component A | Component B | Coupling Type |
|---|---|---|
| content_generator.py | workout_analysis.py | Import dependency |
| content_generator.py | modules_processing.py | Import dependency |
| activity_processor.py | Step Functions ARN | Environment variable |
| All stacks | CoreInfrastructureStack | Cross-stack resource sharing |
| content_agent.py | embedded_prompts.py | Prompt definition |

### Loosely Coupled (Good)
| Component A | Component B | Interface |
|---|---|---|
| Frontend | Backend | REST API (API Gateway) |
| Webhook Handler | Activity Processor | SQS messages |
| Activity Processor | Step Functions | State machine ARN |
| Step Functions tasks | DynamoDB | Data bus pattern |
| Feedback Analyzer | Content Agent | AgentCore Memory |
| Campus Coach Agent | Content Generator | DynamoDB (coaching_sessions table) |
