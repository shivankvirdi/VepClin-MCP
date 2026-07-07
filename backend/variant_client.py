import os
import re
from urllib.parse import quote
from pathlib import Path

import httpx
import time
from Bio import Entrez
from dotenv import load_dotenv

from terminal_ui import print_retry

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

Entrez.email = os.environ.get("NCBI_EMAIL") or "your-email@example.com"
Entrez.api_key = os.environ.get("NCBI_API_KEY") or None


def retry_on_failure(func, *args, max_retries=3, backoff_seconds=5, **kwargs):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if 400 <= e.response.status_code < 500:
                raise
            last_error = e
        except Exception as e:
            last_error = e

        if attempt < max_retries:
            print_retry(attempt, str(last_error), backoff_seconds, title="Upstream service retry")
            time.sleep(backoff_seconds)

    raise RuntimeError(f"Failed after {max_retries} attempts") from last_error


class VariantClient:
    GENOMIC_HGVS_RE = re.compile(r"^(?:chr)?[A-Za-z0-9_.]+:g\..+$", re.IGNORECASE)
    CODING_HGVS_RE = re.compile(
        r"^(?:(?:N[MR]|X[MR])_[0-9]+(?:\.[0-9]+)?|ENST[0-9]+(?:\.[0-9]+)?|LRG_[0-9]+t[0-9]+):c\..+$",
        re.IGNORECASE,
    )

    AA_CODES = {
        "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
        "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
        "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
        "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
    }

    def __init__(self, timeout=20.0):
        self.timeout = timeout
        # 10 req/sec with an API key, 3/sec without — leave headroom either way
        self._entrez_delay = 0.11 if Entrez.api_key else 0.35

    def _to_short_form(self, protein_change: str) -> str:
        short = protein_change.replace("p.", "")
        three_to_one = {v: k for k, v in self.AA_CODES.items()}
        for three, one in three_to_one.items():
            short = short.replace(three, one)
        return short

    # single-variant VEP

    def _classify_hgvs(self, variant: str) -> tuple[str | None, str | None]:
        variant = variant.strip()
        if self.GENOMIC_HGVS_RE.match(variant):
            return "genomic", None
        if self.CODING_HGVS_RE.match(variant):
            return "coding", None
        if variant.startswith("c.") or ":c." in variant:
            return None, (
                "Coding HGVS requires a transcript accession, e.g. "
                "'NM_004333.6:c.1799T>A' or 'ENST00000646891.2:c.1799T>A'."
            )
        if variant.startswith("p.") or ":p." in variant:
            return None, (
                "Protein HGVS is not supported as a direct VEP input. Use genomic HGVS "
                "or coding HGVS with a transcript accession."
            )
        return None, (
            "Supported HGVS formats are genomic, e.g. 'chr7:g.140753336A>T', "
            "or coding with a transcript accession, e.g. 'NM_004333.6:c.1799T>A'."
        )

    def _fetch_vep(self, url, params):
        response = httpx.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_vep_consequence(self, variant: str, build: str = "grch38", transcript_mode: str = "mane_select") -> dict:
        variant = variant.strip()
        hgvs_format, validation_error = self._classify_hgvs(variant)
        if validation_error:
            return {
                "error": "unsupported_hgvs",
                "message": validation_error,
                "input_hgvs": variant,
            }

        base_url = "https://grch37.rest.ensembl.org" if build == "grch37" else "https://rest.ensembl.org"
        url = f"{base_url}/vep/human/hgvs/{quote(variant, safe='')}"

        params = {"content-type": "application/json", "hgvs": 1}
        if transcript_mode == "mane_select":
            params["pick"] = 1

        try:
            data = retry_on_failure(self._fetch_vep, url, params)
        except httpx.HTTPStatusError as e:
            if 400 <= e.response.status_code < 500:
                return {
                    "error": "invalid_variant",
                    "message": f"Ensembl rejected this variant string as invalid or malformed: '{variant}'. "
                            f"Check that it follows supported HGVS notation, e.g. "
                            f"'chr7:g.140753336A>T' or 'NM_004333.6:c.1799T>A'.",
                    "input_hgvs": variant,
                    "hgvs_format": hgvs_format,
                }
            raise

        result = data[0]
        transcripts = result.get("transcript_consequences", [])
        primary = transcripts[0] if transcripts else {}

        gene_symbol = primary.get("gene_symbol")
        consequence = result.get("most_severe_consequence")

        protein_change = None
        protein_change_short = None
        hgvsp = primary.get("hgvsp")
        if consequence != "synonymous_variant" and hgvsp and ":" in hgvsp:
            protein_change = hgvsp.split(":")[1]
            protein_change_short = self._to_short_form(protein_change)

        response_data = {
            "gene_symbol": gene_symbol,
            "consequence": consequence,
            "protein_change": protein_change,
            "protein_change_short": protein_change_short,
            "genomic_start": result.get("start"),
            "genomic_end": result.get("end"),
            "impact": primary.get("impact"),
            "sift_prediction": primary.get("sift_prediction"),
            "sift_score": primary.get("sift_score"),
            "polyphen_prediction": primary.get("polyphen_prediction"),
            "polyphen_score": primary.get("polyphen_score"),
            "build": build,
            "input_hgvs": variant,
            "hgvs_format": hgvs_format,
        }

        if transcript_mode == "all" and len(transcripts) > 1:
            response_data["transcripts"] = [self._transcript_row(tr) for tr in transcripts]

        return response_data

    def _transcript_row(self, tr: dict) -> dict:
        hgvsp = tr.get("hgvsp")
        protein_change = hgvsp.split(":")[1] if hgvsp and ":" in hgvsp else None
        return {
            "transcript_id": tr.get("transcript_id"),
            "consequence": ", ".join(tr.get("consequence_terms", [])) or None,
            "protein_change": protein_change,
            "impact": tr.get("impact"),
            "sift_prediction": tr.get("sift_prediction"),
            "polyphen_prediction": tr.get("polyphen_prediction"),
        }

    # batch VCF parsing + VEP

    def parse_vcf(self, path: str) -> list[str]:
        """Parse a VCF file into VEP region-endpoint variant strings.

        Skips header lines and malformed rows. Multi-allelic ALT values
        (comma-separated) are split into separate variant strings.
        """
        variants = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                fields = line.split("\t")
                if len(fields) < 5:
                    continue

                chrom, pos, _variant_id, ref, alt = fields[0], fields[1], fields[2], fields[3], fields[4]
                chrom = chrom.removeprefix("chr")

                for single_alt in alt.split(","):
                    variants.append(f"{chrom} {pos} . {ref} {single_alt} . . .")

        return variants

    def _fetch_vep_batch(self, variants: list[str], build: str, transcript_mode: str):
        base_url = "https://grch37.rest.ensembl.org" if build == "grch37" else "https://rest.ensembl.org"
        url = f"{base_url}/vep/human/region"

        body = {"variants": variants, "hgvs": 1}
        if transcript_mode == "mane_select":
            body["pick"] = 1

        response = httpx.post(
            url,
            json=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_vep_consequences_batch(self, variants: list[str], build: str = "grch38", transcript_mode: str = "mane_select") -> list[dict]:
        if len(variants) > 200:
            raise ValueError(
                f"Batch of {len(variants)} exceeds Ensembl's 200-variant limit per request. "
                f"Split the file into smaller batches."
            )

        results = retry_on_failure(self._fetch_vep_batch, variants, build, transcript_mode)

        parsed = []
        for result in results:
            transcripts = result.get("transcript_consequences", [])
            primary = transcripts[0] if transcripts else {}

            hgvsp = primary.get("hgvsp")
            consequence = result.get("most_severe_consequence")
            protein_change = None
            protein_change_short = None
            if consequence != "synonymous_variant" and hgvsp and ":" in hgvsp:
                protein_change = hgvsp.split(":")[1]
                protein_change_short = self._to_short_form(protein_change)

            parsed.append({
                "input": result.get("input"),
                "gene_symbol": primary.get("gene_symbol"),
                "consequence": consequence,
                "protein_change": protein_change,
                "protein_change_short": protein_change_short,
                "impact": primary.get("impact"),
                "sift_prediction": primary.get("sift_prediction"),
                "polyphen_prediction": primary.get("polyphen_prediction"),
                "genomic_start": result.get("start"),
                "genomic_end": result.get("end"),
            })

        return parsed

    # ClinVar: single lookup

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
        if not gene_symbol or not protein_change_short:
            return {"found": False, "matches": []}

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
                "germline_review_status": record.get("germline_classification", {}).get("review_status"),
                "germline_last_evaluated": record.get("germline_classification", {}).get("last_evaluated"),
                "germline_traits": self.extract_trait_names(record.get("germline_classification", {})),
                "clinical_impact_classification": record.get("clinical_impact_classification", {}).get("description"),
                "clinical_impact_review_status": record.get("clinical_impact_classification", {}).get("review_status"),
                "clinical_impact_last_evaluated": record.get("clinical_impact_classification", {}).get("last_evaluated"),
                "clinical_impact_traits": self.extract_trait_names(record.get("clinical_impact_classification", {})),
                "oncogenicity_classification": record.get("oncogenicity_classification", {}).get("description"),
                "oncogenicity_review_status": record.get("oncogenicity_classification", {}).get("review_status"),
                "oncogenicity_last_evaluated": record.get("oncogenicity_classification", {}).get("last_evaluated"),
                "oncogenicity_traits": self.extract_trait_names(record.get("oncogenicity_classification", {})),
                "position_verified": position_verified,
                "clinvar_position": clinvar_start,
            })

        return {"found": True, "matches": matches}

    # ClinVar: batch 

    def get_clinvar_summaries_batch(self, vep_results: list[dict]) -> list[dict]:
        """Run ClinVar lookups for a batch of parsed VEP results.

        NCBI has no multi-variant ClinVar endpoint, so this loops one
        esearch+esummary pair per variant, throttled to stay under the
        Entrez rate limit (10/sec with an API key, 3/sec without).
        """
        results = []
        for vep in vep_results:
            gene = vep.get("gene_symbol")
            change = vep.get("protein_change_short")

            clinvar = self.get_clinvar_summary(
                gene, change,
                expected_start=vep.get("genomic_start"),
                expected_end=vep.get("genomic_end"),
            )
            results.append({**vep, "clinvar": clinvar})
            time.sleep(self._entrez_delay)

        return results
    
if __name__ == "__main__":
    print(f"DEBUG: NCBI API key present: {bool(Entrez.api_key)}")
