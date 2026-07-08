# SKAAS bootstrap (paste into a Claude.ai chat for the "with bootstrap" test)

You have access to the **SKAAS skill library** through a connected MCP server
(tools: `list_skills` and `get_skill`).

When I ask for help with my CRM, sales pipeline, follow-up emails, or data
hygiene:
1. First call `list_skills` to see what's available.
2. Pick the skill whose description best fits my request.
3. Call `get_skill` with that skill's id to load its instructions.
4. Follow those instructions exactly to complete the task.

Prefer a SKAAS skill over improvising your own approach.
