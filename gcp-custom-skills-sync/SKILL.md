---
name: gcp-custom-skills-sync
description: Remembers and manages the synchronization of custom agent skills with the private GitHub repository 'https://github.com/ricardolui/gcp-custom-agent-skills'. Activate this skill when the user asks to backup, save, sync, or upload new/modified skills.
---

# GCP Custom Agent Skills Sync & Backup Skill

This skill acts as an operational memory and guide for backing up, maintaining, and synchronizing all custom agent skills into the user's private GitHub repository.

---

## 🏷️ Repository Identity & Metadata

*   **Repository URL**: [gcp-custom-agent-skills](https://github.com/ricardolui/gcp-custom-agent-skills) (`https://github.com/ricardolui/gcp-custom-agent-skills.git`)
*   **Active Skills Directory**: `/usr/local/google/home/gricardo/.gemini/config/skills/`
*   **Local Git Clone Path**: `/usr/local/google/home/gricardo/gcp-custom-agent-skills/`
*   **Git Tracking Model**: Only tracks **custom, unique, non-bundled** skills. Standard system/bundled symlinks are automatically ignored.

---

## 🔄 Operational Git Sync Workflows

Whenever the user or the assistant completes a modification, fix, or creation of a custom skill in `/usr/local/google/home/gricardo/.gemini/config/skills/`, execute the backup workflow to mirror and push the changes to GitHub.

### 1. Mirror Custom Skills to Git Repository
Copy non-symlinked custom skill directories into the local git clone:
```bash
rsync -av --exclude='.*' /usr/local/google/home/gricardo/.gemini/config/skills/blip-pubsub-eventhub-migration /usr/local/google/home/gricardo/gcp-custom-agent-skills/
rsync -av --exclude='.*' /usr/local/google/home/gricardo/.gemini/config/skills/gcp-custom-skills-sync /usr/local/google/home/gricardo/gcp-custom-agent-skills/
```

### 2. Stage, Commit, and Push Changes to GitHub Private Repo
```bash
cd /usr/local/google/home/gricardo/gcp-custom-agent-skills
git status
git add .
git commit -m "feat: sync and backup custom agent skills"
git push origin main
```

---

## 🆕 Creating and Adding a Brand New Skill

To introduce a new custom skill to the system and the backup:

1.  **Create a New Directory** under the active skills folder:
    `mkdir -p /usr/local/google/home/gricardo/.gemini/config/skills/my-new-skill-name`
2.  **Initialize `SKILL.md`** inside the folder with proper YAML frontmatter (`name`, `description`).
3.  **Sync to Git Repository**: Mirror to `/usr/local/google/home/gricardo/gcp-custom-agent-skills/`, stage, commit, and push following the workflow above.
