import pytest
from mcp_server import mcp
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport

@pytest.fixture
async def main_mcp_client():
    async with Client(transport=mcp) as mcp_client:
        yield mcp_client

async def test_get_vep_consequence(main_mcp_client: Client[FastMCPTransport]):
    result = await main_mcp_client.call_tool(
        name="get_vep_consequence",
        arguments={"variant": "chr7:g.140753336A>T"}
    )

    assert result.data is not None
    assert result.data["gene_symbol"] == "BRAF"
    assert result.data["consequence"] == "missense_variant"
    assert result.data["protein_change"] == "p.Val600Glu"
    assert result.data["protein_change_short"] == "V600E"

async def test_get_clinvar_summary(main_mcp_client: Client[FastMCPTransport]):
    result = await main_mcp_client.call_tool(
        name="get_clinvar_summary",
        arguments={"gene_symbol": "BRAF", "protein_change_short": "V600E"}
    )

    assert result.data is not None
    assert result.data["found"] is True
    assert len(result.data["matches"]) >= 1

    match = result.data["matches"][0]
    assert match["variation_id"] == "13961"
    assert "BRAF" in match["title"]
    assert isinstance(match["oncogenicity_traits"], list)
    assert "Neoplasm" in match["oncogenicity_traits"]
    assert isinstance(match["clinical_impact_traits"], list)
    assert "Melanoma" in match["clinical_impact_traits"]