---
inclusion: always
---

# Changelog Management

## Obligation de Mise à Jour du CHANGELOG

**RÈGLE CRITIQUE** : À chaque commit significatif, le fichier `docs/CHANGELOG.md` DOIT être mis à jour.

## Quand Mettre à Jour le CHANGELOG

### ✅ **Commits qui NÉCESSITENT une mise à jour** :
- **Nouvelles fonctionnalités** (agents, Lambda, intégrations)
- **Corrections de bugs** (Step Functions, matching, génération)
- **Optimisations de performance** (réduction d'exécutions, timeouts)
- **Changements d'architecture** (nouvelles tables, stacks, workflows)
- **Améliorations de sécurité** (IAM, encryption, secrets)
- **Modifications de configuration** (CDK, agents, API)
- **Déploiements en production** (nouvelles versions)

### ❌ **Commits qui n'en ont PAS besoin** :
- Corrections de typos dans la documentation
- Reformatage de code sans changement fonctionnel
- Mise à jour de commentaires uniquement
- Changements de .gitignore ou fichiers de config IDE

## Format du CHANGELOG

### Structure Obligatoire

```markdown
## [X.Y.Z] - YYYY-MM-DD - Titre Descriptif

### Added
- **Nouvelle fonctionnalité** : Description détaillée
  - Impact technique
  - Bénéfices utilisateur

### Changed
- **Modification existante** : Description du changement
  - Raison du changement
  - Impact sur le système

### Fixed
- **Correction de bug** : Description du problème résolu
  - Symptômes observés
  - Solution appliquée

### Performance
- **Optimisation** : Métriques avant/après
  - Temps d'exécution
  - Coût AWS
  - Taux de succès
```

### Exemples Concrets

#### ✅ **Bon exemple** :
```markdown
## [0.1.0] - 2025-12-18 - Initial Strava AI Boost Implementation

### Added
- **Local Web Interface**: Python Flask application with AWS Cloudscape components
  - Configuration interface for Strava OAuth and module management
  - Real-time dashboard with activity processing statistics
  - Module activation/deactivation interface

### Added
- **AgentCore Memory Integration**: Personalized content generation agent
  - Persistent user style learning and expression tracking
  - Avoids repetitive phrases across activities
  - Adapts tone based on user preferences and history

### Added
- **Campus Coach Module**: AgentCore Browser Tool integration
  - Automated session extraction via browser automation
  - Intelligent session matching with confidence scoring
  - Performance comparison analysis (actual vs planned)
```

#### ❌ **Mauvais exemple** :
```markdown
## [2.2.1] - 2025-12-17

### Fixed
- Fixed some issues
- Updated code
```

## Processus de Commit

### 1. **Avant le Commit**
```bash
# Vérifier si le CHANGELOG doit être mis à jour
git diff --name-only HEAD~1 HEAD

# Si des fichiers critiques sont modifiés :
# - stacks/*.py
# - lambda_functions/*.py
# - src/agents/*.py
# - Alors OBLIGATOIREMENT mettre à jour docs/CHANGELOG.md
```

### 2. **Mise à Jour du CHANGELOG**
- Ouvrir `docs/CHANGELOG.md`
- Ajouter une nouvelle section en haut (après le titre)
- Utiliser le format standardisé
- Inclure les métriques de performance si applicable
- Mentionner les fichiers modifiés

### 3. **Message de Commit**
```bash
# Format recommandé :
git commit -m "feat: description courte

- Détail 1
- Détail 2

Updated CHANGELOG.md with performance metrics"
```

## Métriques à Inclure

### Performance AWS
- **Temps d'exécution** : avant/après
- **Coût par activité** : estimation
- **Taux de succès** : pourcentage
- **Latence** : end-to-end timing

### Exemples de Métriques
```markdown
### Performance Impact
- Webhook processing: <5s to queue
- Content generation: <30s end-to-end
- Dashboard loading: <2s
- AgentCore Memory lookup: <500ms
- Cost per activity: ~$0.02 (target)
```

## Validation Automatique

### Checklist Avant Commit
- [ ] Le CHANGELOG.md a-t-il été mis à jour ?
- [ ] La version suit-elle le semantic versioning ?
- [ ] Les métriques de performance sont-elles incluses ?
- [ ] La description est-elle claire et technique ?
- [ ] Les fichiers modifiés sont-ils mentionnés ?

### Script de Validation (Recommandé)
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Vérifier si des fichiers critiques sont modifiés
CRITICAL_FILES=$(git diff --cached --name-only | grep -E "(stacks/|lambda_functions/|src/agents/)")

if [ ! -z "$CRITICAL_FILES" ]; then
    # Vérifier si CHANGELOG.md est aussi modifié
    CHANGELOG_MODIFIED=$(git diff --cached --name-only | grep "docs/CHANGELOG.md")
    
    if [ -z "$CHANGELOG_MODIFIED" ]; then
        echo "❌ ERREUR: Fichiers critiques modifiés mais CHANGELOG.md non mis à jour"
        echo "Fichiers modifiés: $CRITICAL_FILES"
        echo "Veuillez mettre à jour docs/CHANGELOG.md avant de commiter"
        exit 1
    fi
fi
```

## Responsabilités

### Développeur
- **OBLIGATOIRE** : Mettre à jour le CHANGELOG pour tout changement fonctionnel
- Inclure les métriques de performance quand disponibles
- Utiliser un langage technique précis
- Mentionner l'impact sur les utilisateurs/système

### Reviewer
- Vérifier que le CHANGELOG a été mis à jour
- Valider la qualité des descriptions
- S'assurer que les métriques sont cohérentes
- Confirmer le respect du format

## Exemples de Sections par Type

### Agents AI
```markdown
### Added
- **Content Generation Agent**: Strands Agent with AgentCore Memory
  - Personal style learning and expression tracking
  - Memory-based content personalization
  - Avoids repetitive phrases across activities
```

### AgentCore Integration
```markdown
### Added
- **Campus Coach Browser Agent**: AgentCore Browser Tool deployment
  - Automated session extraction via CLI scripts
  - Browser automation for Campus Coach scraping
  - Secure credential management via Secrets Manager
```

### Local Interface
```markdown
### Added
- **Python Web Interface**: Flask application with Cloudscape UI
  - Real-time activity processing dashboard
  - Module configuration and management
  - OAuth flow integration for Strava connection
```

## Outils Recommandés

### Génération Automatique
```bash
# Générer un template de CHANGELOG
git log --oneline --since="1 week ago" | head -10

# Voir les fichiers modifiés récemment
git diff --name-only HEAD~5 HEAD
```

### Validation
```bash
# Vérifier le format du CHANGELOG
grep -E "^## \[[0-9]+\.[0-9]+\.[0-9]+\]" docs/CHANGELOG.md

# Compter les entrées récentes
head -50 docs/CHANGELOG.md | grep -c "^##"
```

---

**RAPPEL CRITIQUE** : Le CHANGELOG est la mémoire du projet. Une mise à jour rigoureuse permet :
- **Traçabilité** des changements
- **Debug** efficace des régressions  
- **Communication** claire avec l'équipe
- **Déploiements** sereins en production

**Aucun commit significatif ne doit être fait sans mise à jour du CHANGELOG.**