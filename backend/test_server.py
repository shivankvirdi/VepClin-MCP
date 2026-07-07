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

    # SIFT / PolyPhen / impact enrichment
    assert result.data["impact"] == "MODERATE"
    assert result.data["sift_prediction"] == "deleterious_low_confidence"
    assert result.data["sift_score"] == 0
    assert result.data["polyphen_prediction"] == "probably_damaging"
    assert result.data["polyphen_score"] == pytest.approx(0.935, abs=0.01)

async def test_get_vep_consequence_unsupported_format(main_mcp_client: Client[FastMCPTransport]):
    """Input that doesn't match HGVS shape at all — caught by local validation
    before any request reaches Ensembl."""
    result = await main_mcp_client.call_tool(
        name="get_vep_consequence",
        arguments={"variant": "not_a_real_variant"}
    )

    assert result.data is not None
    assert result.data["error"] == "unsupported_hgvs"
    assert "message" in result.data

async def test_get_vep_consequence_invalid_variant(main_mcp_client: Client[FastMCPTransport]):
    """Well-formed HGVS syntax, but a position Ensembl itself rejects as invalid."""
    result = await main_mcp_client.call_tool(
        name="get_vep_consequence",
        arguments={"variant": "chr7:g.999999999999A>T"}
    )

    assert result.data is not None
    assert result.data["error"] == "invalid_variant"
    assert "message" in result.data

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

    # review_status / last_evaluated enrichment
    assert match["germline_classification"] == "Conflicting classifications of pathogenicity"
    assert match["germline_review_status"] == "criteria provided, conflicting classifications"
    assert match["germline_last_evaluated"] is not None

async def test_get_clinvar_summary_not_found(main_mcp_client: Client[FastMCPTransport]):
    result = await main_mcp_client.call_tool(
        name="get_clinvar_summary",
        arguments={"gene_symbol": "NOTAREALGENE", "protein_change_short": "Z999Z"}
    )

    assert result.data is not None
    assert result.data["found"] is False
    assert result.data["matches"] == []