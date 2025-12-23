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

1. **README.md** (project homepage)
   ```markdown
   **Version:** vX.Y.Z
   **Status:** In Development - Description
   ```

2. **docs/README.md** (documentation hub)
   ```markdown
   **Version:** vX.Y.Z
   **Status:** In Development - Description
   ```

3. **docs/reference/ARCHITECTURE.md**
   ```markdown
   **Version:** vX.Y.Z - Production Ready with Intelligent Analysis
   **Last Updated:** YYYY-MM-DD
   ```

4. **docs/reference/CHANGELOG.md**
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD - Titre Descriptif
   ```

5. **docs/advanced/TESTING.md**
   ```markdown
   **Version:** vX.Y.Z - Documentation Restructure Complete
   **Last Updated:** YYYY-MM-DD
   ```

6. **docs/advanced/PERFORMANCE.md**
   ```markdown
   **Version:** vX.Y.Z - Production Ready
   **Last Updated:** YYYY-MM-DD
   ```

7. **docs/advanced/SECURITY.md**
   ```markdown
   **Version:** vX.Y.Z - Production Ready
   **Last Updated:** YYYY-MM-DD
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
| `README.md` | Project homepage, quick links | Any significant change |
| `docs/README.md` | Documentation hub, navigation | Structure changes |
| `docs/reference/ARCHITECTURE.md` | Technical architecture, diagrams | Code changes, new services |
| `docs/reference/CHANGELOG.md` | Change history | Every commit |
| `docs/getting-started/QUICK-START.md` | 5-minute deployment | Infrastructure changes |
| `docs/getting-started/COMPLETE-SETUP.md` | Full deployment guide | Infrastructure changes |
| `docs/getting-started/FIRST-STEPS.md` | First activity guide | Usage flow changes |
| `docs/user-guide/DASHBOARD.md` | Local interface guide | UI changes |
| `docs/user-guide/CONFIGURATION.md` | OAuth and module setup | Configuration changes |
| `docs/user-guide/TROUBLESHOOTING.md` | Common issues | Bug fixes, new issues |
| `docs/advanced/AGENTCORE.md` | AI agents and memory | AgentCore changes |
| `docs/advanced/PERFORMANCE.md` | Monitoring and tuning | Performance changes |
| `docs/advanced/SECURITY.md` | Security practices | Security changes |
| `docs/advanced/TESTING.md` | Testing procedures | Test changes |
| `docs/reference/KNOWN-ISSUES.md` | Current issues | Bug reports, fixes |

### Cross-References to Check

When updating one file, check these cross-references:

#### **README.md References (Project Homepage)**
- Links to docs/README.md (documentation hub)
- Quick links to QUICK-START.md, FIRST-STEPS.md, TROUBLESHOOTING.md
- Version numbers and status
- Architecture diagrams (Mermaid)
- Technology stack overview

#### **docs/README.md References (Documentation Hub)**
- Links to all documentation files in subdirectories
- Navigation structure consistency
- "Choose Your Path" user journey links
- Cross-references between guides

#### **docs/reference/ARCHITECTURE.md References**
- AWS service versions and configurations
- Lambda configurations and timeouts
- DynamoDB table names and GSI configurations
- Step Functions workflow diagrams
- Performance metrics and cost estimates
- Mermaid diagrams for system architecture

#### **docs/getting-started/ References**
- Cross-references between QUICK-START → FIRST-STEPS → COMPLETE-SETUP
- Links to CONFIGURATION.md and TROUBLESHOOTING.md
- AWS profile references (your-aws-profile)
- Deployment script references

#### **docs/user-guide/ References**
- Links between DASHBOARD.md ↔ CONFIGURATION.md ↔ TROUBLESHOOTING.md
- References to getting-started guides
- Links to advanced topics when relevant

#### **docs/advanced/ References**
- Cross-references between AGENTCORE.md, PERFORMANCE.md, SECURITY.md, TESTING.md
- Links back to user guides and getting started
- References to ARCHITECTURE.md for technical details

#### **docs/reference/ References**
- CHANGELOG.md version consistency with other files
- KNOWN-ISSUES.md links to TROUBLESHOOTING.md
- ARCHITECTURE.md technical cross-references

---

## 🤖 Automated Sync Checklist

### When Modifying Code

#### **Getting Started Guides** (`docs/getting-started/*.md`)
- [ ] Update `README.md` - Quick links section if public flow changes
- [ ] Update `docs/README.md` - Getting started navigation
- [ ] Update cross-references between QUICK-START → FIRST-STEPS → COMPLETE-SETUP
- [ ] Update `docs/reference/CHANGELOG.md` with changes
- [ ] Check AWS profile references (your-aws-profile) are consistent
- [ ] Verify deployment script references are accurate

#### **User Guide Updates** (`docs/user-guide/*.md`)
- [ ] Update `docs/README.md` - User guide navigation
- [ ] Update cross-references between DASHBOARD ↔ CONFIGURATION ↔ TROUBLESHOOTING
- [ ] Update `docs/reference/CHANGELOG.md` with changes
- [ ] Check links to getting-started and advanced sections
- [ ] Verify OAuth flow documentation consistency

#### **Advanced Topics** (`docs/advanced/*.md`)
- [ ] Update `docs/README.md` - Advanced topics navigation
- [ ] Update `docs/reference/ARCHITECTURE.md` - Technical details section
- [ ] Update cross-references between AGENTCORE, PERFORMANCE, SECURITY, TESTING
- [ ] Update `docs/reference/CHANGELOG.md` with changes
- [ ] Check agent configuration documentation consistency

#### **Reference Documentation** (`docs/reference/*.md`)
- [ ] Update `docs/README.md` - Reference navigation
- [ ] Update cross-references to technical documentation
- [ ] Update `docs/reference/CHANGELOG.md` with changes
- [ ] Sync version numbers across all reference files
- [ ] Update Mermaid diagrams if architecture changes

### When Modifying Documentation

#### **README.md Changes (Project Homepage)**
- [ ] Sync with `docs/README.md` navigation structure
- [ ] Update version numbers everywhere
- [ ] Check all quick links are valid
- [ ] Update "Last Updated" dates
- [ ] Verify Mermaid diagrams are current
- [ ] Update technology stack overview

#### **docs/README.md Changes (Documentation Hub)**
- [ ] Sync navigation with actual file structure
- [ ] Update all cross-references to documentation files
- [ ] Verify "Choose Your Path" links work
- [ ] Update version numbers
- [ ] Check all subdirectory links are valid

#### **Architecture Changes**
- [ ] Sync `docs/reference/ARCHITECTURE.md` with system changes
- [ ] Update Mermaid diagrams if needed
- [ ] Update performance metrics
- [ ] Update cost estimates
- [ ] Sync version numbers
- [ ] Update AWS service configurations

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
1. Update `docs/reference/ARCHITECTURE.md` - Lambda section
2. Update `README.md` - Architecture diagrams if needed
3. Update performance metrics if applicable
4. Update `docs/reference/CHANGELOG.md`

#### If CDK Stacks Changed:
1. Update `docs/reference/ARCHITECTURE.md` - Infrastructure section
2. Update `README.md` - Architecture diagrams
3. Update cost estimates if applicable
4. Update `docs/reference/CHANGELOG.md`

#### If Agents Changed:
1. Update `docs/advanced/AGENTCORE.md` - Agent configuration
2. Update `docs/reference/ARCHITECTURE.md` - AI services section
3. Update `README.md` - AI services overview
4. Update `docs/reference/CHANGELOG.md`

#### If Documentation Structure Changed:
1. Update `docs/README.md` - Navigation structure
2. Update `README.md` - Quick links
3. Update all cross-references in affected files
4. Update `docs/reference/CHANGELOG.md`

### Step 3: Sync Versions

```bash
# Update version in all files
NEW_VERSION="X.Y.Z"  # Replace with actual version
NEW_DATE=$(date +%Y-%m-%d)

# Update ARCHITECTURE.md
sed -i "s/Version:.*$/Version: v$NEW_VERSION - Production Ready/" docs/reference/ARCHITECTURE.md
sed -i "s/Last Updated:.*$/Last Updated: $NEW_DATE/" docs/reference/ARCHITECTURE.md

# Update README.md
sed -i "s/Version:.*$/Version: v$NEW_VERSION/" README.md

# Update docs/README.md
sed -i "s/Version:.*$/Version: v$NEW_VERSION/" docs/README.md

# Verify CHANGELOG.md has new version entry
grep "## \[$NEW_VERSION\]" docs/reference/CHANGELOG.md || echo "⚠️  Add version to CHANGELOG.md"
```

### Step 4: Validate Consistency

```bash
# Run validation checks
./scripts/validate-docs.sh  # Create this script

# Manual verification
echo "Check these files have consistent versions:"
echo "- README.md"
echo "- docs/README.md"
echo "- docs/reference/ARCHITECTURE.md"
echo "- docs/reference/CHANGELOG.md"
echo "- docs/advanced/TESTING.md"
echo "- docs/advanced/PERFORMANCE.md"
echo "- docs/advanced/SECURITY.md"
```

---

## 📝 Documentation Update Templates

### Adding New Feature

```markdown
# In docs/reference/CHANGELOG.md
## [X.Y.Z] - YYYY-MM-DD - Feature Name

### Added
- **Feature Name**: Description
  - Technical details
  - Performance impact
  - Cost impact

# In docs/reference/ARCHITECTURE.md
## New Feature Section
Description of architecture...
Update Mermaid diagrams if needed...

# In README.md
Update architecture diagrams if user-facing feature...

# In docs/README.md
Update navigation if new documentation added...
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
- docs/reference/ARCHITECTURE.md
- README.md
- docs/README.md (if mentioned)
- docs/advanced/PERFORMANCE.md
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
- [ ] docs/README.md navigation is up-to-date
- [ ] Mermaid diagrams are current (if applicable)

---

**RAPPEL CRITIQUE** : La documentation est la source de vérité du projet. Une documentation incohérente crée de la confusion et des erreurs. Toujours synchroniser TOUS les fichiers de documentation à chaque changement significatif.

**Note** : Les versions et dates sont maintenues dans les fichiers de documentation (`docs/`), pas dans les fichiers de steering pour éviter des mises à jour trop fréquentes.