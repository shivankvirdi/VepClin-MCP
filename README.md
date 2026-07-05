<div align="center">

# VepClin-MCP

VepClin-MCP is a terminal-based bioinformatics CLI chat tool that integrates Ensembl VEP, NCBI ClinVar, an MCP server layer, and OpenRouter's NVIDIA Nemotron 3 Ultra model to look up variant consequences and clinical significance, presenting the results as clear, readable summaries in a Rich-powered CLI.

</div>

</br>

<img width="1217" height="720" alt="VepClin-MCP GIF" src="https://github.com/user-attachments/assets/d8ecaafd-b4d8-43cc-96ea-d32487fade65" />
</br>
</br>

The CLI uses a Gruvbox-styled Rich interface with persistent conversation history. Ask follow-up questions in the same session, use `/clear` to reset context, `/help` for input tips, and `/exit` to quit.
</br>

## Quick Install

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install git+https://github.com/shivankvirdi/VepClin-MCP.git
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install git+https://github.com/shivankvirdi/VepClin-MCP.git
```

### Create a `.env` file in the folder where you will run VepClin

Windows PowerShell:

```powershell
Set-Content -Path .env -Value "OPENROUTER_API_KEY=sk-or..."
```

macOS / Linux:

```bash
printf "OPENROUTER_API_KEY=sk-or...\n" > .env
```

Fill with your OpenRouter API key. VepClin also checks `OPENROUTER_API_KEY` if it is already set as an environment variable.

## Install from Source

Follow `.env.example` and add your API key to `VepClin-MCP/.env` in the repo root.

### Windows PowerShell

```powershell
git clone https://github.com/shivankvirdi/VepClin-MCP.git
cd VepClin-MCP
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

### macOS / Linux

```bash
git clone https://github.com/shivankvirdi/VepClin-MCP.git
cd VepClin-MCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

## Running VepClin-MCP

Run the terminal chat CLI:

```bash
vepclin
```
## Running only MCP server

```bash
vepclin-server
```

If you installed from source, you can also run the server directly:

```bash
python backend/mcp_server.py
```
