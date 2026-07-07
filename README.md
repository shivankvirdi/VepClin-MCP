<div align="center">
<img width="25%" height="20%" alt="Untitled design" src="./assets/vepclin-mascot.png" />  
<br/><sub><code>Exon the Axolotl</code></sub>
<br/>
  
# VepClin-MCP

VepClin-MCP is a terminal-based bioinformatics CLI chat tool that integrates Ensembl VEP, NCBI ClinVar, an MCP server layer, and OpenRouter's NVIDIA Nemotron 3 Ultra model to look up variant consequences and clinical significance, presenting the results as clear, readable summaries in a Rich-powered CLI.

</div>

</br>
<img width="1217" height="720" alt="vepclin-mcpdemogif" src="https://github.com/user-attachments/assets/26057d12-e124-44c0-9d05-1a1a55ed9c8b" />
</br>
</br>


## Features
- NVIDIA Nemotron 3 Ultra powered chat interface
- Ensembl VEP integration for genomic and transcript-qualified HGVS variant consequence lookup
- ClinVar integration for clinical significance, oncogenicity, review status, traits, & variation IDs
- `/batch`: Upload VCF files & summarize multiple variants
- `/export`: Save latest batch results as CSV, TSV, VCF, or Excel .xlsx
- `/report`: Save single-variant lookup as a PDF report
- `/build`: Switch between GRCh38 and GRCh37 lookups
- `/transcripts`: Choose MANE Select-only results or all transcript consequences
- Gruvbox-styled Rich terminal interface with readable panels, tables, & status messages
- MCP server layer exposing custom reusable variant annotation tools

## Technologies Used
- CLI/UI: `Python`, `Rich`, `Questionary`
- MCP Layer: `FastMCP`
- HTTP/API Client: `httpx`
- AI: OpenRouter API, NVIDIA Nemotron 3 Ultra
- Variant Annotation: Ensembl VEP REST API
- Clinical Data: `NCBI ClinVar` via `Biopython Entrez`
- Excel/PDF Export: `openpyxl`, `ReportLab`
- Storage: Local `config.json` file for session preferences
- Packaging: `setuptools`, `pyproject.toml`
- Testing: `pytest`, `FastMCP` test client

## Quick Install

#### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install git+https://github.com/shivankvirdi/VepClin-MCP.git
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install git+https://github.com/shivankvirdi/VepClin-MCP.git
```

### Set `OPENROUTER_API_KEY` as an environment variable
Fill with your api key from https://openrouter.ai/  
#### Windows PowerShell:

```powershell
[Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", "sk-or...", "User")
```

#### macOS / Linux:

```bash
# Bash
echo 'export OPENROUTER_API_KEY="sk-or..."' >> ~/.zshrc
source ~/.zshrc
```
```zsh
# Zsh
echo 'export OPENROUTER_API_KEY="sk-or..."' >> ~/.bashrc
source ~/.bashrc
```

## Install from Source

#### Windows PowerShell

```powershell
git clone https://github.com/shivankvirdi/VepClin-MCP.git
cd VepClin-MCP
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

#### macOS / Linux

```bash
git clone https://github.com/shivankvirdi/VepClin-MCP.git
cd VepClin-MCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Follow `.env.example` and add your API key to `VepClin-MCP/.env` in the repo root.

## Running VepClin-MCP

Run the terminal chat CLI:

```powershell
vepclin
```
## Running only MCP server
Most users don't need this. The `vepclin` chat CLI starts and uses the MCP tools automatically.
```powershell
vepclin-server
```

If you installed from source, you can also run the server directly:

```bash
python backend/mcp_server.py
```
