# Reviewers for Chakshu

Each folder under `reviewers/` is one team's reviewer. Chakshu reads this repo from its default branch and picks up changes as soon as they merge.

```text
reviewers/<team-or-product>/
  reviewer.yaml        who owns it, which repos and paths it covers, model, limits
  RULES.md             your team's conventions, in plain language
  skills/<skill>/
    SKILL.md           what to check, with a name and description at the top
    ...                checklists, examples, anything the skill can refer to
shared/skills/<skill>/ skills any reviewer can include as shared/<skill>
```

## Adding a reviewer for your team

1. Copy `reviewers/default` to `reviewers/<your-team>`.
2. Edit `reviewer.yaml`: set `name`, `owner_team` (your GitHub team slug), `repos` and, if you want, `paths`.
3. Write skills for the things your team cares about. Short and specific beats long and general.
4. Add your folder to `CODEOWNERS` so your team reviews changes to it.
5. Open a pull request.

People on your team then comment `@<org>/chakshu` on a pull request and Chakshu runs your reviewer.

Full reference: https://chakshu.havelin.in/docs/concepts/reviewers/
