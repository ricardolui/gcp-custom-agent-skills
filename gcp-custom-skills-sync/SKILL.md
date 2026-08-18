---
name: gcp-custom-skills-sync
description: Remembers and manages the synchronization of custom agent skills with the private GitHub repository 'https://github.com/ricardolui/gcp-custom-agent-skills'. Activate this skill when the user asks to backup, save, sync, or upload new/modified skills.
---

# GCP Custom Agent Skills Sync & Backup Skill

This skill acts as an operational memory and guide for backing up, maintaining, and synchronizing all custom agent skills into the user's private GitHub repository.

---

## 🏷️ Repository Identity & Metadata

*   **Repository URL**: [gcp-custom-agent-skills](https://github.com/ricardolui/gcp-custom-agent-skills) (`https://github.com/ricardolui/gcp-custom-agent-skills.git`)
*   **Local Directory Path**: `~/.gemini/config/skills/`
*   **Git Tracking Model**: Only tracks **custom, unique, non-bundled** skills. Standard system/bundled skills are automatically ignored via `.gitignore`.

---

## 🔄 Operational Git Sync Workflows

Whenever the user or the assistant completes a modification, fix, or creation of a skill, you must execute the backup workflow to preserve the changes.

### 1. Stage and Verify Local Changes
To see what custom skills have been modified or newly created, run:
```bash
git status
```
*Note: Any new folder created inside the `~/.gemini/config/skills/` directory that is not in `.gitignore` will be automatically detected as an untracked change.*

### 2. Commit and Push Changes to GitHub Private Repo
Once changes are confirmed, stage, commit, and push them directly:
```bash
git add .
git commit -m "feat: sync and backup custom agent skills"
git push origin main
```

---

## 🆕 Creating and Adding a Brand New Skill

To introduce a new custom skill to the system and the backup:

1.  **Create a New Directory** under the skills folder:
    `mkdir -p ~/.gemini/config/skills/my-new-skill-name`
2.  **Initialize `SKILL.md`** inside the folder with proper YAML frontmatter (`name`, `description`).
3.  **Run Git Commands**: Since the `.gitignore` is pre-configured to only ignore standard bundles, Git will immediately detect the new `/my-new-skill-name/` folder. Stage, commit, and push it following the operational workflow above!
