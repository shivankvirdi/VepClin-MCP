from fastmcp import FastMCP
from variant_client import VariantClient

mcp = FastMCP("vepclin-mcp")
client = VariantClient()

@mcp.tool()
def get_vep_consequence(variant: str) -> dict:
    """Look up the biological effect of a genetic variant given in HGVS genomic notation,
    (e.g. "chr7:g.140753336A>T"). Use this when a user asks what a specific DNA variant does.

    Returns a dict with:
    - gene_symbol: the affected gene (e.g. "BRAF")
    - consequence: the molecular consequence type (e.g. "missense_variant")
    - protein_change: the amino acid change in HGVS protein notation (e.g. "p.Val600Glu")
    ("None" if not applicable, like for synonymous variants)
    - protein_change_short: the same change in short form, (e.g. "V600E" — use this exact
    value when calling get_clinvar_summary)
    """
    return client.get_vep_consequence(variant)

@mcp.tool()
def get_clinvar_summary(gene_symbol: str, protein_change_short: str) -> dict:
    """Look up clinical significance and associated diseases for a genetic variant in ClinVar,
    given its gene symbol and short-form protein change (e.g. "BRAF", "V600E"). Call get_vep_consequence 
    first and pass its gene_symbol and protein_change_short values as arguments here — not protein_change 
    (the p.Val600Glu-style HGVS format), which will not match.
    
    Returns a dict with:
    - found: True if results are found or False
    - matches: List filled with dict of classifications and traits:
        - "variation_id": Clinvar variation ID
        - "title": Variant title (e.g. 'NM_004333.6(BRAF):c.1799T>A (p.Val600Glu)')
        - "germline_classification": (e.g. 'Conflicting classifications of pathogenicity')
        - "germline_traits": (e.g. ['Cardiovascular phenotype', 'Vascular malformation', 'RASopathy'])
        - "clinical_impact_classification": How clinically impactful (e.g. 'Tier I - Strong')
        - "clinical_impact_traits": (e.g. ['Ganglioglioma', 'Malignant glioma', 'Dysembryoplastic neuroepithelial tumor'])
        - "oncogenicity_classification": Tendency to cause tumors/cancer (e.g. 'Oncogenic')
        - "oncogenicity_traits": (e.g. ['Neoplasm'])
    If found is False, function returns {"found": False, "matches": []}
        """
    return client.get_clinvar_summary(gene_symbol, protein_change_short)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8080)