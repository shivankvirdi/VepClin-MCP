import httpx
import time
from Bio import Entrez
Entrez.email = "shivank.virdi@gmail.com"

class VariantClient:
    AA_CODES = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
    "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
    "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
    "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
}
    
    def __init__(self, timeout=20.0):
        self.timeout = timeout

    def get_vep_consequence(self, variant: str) -> dict:
        url = f"https://rest.ensembl.org/vep/human/hgvs/{variant}"

        response = httpx.get(
            url,
            params={"content-type": "application/json", "pick": 1},
            headers={"Accept": "application/json"},
            timeout=self.timeout
        )

        response.raise_for_status()
        data = response.json()
        result = data[0]

        transcripts = result.get("transcript_consequences", [])
        t = transcripts[0] if transcripts else {}

        gene_symbol = t.get("gene_symbol")
        consequence = result.get("most_severe_consequence")
        amino_acids = t.get("amino_acids")
        protein_start = t.get("protein_start")

        protein_change = None
        protein_change_short = None

        if consequence != "synonymous_variant" and amino_acids and "/" in amino_acids:
            ref_aa, alt_aa = amino_acids.split("/")
            protein_change_short = f"{ref_aa}{protein_start}{alt_aa}"  # "V600E"
            if ref_aa in self.AA_CODES and alt_aa in self.AA_CODES:
                protein_change = f"p.{self.AA_CODES[ref_aa]}{protein_start}{self.AA_CODES[alt_aa]}"

        return {
            "gene_symbol": gene_symbol,
            "consequence": consequence,
            "protein_change": protein_change,
            "protein_change_short" : protein_change_short,
        }
    
    def extract_trait_names(self, classification: dict) -> list:
            trait_set = classification.get("trait_set", [])
            names = []
            for trait in trait_set:
                names.append(trait.get("trait_name"))
            return names

    def get_clinvar_summary(self, gene_symbol: str, protein_change_short: str) -> dict:
        term = f"{gene_symbol}[gene] AND {protein_change_short}[Variant Name]"
        search_handle = Entrez.esearch(db="clinvar", term=term)
        search_record = Entrez.read(search_handle)

        id_list = search_record.get("IdList", [])
        if not id_list:
            return {"found": False, "matches": []}
        
        summary_handle = Entrez.esummary(db="clinvar", id=",".join(id_list))
        summary = Entrez.read(summary_handle, validate=False)
        records = summary["DocumentSummarySet"]["DocumentSummary"]

        matches=[]
        for record in records:
            matches.append({
                "variation_id": record.attributes.get("uid"),
                "title": record.get("title"),
                "germline_classification": record.get("germline_classification", {}).get("description"),
                "germline_traits": self.extract_trait_names(record.get("germline_classification", {})),
                "clinical_impact_classification": record.get("clinical_impact_classification", {}).get("description"),
                "clinical_impact_traits": self.extract_trait_names(record.get("clinical_impact_classification", {})),
                "oncogenicity_classification": record.get("oncogenicity_classification", {}).get("description"),
                "oncogenicity_traits": self.extract_trait_names(record.get("oncogenicity_classification", {})),
            })

        return {"found": True, "matches":matches}

if __name__ == "__main__": 
    client = VariantClient()
    vep_result = client.get_vep_consequence("chr7:g.140753336A>T")
    clinvar_result = client.get_clinvar_summary(vep_result["gene_symbol"], vep_result["protein_change_short"])
    print(clinvar_result)