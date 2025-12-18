---
inclusion: always
---

# Documentation Synchronization & Version Management

## 🎯 Objectif

**RÈGLE CRITIQUE** : À chaque modification de code ou documentation, TOUS les fichiers de documentation doivent être synchronisés et les versions doivent être cohérentes.

---

## 📋 Version Management

### Version Actuelle du Projet

Les versions sont gérées dans les fichiers de documentation (`docs/ARCHITECTURE.md`, `docs/HIGH-LEVEL-DESIGN.md`, `README.md`, `docs/CHANGELOG.md`), pas dans les fichiers de steering.

### Fichiers Contenant des Versions

#### **OBLIGATOIRE** - Ces fichiers DOIVENT avoir la même version :

1. **docs/ARCHITECTURE.md**
   ```markdown
   **Version:** vX.Y.Z - Production Ready with Intelligent Analysis
   **Last Updated:** YYYY-MM-DD
   ```

2. **docs/HIGH-LEVEL-DESIGN.md**
   ```markdown
   **Version:** vX.Y.Z - Production Ready
   **Last Updated:** YYYY-MM-DD
   ```

3. **docs/CHANGELOG.md**
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD - Titre Descriptif
   ```

4. **README.md** (footer)
   ```markdown
   **Current Version:** vX.Y.Z
   ```

### Semantic Versioning Rules

- **MAJOR (X.0.0)** : Breaking changes, architecture refactoring
- **MINOR (2.X.0)** : New features, new agents, new integrations
- **PATCH (2.2.X)** : Bug fixes, optimizations, documentation updates

---

## 🔄 Documentation Files to Sync

### Core Documentation Files

| File | Purpose | Update Trigger |
|------|---------|----------------|
| `README.md` | Project overview, quick start | Any significant change |
| `docs/ARCHITECTURE.md` | Technical architecture | Code changes, new services |
| `docs/HIGH-LEVEL-DESIGN.md` | Visual overview | Architecture changes |
| `docs/CHANGELOG.md` | Change history | Every commit |
| `docs/SETUP.md` | Deployment guide | Infrastructure changes |
| `docs/SECURITY.md` | Security practices | Security changes |
| `docs/testing-guide.md` | Testing procedures | Test changes |

### Cross-References to Check

When updating one file, check these cross-references:

#### **README.md References**
- Links to all docs files
- Version numbers
- Prerequisites list
- Quick start commands
- Architecture overview

#### **ARCHITECTURE.md References**
- AWS service versions
- Lambda configurations
- DynamoDB table names
- Step Functions workflow
- Performance metrics

#### **HIGH-LEVEL-DESIGN.md References**
- Architecture diagrams
- Technology stack versions
- Cost estimates
- Performance metrics
- Security configurations

---

## 🤖 Automated Sync Checklist

### When Modifying Code

#### **Lambda Functions** (`lambda_functions/*.py`)
- [ ] Update `docs/ARCHITECTURE.md` - Lambda section
- [ ] Update `docs/HIGH-LEVEL-DESIGN.md` - Compute architecture
- [ ] Update `README.md` if public API changes
- [ ] Update `docs/CHANGELOG.md` with changes
- [ ] Check timeout/memory configurations are documented

#### **CDK Stacks** (`stacks/*.py`)
- [ ] Update `docs/ARCHITECTURE.md` - Infrastructure section
- [ ] Update `docs/HIGH-LEVEL-DESIGN.md` - Architecture decisions
- [ ] Update `README.md` - Architecture overview
- [ ] Update `docs/CHANGELOG.md` with changes
- [ ] Check all AWS service configurations are documented

#### **Agents** (`src/agents/*.py`)
- [ ] Update `docs/ARCHITECTURE.md` - Campus Coach Agent section
- [ ] Update `docs/HIGH-LEVEL-DESIGN.md` - AI Agents section
- [ ] Update `README.md` - Campus Coach Agent section
- [ ] Update `docs/CHANGELOG.md` with changes
- [ ] Check agent configuration is documented

#### **Configuration Files** (`cdk.json`, `requirements.txt`)
- [ ] Update `docs/ARCHITECTURE.md` - Dependencies section
- [ ] Update `docs/HIGH-LEVEL-DESIGN.md` - Technology stack
- [ ] Update `README.md` - Dependencies section
- [ ] Update `docs/CHANGELOG.md` if significant

### When Modifying Documentation

#### **README.md Changes**
- [ ] Sync with `docs/ARCHITECTURE.md` overview
- [ ] Sync with `docs/HIGH-LEVEL-DESIGN.md` overview
- [ ] Update version numbers everywhere
- [ ] Check all links are valid
- [ ] Update "Last Updated" dates

#### **Architecture Changes**
- [ ] Sync `docs/ARCHITECTURE.md` with `docs/HIGH-LEVEL-DESIGN.md`
- [ ] Update diagrams if needed
- [ ] Update performance metrics
- [ ] Update cost estimates
- [ ] Sync version numbers

---

## 📊 Content Consistency Rules

### Performance Metrics

**MUST BE CONSISTENT** across all documentation:

```markdown
# Standard Performance Metrics Format

Webhook Processing:
- Duration: <5 seconds to queue
- Success Rate: 98% (target)
- SQS reliability: Dead letter queue for failures

Content Generation:
- Duration: <30 seconds end-to-end
- Success Rate: 98% (target)
- AgentCore Memory: <500ms lookup
- Personalization: Avoids repetitive expressions

Local Web Interface:
- Dashboard loading: <2 seconds
- Configuration changes: <1 second
- Real-time updates: WebSocket/polling

Cost per Activity:
- AgentCore Memory: $0.001
- Content generation: $0.005 (Claude API)
- Lambda executions: $0.001
- DynamoDB operations: $0.001
- Step Functions: $0.003
- Total: ~$0.02 per activity (target)
```

### Technology Stack

**MUST BE CONSISTENT** across all documentation:

```markdown
# Standard Technology Stack Format

Infrastructure:
- AWS CDK: Python constructs
- Python Runtime: 3.12
- Region: eu-west-1 (Ireland)
- AgentCore CLI: Shell script deployment

AWS Services:
- Lambda: Python 3.12 runtime
- DynamoDB: Core tables (activities, config, rate-limits, sessions)
- Step Functions: Activity processing workflow
- SQS: Message queuing with DLQ
- Bedrock: Claude Sonnet 4.5
- Secrets Manager: OAuth tokens and credentials
- API Gateway: Local interface REST API

AI/ML Framework:
- Strands Agents: Agent orchestration framework
- AgentCore Memory: Persistent personalization
- AgentCore Browser Tool: Campus Coach scraping
- Claude Sonnet 4.5: Content generation and analysis

Local Interface:
- Python Flask/FastAPI: Backend application
- AWS Cloudscape: Frontend UI components
- Real-time Dashboard: Activity processing status
```

### Prerequisites

**MUST BE CONSISTENT** across all documentation:

```markdown
# Standard Prerequisites Format

Required Services:
1. Strava Account (social fitness platform)
   - API Limits: 100 req/15min, 1000 req/day
   - OAuth application registration required
   
2. Campus Coach Account (French training platform) - Optional Module
   - Subscription required for module activation
   - Website: https://campus.coach
   
3. Enduraw Integration (third-party Strava app) - Optional Module
   - Enhanced analytics (pace without wind, weather impact)
   - Processing delay: 2-7 minutes when enabled
   
4. AWS Account
   - Cost: ~$0.02 per activity (estimated)
   - Region: eu-west-1 recommended
   - AgentCore CLI access required

Development Environment:
- Python 3.12+
- AWS CDK CLI
- AgentCore CLI
- Node.js (for CDK)
```

---

## 🔍 Validation Commands

### Check Version Consistency

```bash
# Extract all version numbers from documentation
grep -r "Version:" docs/ README.md | grep -v ".git"
grep -r "v[0-9]\+\.[0-9]\+\.[0-9]\+" docs/ README.md | grep -v ".git"

# Should all show: v2.2.1 or 2.2.1
```

### Check Cross-References

```bash
# Find all markdown links
grep -r "\[.*\](.*\.md)" docs/ README.md

# Verify all links exist
for file in $(grep -roh "\[.*\](\(docs/.*\.md\))" README.md | sed 's/.*(\(.*\))/\1/'); do
    [ -f "$file" ] && echo "✅ $file" || echo "❌ $file MISSING"
done
```

### Check Metrics Consistency

```bash
# Extract all cost mentions
grep -r "\$0\." docs/ README.md

# Extract all duration mentions  
grep -r "minutes\|seconds" docs/ README.md | grep -E "[0-9]+"

# Should all match standard metrics
```

---

## 🚀 Update Workflow

### Step 1: Identify Changes

```bash
# See what files changed
git diff --name-only HEAD

# Categorize changes
LAMBDA_CHANGES=$(git diff --name-only HEAD | grep "lambda_functions/")
STACK_CHANGES=$(git diff --name-only HEAD | grep "stacks/")
AGENT_CHANGES=$(git diff --name-only HEAD | grep "src/agents/")
DOC_CHANGES=$(git diff --name-only HEAD | grep "docs/\|README.md")
```

### Step 2: Update Documentation

Based on changes, update relevant documentation files:

#### If Lambda Functions Changed:
1. Update `docs/ARCHITECTURE.md` - Lambda section
2. Update `docs/HIGH-LEVEL-DESIGN.md` - Compute architecture
3. Update performance metrics if applicable
4. Update `docs/CHANGELOG.md`

#### If CDK Stacks Changed:
1. Update `docs/ARCHITECTURE.md` - Infrastructure
2. Update `docs/HIGH-LEVEL-DESIGN.md` - Architecture decisions
3. Update cost estimates if applicable
4. Update `docs/CHANGELOG.md`

#### If Agents Changed:
1. Update `docs/ARCHITECTURE.md` - Campus Coach Agent
2. Update `docs/HIGH-LEVEL-DESIGN.md` - AI Agents
3. Update `README.md` - Campus Coach Agent section
4. Update `docs/CHANGELOG.md`

### Step 3: Sync Versions

```bash
# Update version in all files
NEW_VERSION="X.Y.Z"  # Replace with actual version
NEW_DATE=$(date +%Y-%m-%d)

# Update ARCHITECTURE.md
sed -i "s/Version:.*$/Version: v$NEW_VERSION - Production Ready/" docs/ARCHITECTURE.md
sed -i "s/Last Updated:.*$/Last Updated: $NEW_DATE/" docs/ARCHITECTURE.md

# Update HIGH-LEVEL-DESIGN.md
sed -i "s/Version:.*$/Version: v$NEW_VERSION - Production Ready/" docs/HIGH-LEVEL-DESIGN.md
sed -i "s/Last Updated:.*$/Last Updated: $NEW_DATE/" docs/HIGH-LEVEL-DESIGN.md

# Verify CHANGELOG.md has new version entry
grep "## \[$NEW_VERSION\]" docs/CHANGELOG.md || echo "⚠️  Add version to CHANGELOG.md"
```

### Step 4: Validate Consistency

```bash
# Run validation checks
./scripts/validate-docs.sh  # Create this script

# Manual verification
echo "Check these files have consistent versions:"
echo "- docs/ARCHITECTURE.md"
echo "- docs/HIGH-LEVEL-DESIGN.md"
echo "- docs/CHANGELOG.md"
echo "- README.md"
```

---

## 📝 Documentation Update Templates

### Adding New Feature

```markdown
# In docs/CHANGELOG.md
## [X.Y.Z] - YYYY-MM-DD - Feature Name

### Added
- **Feature Name**: Description
  - Technical details
  - Performance impact
  - Cost impact

# In docs/ARCHITECTURE.md
## New Feature Section
Description of architecture...

# In docs/HIGH-LEVEL-DESIGN.md
Update relevant diagrams and architecture decisions...

# In README.md
Update overview if user-facing feature...
```

### Fixing Bug

```markdown
# In docs/CHANGELOG.md
## [X.Y.Z] - YYYY-MM-DD - Bug Fix

### Fixed
- **Component**: Description of fix
  - Symptoms observed
  - Root cause
  - Solution applied
  - Performance improvement

# Update relevant architecture docs if design changed
```

### Performance Optimization

```markdown
# In docs/CHANGELOG.md
## [X.Y.Z] - YYYY-MM-DD - Performance Optimization

### Performance
- **Component**: Optimization description
  - Before: X ms / $Y cost
  - After: A ms / $B cost
  - Improvement: Z% faster / W% cheaper

# Update ALL performance metrics in:
- docs/ARCHITECTURE.md
- docs/HIGH-LEVEL-DESIGN.md
- README.md
```

---

## ⚠️ Common Pitfalls to Avoid

### ❌ **Don't Do This**:
- Update code without updating documentation
- Change version in one file but not others
- Update metrics in one place but not everywhere
- Add new features without updating CHANGELOG
- Change architecture without updating diagrams

### ✅ **Always Do This**:
- Update ALL relevant documentation files
- Sync version numbers across ALL files
- Update performance metrics EVERYWHERE
- Add entry to CHANGELOG for every significant change
- Validate consistency before committing

---

## 🎯 Pre-Commit Checklist

Before every commit, verify:

- [ ] Version numbers are consistent across all docs
- [ ] CHANGELOG.md has entry for this change
- [ ] Performance metrics are updated everywhere
- [ ] Cross-references are valid
- [ ] "Last Updated" dates are current
- [ ] All affected documentation files are updated
- [ ] README.md reflects current state
- [ ] Architecture diagrams are up-to-date (if applicable)

---

**RAPPEL CRITIQUE** : La documentation est la source de vérité du projet. Une documentation incohérente crée de la confusion et des erreurs. Toujours synchroniser TOUS les fichiers de documentation à chaque changement significatif.

**Note** : Les versions et dates sont maintenues dans les fichiers de documentation (`docs/`), pas dans les fichiers de steering pour éviter des mises à jour trop fréquentes.