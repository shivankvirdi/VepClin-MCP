VepClin-MCP is a terminal-based bioinformatics CLI chat tool that integrates Ensembl VEP, NCBI ClinVar, an MCP server layer, and OpenRouter's NVIDIA Nemotron 3 Ultra model to look up variant consequences and clinical significance, presenting the results as clear, readable summaries in a Rich-powered CLI.


https://github.com/user-attachments/assets/1f1c3a2e-a605-4a85-a8f4-58bf5e1e59e2


The CLI uses a Gruvbox-styled Rich interface with persistent conversation history. Ask follow-up questions in the same session, use `/clear` to reset context, `/help` for input tips, and `/exit` to quit.

## Quick Install
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install git+https://github.com/shivankvirdi/VepClin-MCP.git
```
### Create a `.env` file in the folder where you will run VepClin
```powershell
OPENROUTER_API_KEY=sk-or...
# Fill with your API key (see .env.example)
```
## Install from Source
Follow `.env.example` & add API key to `VepClin-MCP/.env` (repo root)
```powershell
git clone https://github.com/shivankvirdi/VepClin-MCP.git
cd VepClin-MCP
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```
## Running VepClin-MCP
Run the terminal chat CLI:
```powershell
vepclin
```
Run the MCP server directly:
```powershell
python backend\mcp_server.py
```
