import httpx
import time
from Bio import Entrez

from terminal_ui import print_retry

Entrez.email = "shivank.virdi@gmail.com"

def retry_on_failure(func, *args, max_retries=3, backoff_seconds=5, **kwargs):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if 400 <= e.response.status_code < 500:
                raise  # client error — don't retry, let it propagate immediately
            last_error = e
        except Exception as e:
            last_error = e

        if attempt < max_retries:
            print_retry(attempt, str(last_error), backoff_seconds, title="Upstream service retry")
            time.sleep(backoff_seconds)

    raise RuntimeError(f"Failed after {max_retries} attempts") from last_error

class VariantClient:
    AA_CODES = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
    "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
    "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
    "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
}
    
    def __init__(self, timeout=20.0):
        self.timeout = timeout

    def _to_short_form(self, protein_change: str) -> str:
        short = protein_change.replace("p.", "")
        three_to_one = {v: k for k, v in self.AA_CODES.items()}
        for three, one in three_to_one.items():
            short = short.replace(three, one)
        return short

    def _fetch_vep(self, url):
        response = httpx.get(
            url,
            params={"content-type": "application/json", "pick": 1, "hgvs": 1},
            headers={"Accept": "application/json"},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_vep_consequence(self, variant: str) -> dict:
        url = f"https://rest.ensembl.org/vep/human/hgvs/{variant}"

        try:
            data = retry_on_failure(self._fetch_vep, url)
        except httpx.HTTPStatusError as e:
            if 400 <= e.response.status_code < 500:
                return {
                    "error": "invalid_variant",
                    "message": f"Ensembl rejected this variant string as invalid or malformed: '{variant}'. "
                            f"Check that it follows correct HGVS genomic notation, e.g. 'chr7:g.140753336A>T'.",
                }
            raise  # server-side failure

        result = data[0]

        transcripts = result.get("transcript_consequences", [])
        t = transcripts[0] if transcripts else {}

        gene_symbol = t.get("gene_symbol")
        consequence = result.get("most_severe_consequence")

        protein_change = None
        protein_change_short = None

        hgvsp = t.get("hgvsp")
        if consequence != "synonymous_variant" and hgvsp and ":" in hgvsp:
            protein_change = hgvsp.split(":")[1]
            protein_change_short = self._to_short_form(protein_change)

        return {
            "gene_symbol": gene_symbol,
            "consequence": consequence,
            "protein_change": protein_change,
            "protein_change_short": protein_change_short,
            "genomic_start": result.get("start"),
            "genomic_end": result.get("end"),
        }
    
    def extract_trait_names(self, classification: dict) -> list:
            trait_set = classification.get("trait_set", [])
            names = []
            for trait in trait_set:
                names.append(trait.get("trait_name"))
            return names

    def _fetch_clinvar_search(self, term):
        search_handle = Entrez.esearch(db="clinvar", term=term)
        return Entrez.read(search_handle)

    def _fetch_clinvar_summary(self, id_list):
        summary_handle = Entrez.esummary(db="clinvar", id=",".join(id_list))
        return Entrez.read(summary_handle, validate=False)

    def get_clinvar_summary(self, gene_symbol: str, protein_change_short: str, expected_start: int = None, expected_end: int = None) -> dict:
        term = f"{gene_symbol}[gene] AND {protein_change_short}[Variant Name]"
        search_record = retry_on_failure(self._fetch_clinvar_search, term)

        id_list = search_record.get("IdList", [])
        if not id_list:
            return {"found": False, "matches": []}

        summary = retry_on_failure(self._fetch_clinvar_summary, id_list)
        records = summary["DocumentSummarySet"]["DocumentSummary"]

        matches = []
        for record in records:
            variation_set = record.get("variation_set", [{}])
            loc_list = variation_set[0].get("variation_loc", []) if variation_set else []
            current_loc = next((l for l in loc_list if l.get("status") == "current"), {})

            clinvar_start = int(current_loc["start"]) if current_loc.get("start") else None
            clinvar_end = int(current_loc["stop"]) if current_loc.get("stop") else None

            position_verified = None
            if expected_start is not None and clinvar_start is not None:
                position_verified = (expected_start == clinvar_start)

            matches.append({
                "variation_id": record.attributes.get("uid"),
                "title": record.get("title"),
                "germline_classification": record.get("germline_classification", {}).get("description"),
                "germline_traits": self.extract_trait_names(record.get("germline_classification", {})),
                "clinical_impact_classification": record.get("clinical_impact_classification", {}).get("description"),
                "clinical_impact_traits": self.extract_trait_names(record.get("clinical_impact_classification", {})),
                "oncogenicity_classification": record.get("oncogenicity_classification", {}).get("description"),
                "oncogenicity_traits": self.extract_trait_names(record.get("oncogenicity_classification", {})),
                "position_verified": position_verified,
                "clinvar_position": clinvar_start,
            })

        return {"found": True, "matches": matches}

if __name__ == "__main__":
    client = VariantClient()

    # Known-good case: BRAF V600E
    vep = client.get_vep_consequence("chr7:g.140753336A>T")
    clinvar = client.get_clinvar_summary(
        vep["gene_symbol"], vep["protein_change_short"],
        expected_start=vep["genomic_start"], expected_end=vep["genomic_end"]
    )
    print("BRAF position_verified:", clinvar["matches"][0]["position_verified"])

    # Known-bad case: your off-by-one duplication
    vep2 = client.get_vep_consequence("chr1:g.935845_935847dup")
    clinvar2 = client.get_clinvar_summary(
        vep2["gene_symbol"], vep2["protein_change_short"],
        expected_start=vep2["genomic_start"], expected_end=vep2["genomic_end"]
    )
    print("Duplication position_verified:", clinvar2["matches"][0]["position_verified"] if clinvar2["found"] else "not found")
