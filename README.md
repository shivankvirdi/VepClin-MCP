VepClin-MCP is a terminal-based bioinformatics chat tool that integrates Ensembl VEP, NCBI ClinVar, an MCP server layer, and OpenRouter's NVIDIA Nemotron 3 Ultra model.

The CLI uses a Gruvbox-styled Rich interface with persistent conversation history. Ask follow-up questions in the same session, use `/clear` to reset context, `/help` for input tips, and `/exit` to quit.

Run the chat UI:

```powershell
vepclin
```

Run the MCP server directly:

```powershell
python backend\mcp_server.py
```
